# RL Pipeline Redesign — Efficiency & Accuracy Improvements

**Date:** 2026-05-17
**Status:** Approved (researcher + reviewer consensus, one loop)
**Scope:** Optimisations to the existing RL daily-review and monthly-forecast pipeline. No new subsystems. No new schemas unless noted.

---

## Background

StockAgent's RL pipeline (daily_review + generate_forecast) was hitting Tavily's 1,000/month free tier in the first two months of live operation. Investigation revealed the root cause: `services/data/context/builder.py` calls `fetch_tavily_context(max_queries=2)` at three points per agent run, and the daily review re-runs the full 9-agent orchestrator every single day — including on days where the prediction was correct and the error was small.

A researcher agent performed a phase-by-phase audit of `docs/RL_DESIGN.md`. A reviewer agent then filtered the suggestions for over-engineering, wrong timing, and complexity vs benefit. The final shortlist below is what passed both.

**Design principle (from reviewer):**
> The 3 highest-confidence wins are bug fixes, not new mechanisms. The RL loop already has 8 numbered steps, 4 persisted JSON schemas, a 3-tier ledger, thesis reviewer, conviction tracker, regime detector, seasonal validator, and prompt enhancer. Every new abstraction makes the next refactor harder. Bias toward deletions and one-line constants.

---

## What Is NOT Changing

- RL schema files (`prediction_envelope`, `daily_feedback_log`, `weight_memory`, `learning_ledger`) — no field additions except where noted
- Agent pipeline structure (9 agents, parallel dispatch)
- WeightAdapter mechanisms A/B/C — only the hit-rate step function stays as-is (sigmoid rejected as over-engineering)
- Regime multiplier table and ephemeral-only application
- LearningLedger 3-tier propagation structure
- SeasonalCalendar seeds and YAML format
- ThesisReviewer trigger conditions (structural, not frequency — ATR-relative threshold replaces flat %)

---

## Ship Now — 9 Changes

### 1. Bug Fix: Cross-Cycle Historical Average in PriceInterpolator

**File:** `core/intelligence/rl/algorithms/price_interpolator.py`

**Problem:** `compute_historical_avg_return()` calls `store.load_feedback_log(store.current_cycle_id())`. At month-start, the current cycle's log is empty by definition — so `hist_avg` is always `None` for the very call that needs it most. The LLM-calibrated profile is therefore calibrating without its most valuable input for the first 30 days of every new cycle.

**Fix:** Add `store.load_recent_feedback_entries(n_cycles=6)` that aggregates the last 6 completed cycles' logs. Pass the combined entries to `compute_historical_avg_return`. The function already supports a list of entries — this is purely a call-site change.

**Impact:** accuracy=HIGH (removes a silent always-None bug in the primary calibration signal), effort=SMALL, risk=LOW

---

### 2. Bug Fix: Conviction Streak RSI Proxy

**File:** `core/intelligence/rl/conviction/tracker.py`

**Problem:** `compute_rsi_amplifier()` uses `todays_agent_scores.get("pattern_analysis", 0.5)` as an RSI proxy with thresholds 0.40 / 0.60. `pattern_analysis.overall_score` is a composite of MACD + Bollinger + RSI + Fibonacci + volume — not RSI. The thresholds 0.40/0.60 have no relationship to actual RSI overbought/oversold zones.

**Fix:** Thread `regime_snapshot.sector_rsi` (computed at Step 0, line 318 of `daily_review.py`, already a local variable) into `compute_final_reversion_prior` as a new optional parameter. Use canonical thresholds inside `conviction/tracker.py`:
- Amplify when `verdict == "BUY" AND sector_rsi > 70`
- Amplify when `verdict in ("SELL", "STRONG SELL") AND sector_rsi < 30`

Two-point change: add `sector_rsi: float = 50.0` to `compute_final_reversion_prior` signature, pass it from `daily_review.py:719`. No new data fetches — RSI is already computed.

**Impact:** accuracy=MEDIUM (removes a conceptual bug in a signal used for every streak ≥ 8 days), effort=SMALL, risk=LOW

---

