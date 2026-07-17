# Audit Wave G — RL Semantics (fix-forward + shadow lane) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the user's 2026-07-17 RL-semantics decisions — AUD-060 NEUTRAL direction-credit fixed forward (correct only when the move is flat), AUD-077 verdict shadow lane (log threshold(composite) beside the LLM verdict, zero behavior change), plus AUD-041 (news "last 48h" context actually date-filtered).

**Architecture:** Three independent, small changes. 060 is a one-branch semantic change in `feedback_agent.is_direction_correct` (all consumers — WeightAdapter credit, scorecard, advisor ADD gate — inherit it via the stored `direction_correct` field, forward-only). 077 adds a pure `verdict_from_composite()` mapper + a never-raises JSONL drift logger called at the single live choke point (`SignalAggregator.aggregate`). 041 filters articles by parsed date inside `get_news_context` with an honest window label.

**Tech Stack:** Python 3.11, pytest. No new dependencies.

## Global Constraints

- Branch: `audit-wave-g-rl-semantics` (in-repo branch, NOT a worktree — OneDrive locks).
- TDD: failing test first per task.
- Known-failing baseline (do not worsen): AUD-022 stale mocks (test_phase0_llm_migration / test_orchestrator / test_phase2_api) + event_ingestor unparseable-date test.
- **Deploy-window rule: do NOT push to main between 16:25–17:15 IST on a trading day** (deploy kills the in-flight daily review — 2026-07-17 incident).
- AUD-060 is FORWARD-ONLY: never rewrite stored `direction_correct` values in feedback logs (user decision: "Fix forward", not backfill).
- AUD-077 is OBSERVE-ONLY: the FinalReport's verdict must remain exactly the LLM's; the shadow value is logged, never substituted.
- House style: helpers on pipeline paths never raise; log and degrade.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: AUD-060 — NEUTRAL is correct only when the move is flat

**Files:**
- Modify: `core/intelligence/rl/agents/feedback_agent.py:87-101` (`is_direction_correct`)
- Test: `tests/unit/intelligence/rl/test_direction_semantics.py`

