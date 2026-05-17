# RL Pipeline Optimisations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 8 approved optimisations to the RL pipeline — fixing 2 silent bugs, cutting Tavily calls by ~96%, eliminating ~70% of daily LLM calls, and adding cost telemetry.

**Architecture:** All changes are surgical — no new subsystems, no schema changes except where noted. Tasks 1-2 are bug fixes. Tasks 3-4 are cost/latency wins. Tasks 5-8 are telemetry, correctness, and hygiene. Each task is independently deployable.

**Tech Stack:** Python 3.11+, yfinance, OpenAI SDK, pytest, pathlib, hashlib

---

## File Map

| File | Task | Change |
|---|---|---|
| `core/intelligence/rl/stores/prediction_store.py` | 1 | Add `load_recent_feedback_entries(n_cycles)` |
| `core/intelligence/rl/algorithms/price_interpolator.py` | 1 | Call `load_recent_feedback_entries` instead of `load_feedback_log` |
| `core/intelligence/rl/workflows/generate_forecast.py` | 1 | Pass combined entries to `compute_historical_avg_return` |
| `core/intelligence/rl/conviction/tracker.py` | 2 | Add `sector_rsi` param; use canonical 70/30 thresholds |
| `core/intelligence/rl/workflows/daily_review.py` | 2, 3, 6 | Thread sector_rsi; add early-exit guard; remove Step 9 block |
| `core/config/settings/base.py` | 3 | Add `RL_AGENT_RERUN_THRESHOLD_PCT = 0.5` |
| `services/clients/tavily_fetcher.py` | 4 | Add disk-backed cache around `fetch_tavily_context` |
| `services/clients/llm_client.py` | 5 | Add `record_llm_call` + thin wrapper factories |
| `core/intelligence/rl/workflows/month_end_validation.py` | 6 | New — seasonal validation extracted from daily_review |
| `core/intelligence/rl/agents/thesis_reviewer.py` | 7 | ATR-relative threshold + calibration jsonl append |
| `core/intelligence/rl/stores/ledger_propagator.py` | 8 | Add `downgrade_stale_lessons` |
| `services/scheduler/python/scheduler.py` | 8 | Call downgrade weekly |

---

## Task 1: Fix Cross-Cycle Historical Average Return

**Files:**
- Modify: `core/intelligence/rl/stores/prediction_store.py`
- Modify: `core/intelligence/rl/algorithms/price_interpolator.py`
- Modify: `core/intelligence/rl/workflows/generate_forecast.py`
- Test: `tests/unit/intelligence/rl/test_price_interpolator.py`

**The bug:** `generate_forecast.py:263` calls `store.load_feedback_log(store.current_cycle_id())`. At month-start the current cycle log is empty → `compute_historical_avg_return` always returns `None`. The LLM-calibrated profile never gets historical data.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/intelligence/rl/test_price_interpolator.py

import json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.algorithms.price_interpolator import compute_historical_avg_return


def _make_feedback_log(ticker, cycle_id, entries_data, tmp_dir):
    """Write a minimal feedback log JSON to tmp_dir."""
    from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry, MissAnalysis, TimingAccuracy
    from datetime import date
    entries = []
    for d in entries_data:
        ma = MissAnalysis(
            primary_miss_agent="sentiment",
            miss_type=d.get("miss_type", "magnitude"),
            missed_factors=[],
            over_weighted_factors=[],
            agent_score_drift={},
        )
        ta = TimingAccuracy(predicted_peak_day=5, actual_move_start_day=5, lag_days=0, assessment="on_time")
        entry = FeedbackEntry(
            day=1, date=d["date"],
            predicted_close=100.0, actual_close=d["actual_close"],
            price_error_pct=d["price_error_pct"],
            direction_correct=d.get("direction_correct", True),
            predicted_verdict=d.get("verdict", "BUY"),
            miss_analysis=ma, timing=ta,
        )
        entries.append(entry)
    log = DailyFeedbackLog(ticker=ticker, cycle_id=cycle_id, sector="automobile", entries=entries)
    sector_dir = tmp_dir / "automobile" / ticker
    sector_dir.mkdir(parents=True, exist_ok=True)
    log_path = sector_dir / f"{cycle_id}_daily_feedback_log.json"
    log_path.write_text(log.model_dump_json())
    return log_path


def test_load_recent_feedback_entries_returns_combined(tmp_path):
    """load_recent_feedback_entries aggregates past cycles, not just current."""
    _make_feedback_log("MARUTI", "MARUTI_2026-03", [
        {"date": "2026-03-10", "actual_close": 102.0, "price_error_pct": 2.0, "verdict": "BUY"},
        {"date": "2026-03-11", "actual_close": 98.0,  "price_error_pct": -2.0, "verdict": "BUY"},
    ], tmp_path)
    _make_feedback_log("MARUTI", "MARUTI_2026-04", [
        {"date": "2026-04-10", "actual_close": 103.0, "price_error_pct": 3.0, "verdict": "BUY"},
    ], tmp_path)

    with patch("core.intelligence.rl.stores.prediction_store.settings") as ms:
        ms.PREDICTION_DATA_DIR = str(tmp_path)
        store = PredictionStore("MARUTI", sector="automobile")
        entries = store.load_recent_feedback_entries(n_cycles=6)

    assert len(entries) == 3


def test_compute_historical_avg_return_accepts_entry_list():
    """compute_historical_avg_return works when passed a list of FeedbackEntry objects."""
    from core.schemas.feedback import FeedbackEntry, MissAnalysis, TimingAccuracy
    ma = MissAnalysis(primary_miss_agent="x", miss_type="magnitude", missed_factors=[], over_weighted_factors=[], agent_score_drift={})
    ta = TimingAccuracy(predicted_peak_day=1, actual_move_start_day=1, lag_days=0, assessment="on_time")
    entries = [
        FeedbackEntry(day=i, date=f"2026-03-{10+i:02d}", predicted_close=100.0, actual_close=102.0,
                      price_error_pct=float(i), direction_correct=True, predicted_verdict="BUY",
                      miss_analysis=ma, timing=ta)
        for i in range(5)
    ]
    result = compute_historical_avg_return(entries, "BUY")
    assert result is not None
    assert isinstance(result, float)