### 3. Early-Exit Daily Review on Correct + Small-Error Days

**File:** `core/intelligence/rl/workflows/daily_review.py`

**Problem:** `_run_todays_agent_scores()` re-invokes the full 9-agent orchestrator every trading day, including days where `direction_correct=True` AND `|price_error_pct| < 0.5%`. On those days, WeightAdapter takes essentially zero action (no boost, no penalty, no bias blame). The fallback path — using `predicted_agent_scores` when the orchestrator fails (lines 408-413) — already handles this case correctly.

**Fix:** Add an early-exit guard before the orchestrator call:

```python
# In daily_review.py, before _run_todays_agent_scores()
if direction_correct and abs(price_error_pct) < settings.RL_AGENT_RERUN_THRESHOLD_PCT:
    todays_scores = today_forecast.predicted_agent_scores
else:
    todays_scores = await _run_todays_agent_scores(ticker, sector)
```

`RL_AGENT_RERUN_THRESHOLD_PCT` defaults to `0.5` — add to `settings/base.py`.

**Impact:** cost=HIGH (eliminates ~60-70% of daily orchestrator LLM calls), latency=HIGH (orchestrator is the dominant wall-time consumer in daily review), accuracy=LOW change (WeightAdapter does nothing different on these days), effort=SMALL, risk=LOW

---

### 4. Tavily + Sector Context Cache (One Decorator)

**File:** `services/clients/tavily_fetcher.py`, `services/data/context/builder.py`

**Problem:** `fetch_tavily_context()` fires at 3 call sites per orchestrator run (lines 231, 528, 618 of `builder.py`). The content — policy PDFs, earnings transcripts, MNRE auction docs — does not change within a month. With 8 tickers × 6 Tavily calls × 22 trading days = 1,056 calls/month, already over the 1,000 free-tier limit. Additionally, same-sector Serper/Tavily calls (e.g. HDFCBANK and SBIN both searching "RBI policy news" on the same day) are duplicated.

**Fix:** Add a disk-backed LRU cache wrapper around `fetch_tavily_context`:

```python
# In tavily_fetcher.py
@disk_cache(key=lambda queries, **kw: (tuple(queries), date.today().strftime("%Y-%m")))
def fetch_tavily_context(queries, max_queries=2, ...):
    ...
```

Cache key: `(sorted_queries_tuple, YYYY-MM)` — expires monthly by design (same month = same content). Write-through to `data/predictions/{sector}/tavily_cache/{YYYY-MM}/{hash}.json`. No `runtime_mode` flag, no schema change, no new abstraction threading through every agent.

**Effect on call count:**
```
Before: 8 tickers × 3 sites × 2 queries × 22 days = 1,056/month
After:  8 tickers × 3 sites × 2 queries × 1 (month-start populates) = 48/month
```

Same decorator naturally deduplicates same-sector calls (HDFCBANK + SBIN asking for identical RBI policy queries → one cache hit).

**Impact:** cost=HIGH (drops Tavily 96%), latency=HIGH (Tavily calls are 2-6s each; removes them from daily review hot path), effort=SMALL-MEDIUM, risk=LOW

---

### 5. LLM Cost Telemetry

**File:** `services/clients/llm_client.py` (thin wrapper)

**Problem:** The system makes between 9 and 30+ LLM calls per ticker per day across FeedbackAgent, ThesisReviewer, PriceInterpolator, and the 9-agent re-run. There is no aggregate cost recording. It is impossible to verify whether any of the other changes in this spec are actually reducing costs.

**Fix:** Wrap `get_async_llm_client()` and `get_llm_client()` with a thin instrumentor that appends one JSON line per call to `outputs/llm_log/{YYYY-MM-DD}.jsonl`:

```json
{"ts": "2026-05-17T16:32:01Z", "ticker": "MARUTI", "caller": "FeedbackAgent", "model": "qwen/qwen-2.5-72b-instruct", "input_tokens": 1420, "output_tokens": 380, "latency_ms": 2341, "success": true}
```