**Interfaces:**
- `is_direction_correct(predicted_verdict: str, actual_direction: str) -> bool` — signature unchanged; NEUTRAL branch flips from `return True` to `return actual_direction == "FLAT"`. `classify_direction` (UP/DOWN/FLAT vs ±`FLAT_THRESHOLD_PCT`) is unchanged and already the flat authority.
- Ripple (accepted, by design): daily direction accuracy drops to honest levels; WeightAdapter stops crediting NEUTRAL free passes; advisor `direction_accuracy_7d ≥ 0.60` ADD gate becomes stricter; `_should_skip_agent_rerun` fires the agent re-run more often on wrong-NEUTRAL days (small cost increase).

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/intelligence/rl/test_direction_semantics.py — AUD-060 fix-forward."""
from core.intelligence.rl.agents.feedback_agent import (
    classify_direction, is_direction_correct,
)


def test_neutral_correct_only_when_flat():
    assert is_direction_correct("NEUTRAL", "FLAT") is True
    assert is_direction_correct("NEUTRAL", "UP") is False
    assert is_direction_correct("NEUTRAL", "DOWN") is False


def test_directional_verdicts_unchanged():
    assert is_direction_correct("BUY", "UP") is True
    assert is_direction_correct("STRONG BUY", "UP") is True
    assert is_direction_correct("BUY", "DOWN") is False
    assert is_direction_correct("SELL", "DOWN") is True
    assert is_direction_correct("STRONG SELL", "UP") is False
    assert is_direction_correct("sell", "DOWN") is True   # case-insensitive


def test_unknown_verdict_treated_like_neutral():
    # HOLD/garbage make no directional claim either — same flat rule
    assert is_direction_correct("HOLD", "FLAT") is True
    assert is_direction_correct("HOLD", "UP") is False


def test_rule_matches_synthetic_generator():
    """The synthetic generator has always used flat-only NEUTRAL credit —
    live and synthetic semantics must now agree (the AUD-060 defect was the
    disagreement)."""
    for actual in ("UP", "DOWN", "FLAT"):
        expected = (actual == "FLAT")
        assert is_direction_correct("NEUTRAL", actual) is expected


def test_classify_direction_flat_band_unchanged():
    # predicted 100, threshold ±0.3%: 100.2 flat, 100.4 up, 99.6 down
    assert classify_direction(100.2, 100.0) == "FLAT"
    assert classify_direction(100.4, 100.0) == "UP"
    assert classify_direction(99.6, 100.0) == "DOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/intelligence/rl/test_direction_semantics.py -v`
Expected: `test_neutral_correct_only_when_flat` and `test_unknown_verdict_treated_like_neutral` and `test_rule_matches_synthetic_generator` FAIL (NEUTRAL currently always True).

- [ ] **Step 3: Implement**

Replace `is_direction_correct` in `core/intelligence/rl/agents/feedback_agent.py`:

```python
def is_direction_correct(predicted_verdict: str, actual_direction: str) -> bool:
    """
    True if the verdict's implied direction aligns with the actual price move.
    BUY / STRONG BUY   → expects UP
    SELL / STRONG SELL → expects DOWN
    NEUTRAL / other    → expects FLAT (within ±FLAT_THRESHOLD_PCT)

    AUD-060 (fix-forward 2026-07-17): NEUTRAL used to be an automatic hit,
    inflating direction accuracy, WeightAdapter credit, and the advisor ADD
    gate. A NEUTRAL claim is now correct only when the move was actually
    flat — the rule the synthetic generator always used. Applies to new
    reviews only; stored direction_correct values are never rewritten.
    """
    bullish = {"BUY", "STRONG BUY"}
    bearish = {"SELL", "STRONG SELL"}
    verdict_upper = predicted_verdict.upper()
    if verdict_upper in bullish:
        return actual_direction == "UP"
    if verdict_upper in bearish:
        return actual_direction == "DOWN"
    return actual_direction == "FLAT"
```

- [ ] **Step 4: Run tests + sweep for old-rule assertions**

Run: `python -m pytest tests/unit/intelligence/rl/test_direction_semantics.py -v` (expect PASS), then `python -m pytest tests/unit/intelligence -q` and `grep -rn "is_direction_correct" tests/`. Any pre-existing test asserting `NEUTRAL → True` on a non-FLAT day encodes the old defect — update it to the new contract and note it in the commit message.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(wave-g): NEUTRAL direction credit only on flat moves, forward-only (AUD-060)"
```

---

### Task 2: AUD-077 — verdict shadow lane (observe-only)

**Files:**
- Create: `src/backend/shared/pipeline/verdict_shadow.py`
- Modify: `src/backend/shared/pipeline/signal_aggregator.py` (`aggregate`, after `_parse` at :172)
- Test: `tests/unit/shared/test_verdict_shadow.py`

**Interfaces:**
- Produces: `verdict_from_composite(composite: float) -> str` — maps [0,1] onto `settings.SCORE_THRESHOLDS` bands, returns the LLM-style label ("STRONG BUY"/"BUY"/"NEUTRAL"/"SELL"/"STRONG SELL"); `log_verdict_shadow(ticker: str, composite: float, llm_verdict: str, llm_final_score: float, learned_weights_used: bool, shadow_log: str | None = None) -> dict | None` — appends one JSON line to `data/rl/verdict_shadow.jsonl` `{ts, ticker, composite, threshold_verdict, llm_verdict, llm_final_score, diverged, learned_weights_used}` + one INFO line; returns the record; never raises (returns None on failure).
- `SignalAggregator.aggregate` return value and `FinalReport` are UNCHANGED — the LLM verdict stays authoritative.
- Analysis window: after ~2 weeks of prod rows, divergence rate + direction-accuracy split (threshold-lane vs LLM-lane, joined against feedback logs) decides hard-bind vs keep (gates AUD-098).

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/shared/test_verdict_shadow.py — AUD-077 shadow lane."""
import json

import backend.shared.pipeline.verdict_shadow as vs


def test_verdict_from_composite_bands():
    assert vs.verdict_from_composite(0.90) == "STRONG BUY"
    assert vs.verdict_from_composite(0.75) == "STRONG BUY"   # lo-inclusive
    assert vs.verdict_from_composite(0.60) == "BUY"
    assert vs.verdict_from_composite(0.50) == "NEUTRAL"
    assert vs.verdict_from_composite(0.30) == "SELL"
    assert vs.verdict_from_composite(0.05) == "STRONG SELL"
    assert vs.verdict_from_composite(0.0) == "STRONG SELL"
    assert vs.verdict_from_composite(1.0) == "STRONG BUY"