def test_compute_historical_avg_return_empty_list_returns_none():
    result = compute_historical_avg_return([], "BUY")
    assert result is None
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_price_interpolator.py -k "load_recent_feedback" -v
```
Expected: `AttributeError: 'PredictionStore' object has no attribute 'load_recent_feedback_entries'`

- [ ] **Step 3: Add `load_recent_feedback_entries` to PredictionStore**

In `core/intelligence/rl/stores/prediction_store.py`, add after `load_feedback_log`:

```python
def load_recent_feedback_entries(self, n_cycles: int = 6) -> list:
    """
    Aggregate FeedbackEntry objects from the last n_cycles completed logs.
    Returns a flat list — most recent cycle first.
    Silently skips unreadable files.
    """
    from core.schemas.feedback import DailyFeedbackLog
    ticker_dir = self._ticker_dir()
    pattern = f"{self.ticker}_*_daily_feedback_log.json"
    log_files = sorted(ticker_dir.glob(pattern), reverse=True)[:n_cycles]
    entries = []
    for path in log_files:
        try:
            log = DailyFeedbackLog.model_validate_json(path.read_text(encoding="utf-8"))
            entries.extend(log.entries)
        except Exception as exc:
            logger.debug("[PredictionStore] Skipping unreadable log %s: %s", path.name, exc)
    return entries
```

- [ ] **Step 4: Update `compute_historical_avg_return` to accept a list**

In `core/intelligence/rl/algorithms/price_interpolator.py`, replace the function body (lines 428-458):

```python
def compute_historical_avg_return(
    feedback_log_or_entries,
    verdict: str,
    last_n_cycles: int = 6,
) -> float | None:
    """
    Compute median observed price_error_pct for a given verdict.
    Accepts either a DailyFeedbackLog object or a plain list of FeedbackEntry objects.
    Returns None if fewer than 3 matching entries.
    """
    try:
        if isinstance(feedback_log_or_entries, list):
            all_entries = feedback_log_or_entries
        elif feedback_log_or_entries is None:
            return None
        else:
            all_entries = feedback_log_or_entries.entries or []

        if not all_entries:
            return None

        matching = [
            e.price_error_pct
            for e in all_entries
            if e.predicted_verdict.upper() == verdict.upper()
        ]
        if len(matching) < 3:
            return None
        matching_sorted = sorted(matching)
        mid = len(matching_sorted) // 2
        median = (
            matching_sorted[mid]
            if len(matching_sorted) % 2 != 0
            else (matching_sorted[mid - 1] + matching_sorted[mid]) / 2
        )
        return round(median, 2)
    except Exception:
        return None
```

- [ ] **Step 5: Fix the call site in generate_forecast.py**

In `core/intelligence/rl/workflows/generate_forecast.py`, replace lines 263-264:

```python
# OLD:
feedback_log = store.load_feedback_log(store.current_cycle_id())
hist_avg = compute_historical_avg_return(feedback_log, report.verdict)

# NEW:
all_feedback_entries = store.load_recent_feedback_entries(n_cycles=6)
hist_avg = compute_historical_avg_return(all_feedback_entries, report.verdict)
```

- [ ] **Step 6: Run all three new tests**

```
pytest tests/unit/intelligence/rl/test_price_interpolator.py -k "load_recent or historical_avg" -v
```
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add core/intelligence/rl/stores/prediction_store.py \
        core/intelligence/rl/algorithms/price_interpolator.py \
        core/intelligence/rl/workflows/generate_forecast.py \
        tests/unit/intelligence/rl/test_price_interpolator.py
git commit -m "fix(rl): cross-cycle historical avg return — no longer always None at month-start"
```

---

## Task 2: Fix Conviction Streak RSI Proxy

**Files:**
- Modify: `core/intelligence/rl/conviction/tracker.py`
- Modify: `core/intelligence/rl/workflows/daily_review.py`
- Test: `tests/unit/intelligence/rl/test_conviction.py`

**The bug:** `compute_rsi_amplifier` uses `pattern_analysis.overall_score` (a composite 0-1) as RSI proxy with thresholds 0.40/0.60. The actual sector RSI (computed in Step 0 of daily_review) should be used with canonical 70/30 thresholds.

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/unit/intelligence/rl/test_conviction.py

from core.intelligence.rl.conviction.tracker import compute_rsi_amplifier, compute_final_reversion_prior


def test_rsi_amplifier_bullish_streak_overbought_triggers():
    """Bullish streak + sector_rsi > 70 → amplifier 1.5."""
    result = compute_rsi_amplifier(
        verdict="BUY",
        todays_agent_scores={"pattern_analysis": 0.8},
        streak_days=9,
        sector_rsi=75.0,
    )
    assert result == 1.5


def test_rsi_amplifier_bullish_streak_normal_rsi_no_trigger():
    """Bullish streak + sector_rsi 55 → no amplifier."""
    result = compute_rsi_amplifier(
        verdict="BUY",
        todays_agent_scores={"pattern_analysis": 0.8},
        streak_days=9,
        sector_rsi=55.0,
    )
    assert result == 1.0


def test_rsi_amplifier_bearish_streak_oversold_triggers():
    """Bearish streak + sector_rsi < 30 → amplifier 1.5."""
    result = compute_rsi_amplifier(
        verdict="SELL",
        todays_agent_scores={"pattern_analysis": 0.3},
        streak_days=10,
        sector_rsi=25.0,
    )
    assert result == 1.5


def test_rsi_amplifier_short_streak_no_trigger():
    """Streak < STREAK_WARNING_THRESHOLD → always 1.0 regardless of RSI."""
    result = compute_rsi_amplifier(
        verdict="BUY",
        todays_agent_scores={"pattern_analysis": 0.1},
        streak_days=3,
        sector_rsi=85.0,
    )
    assert result == 1.0


