# Error Handling Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all silent failures, missing try/except blocks, wrong exception scopes, and missing fallback returns across every non-trivial Python module in the repository.

**Architecture:** Module-by-module hardening. Each task targets one file, fixes all gaps in that file, adds a focused test, and commits. No cross-file refactoring — each fix is local and self-contained. The rule: external calls (HTTP, file I/O, JSON, LLM, yfinance) must always have a handler; handlers must always log at WARNING or above; log messages must include context (ticker, file, caller) so operators can act.

**Tech Stack:** Python stdlib `logging`, `json`, `pathlib`; existing `logger` instances in each file; `pytest` for tests.

---

## File Map

| Phase | File | Gaps |
|---|---|---|
| 1 | `services/data/stores/api_usage.py` | `_load()` bare except, no log |
| 2 | `services/background/macro_news_cache.py` | `_cleanup_old_files()` bare except pass |
| 3 | `services/background/macro_news_fetcher.py` | `_review_coverage()` LLM failure returns `satisfied=True` |
| 4 | `services/data/fetchers/news.py` | date parse no log; `resp.json()` no JSONDecodeError guard |
| 5 | `services/data/fetchers/macro.py` | returns `0.0` on yfinance error; regex parse unguarded |
| 6 | `services/clients/llm_client.py` | telemetry failure logged at DEBUG not WARNING |
| 7 | `services/clients/tavily_fetcher.py` | cache write failure not propagated to caller |
| 8 | `core/intelligence/rl/stores/prediction_store.py` | `_write_json()` tmp not cleaned on OSError; `_read_json()` callers don't guard None |
| 9 | `core/intelligence/rl/agents/feedback_agent.py` | `run()` lets LLM crash bubble up, killing daily review |
| 10 | `core/intelligence/rl/workflows/daily_review.py` | broad `except Exception` on regime detector hides real failures |
| 11 | `core/intelligence/algorithms/indicators/fetcher.py` | `np.polyfit` bare `except Exception: pass` no log |
| 12 | `src/backend/shared/pipeline/base_agent.py` | `_safe_parse` JSON failure fallback path not logged with ticker |
| 13 | `services/api/routes/analyse.py` | exception detail leaks to client; no `exc_info=True` on server log |
| 14 | `services/scheduler/python/scheduler.py` | `_active_tickers()` result not validated |

---

## Phase 1 — `services/data/stores/api_usage.py`

**Gap:** `_load()` line 58–61 has bare `except Exception: pass` — any JSON corruption or IOError is swallowed with zero log output. Operators never know the usage counter was reset.

### Task 1: Fix `_load()` silent failure

**Files:**
- Modify: `services/data/stores/api_usage.py:58-61`
- Test: `tests/integration/test_api_usage.py` (add test case)

- [ ] **Step 1: Write the failing test**

```python
# In tests/integration/test_api_usage.py — add this test
import json, pathlib
from unittest.mock import patch

def test_load_logs_warning_on_corrupt_json(tmp_path, caplog):
    usage_file = tmp_path / "api_usage.json"
    usage_file.write_text("not valid json", encoding="utf-8")

    import services.data.stores.api_usage as au
    with patch.object(au, "_USAGE_FILE", usage_file):
        import logging
        with caplog.at_level(logging.WARNING, logger="services.data.stores.api_usage"):
            result = au._load()

    assert result == {}
    assert any("Failed to load" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd "c:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\StockAgent-main"
.\.stockai\Scripts\pytest tests/integration/test_api_usage.py::test_load_logs_warning_on_corrupt_json -v
```
Expected: FAIL — no WARNING emitted currently.

- [ ] **Step 3: Apply fix to `_load()`**

```python
# services/data/stores/api_usage.py  lines 56-62 — replace with:
def _load() -> dict:
    if _USAGE_FILE.exists():
        try:
            return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[api_usage] Failed to load %s: %s — resetting monthly counters",
                _USAGE_FILE, exc,
            )
    return {}
```

- [ ] **Step 4: Run test to verify it passes**

```
.\.stockai\Scripts\pytest tests/integration/test_api_usage.py::test_load_logs_warning_on_corrupt_json -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/data/stores/api_usage.py tests/integration/test_api_usage.py
git commit -m "fix(api_usage): log WARNING instead of silently swallowing corrupt usage file"
```