def test_log_verdict_shadow_appends_record(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="MARUTI", composite=0.62, llm_verdict="NEUTRAL",
        llm_final_score=0.55, learned_weights_used=True,
        shadow_log=str(log),
    )
    assert rec["threshold_verdict"] == "BUY"
    assert rec["diverged"] is True
    on_disk = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert on_disk["ticker"] == "MARUTI"
    assert on_disk["composite"] == 0.62
    assert on_disk["learned_weights_used"] is True
    assert on_disk["ts"]


def test_log_verdict_shadow_agreement_not_diverged(tmp_path):
    log = tmp_path / "shadow.jsonl"
    rec = vs.log_verdict_shadow(
        ticker="TCS", composite=0.50, llm_verdict="neutral",
        llm_final_score=0.5, learned_weights_used=False,
        shadow_log=str(log),
    )
    assert rec["diverged"] is False        # case-insensitive comparison


def test_log_verdict_shadow_never_raises(tmp_path):
    # a directory as the log path forces the write to fail
    rec = vs.log_verdict_shadow(
        ticker="X", composite=0.5, llm_verdict="NEUTRAL",
        llm_final_score=0.5, learned_weights_used=False,
        shadow_log=str(tmp_path),
    )
    assert rec is None


def test_aggregator_calls_shadow_logger():
    import inspect
    from backend.shared.pipeline.signal_aggregator import SignalAggregator
    assert "log_verdict_shadow" in inspect.getsource(SignalAggregator.aggregate)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/shared/test_verdict_shadow.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'backend.shared.pipeline.verdict_shadow'`

- [ ] **Step 3: Implement**

`src/backend/shared/pipeline/verdict_shadow.py`:

```python
"""
backend/shared/pipeline/verdict_shadow.py
==========================================
AUD-077 shadow lane (observe-only, decision 2026-07-17).

The RL loop learns per-agent weights, but the final verdict is emitted
free-form by the aggregation LLM — the learned composite reaches it only as
one prompt line, so the weight loop's causal effect on verdicts is unmeasured
(live evidence: SUZLON 0/10 direction accuracy on an 11-day BUY streak).

This module logs what the verdict WOULD be if bound to the learned composite
via settings.SCORE_THRESHOLDS, next to what the LLM actually said. It never
changes behavior. After ~2 weeks of rows, join data/rl/verdict_shadow.jsonl
against the feedback logs to compare the two lanes' direction accuracy —
that comparison decides hard-bind vs keep (and unblocks AUD-098).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.shared.config import settings

logger = logging.getLogger(__name__)

_SHADOW_LOG = Path("data") / "rl" / "verdict_shadow.jsonl"


def verdict_from_composite(composite: float) -> str:
    """Map a [0,1] composite onto settings.SCORE_THRESHOLDS bands.

    Bands are lo-inclusive, checked from the highest lo downward, so band
    edges resolve upward (0.75 -> STRONG BUY). Labels match the LLM's verdict
    vocabulary ("strong_buy" -> "STRONG BUY").
    """
    composite = max(0.0, min(1.0, float(composite)))
    for name, (lo, _hi) in sorted(
        settings.SCORE_THRESHOLDS.items(), key=lambda kv: kv[1][0], reverse=True
    ):
        if composite >= lo:
            return name.replace("_", " ").upper()
    return "STRONG SELL"


def log_verdict_shadow(
    ticker: str,
    composite: float,
    llm_verdict: str,
    llm_final_score: float,
    learned_weights_used: bool,
    shadow_log: str | None = None,
) -> dict | None:
    """Append one shadow record. Observe-only, never raises."""
    try:
        threshold_verdict = verdict_from_composite(composite)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "composite": round(float(composite), 4),
            "threshold_verdict": threshold_verdict,
            "llm_verdict": llm_verdict,
            "llm_final_score": round(float(llm_final_score), 4),
            "diverged": threshold_verdict != (llm_verdict or "").strip().upper(),
            "learned_weights_used": learned_weights_used,
        }
        path = Path(shadow_log) if shadow_log else _SHADOW_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        logger.info(
            "[verdict_shadow] %s composite=%.3f -> %s | llm=%s (%.3f) | diverged=%s",
            ticker, rec["composite"], threshold_verdict,
            llm_verdict, rec["llm_final_score"], rec["diverged"],
        )
        return rec
    except Exception as exc:
        logger.warning("[verdict_shadow] log failed (non-fatal): %s", exc)
        return None
```

`src/backend/shared/pipeline/signal_aggregator.py` — in `aggregate`, replace the final `return self._parse(...)` line:

```python
        report = self._parse(raw, ticker, company_name, weighted_scores, agent_outputs)
        # AUD-077 shadow lane (observe-only): what the verdict WOULD be if
        # bound to the learned composite — never substituted for the LLM's.
        from backend.shared.pipeline.verdict_shadow import log_verdict_shadow
        log_verdict_shadow(
            ticker=ticker,
            composite=composite,
            llm_verdict=report.verdict,
            llm_final_score=report.final_score,
            learned_weights_used=bool(learned_weights),
        )
        return report
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/shared/test_verdict_shadow.py -v` then `python -m pytest tests/unit -k "aggregator" -q`
Expected: PASS (aggregator unit tests unchanged — the logger degrades silently under mocks).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(wave-g): verdict shadow lane — threshold(composite) logged beside LLM verdict (AUD-077)"
```

---

### Task 3: AUD-041 — news context actually date-filtered

**Files:**
- Modify: `services/data/fetchers/news.py` (`get_news_context` :274-321)
- Test: `tests/unit/test_news_context_window.py`

**Interfaces:**
- `get_news_context(ticker: str, max_articles: int = 5, window_days: int = 3) -> str` — new keyword arg with default; articles whose `_normalize_date` output parses to an ISO date OLDER than `window_days` calendar days are dropped; articles with unparseable/unknown dates are dropped too (an undated article cannot be correlated with the trading day under review — same rule the chat prompt already enforces). Header line becomes `"Recent news for {ticker} (last {window_days} days):"`. All-filtered → `"Market context unavailable."`. 3-day default covers the Monday-reviews-Friday weekend gap honestly (the old label claimed 48h and delivered April).

- [ ] **Step 1: Write the failing test**

```python
"""tests/unit/test_news_context_window.py — AUD-041 date-filtered RL news context."""
from datetime import date, timedelta

import services.data.fetchers.news as news


def _patch_results(monkeypatch, results):
    monkeypatch.setattr(news, "search_serper_news", lambda *a, **k: results)
    monkeypatch.setattr(news._s if hasattr(news, "_s") else news, "SERPER_API_KEY", "k", raising=False)


def test_old_articles_are_dropped(monkeypatch):
    today = date.today().isoformat()
    stale = (date.today() - timedelta(days=86)).isoformat()
    _patch_results(monkeypatch, [
        {"date": today, "title": "Fresh headline", "snippet": "s", "source": "ET"},
        {"date": stale, "title": "April ghost", "snippet": "s", "source": "ET"},
    ])
    ctx = news.get_news_context("TATAELXSI")
    assert "Fresh headline" in ctx
    assert "April ghost" not in ctx


def test_undated_articles_are_dropped(monkeypatch):
    _patch_results(monkeypatch, [
        {"date": "", "title": "Undated thing", "snippet": "s", "source": "ET"},
    ])
    assert news.get_news_context("TCS") == "Market context unavailable."


def test_all_stale_returns_unavailable(monkeypatch):
    stale = (date.today() - timedelta(days=30)).isoformat()
    _patch_results(monkeypatch, [
        {"date": stale, "title": "Old", "snippet": "s", "source": "ET"},
    ])
    assert news.get_news_context("TCS") == "Market context unavailable."


def test_window_label_is_honest(monkeypatch):
    today = date.today().isoformat()
    _patch_results(monkeypatch, [
        {"date": today, "title": "Now", "snippet": "s", "source": "ET"},
    ])
    ctx = news.get_news_context("TCS", window_days=3)
    assert "last 3 days" in ctx
    assert "48h" not in ctx


def test_relative_dates_still_work(monkeypatch):
    _patch_results(monkeypatch, [
        {"date": "2 hours ago", "title": "Breaking", "snippet": "s", "source": "ET"},
        {"date": "2 weeks ago", "title": "Stale relative", "snippet": "s", "source": "ET"},
    ])
    ctx = news.get_news_context("INFY")
    assert "Breaking" in ctx
    assert "Stale relative" not in ctx
```

Note: `_patch_results` must match how `get_news_context` reads the key — it imports `settings as _s` inside the function; patch `backend.shared.config.settings.SERPER_API_KEY` via monkeypatch.setattr on that module instead if the helper above doesn't bite. Verify at execution time and adjust the fixture, keeping the five behavioral assertions exactly as written.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_news_context_window.py -v`
Expected: `test_old_articles_are_dropped`, `test_undated_articles_are_dropped`, `test_all_stale_returns_unavailable`, `test_window_label_is_honest`, `test_relative_dates_still_work` FAIL (no filtering today).

- [ ] **Step 3: Implement**

In `services/data/fetchers/news.py`, replace the body of `get_news_context` from the header line down:

```python
def get_news_context(ticker: str, max_articles: int = 5, window_days: int = 3) -> str:
    """
    Fetch recent news for a specific NSE ticker for the RL daily review.

    Called by daily_review.py to populate FeedbackAgentInput.market_context_today.
    Uses Serper /news with a company-specific query and geo=in for India.

    AUD-041: articles are FILTERED to the last `window_days` calendar days
    (3 covers the Monday-reviews-Friday weekend gap); dated-but-old and
    undated articles are dropped — the old "(last 48h context)" label carried
    months-old stories straight into the RL training signal.

    Returns a formatted string with [Date: YYYY-MM-DD] tags so FeedbackAgent
    can correlate articles with the trading day under review.
    Returns "Market context unavailable." on failure — never raises.
    """
    try:
        from backend.shared.config import settings as _s
        key = _s.SERPER_API_KEY
        if not key:
            logger.debug("[news] get_news_context: no Serper key configured")
            return "Market context unavailable."

        query   = f"{ticker} NSE India company news results"
        results = search_serper_news(query, n=max_articles, api_key=key, geo="in")

        if not results:
            logger.debug("[news] get_news_context: no results for %s", ticker)
            return "Market context unavailable."

        cutoff = date.today() - timedelta(days=window_days)
        lines = [f"Recent news for {ticker} (last {window_days} days):"]
        dropped = 0
        for r in results[:max_articles]:
            date_str = _normalize_date(r.get("date", ""))
            try:
                article_date = date.fromisoformat(date_str)
            except ValueError:
                dropped += 1        # undated/unparseable — can't correlate
                continue
            if article_date < cutoff:
                dropped += 1        # AUD-041: the April-ghost class
                continue
            title   = r.get("title", "").strip()
            snippet = r.get("snippet", "").strip()
            source  = r.get("source", "")
            if title:
                lines.append(
                    f"• [Date: {date_str}] [{source}] {title}"
                    + (f": {snippet}" if snippet else "")
                )
        if dropped:
            logger.debug("[news] get_news_context: dropped %d stale/undated articles for %s",
                         dropped, ticker)

        return "\n".join(lines) if len(lines) > 1 else "Market context unavailable."

    except Exception as exc:
        logger.warning("[news] get_news_context failed for %s: %s", ticker, exc)
        return "Market context unavailable."
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_news_context_window.py -v` then `python -m pytest tests/unit -k "news" -q`
Expected: PASS; existing news tests unaffected (they exercise `fetch_news_context`/search fns, not this filter).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(wave-g): date-filter RL news context to an honest window (AUD-041)"
```

---

### Task 4: Full suite, ledger, merge, push, verify

- [ ] **Step 1: Full suite** — `python -m pytest tests/ -q`; fail set must equal the known baseline.
- [ ] **Step 2: LEDGER** — AUD-060 → FIXED-FORWARD (shadow-data note), AUD-077 → SHADOW LANE LIVE (decision + 2-week analysis date ~2026-07-31, gates 098), AUD-041 → FIXED. Append a Wave G section (style of Waves A–F). No prod specifics.
- [ ] **Step 3: Merge + push** — ff-only to main, delete branch. **Check the clock first: not between 16:25–17:15 IST on a trading day.**
- [ ] **Step 4: Verify deploy + memory** — Railway deploy SUCCESS + clean startup; update `project_tech_audit_program.md`: Wave G shipped, shadow-data ripe ~2026-07-31, AUD-098 + hard-bind decision then; AUD-066 (credit-assignment upgrade) stays gated on the same data.