def test_compute_final_reversion_prior_uses_sector_rsi():
    """compute_final_reversion_prior passes sector_rsi to amplifier."""
    prior_with_overbought = compute_final_reversion_prior(
        streak_days=9, verdict="BUY",
        todays_agent_scores={}, sector_rsi=80.0
    )
    prior_with_normal = compute_final_reversion_prior(
        streak_days=9, verdict="BUY",
        todays_agent_scores={}, sector_rsi=50.0
    )
    # Overbought RSI with bullish streak amplifies — prior should be higher
    assert prior_with_overbought > prior_with_normal
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_conviction.py -k "rsi_amplifier or final_reversion_prior" -v
```
Expected: `TypeError: compute_rsi_amplifier() got an unexpected keyword argument 'sector_rsi'`

- [ ] **Step 3: Update tracker.py**

In `core/intelligence/rl/conviction/tracker.py`, replace `compute_rsi_amplifier` and `compute_final_reversion_prior`:

```python
def compute_rsi_amplifier(
    verdict: str,
    todays_agent_scores: dict[str, float],
    streak_days: int,
    sector_rsi: float = 50.0,
) -> float:
    """
    Return 1.5 if sector RSI contradicts the streak verdict, otherwise 1.0.
    Only activates when streak_days >= STREAK_WARNING_THRESHOLD.

    Uses actual sector_rsi from RegimeDetector (already computed in daily_review Step 0):
      BULLISH streak + sector_rsi > 70  → overbought → amplify
      BEARISH streak + sector_rsi < 30  → oversold   → amplify
    """
    if streak_days < STREAK_WARNING_THRESHOLD:
        return 1.0

    direction = verdict_direction(verdict)

    if direction == "BULLISH" and sector_rsi > 70.0:
        logger.debug(
            "[ConvictionTracker] RSI overbought (BULLISH streak, sector_rsi=%.1f > 70) → amplifier 1.5×",
            sector_rsi,
        )
        return _RSI_AMPLIFIER

    if direction == "BEARISH" and sector_rsi < 30.0:
        logger.debug(
            "[ConvictionTracker] RSI oversold (BEARISH streak, sector_rsi=%.1f < 30) → amplifier 1.5×",
            sector_rsi,
        )
        return _RSI_AMPLIFIER

    return 1.0


def compute_final_reversion_prior(
    streak_days: int,
    verdict: str,
    todays_agent_scores: dict[str, float],
    sector_rsi: float = 50.0,
) -> float:
    """
    Convenience wrapper: compute base prior, apply RSI amplifier, cap at 0.30.
    sector_rsi should come from regime_snapshot.sector_rsi (Step 0 of daily_review).
    """
    base = compute_reversion_prior(streak_days)
    if base == 0.0:
        return 0.0
    amplifier = compute_rsi_amplifier(verdict, todays_agent_scores, streak_days, sector_rsi)
    return round(min(_MAX_REVERSION_PRIOR, base * amplifier), 4)
```

- [ ] **Step 4: Thread sector_rsi into daily_review.py**

In `core/intelligence/rl/workflows/daily_review.py`, find the call to `compute_final_reversion_prior` (around line 719) and add `sector_rsi`:

```python
# OLD:
final_reversion_prior = compute_final_reversion_prior(
    streak_days=updated_streak.streak_days,
    verdict=today_forecast.predicted_verdict,
    todays_agent_scores=todays_scores,
)

# NEW:
final_reversion_prior = compute_final_reversion_prior(
    streak_days=updated_streak.streak_days,
    verdict=today_forecast.predicted_verdict,
    todays_agent_scores=todays_scores,
    sector_rsi=regime_snapshot.sector_rsi,
)
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/rl/test_conviction.py -v
```
Expected: all tests pass (new + existing)

- [ ] **Step 6: Commit**

```bash
git add core/intelligence/rl/conviction/tracker.py \
        core/intelligence/rl/workflows/daily_review.py \
        tests/unit/intelligence/rl/test_conviction.py
git commit -m "fix(rl): conviction streak RSI proxy — use actual sector_rsi with 70/30 thresholds"
```

---

## Task 3: Early-Exit Daily Review on Correct + Small-Error Days

**Files:**
- Modify: `core/intelligence/rl/workflows/daily_review.py`
- Modify: `core/config/settings/base.py`
- Test: `tests/unit/intelligence/rl/test_daily_review_early_exit.py`

**The win:** When direction is correct AND error < 0.5%, the full 9-agent orchestrator (9 LLM calls) is skipped. The existing fallback (using predicted scores) already works — we just guard it earlier.

- [ ] **Step 1: Add setting to base.py**

In `core/config/settings/base.py`, find the RL settings block and add:

```python
# Early-exit threshold: skip orchestrator re-run when direction is correct
# and abs(price_error_pct) is below this value. Set to 0.0 to disable.
RL_AGENT_RERUN_THRESHOLD_PCT: float = 0.5
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/intelligence/rl/test_daily_review_early_exit.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def test_early_exit_skips_orchestrator_on_correct_small_error():
    """
    When direction_correct=True and |error| < threshold, _run_todays_agent_scores
    must NOT be called — predicted scores are used directly.
    """
    mock_run_scores = MagicMock(return_value={"fundamentals": 0.7, "risk_macro": 0.5})

    predicted_scores = {"fundamentals": 0.72, "risk_macro": 0.48}

    # Simulate the guard logic directly (extracted as a testable function)
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun

    result = _should_skip_agent_rerun(
        direction_correct=True,
        price_error_pct=0.3,
        threshold=0.5,
    )
    assert result is True


def test_early_exit_does_not_skip_on_direction_wrong():
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    result = _should_skip_agent_rerun(
        direction_correct=False,
        price_error_pct=0.2,
        threshold=0.5,
    )
    assert result is False


def test_early_exit_does_not_skip_on_large_error():
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    result = _should_skip_agent_rerun(
        direction_correct=True,
        price_error_pct=1.5,
        threshold=0.5,
    )
    assert result is False


def test_early_exit_threshold_zero_always_reruns():
    """threshold=0.0 disables the early exit entirely."""
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    result = _should_skip_agent_rerun(
        direction_correct=True,
        price_error_pct=0.1,
        threshold=0.0,
    )
    assert result is False
```

- [ ] **Step 3: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_daily_review_early_exit.py -v
```
Expected: `ImportError: cannot import name '_should_skip_agent_rerun' from 'daily_review'`