Add a daily rollup endpoint `GET /scheduler/cost-summary?date=YYYY-MM-DD` that sums tokens and estimates USD cost at current OpenRouter pricing.

**Impact:** cost=HIGH (you cannot optimise what you cannot see), effort=SMALL, risk=LOW

---

### 6. Seasonal Validation → Month-End Only

**File:** `core/intelligence/rl/workflows/daily_review.py` (Step 9), new file `core/intelligence/rl/workflows/month_end_validation.py`

**Problem:** Step 9 of daily_review runs `SeasonalValidator.validate_pattern()` for every active seasonal seed, every single day the stock is in a seasonal period. Validation scans the full feedback log per pattern — O(active_seeds × log_size). In October/November (budget + Diwali seasons), multiple patterns are active simultaneously.

**Fix:** Remove Step 9 from `daily_review.py`. Create `month_end_validation.py` that runs on the last trading day of each cycle, invoked from the scheduler after the monthly review completes. 1-day lag in seed invalidation is harmless — a lesson marked `still_valid=False` one day later changes nothing material.

**Impact:** latency=MEDIUM (removes O(N²) work from daily hot path on heavy seasonal days), accuracy=NONE change (1-day validation lag is harmless), effort=SMALL, risk=LOW

---

### 7. ATR-Relative ThesisReviewer Threshold

**File:** `core/intelligence/rl/agents/thesis_reviewer.py`

**Problem:** `should_trigger_review()` fires when `abs(price_error_pct) > 2.0` — a flat threshold for all stocks. For HDFCBANK (ATR ~0.8%), a 2% miss is a 2.5-sigma event. For ADANIGREEN (ATR ~3.5%), a 2% miss is sub-1-sigma noise. Result: thesis review fires constantly on volatile stocks (wasting LLM tokens) and under-fires on stable stocks (missing real thesis breaks).

**Fix:** Replace flat threshold with ATR-relative threshold computed inline:

```python
def should_trigger_review(price_error_pct: float, ticker: str, direction_correct: bool, miss_type: str) -> bool:
    atr_pct = _compute_atr_pct(ticker)  # yfinance 14-day ATR / price, same fn as generate_forecast
    threshold = max(1.5, 1.5 * atr_pct)
    size_trigger = abs(price_error_pct) > threshold
    structural_trigger = not direction_correct and miss_type in {"direction_flip", "model_bias"}
    return size_trigger or structural_trigger
```

`_compute_atr_pct` handles new stocks gracefully: yfinance returns OHLCV from day 1 of NSE listing; `max(1.5, ...)` floor prevents 0% threshold if ATR is unavailable.

No schema change — ATR is computed fresh, not stored.

**Impact:** accuracy=MEDIUM (right-sizes a scarce review mechanism), cost=MEDIUM (fewer noise calls on volatile tickers), effort=SMALL, risk=LOW

---

### 8. Lesson Scope Downgrade (Stale Cleanup)

**File:** `core/intelligence/rl/stores/ledger_propagator.py`

**Problem:** Scope upgrades are one-way and never re-evaluated. A lesson once promoted to `market_wide` stays there forever, polluting the Tier 3 FeedbackAgent prompt even if the pattern hasn't fired in 6 months and was confirmed by only one ticker.

**Fix:** Add `downgrade_stale_lessons(ledger_path, staleness_days=30)` called from the weekly scheduler job:

```python
for lesson in ledger.lessons:
    if lesson.scope == "market_wide" and lesson.contributing_tickers <= 1:
        days_inactive = (today - lesson.last_seen).days
        if days_inactive > staleness_days:
            lesson.scope = "sector_wide"  # one tier down
    elif lesson.scope == "sector_wide" and lesson.still_valid:
        days_inactive = (today - lesson.last_seen).days
        if days_inactive > staleness_days * 2:  # 60 days for sector-wide
            lesson.still_valid = False
```

Lessons resurface naturally when patterns repeat.

**Impact:** accuracy=MEDIUM (cleaner Tier 2/3 prompt context), cost=LOW (smaller prompts), effort=SMALL, risk=LOW

---

### 9. ThesisReviewer Calibration Telemetry