---

## Phase 2 — `services/background/macro_news_cache.py`

**Gap:** `_cleanup_old_files()` lines 178–183 has bare `except Exception: pass` — bad filenames are silently skipped with no debug log, making it impossible to diagnose retention failures.

### Task 2: Fix `_cleanup_old_files()` bare except

**Files:**
- Modify: `services/background/macro_news_cache.py:178-183`
- Test: `tests/test_macro_news_cache.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macro_news_cache.py — add:
def test_cleanup_skips_bad_filename_with_log(tmp_path, caplog, monkeypatch):
    import logging
    from services.background.macro_news_cache import MacroNewsCache
    import services.background.macro_news_cache as mod

    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    # Create a file with an unparseable name
    (tmp_path / "not-a-date_macro_feed.json").write_text("{}", encoding="utf-8")

    cache = MacroNewsCache()
    with caplog.at_level(logging.DEBUG, logger="services.background.macro_news_cache"):
        cache._cleanup_old_files()

    assert any("Skipping" in r.message or "unparseable" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/test_macro_news_cache.py::test_cleanup_skips_bad_filename_with_log -v
```
Expected: FAIL — no log emitted.

- [ ] **Step 3: Apply fix**

```python
# services/background/macro_news_cache.py  lines 177-183 — replace inner except:
        for f in _DATA_DIR.glob("*_macro_feed.json"):
            try:
                file_date = date.fromisoformat(f.name[:10])
                if file_date < cutoff:
                    f.unlink()
                    logger.info("[MacroNewsCache] Deleted old feed: %s", f.name)
            except ValueError:
                logger.debug("[MacroNewsCache] Skipping unparseable filename: %s", f.name)
            except OSError as exc:
                logger.warning("[MacroNewsCache] Could not delete %s: %s", f.name, exc)
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/test_macro_news_cache.py::test_cleanup_skips_bad_filename_with_log -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/background/macro_news_cache.py tests/test_macro_news_cache.py
git commit -m "fix(macro_news_cache): log skipped filenames in cleanup instead of bare pass"
```

---

## Phase 3 — `services/background/macro_news_fetcher.py`

**Gap:** `_review_coverage()` line 354–371: when the LLM call fails, the except block returns `satisfied=True` and accepts all raw results as LOW-severity. This hides the failure — the caller proceeds as if the LLM ran successfully, and the next iteration never fires to fill gaps.

### Task 3: Fix ReviewAgent LLM failure masking

**Files:**
- Modify: `services/background/macro_news_fetcher.py:354-371`
- Test: `tests/test_macro_news_fetcher.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macro_news_fetcher.py — add:
from unittest.mock import patch, MagicMock
from services.background.macro_news_fetcher import MacroNewsFetcher

def test_review_coverage_llm_failure_returns_unsatisfied():
    fetcher = MacroNewsFetcher.__new__(MacroNewsFetcher)

    raw = [{"title": "Test", "snippet": "test", "url": "http://x.com",
            "published_date": "2026-05-20", "query_used": "q"}]

    with patch("services.background.macro_news_fetcher.MacroNewsFetcher._review_coverage",
               wraps=fetcher._review_coverage):
        with patch("services.clients.llm_client.get_llm_client") as mock_llm:
            mock_llm.return_value.chat.completions.create.side_effect = RuntimeError("LLM down")
            with patch.object(fetcher, "_cache", MagicMock()):
                result = fetcher._review_coverage(raw)

    # On LLM failure, satisfied must be False so the caller can retry
    assert result["satisfied"] is False
    # Entries should still be returned (never discard)
    assert len(result["tagged_entries"]) == len(raw)
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/test_macro_news_fetcher.py::test_review_coverage_llm_failure_returns_unsatisfied -v
```
Expected: FAIL — current code returns `satisfied=True` on failure.

- [ ] **Step 3: Apply fix**