- [ ] **Step 4: Add the guard function and wire it in daily_review.py**

First, add the helper function near the top of `core/intelligence/rl/workflows/daily_review.py` (after imports):

```python
def _should_skip_agent_rerun(
    direction_correct: bool,
    price_error_pct: float,
    threshold: float,
) -> bool:
    """True when the orchestrator re-run can be skipped safely."""
    if threshold <= 0.0:
        return False
    return direction_correct and abs(price_error_pct) < threshold
```

Then in the same file, replace the block around line 400 (the `_run_todays_agent_scores` call):

```python
# OLD (lines ~400-413):
wm_for_scores = store.load_weight_memory()
todays_scores = _run_todays_agent_scores(
    ticker,
    sector=sector,
    learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
)
if not todays_scores and today_forecast.predicted_agent_scores:
    todays_scores = dict(today_forecast.predicted_agent_scores)
    logger.info(...)

# NEW:
wm_for_scores = store.load_weight_memory()
_skip_rerun = _should_skip_agent_rerun(
    direction_correct=direction_correct,
    price_error_pct=price_error_pct,
    threshold=getattr(settings, "RL_AGENT_RERUN_THRESHOLD_PCT", 0.5),
)
if _skip_rerun:
    todays_scores = dict(today_forecast.predicted_agent_scores) if today_forecast.predicted_agent_scores else {}
    logger.info(
        "[daily_review] Early-exit: direction correct + error %.2f%% < %.1f%% "
        "— using predicted scores, skipping orchestrator re-run",
        abs(price_error_pct),
        getattr(settings, "RL_AGENT_RERUN_THRESHOLD_PCT", 0.5),
    )
else:
    todays_scores = _run_todays_agent_scores(
        ticker,
        sector=sector,
        learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
    )
    if not todays_scores and today_forecast.predicted_agent_scores:
        todays_scores = dict(today_forecast.predicted_agent_scores)
        logger.info(
            "[daily_review] Agent re-run unavailable for %s — "
            "using envelope predicted scores as fallback for drift analysis", ticker,
        )
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/rl/test_daily_review_early_exit.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add core/intelligence/rl/workflows/daily_review.py \
        core/config/settings/base.py \
        tests/unit/intelligence/rl/test_daily_review_early_exit.py
git commit -m "feat(rl): early-exit daily review — skip agent re-run on correct+small-error days (~70% LLM reduction)"
```

---

## Task 4: Tavily Cache (96% Call Reduction)

**Files:**
- Modify: `services/clients/tavily_fetcher.py`
- Test: `tests/unit/intelligence/rl/test_tavily_cache.py`

**The win:** Month-start populates the cache. Every daily review call on the same query hits disk. Monthly Tavily usage drops from ~1,056 to ~48.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/intelligence/rl/test_tavily_cache.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_fetch_tavily_context_writes_cache_on_first_call(tmp_path):
    """First call hits Tavily API and writes result to disk."""
    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", return_value=[
             {"title": "RBI holds rates", "content": "RBI held rates at 6.5%", "url": "https://et.com/1", "published_date": "", "score": 0.9}
         ]):
        from services.clients.tavily_fetcher import fetch_tavily_context
        result = fetch_tavily_context(["RBI rate decision india 2026"])

    assert "RBI holds rates" in result
    cache_files = list(tmp_path.glob("**/*.txt"))
    assert len(cache_files) == 1


def test_fetch_tavily_context_cache_hit_skips_api(tmp_path):
    """Second call with same queries returns cached result without hitting API."""
    queries = ["India Nifty market news today"]
    cached_content = "cached result from month-start"

    import hashlib
    from datetime import date
    month = date.today().strftime("%Y-%m")
    q_hash = hashlib.md5("|".join(sorted(queries[:2])).encode()).hexdigest()[:12]
    cache_file = tmp_path / month / f"{q_hash}.txt"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(cached_content, encoding="utf-8")

    mock_tavily = MagicMock(return_value=[])

    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", mock_tavily):
        from services.clients.tavily_fetcher import fetch_tavily_context
        result = fetch_tavily_context(queries)

    mock_tavily.assert_not_called()
    assert result == cached_content


def test_fetch_tavily_context_different_month_misses_cache(tmp_path):
    """Queries from a previous month do not serve as cache for current month."""
    queries = ["Sensex outlook India 2026"]
    import hashlib
    q_hash = hashlib.md5("|".join(sorted(queries[:2])).encode()).hexdigest()[:12]
    old_cache = tmp_path / "2026-04" / f"{q_hash}.txt"
    old_cache.parent.mkdir(parents=True)
    old_cache.write_text("stale old content", encoding="utf-8")

    mock_tavily = MagicMock(return_value=[])

    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", mock_tavily):
        from services.clients.tavily_fetcher import fetch_tavily_context
        fetch_tavily_context(queries)

    mock_tavily.assert_called()
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_tavily_cache.py -v
```
Expected: `ImportError: cannot import name '_TAVILY_CACHE_DIR'`

- [ ] **Step 3: Add cache to tavily_fetcher.py**

In `services/clients/tavily_fetcher.py`, add after the existing imports:

```python
import hashlib
from datetime import date
from pathlib import Path

# Disk cache directory — monthly expiry by key design
_TAVILY_CACHE_DIR = Path("data/tavily_cache")


def _cache_path(queries: list[str], max_queries: int) -> Path:
    """Deterministic cache path: keyed on sorted query content + current month."""
    month = date.today().strftime("%Y-%m")
    canonical = "|".join(sorted(queries[:max_queries]))
    q_hash = hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]
    return _TAVILY_CACHE_DIR / month / f"{q_hash}.txt"