**File:** `core/intelligence/rl/agents/thesis_reviewer.py`

**Problem:** `horizon_confidence_multiplier` is chosen by an LLM from guidance lines (0.85, 0.70, 0.50, 0.30). There is no measurement of whether the LLM's chosen multiplier was well-calibrated — i.e. when it returned 0.50 ("thesis fundamentally wrong"), were the next 5-10 days actually worse than when it returned 0.85?

**Fix:** Append one line per thesis review call to `data/predictions/{sector}/{ticker}/thesis_calls.jsonl`:

```json
{"date": "2026-05-17", "ticker": "MARUTI", "multiplier": 0.70, "assumptions_invalidated": ["crude stable ~$82"], "price_error_at_trigger": -2.8}
```

A weekly job fills in `observed_error_next_5d` and `observed_error_next_10d` once those days have passed. No class, no new schema — raw jsonl. After Month 3, surfaces as a simple table in the Analytics page.

**Impact:** accuracy=MEDIUM (closes a feedback gap that would otherwise require manual inspection), cost=LOW, effort=SMALL, risk=LOW

---

## Deferred — Not Now

| What | When to revisit |
|---|---|
| Time-varying `max_total_drift_from_base` (0.15 → ramp to 0.35) | Month 6 — need weight-history data showing the cap is actually constraining good learning |
| Regime detector hysteresis (2-of-3 day rule) | Month 6 — need logged evidence of actual daily regime flapping |
| Bayesian cross-ticker lesson confidence | When cross-ticker lessons exceed 50+ (need volume to justify framing) |
| Empirical decay rates (measured from invalidation history) | Month 4+ |
| FII proxy threshold tightening | With regime hysteresis — tune both together |

---

## Dropped — Rejected by Reviewer

| What | Why dropped |
|---|---|
| Continuous sigmoid for hit-rate boost/penalty | Step function is readable and the dead zone (36-64%) prevents chasing noise. tanh adds complexity with near-zero measurable gain at current data volumes |
| ATR-relative PriceInterpolator path-shape ramp | Same critique. Step function is fine; the LLM profile already adapts to volatility |
| Adaptive bias window weights (rebalance by fullness) | Invisible to outcomes; adds debugging complexity with zero measurable gain |

---

## Files Changed Summary

| File | Change |
|---|---|
| `core/intelligence/rl/algorithms/price_interpolator.py` | Cross-cycle feedback log aggregation |
| `core/intelligence/rl/conviction/tracker.py` | RSI proxy → actual sector_rsi from regime_snapshot |
| `core/intelligence/rl/workflows/daily_review.py` | Early-exit guard + remove Step 9 |
| `core/intelligence/rl/workflows/month_end_validation.py` | New — seasonal validation, moved from daily |
| `core/intelligence/rl/agents/thesis_reviewer.py` | ATR-relative threshold + calibration jsonl append |
| `core/intelligence/rl/stores/ledger_propagator.py` | `downgrade_stale_lessons()` function |
| `services/clients/tavily_fetcher.py` | Disk-backed cache decorator on `fetch_tavily_context` |
| `services/clients/llm_client.py` | Thin cost-telemetry wrapper |
| `core/config/settings/base.py` | `RL_AGENT_RERUN_THRESHOLD_PCT = 0.5` |
| `outputs/llm_log/` | New directory — daily jsonl cost logs |
| `data/predictions/{sector}/tavily_cache/` | New directory — monthly Tavily cache |

---

## Expected Outcomes

| Metric | Before | After |
|---|---|---|
| Tavily calls/month (8 tickers) | ~1,056 (over limit) | ~48 (well under 1,000) |
| Daily orchestrator LLM calls | 9 agents × 8 tickers × 22 days = 1,584 | ~475 (on correct+small-error days, ~70% skipped) |
| Seasonal validation overhead | Daily O(seeds × log) on seasonal days | Monthly batch only |
| ThesisReviewer false-fire rate (volatile tickers) | High (flat 2% threshold) | Calibrated to ticker ATR |
| Historical avg return availability | Always None at month-start | Non-None from Month 2 |