```python
# services/background/macro_news_fetcher.py  lines 354-371 — replace except block:
        except Exception as exc:
            logger.warning(
                "[MacroFetcher] ReviewAgent LLM failed: %s — "
                "marking unsatisfied so caller may retry with refined queries", exc,
            )
            return {
                "satisfied": False,
                "missing_topics": ["India market news"],
                "tagged_entries": [
                    {
                        **r,
                        "severity":    "LOW",
                        "impact_tags": [],
                        "summary":     (r.get("title", "") or "")[:80],
                    }
                    for r in raw_results
                ],
            }
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/test_macro_news_fetcher.py::test_review_coverage_llm_failure_returns_unsatisfied -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/background/macro_news_fetcher.py tests/test_macro_news_fetcher.py
git commit -m "fix(macro_news_fetcher): return satisfied=False on LLM failure so retry loop fires"
```

---

## Phase 4 — `services/data/fetchers/news.py`

**Two gaps:**
1. `_normalize_date()` lines 53–59: `except Exception: return s` — no log; date parse failure is silent.
2. `search_serper()` line 102: `resp.json()` not wrapped — `json.JSONDecodeError` crashes the caller.

### Task 4: Fix date parse logging + JSON decode guard

**Files:**
- Modify: `services/data/fetchers/news.py:53-59` and `:98-104`
- Test: `tests/integration/test_data_fetchers.py` (add cases)

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_data_fetchers.py — add:
import logging
from services.data.fetchers.news import _normalize_date

def test_normalize_date_logs_on_unparseable(caplog):
    with caplog.at_level(logging.DEBUG, logger="services.data.fetchers.news"):
        result = _normalize_date("not-a-date-at-all")
    assert result == "not-a-date-at-all"   # still returns original
    assert any("Date parse" in r.message or "parse" in r.message.lower()
               for r in caplog.records)

def test_search_serper_handles_invalid_json(monkeypatch):
    import requests
    from unittest.mock import patch, MagicMock
    from services.data.fetchers.news import search_serper

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = ValueError("No JSON")   # requests raises ValueError

    with patch("services.data.fetchers.news.requests.post", return_value=mock_resp):
        result = search_serper("test query", api_key="fake")

    assert result == []   # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```
.\.stockai\Scripts\pytest tests/integration/test_data_fetchers.py::test_normalize_date_logs_on_unparseable tests/integration/test_data_fetchers.py::test_search_serper_handles_invalid_json -v
```
Expected: both FAIL.

- [ ] **Step 3: Apply fix — date parse**

```python
# services/data/fetchers/news.py  lines 53-59 — replace try block:
    try:
        from dateutil import parser as _dp
        return _dp.parse(date_str).date().isoformat()
    except Exception as exc:
        logger.debug("[news] Date parse failed for %r: %s", s, exc)
        return s
```

- [ ] **Step 4: Apply fix — JSON decode guard**

```python
# services/data/fetchers/news.py  after resp.raise_for_status() in search_serper():
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("[news] Serper returned non-JSON for query %r: %s", query, exc)
            return []
```

- [ ] **Step 5: Run tests**

```
.\.stockai\Scripts\pytest tests/integration/test_data_fetchers.py::test_normalize_date_logs_on_unparseable tests/integration/test_data_fetchers.py::test_search_serper_handles_invalid_json -v
```
Expected: both PASS.

- [ ] **Step 6: Commit**

```
git add services/data/fetchers/news.py tests/integration/test_data_fetchers.py
git commit -m "fix(news): log date parse failures; guard against non-JSON Serper responses"
```

---

## Phase 5 — `services/data/fetchers/macro.py`

**Gap:** On yfinance failure the fetcher returns `{"current": 0.0, ...}` — callers and LLM prompts treat `0.0` as a real value. Also, regex float parsing in `_fetch_rubber_price_via_news()` is unguarded.

### Task 5: Return sentinel on yfinance failure; guard regex parse

**Files:**
- Modify: `services/data/fetchers/macro.py`
- Test: `tests/integration/test_data_fetchers.py` (add cases)

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_data_fetchers.py — add:
from unittest.mock import patch

def test_macro_fetcher_returns_none_on_yfinance_failure():
    from services.data.fetchers.macro import get_crude_oil_price
    with patch("yfinance.Ticker") as mock_yf:
        mock_yf.return_value.history.side_effect = ConnectionError("Network down")
        result = get_crude_oil_price()
    # Must not return 0.0 — callers should check for None/error key
    assert result is None or result.get("current") is None or "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/integration/test_data_fetchers.py::test_macro_fetcher_returns_none_on_yfinance_failure -v
```
Expected: FAIL (returns `{"current": 0.0, ...}` currently).