```

Then modify `fetch_tavily_context` by wrapping the existing logic:

```python
def fetch_tavily_context(
    queries: list[str],
    max_queries: int = 2,
    max_results_per_query: int = 2,
) -> str:
    """
    Run up to `max_queries` Tavily searches and return formatted context.
    Results are cached to disk for the current calendar month — same query
    within the same month returns the cached result without hitting the API.
    """
    if not queries:
        return "No Tavily queries provided."

    # --- Cache check ---
    cache_file = _cache_path(queries, max_queries)
    if cache_file.exists():
        logger.debug("[tavily] Cache hit: %s", cache_file.name)
        return cache_file.read_text(encoding="utf-8")

    # --- Live fetch (existing logic, unchanged) ---
    lines: list[str] = []
    for query in queries[:max_queries]:
        results = search_tavily(query, max_results=max_results_per_query)
        if not results:
            lines.append(f"[No Tavily results for: {query}]")
            continue
        lines.append(f"\n--- Tavily (full content): {query} ---")
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            from backend.shared.config import settings as _tav_settings
            _max = _tav_settings.TAVILY_MAX_CONTENT_CHARS
            if len(content) > _max:
                content = content[:_max] + "…"
            lines.append(f"• {title}\n  {content}\n  Source: {url}")

    result = "\n".join(lines) if lines else "No Tavily data available."

    # --- Write to cache ---
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(result, encoding="utf-8")
        logger.debug("[tavily] Cache written: %s", cache_file.name)
    except Exception as exc:
        logger.warning("[tavily] Cache write failed (non-fatal): %s", exc)

    return result
```

- [ ] **Step 4: Run tests**

```
pytest tests/unit/intelligence/rl/test_tavily_cache.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/clients/tavily_fetcher.py \
        tests/unit/intelligence/rl/test_tavily_cache.py
git commit -m "feat(rl): disk-backed Tavily cache — monthly expiry reduces calls from ~1056 to ~48/month"
```

---

## Task 5: LLM Cost Telemetry

**Files:**
- Modify: `services/clients/llm_client.py`
- Test: `tests/unit/intelligence/rl/test_llm_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/intelligence/rl/test_llm_telemetry.py
import json
from pathlib import Path
from unittest.mock import patch


def test_record_llm_call_writes_jsonl(tmp_path):
    """record_llm_call appends a valid JSON line to outputs/llm_log/{date}.jsonl."""
    with patch("services.clients.llm_client._LLM_LOG_DIR", tmp_path):
        from services.clients.llm_client import record_llm_call
        record_llm_call(
            caller="FeedbackAgent",
            model="qwen/qwen-2.5-72b-instruct",
            input_tokens=1420,
            output_tokens=380,
            latency_ms=2341,
            success=True,
        )

    log_files = list(tmp_path.glob("*.jsonl"))
    assert len(log_files) == 1
    line = json.loads(log_files[0].read_text().strip())
    assert line["caller"] == "FeedbackAgent"
    assert line["input_tokens"] == 1420
    assert line["success"] is True
    assert "ts" in line


def test_record_llm_call_is_nonfatal_on_bad_path():
    """record_llm_call must never raise — bad path is silently swallowed."""
    with patch("services.clients.llm_client._LLM_LOG_DIR", Path("/nonexistent/path")):
        from services.clients.llm_client import record_llm_call
        record_llm_call("test", "model", 0, 0, 0, False)  # must not raise
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_llm_telemetry.py -v
```
Expected: `ImportError: cannot import name 'record_llm_call'`

- [ ] **Step 3: Add telemetry to llm_client.py**

In `services/clients/llm_client.py`, add after existing imports:

```python
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
_LLM_LOG_DIR = Path("outputs/llm_log")


def record_llm_call(
    caller: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
) -> None:
    """Append one JSON line per LLM call to outputs/llm_log/{date}.jsonl. Never raises."""
    try:
        _LLM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _LLM_LOG_DIR / f"{date.today().isoformat()}.jsonl"
        entry = json.dumps({
            "ts":            datetime.now(timezone.utc).isoformat(),
            "caller":        caller,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "latency_ms":    latency_ms,
            "success":       success,
        })
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except Exception as exc:
        logger.debug("[llm_client] telemetry write failed (non-fatal): %s", exc)
```

- [ ] **Step 4: Add `record_call` usage to FeedbackAgent**

In `core/intelligence/rl/agents/feedback_agent.py`, find the LLM call and wrap it with timing + telemetry. Add `import time` and `from services.clients.llm_client import record_llm_call` at the top, then wrap:

```python
import time
from services.clients.llm_client import record_llm_call

# Around the LLM call in FeedbackAgent (exact location depends on the method):
_t0 = time.monotonic()
response = client.chat.completions.create(...)
_latency = int((time.monotonic() - _t0) * 1000)
record_llm_call(
    caller="FeedbackAgent",
    model=response.model,
    input_tokens=response.usage.prompt_tokens if response.usage else 0,
    output_tokens=response.usage.completion_tokens if response.usage else 0,
    latency_ms=_latency,
    success=True,
)
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/rl/test_llm_telemetry.py -v
```
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add services/clients/llm_client.py \
        core/intelligence/rl/agents/feedback_agent.py \
        tests/unit/intelligence/rl/test_llm_telemetry.py
git commit -m "feat(rl): LLM cost telemetry — daily jsonl log at outputs/llm_log/"
```

---

## Task 6: Seasonal Validation → Month-End Only

**Files:**
- Create: `core/intelligence/rl/workflows/month_end_validation.py`
- Modify: `core/intelligence/rl/workflows/daily_review.py`
- Test: `tests/unit/intelligence/rl/test_month_end_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/intelligence/rl/test_month_end_validation.py
from datetime import date
from unittest.mock import patch, MagicMock


def test_is_last_trading_day_of_month_end_of_month():
    """Last trading day of month returns True."""
    from core.intelligence.rl.workflows.month_end_validation import _is_last_trading_day_of_month

    # Mock nse_calendar so no trading days remain after the 30th
    with patch("core.intelligence.rl.workflows.month_end_validation.nse_calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = False  # no more trading days this month
        result = _is_last_trading_day_of_month(date(2026, 5, 29))

    assert result is True


def test_is_last_trading_day_of_month_mid_month():
    """Mid-month date returns False."""
    from core.intelligence.rl.workflows.month_end_validation import _is_last_trading_day_of_month

    with patch("core.intelligence.rl.workflows.month_end_validation.nse_calendar") as mock_cal:
        mock_cal.is_trading_day.return_value = True  # more trading days exist
        result = _is_last_trading_day_of_month(date(2026, 5, 15))

    assert result is False
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_month_end_validation.py -v
```
Expected: `ModuleNotFoundError: No module named 'core.intelligence.rl.workflows.month_end_validation'`

- [ ] **Step 3: Create month_end_validation.py**

```python
# core/intelligence/rl/workflows/month_end_validation.py
"""
Month-end seasonal pattern validation.

Extracted from daily_review.py Step 9. Runs once at end of each month
instead of every day — SeasonalValidator needs accumulated data to be meaningful.
Called from daily_review.py only when _is_last_trading_day_of_month() is True.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

from core.intelligence.rl.nse_calendar import nse_calendar
from core.intelligence.seasonal.validator import SeasonalValidator
from core.config import settings

logger = logging.getLogger(__name__)


def _is_last_trading_day_of_month(d: date) -> bool:
    """True if no trading days remain in d's month after d."""
    last_calendar_day = monthrange(d.year, d.month)[1]
    for day_num in range(d.day + 1, last_calendar_day + 1):
        try:
            if nse_calendar.is_trading_day(date(d.year, d.month, day_num)):
                return False
        except Exception:
            pass
    return True


def run_month_end_validation(
    ticker: str,
    sector: str,
    store,
    seasonal_ctx,
    seasonal_calendar,
    ticker_ledger,
    cycle_id: str,
    review_date: date,
) -> None:
    """
    Validate active seasonal patterns against this month's feedback log.
    Mutates ticker_ledger in-place. Caller is responsible for saving the ledger.
    """
    if not seasonal_ctx.is_seasonal_period:
        return

    try:
        validator = SeasonalValidator(
            sector=sector,
            base_dir=settings.PREDICTION_DATA_DIR,
        )
        active_seeds = seasonal_calendar.active_patterns_on(review_date)
        feedback_log = store.load_feedback_log(cycle_id)

        ledger_dirty = False
        for pattern in active_seeds:
            result = validator.validate_pattern(
                pattern=pattern,
                review_date=review_date,
                feedback_log=feedback_log,
            )
            lesson = ticker_ledger.find_by_pattern(result.pattern_id)
            if lesson is None:
                continue
            if result.record.invalidated and lesson.still_valid:
                lesson.still_valid = False
                ledger_dirty = True
                logger.info(
                    "[month_end_validation] Lesson %s invalidated — pattern %s contradicted",
                    lesson.lesson_id, result.pattern_id,
                )
            elif result.record.validated_by_rl and result.direction_matched:
                lesson.confidence = min(1.0, lesson.confidence + 0.05)
                ledger_dirty = True

        validator.save_state()

        if ledger_dirty:
            store.save_learning_ledger(ticker_ledger)

        logger.info(
            "[month_end_validation] %s %s — %d patterns validated",
            ticker, review_date, len(active_seeds),
        )
    except Exception as exc:
        logger.warning("[month_end_validation] Failed for %s on %s (non-fatal): %s", ticker, review_date, exc)
```

- [ ] **Step 4: Replace Step 9 in daily_review.py**

Remove the Step 9 block from `daily_review.py` (lines 805-862 — the entire `if seasonal_ctx.is_seasonal_period:` block at the bottom) and replace with:

```python
    # ------------------------------------------------------------------ #
    # Step 9 (P1): Seasonal validation — month-end only
    # Runs only on the last trading day of the month to avoid O(N²) overhead.
    # ------------------------------------------------------------------ #
    from core.intelligence.rl.workflows.month_end_validation import (
        _is_last_trading_day_of_month,
        run_month_end_validation,
    )
    if _is_last_trading_day_of_month(review_date):
        run_month_end_validation(
            ticker=ticker,
            sector=sector,
            store=store,
            seasonal_ctx=seasonal_ctx,
            seasonal_calendar=seasonal_calendar,
            ticker_ledger=ticker_ledger,
            cycle_id=cycle_id,
            review_date=review_date,
        )
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/rl/test_month_end_validation.py -v
```
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add core/intelligence/rl/workflows/month_end_validation.py \
        core/intelligence/rl/workflows/daily_review.py \
        tests/unit/intelligence/rl/test_month_end_validation.py
git commit -m "feat(rl): seasonal validation moved to month-end — removes O(seeds×log) from daily hot path"
```

---

## Task 7: ATR-Relative ThesisReviewer + Calibration Telemetry

**Files:**
- Modify: `core/intelligence/rl/agents/thesis_reviewer.py`
- Test: `tests/unit/intelligence/rl/test_thesis_reviewer.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/unit/intelligence/rl/test_thesis_reviewer.py
from unittest.mock import patch, MagicMock
from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer


def test_should_review_high_atr_stock_needs_larger_miss():
    """For a volatile stock (ATR 3.5%), flat 2% miss should NOT trigger review."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)  # skip __init__ (no API key in tests)
    with patch.object(reviewer, "_compute_atr_pct", return_value=3.5):
        result = reviewer.should_review(
            price_error_pct=2.0,
            direction_correct=True,
            miss_type="magnitude",
        )
    assert result is False  # 2% < max(1.5, 1.5*3.5=5.25)


def test_should_review_low_atr_stock_triggers_at_1_5_pct():
    """For a stable stock (ATR 0.8%), a 1.6% miss should trigger review."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", return_value=0.8):
        result = reviewer.should_review(
            price_error_pct=1.6,
            direction_correct=True,
            miss_type="magnitude",
        )
    assert result is True  # 1.6% > max(1.5, 1.5*0.8=1.2) → threshold=1.5


def test_should_review_structural_miss_always_triggers():
    """direction_flip always triggers regardless of ATR or error size."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", return_value=5.0):
        result = reviewer.should_review(
            price_error_pct=0.5,
            direction_correct=False,
            miss_type="direction_flip",
        )
    assert result is True


def test_should_review_atr_fetch_failure_uses_floor():
    """If ATR fetch fails, threshold falls back to floor 1.5%."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", side_effect=Exception("no data")):
        result = reviewer.should_review(
            price_error_pct=2.0,
            direction_correct=True,
            miss_type="magnitude",
        )
    # floor=1.5, threshold=max(1.5, 1.5*0)=1.5, error=2.0 > 1.5 → True
    assert result is True
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_thesis_reviewer.py -k "atr" -v
```
Expected: errors — `should_review` doesn't accept `miss_type` yet or `_compute_atr_pct` doesn't exist

- [ ] **Step 3: Update thesis_reviewer.py**

Replace the `THESIS_REVIEW_THRESHOLD` constant and `should_review` method, and add `_compute_atr_pct`:

```python
# Remove the old constant:
# THESIS_REVIEW_THRESHOLD: float = 2.0