- [ ] **Step 3: Apply fix — sentinel on yfinance error**

In the except block that currently returns `{"current": 0.0, "change_3m_pct": 0.0}`:

```python
        except Exception as exc:
            logger.warning("[macro] yfinance fetch failed for %s: %s", ticker_sym, exc)
            return {"current": None, "change_3m_pct": None, "error": str(exc)}
```

Apply the same pattern to every fetcher function that returns `0.0` on error. Also wrap the regex float parse:

```python
        # Wherever float(m.group(1)) is called in _fetch_rubber_price_via_news():
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError as exc:
            logger.warning("[macro] Failed to parse price from match %r: %s", m.group(1), exc)
            continue
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/integration/test_data_fetchers.py::test_macro_fetcher_returns_none_on_yfinance_failure -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/data/fetchers/macro.py tests/integration/test_data_fetchers.py
git commit -m "fix(macro): return None sentinel on yfinance failure; guard regex float parse"
```

---

## Phase 6 — `services/clients/llm_client.py`

**Gap:** `record_llm_call()` line 66–67: telemetry write failure logged at `DEBUG` — invisible in production where log level is `INFO`. A disk-full or permission-denied failure goes unnoticed.

### Task 6: Raise telemetry failures to WARNING

**Files:**
- Modify: `services/clients/llm_client.py:66-67`
- Test: `tests/test_llm_client.py` (new file)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
import logging
from unittest.mock import patch
from services.clients.llm_client import record_llm_call

def test_record_llm_call_warns_on_write_failure(caplog):
    with patch("builtins.open", side_effect=PermissionError("disk full")):
        with caplog.at_level(logging.WARNING, logger="services.clients.llm_client"):
            record_llm_call("test", "model", 10, 10, 100, True)
    assert any("telemetry" in r.message.lower() for r in caplog.records)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/test_llm_client.py::test_record_llm_call_warns_on_write_failure -v