# Add ATR floor constant:
_ATR_THRESHOLD_FLOOR: float = 1.5      # minimum threshold % regardless of ATR
_ATR_THRESHOLD_MULTIPLIER: float = 1.5  # threshold = max(floor, multiplier * atr_pct)
```

Add `_compute_atr_pct` method to `ThesisReviewer`:

```python
def _compute_atr_pct(self, ticker: str) -> float:
    """14-day ATR as % of price. Returns 0.0 on failure (caller uses floor)."""
    try:
        from core.intelligence.rl.algorithms.price_interpolator import compute_atr_pct
        from core.data.fetchers.price import get_price_history
        ohlcv = get_price_history(ticker, years=1)
        return compute_atr_pct(ohlcv)
    except Exception:
        return 0.0
```

Replace `should_review`:

```python
def should_review(
    self,
    price_error_pct: float,
    direction_correct: bool,
    miss_type: str,
    ticker: str = "",
) -> bool:
    """True when a thesis review is warranted."""
    # Structural miss always triggers
    if not direction_correct and miss_type in THESIS_REVIEW_MISS_TYPES:
        return True
    # ATR-relative size trigger
    try:
        atr_pct = self._compute_atr_pct(ticker) if ticker else 0.0
    except Exception:
        atr_pct = 0.0
    threshold = max(_ATR_THRESHOLD_FLOOR, _ATR_THRESHOLD_MULTIPLIER * atr_pct)
    return abs(price_error_pct) > threshold
```

Add calibration jsonl append inside `review()`, after the successful parse:

```python
# After: return self._parse(raw, key_assumptions)
# Add calibration telemetry:
import json as _json
from datetime import date as _date
from pathlib import Path as _Path
try:
    _cal_dir = _Path("data/predictions") / sector / ticker
    _cal_dir.mkdir(parents=True, exist_ok=True)
    _cal_path = _cal_dir / "thesis_calls.jsonl"
    _entry = _json.dumps({
        "date": str(_date.today()),
        "ticker": ticker,
        "multiplier": result.horizon_confidence_multiplier,
        "thesis_intact": result.thesis_intact,
        "price_error_at_trigger": round(abs(price_error_pct), 2) if price_error_pct else None,
    })
    with open(_cal_path, "a", encoding="utf-8") as _fh:
        _fh.write(_entry + "\n")
except Exception:
    pass  # telemetry is non-fatal
return result
```

Note: `review()` currently doesn't receive `price_error_pct`. Add it as an optional param:

```python
def review(
    self,
    ticker: str,
    sector: str,
    key_assumptions: list[str],
    fb_output: FeedbackAgentOutput,
    market_context: str,
    price_error_pct: float = 0.0,  # for calibration telemetry only
) -> ThesisReview:
```

Update the call site in `daily_review.py` to pass `ticker` to `should_review` and `price_error_pct` to `review`:

```python
# In daily_review.py, find the thesis_reviewer.should_review call and update:
if thesis_reviewer.should_review(price_error_pct, direction_correct, fb_output.miss_type, ticker=ticker):
    thesis_review = thesis_reviewer.review(
        ticker, sector, key_assumptions, fb_output, market_context,
        price_error_pct=price_error_pct,
    )
```

- [ ] **Step 4: Run tests**

```
pytest tests/unit/intelligence/rl/test_thesis_reviewer.py -v
```
Expected: all pass (new + existing)

- [ ] **Step 5: Commit**

```bash
git add core/intelligence/rl/agents/thesis_reviewer.py \
        core/intelligence/rl/workflows/daily_review.py \
        tests/unit/intelligence/rl/test_thesis_reviewer.py
git commit -m "feat(rl): ATR-relative thesis threshold + calibration telemetry jsonl"
```

---

## Task 8: Lesson Scope Downgrade (Stale Cleanup)

**Files:**
- Modify: `core/intelligence/rl/stores/ledger_propagator.py`
- Modify: `services/scheduler/python/scheduler.py`
- Test: `tests/unit/intelligence/rl/test_shared_ledger.py`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/unit/intelligence/rl/test_shared_ledger.py
from datetime import date, timedelta
from core.schemas.feedback import LearningLedger, Lesson
from core.intelligence.rl.stores.ledger_propagator import downgrade_stale_lessons


def _make_lesson(scope: str, days_ago: int, n_tickers: int = 1) -> Lesson:
    last_seen = (date.today() - timedelta(days=days_ago)).isoformat()
    return Lesson(
        lesson_id="L001",
        date_learned="2026-01-01",
        last_seen=last_seen,
        category="macro",
        scope=scope,
        pattern="test_pattern",
        observation="test",
        rule="test rule",
        confidence=0.75,
        occurrences=2,
        still_valid=True,
        contributing_tickers=[f"TICK{i}" for i in range(n_tickers)],
    )


def test_downgrade_stale_market_wide_single_ticker():
    """market_wide lesson with 1 ticker unseen 31+ days → downgraded to sector_wide."""
    ledger = LearningLedger(ticker="SHARED", sector="automobile", lessons=[
        _make_lesson("market_wide", days_ago=35, n_tickers=1)
    ])
    downgrade_stale_lessons(ledger, staleness_days=30)
    assert ledger.lessons[0].scope == "sector_wide"


def test_downgrade_stale_sector_wide_single_ticker_marks_invalid():
    """sector_wide lesson with 1 ticker unseen 61+ days → still_valid=False."""
    ledger = LearningLedger(ticker="SHARED", sector="automobile", lessons=[
        _make_lesson("sector_wide", days_ago=65, n_tickers=1)
    ])
    downgrade_stale_lessons(ledger, staleness_days=30)
    assert ledger.lessons[0].still_valid is False


def test_no_downgrade_for_multi_ticker_lesson():
    """market_wide lesson with 3 contributing tickers is NOT downgraded even if stale."""
    ledger = LearningLedger(ticker="SHARED", sector="automobile", lessons=[
        _make_lesson("market_wide", days_ago=35, n_tickers=3)
    ])
    downgrade_stale_lessons(ledger, staleness_days=30)
    assert ledger.lessons[0].scope == "market_wide"


def test_no_downgrade_for_fresh_lesson():
    """Lesson seen 5 days ago is not touched."""
    ledger = LearningLedger(ticker="SHARED", sector="automobile", lessons=[
        _make_lesson("market_wide", days_ago=5, n_tickers=1)
    ])
    downgrade_stale_lessons(ledger, staleness_days=30)
    assert ledger.lessons[0].scope == "market_wide"
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/unit/intelligence/rl/test_shared_ledger.py -k "downgrade" -v
```
Expected: `ImportError: cannot import name 'downgrade_stale_lessons'`

- [ ] **Step 3: Add `downgrade_stale_lessons` to ledger_propagator.py**

```python
# Add to core/intelligence/rl/stores/ledger_propagator.py

from datetime import date as _date


def downgrade_stale_lessons(
    ledger: "LearningLedger",
    staleness_days: int = 30,
) -> int:
    """
    Downgrade scope for lessons that haven't been seen in staleness_days
    AND were confirmed by only one ticker (noise, not true cross-ticker signal).

    Rules:
      market_wide  + 1 ticker + inactive >  staleness_days → sector_wide
      sector_wide  + 1 ticker + inactive > 2×staleness_days → still_valid=False

    Returns number of lessons modified.
    """
    today = _date.today()
    modified = 0
    for lesson in ledger.lessons:
        if not lesson.still_valid:
            continue
        if len(lesson.contributing_tickers) > 1:
            continue  # multi-ticker lessons are real signal — never auto-downgrade
        try:
            last_seen = _date.fromisoformat(lesson.last_seen)
            days_inactive = (today - last_seen).days
        except Exception:
            continue

        if lesson.scope == "market_wide" and days_inactive > staleness_days:
            lesson.scope = "sector_wide"
            modified += 1
            logger.info(
                "[ledger_propagator] Downgraded %s from market_wide → sector_wide "
                "(1 ticker, %d days inactive)",
                lesson.lesson_id, days_inactive,
            )
        elif lesson.scope == "sector_wide" and days_inactive > staleness_days * 2:
            lesson.still_valid = False
            modified += 1
            logger.info(
                "[ledger_propagator] Invalidated %s (sector_wide, 1 ticker, %d days inactive)",
                lesson.lesson_id, days_inactive,
            )
    return modified
```

- [ ] **Step 4: Call it weekly from the scheduler**

In `services/scheduler/python/scheduler.py`, find the scheduler job registration and add a weekly cleanup job:

```python
# Add after existing job registrations:

def _run_weekly_ledger_cleanup() -> None:
    """Downgrade stale single-ticker market-wide/sector-wide lessons."""
    from core.intelligence.rl.stores.ledger_propagator import downgrade_stale_lessons
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    from core.config import settings

    tickers = list(settings.SCHEDULER_TICKERS or [])
    for ticker in tickers:
        try:
            store = PredictionStore(ticker, sector=_get_sector(ticker))
            _, sector_ledger, market_ledger = store.load_all_ledgers()
            n1 = downgrade_stale_lessons(market_ledger)
            n2 = downgrade_stale_lessons(sector_ledger)
            if n1:
                store.save_market_ledger(market_ledger)
            if n2:
                store.save_sector_ledger(sector_ledger)
            logger.info("[scheduler] Ledger cleanup %s: %d lessons modified", ticker, n1 + n2)
        except Exception as exc:
            logger.warning("[scheduler] Ledger cleanup failed for %s: %s", ticker, exc)


# Register as weekly job (runs every Monday at 9am IST = 3:30am UTC):
scheduler.add_job(
    _run_weekly_ledger_cleanup,
    "cron",
    day_of_week="mon",
    hour=3,
    minute=30,
    id="ledger_cleanup_weekly",
    replace_existing=True,
)
```

- [ ] **Step 5: Run tests**

```
pytest tests/unit/intelligence/rl/test_shared_ledger.py -v
```
Expected: all pass (new + existing)

- [ ] **Step 6: Run full unit suite to confirm no regressions**

```
pytest tests/unit/ -q --tb=short 2>&1 | tail -15
```
Expected: same or better pass count vs baseline

- [ ] **Step 7: Commit**

```bash
git add core/intelligence/rl/stores/ledger_propagator.py \
        services/scheduler/python/scheduler.py \
        tests/unit/intelligence/rl/test_shared_ledger.py
git commit -m "feat(rl): lesson scope downgrade — weekly cleanup of stale single-ticker market-wide lessons"
```

---

## Self-Review Checklist (run after writing this plan)

**Spec coverage:**
- [x] Task 1 → Spec item 1 (cross-cycle historical avg bug)
- [x] Task 2 → Spec item 2 (RSI proxy bug)
- [x] Task 3 → Spec item 3 (early-exit)
- [x] Task 4 → Spec item 4 (Tavily cache)
- [x] Task 5 → Spec item 5 (LLM telemetry)
- [x] Task 6 → Spec item 6 (seasonal validation month-end)
- [x] Task 7 → Spec items 7+9 (ATR threshold + calibration telemetry, same file)
- [x] Task 8 → Spec item 8 (lesson scope downgrade)

**Type consistency:**
- `load_recent_feedback_entries` returns `list` — `compute_historical_avg_return` now accepts `list` ✓
- `compute_rsi_amplifier(sector_rsi=float)` matches `compute_final_reversion_prior(sector_rsi=float)` ✓
- `_should_skip_agent_rerun` returns `bool` — used as guard in daily_review ✓
- `downgrade_stale_lessons(ledger, staleness_days)` returns `int` — scheduler uses return value for conditional save ✓
- `should_review(ticker=str)` added — call site in daily_review passes `ticker=ticker` ✓
- `review(price_error_pct=float)` added — call site passes `price_error_pct=price_error_pct` ✓