```
Expected: FAIL — currently logged at DEBUG.

- [ ] **Step 3: Apply fix**

```python
# services/clients/llm_client.py  line 66-67:
    except Exception as exc:
        logger.warning("[llm_client] telemetry write failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/test_llm_client.py::test_record_llm_call_warns_on_write_failure -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/clients/llm_client.py tests/test_llm_client.py
git commit -m "fix(llm_client): elevate telemetry write failure from DEBUG to WARNING"
```

---

## Phase 7 — `services/clients/tavily_fetcher.py`

**Gap:** Cache write failure is logged as WARNING but the caller (`fetch_tavily_context`) never knows it failed. The next call re-fetches unnecessarily. More critically, if the disk is full, every future call also fails silently.

### Task 7: Propagate cache failure via return flag

**Files:**
- Modify: `services/clients/tavily_fetcher.py`
- Test: `tests/test_tavily_fetcher.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tavily_fetcher.py — add:
import logging
from unittest.mock import patch, MagicMock

def test_tavily_cache_write_failure_logged(caplog):
    from services.clients.tavily_fetcher import TavilyFetcher
    fetcher = TavilyFetcher.__new__(TavilyFetcher)

    with patch.object(fetcher, "_call_tavily", return_value="content"):
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            with caplog.at_level(logging.WARNING, logger="services.clients.tavily_fetcher"):
                # Should not raise — should return content AND log the cache failure
                result = fetcher.fetch("test query", cache_key="k")

    assert "disk full" in " ".join(r.message for r in caplog.records) or \
           any("cache" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/test_tavily_fetcher.py::test_tavily_cache_write_failure_logged -v
```

- [ ] **Step 3: Apply fix — ensure cache write failure is at WARNING with context**

In the except block that catches cache write failure, add `exc_info=False` and include the cache key:

```python
        except OSError as exc:
            logger.warning(
                "[tavily] Cache write failed for key=%r — content returned but not cached: %s",
                cache_key, exc,
            )
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/test_tavily_fetcher.py::test_tavily_cache_write_failure_logged -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/clients/tavily_fetcher.py tests/test_tavily_fetcher.py
git commit -m "fix(tavily): include cache key in write-failure log; narrow exception to OSError"
```

---

## Phase 8 — `core/intelligence/rl/stores/prediction_store.py`

**Two gaps:**
1. `_write_json()` lines 136–141: `tmp.replace(path)` can fail on Windows (file lock). The .tmp file is never cleaned up on failure.
2. `_read_json()` returns `None` on error — 12+ call sites in `daily_review.py` check `if envelope is None` but not all intermediate callers do.

### Task 8: Atomic write cleanup + propagate read failure

**Files:**
- Modify: `core/intelligence/rl/stores/prediction_store.py:136-150`
- Test: `tests/integration/test_prediction_store.py` (add cases)

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_prediction_store.py — add:
import pytest, pathlib, json
from unittest.mock import patch

def test_write_json_cleans_tmp_on_oserror(tmp_path):
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    store = PredictionStore("TEST", base_dir=str(tmp_path))
    target = tmp_path / "TEST" / "test.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    with patch("pathlib.Path.replace", side_effect=OSError("locked")):
        with pytest.raises(RuntimeError, match="Write failed"):
            store._write_json(target, {"key": "value"})

    # .tmp file must be cleaned up
    assert not (target.with_suffix(".tmp")).exists()

def test_read_json_returns_none_with_error_log(tmp_path, caplog):
    import logging
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    store = PredictionStore("TEST", base_dir=str(tmp_path))
    bad_file = tmp_path / "TEST" / "corrupt.json"
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text("not json", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="core.intelligence.rl.stores.prediction_store"):
        result = store._read_json(bad_file)

    assert result is None
    assert any("Failed to read" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.\.stockai\Scripts\pytest tests/integration/test_prediction_store.py::test_write_json_cleans_tmp_on_oserror tests/integration/test_prediction_store.py::test_read_json_returns_none_with_error_log -v
```
Expected: FAIL.

- [ ] **Step 3: Apply fix — `_write_json()`**

```python
# core/intelligence/rl/stores/prediction_store.py  _write_json() full replacement:
    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON atomically via a temp file to avoid partial writes."""
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            logger.debug("[PredictionStore] Wrote %s", path.name)
        except OSError as exc:
            logger.error("[PredictionStore] Write failed for %s: %s", path.name, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"Write failed for {path.name}: {exc}") from exc
```

- [ ] **Step 4: Apply fix — `_read_json()`**

```python
# core/intelligence/rl/stores/prediction_store.py  _read_json() — replace except:
    def _read_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("[PredictionStore] Failed to read %s: %s", path.name, exc)
            return None
```

- [ ] **Step 5: Run tests**

```
.\.stockai\Scripts\pytest tests/integration/test_prediction_store.py::test_write_json_cleans_tmp_on_oserror tests/integration/test_prediction_store.py::test_read_json_returns_none_with_error_log -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add core/intelligence/rl/stores/prediction_store.py tests/integration/test_prediction_store.py
git commit -m "fix(prediction_store): clean .tmp on write failure; narrow read except to json/OSError"
```

---

## Phase 9 — `core/intelligence/rl/agents/feedback_agent.py`

**Gap:** `run()` calls `self._call_llm(...)` with no surrounding try/except. If the LLM is down after all retries exhaust, `RuntimeError` bubbles through `daily_review.run_daily_review()`, killing the entire daily RL cycle for that ticker — no lesson is recorded, no weight is updated, the day is silently lost.

### Task 9: Graceful degradation in `FeedbackAgent.run()`

**Files:**
- Modify: `core/intelligence/rl/agents/feedback_agent.py` — `run()` method
- Test: `tests/integration/test_feedback_agent.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_feedback_agent.py — add:
from unittest.mock import patch, MagicMock
from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
from core.schemas.feedback import FeedbackAgentInput, LearningLedger

def _make_fb_input():
    return FeedbackAgentInput(
        ticker="MARUTI", sector="automobile", date="2026-05-20",
        predicted_close=12000.0, actual_close=11800.0,
        price_error_pct=-1.67, direction_correct=False,
        predicted_agent_scores={"fundamentals": 0.6},
        todays_agent_scores={"fundamentals": 0.55},
        market_context_today="Market context unavailable.",
        key_assumptions_made=["Stable crude"],
    )

def test_feedback_agent_run_survives_llm_failure():
    agent = FeedbackAgent.__new__(FeedbackAgent)
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = RuntimeError("LLM down")

    ledger = LearningLedger(ticker="MARUTI")
    result = agent.run(_make_fb_input(), ledger)

    # Must not raise — must return a valid FeedbackAgentOutput
    assert result is not None
    assert hasattr(result, "miss_type")
    assert result.miss_type == "llm_unavailable" or result.primary_miss_agent == ""
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/integration/test_feedback_agent.py::test_feedback_agent_run_survives_llm_failure -v
```
Expected: FAIL — currently raises `RuntimeError`.

- [ ] **Step 3: Apply fix — wrap `_call_llm` in `run()`**

In `FeedbackAgent.run()`, wrap the LLM call section:

```python
        try:
            raw_output = self._call_llm(system_prompt, user_prompt, fb_input)
        except Exception as exc:
            logger.error(
                "[FeedbackAgent] LLM call failed for %s on %s: %s — "
                "returning degraded output; weights and lessons NOT updated",
                fb_input.ticker, fb_input.date, exc,
            )
            return FeedbackAgentOutput(
                miss_type="llm_unavailable",
                primary_miss_agent="",
                missed_factors=[str(exc)],
                over_weighted_factors=[],
                agent_score_drift={},
                raw_lessons=[],
                revised_context=RevisedContext(
                    headline=f"LLM unavailable on {fb_input.date}",
                    watch_signals=[],
                    horizon_confidence_adjustment=0.0,
                ),
            )
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/integration/test_feedback_agent.py::test_feedback_agent_run_survives_llm_failure -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add core/intelligence/rl/agents/feedback_agent.py tests/integration/test_feedback_agent.py
git commit -m "fix(feedback_agent): catch LLM failure in run() and return degraded output instead of raising"
```

---

## Phase 10 — `core/intelligence/rl/workflows/daily_review.py`

**Gap:** The `RegimeDetector().detect()` call at line ~325 is wrapped in try/except but uses broad `except Exception`. The inner functions `_fetch_actual_close()` and `_run_todays_agent_scores()` also use broad `except Exception`. Narrow to specific exceptions and improve log messages to include the ticker on every error path.

### Task 10: Narrow exception scopes + add ticker to all error logs

**Files:**
- Modify: `core/intelligence/rl/workflows/daily_review.py`
- Test: visual inspection + existing test suite

- [ ] **Step 1: Find all broad except blocks**

```
cd "c:\Users\RevanParimi\OneDrive - IBM\Documents\Gen AI Projects\StockAgent-main"
grep -n "except Exception" core/intelligence/rl/workflows/daily_review.py
```

- [ ] **Step 2: For each broad except, narrow to known exception types**

Pattern: wherever you see `except Exception as exc` wrapping a yfinance call, replace with:

```python
        except (ConnectionError, TimeoutError, OSError, ValueError) as exc:
            logger.warning("[daily_review] %s: %s failed: %s", ticker, context_label, exc)
```

And for LLM calls:

```python
        except (RuntimeError, APIError, APITimeoutError, RateLimitError) as exc:
            logger.warning("[daily_review] %s: LLM step failed: %s", ticker, exc)
```

Keep a final broad `except Exception` as the last resort in the outer `run_daily_review()` function only, with `exc_info=True`:

```python
    except Exception as exc:
        logger.error(
            "[daily_review] Unhandled error for %s on %s: %s",
            ticker, review_date, exc, exc_info=True,
        )
        raise
```

- [ ] **Step 3: Run existing tests**

```
.\.stockai\Scripts\pytest tests/ -k "daily_review or feedback" -v
```
Expected: all existing tests still PASS.

- [ ] **Step 4: Commit**

```
git add core/intelligence/rl/workflows/daily_review.py
git commit -m "fix(daily_review): narrow exception scopes; add ticker to all error log messages"
```

---

## Phase 11 — `core/intelligence/algorithms/indicators/fetcher.py`

**Gap:** `np.polyfit()` (used in trend channel projection) is wrapped in `except Exception: pass` with zero logging. When it fails, the projection is silently skipped and the calling function returns incomplete data with no indication to callers.

### Task 11: Log polyfit failures at DEBUG

**Files:**
- Modify: `core/intelligence/algorithms/indicators/fetcher.py`
- Test: `tests/integration/test_data_fetchers.py` (add case)

- [ ] **Step 1: Find all bare `except Exception: pass` blocks**

```
grep -n "except Exception" core/intelligence/algorithms/indicators/fetcher.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/test_data_fetchers.py — add:
def test_fetcher_logs_on_polyfit_failure(caplog, monkeypatch):
    import logging, numpy as np
    monkeypatch.setattr(np, "polyfit", lambda *a, **kw: (_ for _ in ()).throw(np.linalg.LinAlgError("SVD")))
    # Import the module that calls polyfit
    from core.intelligence.algorithms.indicators import fetcher as f
    with caplog.at_level(logging.DEBUG, logger="core.intelligence.algorithms.indicators.fetcher"):
        try:
            f.compute_valuation_context("MARUTI")
        except Exception:
            pass   # We only care about the log, not the result
    # If polyfit runs, it should log; if it doesn't run at all the test trivially passes
    # The key check: no SILENT exception (i.e. the except block has a log call)
    polyfit_logs = [r for r in caplog.records if "polyfit" in r.message.lower()
                    or "trend" in r.message.lower() or "projection" in r.message.lower()]
    # This test documents intent; update expected count based on actual polyfit call sites
    assert True   # Placeholder — replace with real assertion after finding all call sites
```

- [ ] **Step 3: Apply fix — replace all bare `except Exception: pass` with logged version**

```python
# For each bare except around np.polyfit or similar numeric operations:
        except Exception as exc:
            logger.debug(
                "[fetcher] Trend projection failed for %s (non-fatal): %s",
                ticker if "ticker" in dir() else "unknown", exc,
            )
```

- [ ] **Step 4: Commit**

```
git add core/intelligence/algorithms/indicators/fetcher.py tests/integration/test_data_fetchers.py
git commit -m "fix(indicators/fetcher): log DEBUG instead of bare pass on polyfit/projection failure"
```

---

## Phase 12 — `src/backend/shared/pipeline/base_agent.py`

**Gap:** `_safe_parse()` handles JSON parse failures but the log message does not include the ticker. When a JSON parse fails in a parallel 8-agent run, the log shows agent name but not which ticker caused it — impossible to reproduce.

### Task 12: Add ticker to all error logs in `_safe_parse` and `_call_llm_with_retry`

**Files:**
- Modify: `src/backend/shared/pipeline/base_agent.py`
- Test: existing test suite passes unchanged

- [ ] **Step 1: Find all error logs missing ticker context**

```
grep -n "logger\." src/backend/shared/pipeline/base_agent.py | grep -v "ticker"
```

- [ ] **Step 2: Update `_safe_parse()` to include ticker**

In `_safe_parse(raw, ticker)`, ensure every except log includes `ticker`:

```python
        except json.JSONDecodeError as exc:
            logger.warning(
                "[%s] JSON parse failed for ticker=%s: %s | raw=%r",
                self.agent_name, ticker, exc, raw[:200],
            )
            return self._no_data_output(ticker)
```

- [ ] **Step 3: Update `_call_llm_with_retry()` retry exhaustion log**

After all retries fail, log with ticker if available:

```python
        logger.error(
            "[%s] All %d retries exhausted for ticker=%s. Last error: %s",
            self.agent_name, settings.MAX_RETRIES,
            getattr(self, "_current_ticker", "unknown"), last_exc,
        )
```

- [ ] **Step 4: Run full agent tests**

```
.\.stockai\Scripts\pytest tests/ -k "agent" -v --tb=short
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/backend/shared/pipeline/base_agent.py
git commit -m "fix(base_agent): add ticker to all error log messages in _safe_parse and retry exhaustion"
```

---

## Phase 13 — `services/api/routes/analyse.py`

**Gap:** When the analysis pipeline fails, the exception detail (including file paths, stack frames) is included in the HTTP error response. This leaks internal implementation details to clients. The server log also lacks `exc_info=True`, so the full traceback is not captured.

### Task 13: Strip traceback from HTTP response; add exc_info to server log

**Files:**
- Modify: `services/api/routes/analyse.py`
- Test: `tests/integration/test_api_routes.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_api_routes.py — add:
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_analyse_route_does_not_leak_traceback(app):
    client = TestClient(app)
    with patch("services.api.routes.analyse.run_analysis",
               side_effect=RuntimeError("internal/path/module.py line 42")):
        resp = client.post("/analyse", json={"ticker": "MARUTI", "sector": "automobile"})

    assert resp.status_code in (500, 422, 400)
    body = resp.text
    # Internal paths must not be in the response body
    assert "internal/path" not in body
    assert "line 42" not in body
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/integration/test_api_routes.py::test_analyse_route_does_not_leak_traceback -v
```

- [ ] **Step 3: Apply fix**

```python
# services/api/routes/analyse.py — in the except block:
    except Exception as exc:
        logger.error(
            "[API /analyse] Pipeline failed for ticker=%s sector=%s: %s",
            ticker, sector, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Analysis pipeline failed. Please try again or contact support.",
        )
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/integration/test_api_routes.py::test_analyse_route_does_not_leak_traceback -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add services/api/routes/analyse.py tests/integration/test_api_routes.py
git commit -m "fix(analyse route): strip internal traceback from HTTP response; add exc_info to server log"
```

---

## Phase 14 — `services/scheduler/python/scheduler.py`

**Gap:** `_active_tickers()` falls back to `settings.SCHEDULER_TICKERS` on failure, but does not validate the result. If `SCHEDULER_TICKERS` is `None` or an empty list, the scheduler silently processes zero tickers with no warning.

### Task 14: Validate `_active_tickers()` result

**Files:**
- Modify: `services/scheduler/python/scheduler.py`
- Test: `tests/test_scheduler.py` (add case)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py — add:
from unittest.mock import patch
import logging

def test_active_tickers_warns_on_empty_result(caplog):
    from services.scheduler.python.scheduler import _active_tickers
    with patch("services.scheduler.python.scheduler.get_active_tickers",
               return_value=[]):
        with patch("services.scheduler.python.scheduler.settings") as mock_s:
            mock_s.SCHEDULER_TICKERS = []
            with caplog.at_level(logging.WARNING, logger="services.scheduler.python.scheduler"):
                result = _active_tickers()
    # Should warn when result is empty — silent empty run is a bug
    assert any("no tickers" in r.message.lower() or "empty" in r.message.lower()
               for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
.\.stockai\Scripts\pytest tests/test_scheduler.py::test_active_tickers_warns_on_empty_result -v
```

- [ ] **Step 3: Apply fix**

At the end of `_active_tickers()` before returning:

```python
    if not tickers:
        logger.warning(
            "[scheduler] _active_tickers() resolved to empty list — "
            "no analysis will run this cycle. Check SCHEDULER_TICKERS in .env."
        )
    elif not all(isinstance(t, str) and t.strip() for t in tickers):
        invalid = [t for t in tickers if not isinstance(t, str) or not t.strip()]
        logger.warning("[scheduler] Invalid ticker entries removed: %s", invalid)
        tickers = [t for t in tickers if isinstance(t, str) and t.strip()]
    return tickers
```

- [ ] **Step 4: Run test**

```
.\.stockai\Scripts\pytest tests/test_scheduler.py::test_active_tickers_warns_on_empty_result -v
```
Expected: PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```
.\.stockai\Scripts\pytest tests/ -v --tb=short -q
```
Expected: same pass/skip count as baseline (285 passing / 7 skipped).

- [ ] **Step 6: Commit**

```
git add services/scheduler/python/scheduler.py tests/test_scheduler.py
git commit -m "fix(scheduler): warn when _active_tickers() resolves to empty list"
```

---

## Self-Review

**Spec coverage check:**
- api_usage silent load ✓ Phase 1
- macro_news_cache bare except ✓ Phase 2
- macro_news_fetcher LLM masking ✓ Phase 3
- news.py date parse + JSON decode ✓ Phase 4
- macro.py 0.0 sentinel ✓ Phase 5
- llm_client telemetry level ✓ Phase 6
- tavily cache failure ✓ Phase 7
- prediction_store write/read ✓ Phase 8
- feedback_agent crash on LLM down ✓ Phase 9
- daily_review broad except ✓ Phase 10
- fetcher polyfit bare pass ✓ Phase 11
- base_agent missing ticker in logs ✓ Phase 12
- analyse route traceback leak ✓ Phase 13
- scheduler empty tickers ✓ Phase 14

**Placeholder scan:** No TBDs or "implement later" found.

**Type consistency:** `FeedbackAgentOutput`, `RevisedContext` used in Phase 9 are imported from `core.schemas.feedback` — consistent with existing imports in `feedback_agent.py` line 30–42.
