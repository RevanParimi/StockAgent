# RL Design — Adaptive Prediction Loop

> Complete reference for the self-learning RL feedback system.
> Covers: 4 JSON memory files, full daily loop (Steps 0–9), month-start forecast,
> all static formulas & multipliers, LLM contracts, schemas, and static-vs-LLM boundary.
> Updated: 2026-05-19 · Phases 5 + 6 + Evolution P1–P5 complete + 8 optimisations shipped.

---

## Recent Optimisations (2026-05-17)

Eight improvements shipped. Together they cut Tavily calls by 96%, eliminate ~70% of
daily LLM calls, and fix two silent bugs.

| # | Change | File | Impact |
|---|---|---|---|
| 1 | **Bug fix:** `compute_historical_avg_return` now reads last 6 completed cycles (was always reading current month = empty) | `price_interpolator.py`, `prediction_store.py`, `generate_forecast.py` | PriceInterpolator now gets real calibration from Month 2 |
| 2 | **Bug fix:** Conviction streak RSI proxy now uses actual `regime_snapshot.sector_rsi` with 70/30 thresholds (was using `pattern_analysis.overall_score` with made-up 0.40/0.60 thresholds) | `conviction/tracker.py`, `daily_review.py` | Accurate overbought/oversold detection |
| 3 | **Early-exit:** Daily review skips full 9-agent orchestrator when `direction_correct AND \|error\| < RL_AGENT_RERUN_THRESHOLD_PCT (0.5%)` | `daily_review.py`, `settings/base.py` | ~70% reduction in daily LLM calls |
| 4 | **Tavily cache:** `fetch_tavily_context` writes results to `data/tavily_cache/{YYYY-MM}/{hash}.txt` on first call; reads from disk for the rest of the month | `tavily_fetcher.py` | 1,056 → 48 Tavily calls/month |
| 5 | **LLM telemetry:** Every LLM call appends a JSON line to `outputs/llm_log/{date}.jsonl` (caller, model, tokens, latency, success) | `llm_client.py`, `feedback_agent.py` | Cost visibility — can now measure all savings |
| 6 | **Seasonal validation → month-end:** Step 9 of daily review now runs only on the last trading day of each month | `daily_review.py`, new `month_end_validation.py` | Removes O(seeds×log) from daily hot path |
| 7 | **ATR-relative thesis threshold:** `ThesisReviewer.should_review` uses `max(1.5, 1.5 × atr_pct)` instead of flat 2%. Also appends calibration jsonl per call | `thesis_reviewer.py` | Right-sizes reviews: HDFCBANK threshold 1.5%, ADANIGREEN 5.25% |
| 8 | **Lesson scope downgrade:** Weekly cron downgrades stale single-ticker `market_wide` lessons to `sector_wide` after 30 days inactive | `ledger_propagator.py`, `scheduler.py` | Cleaner Tier 3 FeedbackAgent prompt |

**Settings change:** All algorithm thresholds and RL constants are now plain Python constants
in `settings/base.py` (no `os.getenv`). Only API keys, URLs, and cron schedules use `os.getenv`.
The `getattr(settings, "X", default)` anti-pattern has been removed — all settings are now
accessed directly as `settings.X`.

---

---

## 1. System Purpose

StockAgent maintains per-ticker persistent memory across months. Every prediction is written down.
Every miss is root-caused and used to update agent credibility weights. After 6 months the system
has a proprietary rulebook for how each specific stock responds to specific real-world events.

```
Month 1:  Forecasts from config defaults + pre-seeded seasonal patterns
Month 3:  Weights earned from 60 days of real accuracy data
Month 6:  Lessons accumulated, seasonal seeds validated, cross-ticker sector patterns active
Month 12: Proprietary calendar + ledger; miss rate on known patterns approaches near-zero
```

---

## 2. Architecture Overview

```
MONTH START (1st trading day)
  generate_forecast.py
    ├── Load WeightMemory (or bootstrap from base weights)
    ├── SeasonalCalendar → seasonal context per day         [STATIC: YAML + ledger]
    ├── PromptEnhancer   → extra search queries per agent   [STATIC: template map]
    ├── Run N-agent pipeline via sector orchestrator        [LLM: agents]
    ├── price_interpolator → 30-day linear price path       [STATIC: formula]
    ├── confidence_decay  → 0.5% per day horizon decay      [STATIC: formula]
    └── Save PredictionEnvelope

DAILY (weekdays 4:30pm IST / 11:00 UTC)
  daily_review.py
    ├── Step 0   RegimeDetector   → classify market regime  [STATIC: VIX/FII/RSI]
    ├── Step 1   Load today's forecast from PredictionEnvelope
    ├── Step 2   Fetch actual close via yfinance
    ├── Step 3   Compute error metrics                      [STATIC: formulas]
    ├── Step 4   FeedbackAgent    → miss analysis + lessons [LLM: qwen, temp=0.3]
    │    ├── Inject streak warning if ConvictionStreak ≥ 8 [STATIC: threshold]
    │    ├── Inject regime narrative (non-NORMAL only)      [STATIC: assembled]
    │    └── Inject tiered lessons summary (TIER 1/2/3)    [STATIC: assembled]
    ├── Step 5   WeightAdapter    → update weight_memory    [STATIC: deterministic]
    ├── Step 5.5 Apply regime multipliers → ephemeral eff. weights [STATIC: NOT persisted]
    ├── Step 6   LearningLedger  → merge lessons + propagate (P2) [STATIC: blend formula]
    ├── Step 6.5 ConvictionTracker → update streak + reversion_prior [STATIC: formula]
    ├── Step 7   Revise remaining forecasts                 [STATIC + eff. weights]
    ├── Step 8   Append FeedbackEntry to daily_feedback_log
    └── Step 9   SeasonalValidator → update seed validity  [STATIC: state machine]
```

**Key invariant:** Regime multipliers (Step 5.5) are ephemeral — applied per-day, NEVER written to `weight_memory.json`. Learned weights drift slowly; regime multipliers are daily overlays only.

---

## 3. The 4 Persistent JSON Memory Files

```
data/predictions/
  {sector}/
    _shared_ledger.json          ← scope=sector_wide lessons (all tickers in sector) [NEW P2]
  _market_ledger.json             ← scope=market_wide (all sectors) [NEW P2]
  {sector}/{TICKER}/
    {TICKER}_{YYYY-MM}_prediction_envelope.json   ← monthly, archived each cycle
    {TICKER}_{YYYY-MM}_daily_feedback_log.json    ← monthly, archived each cycle
    {TICKER}_{YYYY-MM}_prompt_enhancements.json   ← monthly, per-cycle [NEW P4]
    {TICKER}_agent_weight_memory.json             ← PERMANENT across cycles
    {TICKER}_learning_ledger.json                 ← PERMANENT across cycles
```

### 3.1 `prediction_envelope.json` — Living 30-day Forecast

```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-04",
  "sector": "automobile",
  "generated_at": "2026-04-08",
  "base_close": 10500.0,
  "weight_version_used": 3,
  "conviction_streak": {
    "current_verdict": "BUY",
    "streak_days": 5,
    "streak_start_date": "2026-04-09",
    "max_streak_seen": 8,
    "reversion_prior": 0.025
  },
  // NEW — per-agent catalyst snapshot at forecast time (all 5 fields are optional, default {})
  "agent_predictions": {
    "sales_demand": {
      "bull_case_if": "FADA dispatch +12% YoY if rural recovery holds",
      "bear_case_if": "Crude >$90 compresses margin 100-150bps",
      "ticker_vs_peers": "MARUTI dispatch +8% vs TATA -2% this month",
      "what_changed": "FII inflow +₹2,000Cr; dealer inventory down 3 days",
      "data_confidence": 0.82
    }
  },
  "daily_forecasts": [{
    "day": 1,
    "date": "2026-04-09",
    "predicted_close": 10580.0,
    "predicted_change_pct": 0.76,
    "predicted_verdict": "BUY",
    "predicted_agent_scores": {
      "sales_demand": 0.72, "fundamentals": 0.68, "pattern_analysis": 0.65,
      "sentiment": 0.70, "risk_macro": 0.55
    },
    "confidence": 0.71,
    "key_assumptions": ["crude stable ~$82", "FADA dispatch +6% MoM"],
    "revised": false,
    "revision_count": 0,
    "predicted_agent_catalysts": {
      "sales_demand": {"bull_case_if": "FADA +12%", "data_confidence": 0.7},
      "risk_macro": {"bear_case_if": "Crude >$90", "data_confidence": 0.9}
    }
  }]
}
```

### 3.2 `daily_feedback_log.json` — Miss Diary

```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-04",
  "sector": "automobile",
  "entries": [{
    "day": 1,
    "date": "2026-04-09",
    "predicted_close": 10580.0,
    "actual_close": 10430.0,
    "price_error_pct": -1.42,
    "direction_correct": false,
    "miss_analysis": {
      "primary_miss_agent": "risk_macro",
      "miss_type": "model_bias",
      "missed_factors": ["RBI rate hold surprise", "FII single-day outflow ₹2200Cr"],
      "over_weighted_factors": ["FADA dispatch optimism — market ignored it on policy day"],
      "agent_score_drift": {"sales_demand": 0.04, "risk_macro": -0.18}
    },
    "timing": {
      "predicted_peak_day": 7,
      "actual_move_start_day": 4,
      "lag_days": -3,
      "assessment": "early"
    },
    "revised_context": {
      "headline": "RBI policy day suppressed demand signals",
      "risks_next_7_days": ["RBI follow-through commentary", "FII positioning"],
      "catalysts_next_7_days": ["FADA data release in 5 days"],
      "watch_signals": ["INR past 84", "crude past $85"],
      "horizon_confidence_adjustment": -0.05
    },
    "lessons_generated": ["L003"],
    "weight_adjustment_applied": "v4",
    "predicted_catalysts_snapshot": {
      "sales_demand": {"bull_case_if": "FADA +12%", "data_confidence": 0.75},
      "risk_macro": {"bear_case_if": "Crude >$90", "data_confidence": 0.9}
    }
  }]
}
```

### 3.3 `agent_weight_memory.json` — Earned Credibility

```json
{
  "ticker": "MARUTI",
  "sector": "automobile",
  "last_updated": "2026-04-15",
  "weight_version": 4,
  "current_weights": {
    "sales_demand": 0.22, "fundamentals": 0.24, "pattern_analysis": 0.18,
    "sentiment": 0.14, "risk_macro": 0.22
  },
  "base_weights": {
    "sales_demand": 0.25, "fundamentals": 0.20, "pattern_analysis": 0.20,
    "sentiment": 0.15, "risk_macro": 0.20
  },
  "adjustment_bounds": { "max_single_step": 0.05, "max_total_drift_from_base": 0.15 },
  "agent_accuracy": {
    "risk_macro": {"direction_hits": 6, "total": 7, "avg_error": 0.03}
  },
  "weight_history": [{
    "version": 4, "date": "2026-04-15",
    "weights": {"risk_macro": 0.22, "...": "..."},
    "reason": "risk_macro hit 6/7 directions correctly; bumped +0.02. sales_demand over-optimistic 4/7; trimmed -0.03"
  }]
}
```

### 3.4 `learning_ledger.json` — Pattern Knowledge

```json
{
  "ticker": "MARUTI",
  "sector": "automobile",
  "last_updated": "2026-04-15",
  "confidence_decay_rate": 0.02,
  "lessons": [{
    "lesson_id": "L001",
    "date_learned": "2026-04-10",
    "last_seen": "2026-04-15",
    "category": "macro",
    "scope": "sector_wide",
    "pattern": "RBI_policy_day",
    "observation": "On RBI policy announcement days, risk_macro score drop >0.15 predicts actual direction in 80% of cases",
    "rule": "Boost risk_macro weight by +0.05 when RBI event is detected in market context",
    "confidence": 0.80,
    "occurrences": 3,
    "still_valid": true,
    "contributing_tickers": ["MARUTI", "TATAMOTORS"]
  }],
  "miss_counter": {
    "RBI_policy_surprise": 3, "FII_outflow_spike": 5, "crude_oil_spot_price": 4
  }
}
```

---

## 4. Step-by-Step Daily Review Flow

### Step 0 — Regime Detection *(STATIC — no LLM)*

```
RegimeDetector.detect(as_of_date, sector) → RegimeSnapshot
  Signal 1: India VIX  ← yfinance ^INDIAVIX  (fallback: 17.0)
  Signal 2: FII Proxy  ← Nifty 50 (^NSEI) 5-day momentum %  (fallback: 0.0)
  Signal 3: Sector RSI ← sector index OHLCV via Wilder EWM RSI(14)  (fallback: 50.0)
```

**Sector RSI tickers:**

| Sector | Ticker |
|---|---|
| automobile | `^CNXAUTO` |
| banking_bfsi | `^NSEBANK` |
| it_sector | `^CNXIT` |
| renewable_energy | `^CNXENERGY` |
| fallback | `^NSEI` |

**Thresholds (all STATIC constants in settings.py):**

| Constant | Value |
|---|---|
| `VIX_VOLATILE_THRESHOLD` | 22.0 |
| `VIX_LOW_VOL_THRESHOLD` | 14.0 |
| `FII_PROXY_THRESHOLD` | ±1.0% |
| `RSI_OVERBOUGHT` | 70.0 |
| `RSI_OVERSOLD` | 30.0 |

**Classification (first match wins, STATIC priority order):**

| Priority | Regime | Condition |
|---|---|---|
| 1 | `MACRO_CRISIS` | VIX > 22 AND Nifty-5d < −1.0% |
| 2 | `RISK_OFF` | VIX > 22 OR (14≤VIX≤22 AND Nifty-5d < −1.0%) |
| 3 | `MOMENTUM_EXTENDED` | VIX < 14 AND Nifty-5d > +1.0% AND Sector RSI > 70 |
| 4 | `RISK_ON` | VIX < 22 AND Nifty-5d > +1.0% AND Sector RSI < 70 |
| 5 | `OVERSOLD` | Sector RSI < 30 (macro-independent) |
| 6 | `NORMAL` | everything else — base learned weights, no adjustment |

### Steps 1–3 — Load, Fetch, Compute *(STATIC)*

```
Step 1: PredictionStore.load_envelope(cycle_id) → today's forecast row
Step 2: yfinance.download(ticker+".NS", period="5d")["Close"] → actual_close
Step 3: STATIC formulas:
  price_error_pct     = (actual - predicted) / predicted × 100
  direction_correct   = classify_direction(predicted, actual) matches verdict direction
  classify_direction():  UP/DOWN/FLAT based on RL_FLAT_THRESHOLD_PCT = 0.3%
  timing_accuracy:    predicted_peak_day vs actual_move_start_day → lag_days, assessment
```

### Step 4 — FeedbackAgent *(LLM)*

**What the LLM receives:**

```json
{
  "ticker": "MARUTI",
  "sector": "automobile",
  "date": "2026-04-09",
  "predicted_close": 10580.0,
  "actual_close": 10430.0,
  "price_error_pct": -1.42,
  "direction_correct": false,
  "predicted_agent_scores": {"sales_demand": 0.72, "risk_macro": 0.55, "...": "..."},
  "todays_agent_scores": {"sales_demand": 0.76, "risk_macro": 0.37, "...": "..."},
  "market_context_today": "RBI held rates unexpectedly; FII sold ₹2200Cr in auto sector; crude at $84",
  "key_assumptions_that_were_made": ["crude stable ~$82", "no major policy announcement"],
  "existing_lesson_ids": ["L001", "L002"],
  "learning_ledger_summary": "T1: L001: RBI days → trust risk_macro more...\nT2: (sector) ...\nT3: (market) ...",
  "streak_warning": "CONVICTION STREAK ALERT: 12 consecutive BUY days. Reversion prior: 20%...",
  "regime_narrative": "MACRO_CRISIS: VIX=24.1, Nifty fell 1.8% over 5 days. Macro risk dominates."
}
```

**What the LLM returns (must be valid JSON):**

```json
{
  "primary_miss_agent": "risk_macro",
  "miss_type": "model_bias",
  "missed_factors": ["RBI rate hold surprise", "FII outflow ₹2200Cr"],
  "over_weighted_factors": ["FADA dispatch optimism — market ignored it on policy day"],
  "agent_score_drift": {"risk_macro": -0.18, "sales_demand": 0.04},
  "new_lessons": [{
    "category": "macro",
    "scope": "sector_wide",
    "pattern": "RBI_policy_day",
    "observation": "When RBI makes a surprise decision, market ignores all fundamental signals",
    "rule": "On RBI event days, boost risk_macro by +0.05 and discount sales_demand by -0.04",
    "confidence": 0.75
  }],
  "revised_context": {
    "headline": "RBI policy surprise suppressed demand signals",
    "risks_next_7_days": ["RBI follow-through commentary", "FII positioning"],
    "catalysts_next_7_days": ["FADA data release in 5 days"],
    "watch_signals": ["INR past 84"],
    "horizon_confidence_adjustment": -0.05
  }
}
```

**LLM rules (system prompt):**
- Do NOT cite analyst ratings, broker targets, or EPS estimates as missed factors
- Valid missed factors: price action, macro events, sector data, technical signals, fundamentals, policy, commodities, regulatory actions
- Temperature: `0.3` (surfaces non-obvious cross-signal patterns)
- `max_tokens: 1500`, `response_format: {"type": "json_object"}`
- System prompt is dynamically built: `build_system_prompt(sector, agent_names)` — no hardcoded agent names

**Catalyst context (new in 2026-05):**
`FeedbackAgentInput` now carries `predicted_catalysts_by_agent` — the bull/bear cases that were
predicted for each agent at forecast time. The FeedbackAgent system prompt has a dedicated section:

```
[PREDICTED CATALYSTS FROM LAST CYCLE — did they materialise?]
  sales_demand bull case: FADA dispatch +12% YoY if rural recovery holds
  risk_macro bear case: Crude >$90 compresses margin 100-150bps (data_confidence: 0.90)
```

This enables catalyst-level miss attribution: instead of "sales_demand was wrong (unknown why)",
the agent can reason "We predicted FADA +12%, actual came in at +8% — magnitude miss, not direction."
Low-confidence predictions (`data_confidence < 0.5`) are flagged to penalise misses less.

### Step 5 — WeightAdapter *(STATIC — no LLM)*

Three sequential stages, all deterministic. All constants are now in `settings/base.py`
and env-overridable (see settings reference table at end of this doc).

---

**Stage 1 — Accuracy Computation** (`_compute_accuracy`)

Window: last `WEIGHT_ACCURACY_WINDOW = 7` **trading days** (calendar-aware, weekends excluded).

Hit-credit rules per entry:
- `direction_correct = True` → **all agents** get a hit
- `direction_correct = False` AND `miss_type ∈ NO_PENALTY_MISS_TYPES` → **all agents** get a hit (model not at fault)
- `direction_correct = False` AND miss is penalisable → **non-primary agents** get a hit; **primary miss agent** does not

`NO_PENALTY_MISS_TYPES = {"data_gap", "data_stale", "external_shock"}`

Returns: `dict[agent_name → AgentAccuracy(direction_hits, total, avg_error)]`

---

**Stage 2 — Delta Computation** (`_compute_deltas`)

Three independent mechanisms. All deltas accumulate on the same agent before Stage 3 bounds.

#### Mechanism A — Hit-rate boost / penalty (every agent)

```
effective_boost_threshold   = WEIGHT_BOOST_HIT_RATE   + seasonal_delta  (default 0.70)
effective_penalty_threshold = WEIGHT_PENALTY_HIT_RATE + seasonal_delta  (default 0.40)

hit_rate = direction_hits / total   (from Stage 1, last 7 trading days)

if hit_rate >= effective_boost_threshold:    delta += RL_BOOST   (+0.02)
elif hit_rate <= effective_penalty_threshold: delta += RL_PENALTY (-0.03)
else:                                         delta  = 0.0
```

`seasonal_delta` shifts both thresholds by the same amount — raises the bar during easy periods
(festive season), lowers it during structurally hard ones (budget week, earnings blackout).
e.g. `sales_demand: +0.08` during festive → boost only if hit_rate ≥ 0.78 instead of 0.70.

#### Mechanism B — Bias penalty (primary miss agent only, penalisable miss types only)

Replaces the old "2 consecutive days" streak. Uses a **weighted rolling miss rate** across
three trading-day windows so one good day in a bad run doesn't zero out the penalty signal.

```
bias_score = Σ( window_weight × agent_miss_rate_in_window )
             ────────────────────────────────────────────────
                        Σ( window_weight )

Windows and weights (hardcoded in code, not settings):
  5 td  (~1 week)  → weight 0.50   ← recent performance dominates
  10 td (~2 weeks) → weight 0.30
  21 td (~1 month) → weight 0.20

agent_miss_rate_in_window = penalisable_misses_blamed_on_agent / total_penalisable_entries

if bias_score < RL_BIAS_TRIGGER (0.55):
    bias_penalty = 0.0                               ← noise, no penalty

if RL_BIAS_TRIGGER (0.55) ≤ bias_score < RL_BIAS_FULL (0.70):
    scale        = (bias_score − 0.55) / (0.70 − 0.55)    ← linear 0→1
    bias_penalty = RL_MISS_STREAK_PENALTY × scale × miss_type_multiplier

if bias_score ≥ RL_BIAS_FULL (0.70):
    scale        = 1.0                               ← capped at full penalty
    bias_penalty = RL_MISS_STREAK_PENALTY × 1.0 × miss_type_multiplier
```

Worked examples (no seasonal adjustment, miss_type = "direction_flip" → multiplier 1.0):

| bias_score | scale | bias_penalty | what it means |
|---|---|---|---|
| 0.40 | — | 0.000 | occasional miss, ignore |
| 0.55 | 0.00 | 0.000 | just at trigger, no penalty yet |
| 0.625 | 0.50 | −0.025 | consistent underperformer |
| 0.70 | 1.00 | −0.050 | full penalty — badly miscalibrated |
| 0.85 | 1.00 (capped) | −0.050 | full penalty — same cap |

#### Mechanism C — Timing penalty multiplier

Applied to `bias_penalty` when `miss_type = "timing"`. Determines `miss_type_multiplier`:

```
abs_lag = |timing_lag_days|   (actual price peak − predicted peak, in trading days)

if abs_lag ≤ RL_TIMING_FREE_WINDOW (3):     multiplier = 0.00  → no bias penalty
if abs_lag ≤ RL_TIMING_PARTIAL_WINDOW (7):  multiplier = 0.20  → light signal
if abs_lag > RL_TIMING_PARTIAL_WINDOW (7):  multiplier = 0.50  → real timing failure
```

For non-timing miss types, `multiplier = MISS_TYPE_PENALTY_MULTIPLIER[miss_type]`:

| miss_type | multiplier | Rationale |
|---|---|---|
| `direction_flip` | 1.00 | Full penalty — model called direction wrong |
| `model_bias` | 1.00 | Full penalty — systematic miscalibration |
| `magnitude` | 0.25 | Partial — direction right, size wrong |
| `timing` | see tiers above | Depends on lag magnitude |
| `data_gap` | 0.00 | Not model's fault — no data available |
| `data_stale` | 0.00 | Not model's fault — stale input |
| `external_shock` | 0.00 | Not model's fault — unpredictable event |

Final delta for primary miss agent = Mechanism A delta + bias_penalty

---

**Stage 3 — Bound Application + Normalization** (`_apply_deltas`)

```
For each agent:
  1. Clamp delta to ±WEIGHT_MAX_STEP (0.05)           ← largest move in one day
  2. proposed = current_weight + clamped_delta
  3. lo = max(0.0, base_weight − WEIGHT_MAX_DRIFT)     ← floor: base − 0.15
     hi = base_weight + WEIGHT_MAX_DRIFT               ← ceiling: base + 0.15
  4. proposed = clamp(proposed, lo, hi)
  5. Re-normalize all agents: weight /= Σ(all weights) ← always sums to 1.0
```

`WEIGHT_MAX_STEP = 0.05` prevents a single bad day from catastrophically shifting the model.
`WEIGHT_MAX_DRIFT = 0.15` keeps weights within ±15 percentage points of the calibrated base.

### Step 5.5 — Regime Multipliers Applied *(STATIC, EPHEMERAL)*

```
effective_weight[agent] = learned_weight[agent] × regime_multiplier[agent]
                          ────────────────────────────────────────────────
                            Σ(learned_weight[i] × regime_multiplier[i])
```

**Full Regime Multiplier Table:**

| Agent | MACRO_CRISIS | RISK_OFF | NORMAL | RISK_ON | MOMENTUM_EXT | OVERSOLD |
|---|---|---|---|---|---|---|
| risk_macro | **1.40** | 1.20 | 1.00 | 0.90 | 0.85 | 1.10 |
| fundamentals | 0.80 | 0.90 | 1.00 | **1.10** | 1.05 | 1.00 |
| sales_demand | 0.70 | 0.85 | 1.00 | **1.10** | 0.95 | 1.00 |
| sentiment | 0.80 | 0.90 | 1.00 | **1.15** | 0.80 | 0.90 |
| pattern_analysis | 0.90 | 0.95 | 1.00 | 0.95 | **1.20** | **1.30** |
| competitive_intel | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| valuation_catalyst | 0.90 | 0.95 | 1.00 | 1.10 | 1.10 | 1.05 |
| raw_materials | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| policy_regulatory | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

> Values > 1.0 = boost agent influence; < 1.0 = discount. NORMAL = passthrough (all 1.00).

**NOT written to weight_memory.json.** Regime multipliers cannot corrupt long-run accuracy weights.

### Step 6 — Learning Ledger Merge *(STATIC)*

**Lesson routing (write path):**

```
FeedbackAgent output lesson → merge_lessons_into_ledger()
  lesson.scope == "stock_specific"
      └── write to TICKER_learning_ledger.json
  lesson.scope == "sector_wide"
      ├── write to TICKER_learning_ledger.json  (source record)
      └── propagate → SECTOR/_shared_ledger.json
  lesson.scope == "market_wide"
      ├── write to TICKER_learning_ledger.json
      ├── propagate → SECTOR/_shared_ledger.json
      └── propagate → ROOT/_market_ledger.json
```

**Deduplication formula (STATIC):**
```
If same pattern already in shared_ledger:
  new_confidence = 0.70 × existing + 0.30 × incoming
  occurrences += 1
  last_seen = today
  contributing_tickers.append(source_ticker)
Else:
  add as new lesson
```

**Cross-ticker confidence boost (STATIC):**
```
Each NEW ticker that confirms a sector_wide lesson: confidence += 0.05
After 3 independent tickers confirm: lesson marked "validated"
```

**Tiered read for FeedbackAgent context:**

| Tier | Source | Max lessons in prompt |
|---|---|---|
| T1 (most specific) | ticker_learning_ledger.json (stock_specific) | top 6 by eff_confidence |
| T2 (sector) | _shared_ledger.json (sector_wide) | top 3 by eff_confidence |
| T3 (market) | _market_ledger.json (market_wide) | top 2 by eff_confidence |

### Step 6.5 — Conviction Streak *(STATIC)*

**Reversion Prior Formula:**
```
streak_days 0–4  → reversion_prior = 0.00  (normal operation)
streak_days 5–7  → reversion_prior = 0.05  (mild caution)
streak_days 8–10 → reversion_prior = 0.10  (moderate)
streak_days 11–14→ reversion_prior = 0.15  (elevated)
streak_days 15–20→ reversion_prior = 0.20  (high risk)
streak_days ≥21  → reversion_prior = 0.25  (max, capped)

Formula: reversion_prior = min(0.25, max(0, (streak_days - 4) × 0.025))
```

**RSI Divergence Amplifier (STATIC):**
```
Condition A: verdict = "BUY"  AND pattern_analysis.rsi_macd_bb < 0.40
Condition B: verdict = "SELL" AND pattern_analysis.rsi_macd_bb > 0.60
If (streak ≥ 8) AND (A or B):
    final_prior = min(0.30, reversion_prior × 1.5)
```

**Applied to confidence:**
```
adjusted_confidence = base_confidence × (1.0 - reversion_prior × 0.5)
```

**Streak warning injected into FeedbackAgent prompt when streak ≥ 8 (STATIC template):**
```
Explicitly assess: RSI divergence, declining volume on up days,
delivery % drop on price rise, relative underperformance vs sector.
```

### Step 7 — Revise Remaining Forecasts *(STATIC)*

```
For each remaining day in PredictionEnvelope:
  1. Re-run SignalAggregator with effective_weights (learned × regime multiplier)
  2. Apply active lesson rules inline (e.g. RBI day discount from ledger)
  3. Apply seasonal adjustments from SeasonalCalendar.get_context(day.date, ledger)
  4. Apply revised_context.horizon_confidence_adjustment
  5. Apply reversion_prior dampening: confidence × (1 - reversion_prior × 0.5)
  6. Update day.revised = True, day.revision_count += 1
```

### Steps 8–9 — Persist + Validate *(STATIC)*

```
Step 8: PredictionStore.append_feedback_entry(entry, cycle_id)
         Idempotent: replaces existing entry for same date before appending
         Atomic write: .tmp → rename (never corrupts live file)

Step 9: SeasonalValidator.validate_pattern(pattern_id, feedback_log)
         If pattern fired correctly in log → increment reinforced/validated counter
         If pattern did NOT fire ≥3 cycles → still_valid = False → removed from injection
```

---

## 5. Miss Taxonomy — 7 Types

**Who classifies:** LLM (FeedbackAgent). **Who applies penalty:** STATIC WeightAdapter.

| Miss Type | When to use | Penalty multiplier | Agent absolved? |
|---|---|---|---|
| `data_gap` | Data not yet published at forecast time (e.g. FADA releases on 10th, forecast on 5th) | **0.0×** | ✅ Yes |
| `data_stale` | Hardcoded/outdated data used (e.g. RBI repo rate not updated after MPC) | **0.0×** | ✅ Yes |
| `external_shock` | Unpredictable black-swan (circuit breaker, sudden tariff, geopolitical event) | **0.0×** | ✅ Yes |
| `timing` | Direction was correct but move happened earlier/later than predicted | **0.5×** | Partial |
| `magnitude` | Direction correct but size of move was wrong | **0.25×** | Partial |
| `model_bias` | Agent consistently over/under-estimates a specific signal | **1.0×** | ❌ No |
| `direction_flip` | Completely wrong direction, no valid external cause | **1.0×** | ❌ No |

```python
# Defined in core/schemas/feedback.py — SINGLE source of truth
MISS_TYPE_PENALTY_MULTIPLIER = {
    "data_gap": 0.0, "data_stale": 0.0, "external_shock": 0.0,
    "timing": 0.5, "magnitude": 0.25,
    "model_bias": 1.0, "direction_flip": 1.0,
}
NO_PENALTY_MISS_TYPES = frozenset({"data_gap", "data_stale", "external_shock"})
```

---

## 6. Lesson Confidence Decay — Formula *(STATIC)*

```
effective_confidence = stored_confidence × (1 - decay_rate) ^ months_inactive

Default decay_rate = 0.02 per month (configurable on LearningLedger)
Floor = 0.10 — lessons never fully discarded automatically

Example: confidence=0.80, last_seen 6 months ago:
  0.80 × (0.98^6) ≈ 0.71 (shown to LLM as eff_confidence)

Seasonal lessons: decay_exempt = true → no decay applied
```

`active_lessons_summary()` injects `eff_confidence`, not stored confidence, so LLM naturally weights recent patterns higher.

---

## 7. Seasonal Calendar (P1)

Two-layer architecture:

```
Layer 1: Pre-seeded domain knowledge (human-authored YAML, per sector)
         Written once. Never auto-deleted. Can be reinforced or invalidated by RL.

Layer 2: RL-discovered seasonal lessons (auto-generated from FeedbackAgent misses)
         Created when miss_type = seasonal. Reinforces or contradicts Layer 1.
```

**Seed state machine:**

```
SEEDED (confident=0.75, validated_by_rl=false)
    ↓  FeedbackAgent detects same pattern
REINFORCED (confidence += 0.05, occurrences++)
    ↓  ≥2 full cycles confirm
VALIDATED (validated_by_rl = true, confidence locked ≥0.75)
    ↓  ≥3 cycles where pattern does NOT fire
INVALIDATED (still_valid = false, no longer injected)
```

**Seed table — Automobile:**

| ID | Name | Months | Bias | Confidence | agents_affected |
|---|---|---|---|---|---|
| SEA_AUTO_001 | december_model_clearance | Dec | Bearish (margin) | 0.75 | sales_demand −0.08, fundamentals −0.05 |
| SEA_AUTO_002 | navratri_diwali_peak | Oct–Nov | Positive | 0.80 | sales_demand +0.10, sentiment +0.08 |
| SEA_AUTO_003 | shravan_inauspicious | Jul–Aug | Negative | 0.65 | sales_demand −0.07 |
| SEA_AUTO_004 | q4_march_wholesale_push | Mar | Deceptive positive | 0.70 | sales_demand −0.06 (discount FADA wholesale) |
| SEA_AUTO_005 | budget_week_policy_wait | Jan week4–Feb week1 | Cautious | 0.60 | policy_regulatory −0.10, risk_macro −0.08 |
| SEA_AUTO_006 | april_new_year_launch_hype | Apr | Positive sentiment | 0.65 | sentiment +0.06 |

**Seed table — Banking/BFSI:**

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_BFSI_001 | march_year_end_credit_push | Mar | Positive | 0.75 |
| SEA_BFSI_002 | rbi_mpc_meeting_week | Bimonthly | Cautious | 0.80 |
| SEA_BFSI_003 | q1_npa_recognition_risk | Apr | Negative | 0.65 |
| SEA_BFSI_004 | budget_banking_policy | Feb | Positive/Volatile | 0.70 |

**Seed table — IT Sector:**

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_IT_001 | us_tech_earnings_spillover | Jan, Apr, Jul, Oct | Correlated | 0.75 |
| SEA_IT_002 | q1_attrition_cost_peak | Apr–May | Negative margin | 0.65 |
| SEA_IT_003 | us_budget_uncertainty | Sep–Oct | Cautious | 0.70 |
| SEA_IT_004 | inr_weakening_tailwind | Any | Revenue positive | 0.60 |

**Seed table — Renewable Energy:**

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_RE_001 | monsoon_solar_generation_dip | Jun–Sep | Output negative | 0.80 |
| SEA_RE_002 | cop_climate_summit_hype | Oct–Nov | Sentiment positive | 0.65 |
| SEA_RE_003 | year_end_capex_push | Oct–Dec | Order book positive | 0.70 |
| SEA_RE_004 | tariff_revision_q1 | Jan–Feb | Policy risk | 0.60 |

---

## 8. PromptEnhancer — miss_counter → Search Queries (P4)

**When it runs:** Once per month-start in `generate_forecast.py`. Output cached per cycle.

**Logic (STATIC — no LLM):**

```
1. Read miss_counter from LearningLedger
2. Take top_n=3 most frequent missed factors
3. Look up MISS_FACTOR_TO_QUERY_TEMPLATE[factor][agent_name]
4. Save to {TICKER}_{cycle}_prompt_enhancements.json
5. BaseAgent.run() loads enhancement file → appends extra_queries[:2] to base CONTEXT_SEARCH_QUERIES
```

**Miss Factor → Query Template Map (STATIC):**

| Miss Factor | Agent | Query Template |
|---|---|---|
| `FII_outflow_spike` | risk_macro | `{ticker} FII DII net flows provisional {date}` |
| `FII_outflow_spike` | sentiment | `FII selling India equity {month} {year}` |
| `crude_oil_spot_price` | raw_materials | `Brent crude spot price today {date}` |
| `crude_oil_spot_price` | risk_macro | `crude oil impact Indian automobile sector {month}` |
| `RBI_policy_surprise` | risk_macro | `RBI MPC meeting upcoming schedule {year}` |
| `RBI_policy_surprise` | fundamentals | `RBI repo rate decision impact auto loan rates` |
| `INR_depreciation` | risk_macro | `USD INR exchange rate {date}` |
| `INR_depreciation` | raw_materials | `INR depreciation impact import cost automobile {year}` |
| `month_end_inventory_flush` | sales_demand | `{ticker} dealer inventory days channel check {month}` |

**Self-regulating:** If queries successfully find the missing data, miss_count stops growing → factor falls out of top-N next cycle → deprioritized automatically. No manual reset.

---

## 9. Month-Start Forecast Generation

**Price Interpolator (STATIC):**

```
verdict → implied monthly return assumption:
  STRONG BUY: +8% over 30 days
  BUY:        +4%
  NEUTRAL:    ±0%
  SELL:       -4%
  STRONG SELL: -8%

price_delta = base_close × (monthly_return / 30_trading_days)
DailyForecast[day].predicted_close = base_close + price_delta × day
```

**Confidence Decay (STATIC):**

```
decay_per_day ≈ 0.005 (0.5% per day further out)
base_confidence = FinalReport.final_score (from agent pipeline)
DailyForecast[day].confidence = base_close_confidence × (1 - decay_per_day × day)
```

**Envelope builder applies on top:** seasonal agent adjustments from SeasonalCalendar.

---

## 10. All RL Schemas (`core/schemas/feedback.py`)

| Schema | Purpose | Persistent? |
|---|---|---|
| `DailyForecast` | One row in prediction_envelope (predicted_close, verdict, confidence, revised) + `predicted_agent_catalysts` | Per cycle |
| `PredictionEnvelope` | Full 30-day forecast sheet + conviction_streak + `agent_predictions` (catalyst snapshot at forecast time) | Per cycle |
| `ConvictionStreak` | current_verdict, streak_days, reversion_prior (0–0.30) | In envelope |
| `MissAnalysis` | Root cause: primary_miss_agent, miss_type, missed_factors, agent_score_drift | Per day |
| `TimingAccuracy` | predicted_peak_day, actual_move_start_day, lag_days, assessment | Per day |
| `RevisedContext` | headline, risks[], catalysts[], watch_signals[], horizon_confidence_adjustment | Per day |
| `FeedbackEntry` | One day: actual close, miss_analysis, timing, revised_context, lessons_generated + `predicted_catalysts_snapshot` | Per cycle |
| `DailyFeedbackLog` | All FeedbackEntry rows for one cycle | Per cycle |
| `AgentAccuracy` | direction_hits, total, avg_error (rolling stats per agent) | In WeightMemory |
| `WeightHistoryEntry` | Version, date, weights, reason (human-readable explanation) | In WeightMemory |
| `WeightMemory` | current_weights, base_weights, bounds, agent_accuracy, weight_history | **PERMANENT** |
| `Lesson` | pattern, rule, confidence, occurrences, scope, last_seen, contributing_tickers | In ledger |
| `LearningLedger` | lessons[], miss_counter, confidence_decay_rate | **PERMANENT** |
| `RegimeSnapshot` | regime_label, vix_value, fii_proxy, sector_rsi, multipliers, narrative | Ephemeral |
| `FeedbackAgentInput` | Full LLM input: ticker, scores, context, existing_lesson_ids, streak, regime + `predicted_catalysts_by_agent` | Ephemeral |
| `FeedbackAgentOutput` | Full LLM output: miss_type, missed_factors, new_lessons, revised_context | Ephemeral |
| `SeasonalContext` | active_seeds, active_rl_lessons, agent_adjustments, narrative | Ephemeral |

### What RL Currently Sees From Logs

| Signal | Status | Storage location |
|---|---|---|
| `bull_case_if` / `bear_case_if` per agent | ✅ stored in `agent_predictions` + `predicted_agent_catalysts` | `PredictionEnvelope` + `DailyForecast` |
| `data_confidence` per agent | ✅ stored alongside bull/bear; low-confidence penalised less | `PredictionEnvelope.agent_predictions` |
| `what_changed` per agent | ✅ stored in `agent_predictions` per cycle | `PredictionEnvelope.agent_predictions` |
| `predicted_catalysts_by_agent` in FeedbackAgent | ✅ injected for catalyst-level attribution | `FeedbackAgentInput.predicted_catalysts_by_agent` |
| `predicted_catalysts_snapshot` in feedback log | ✅ stored for audit trail alongside `miss_analysis` | `FeedbackEntry.predicted_catalysts_snapshot` |

---

## 11. RL Configuration Reference

| Setting | Default | What it controls |
|---|---|---|
| `PREDICTION_DATA_DIR` | `data/predictions` | Root folder for all JSON memory files |
| `FORECAST_HORIZON_DAYS` | 30 | Trading days to forecast on month-start |
| `WEIGHT_MAX_STEP` | 0.05 | Max weight change per daily step |
| `WEIGHT_MAX_DRIFT` | 0.15 | Max total drift from base weight |
| `WEIGHT_MIN_OBSERVATIONS` | 3 | Days before weight adaptation activates |
| `WEIGHT_ACCURACY_WINDOW` | 7 | Rolling window (days) for hit-rate calc |
| `WEIGHT_BOOST_HIT_RATE` | 0.70 | Hit rate ≥ this → weight boost fires (Mechanism A threshold) |
| `WEIGHT_PENALTY_HIT_RATE` | 0.40 | Hit rate ≤ this → weight penalty fires (Mechanism A threshold) |
| `RL_BOOST` | +0.02 | Delta added when hit_rate ≥ boost threshold (Mechanism A magnitude) |
| `RL_PENALTY` | −0.03 | Delta added when hit_rate ≤ penalty threshold (Mechanism A magnitude) |
| `RL_MISS_STREAK_PENALTY` | −0.05 | Base bias penalty at full bias_score=1.0 (Mechanism B magnitude) |
| `RL_BIAS_TRIGGER` | 0.55 | Weighted rolling miss rate at which bias penalty starts scaling (Mechanism B) |
| `RL_BIAS_FULL` | 0.70 | Weighted rolling miss rate at which full `RL_MISS_STREAK_PENALTY` applies (Mechanism B) |
| `RL_TIMING_FREE_WINDOW` | 3 | Lag ≤ N trading days → 0× timing penalty (within-week noise) (Mechanism C) |
| `RL_TIMING_PARTIAL_WINDOW` | 7 | Lag ≤ N trading days → 0.20× timing penalty; lag > N → 0.50× (Mechanism C) |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Daily review cron (11:00 UTC = 4:30pm IST) |
| `RL_FLAT_THRESHOLD_PCT` | 0.3 | % change threshold for UP/DOWN/FLAT classification |
| `VIX_VOLATILE_THRESHOLD` | 22.0 | VIX above = volatile macro |
| `VIX_LOW_VOL_THRESHOLD` | 14.0 | VIX below = low-vol trending |
| `FII_OUTFLOW_THRESHOLD` | −5000.0 | ₹Cr 5-day net outflow → MACRO_RISK flag |
| `FII_INFLOW_THRESHOLD` | +5000.0 | ₹Cr 5-day net inflow → RISK_ON flag |
| `RSI_OVERBOUGHT` | 70.0 | Sector RSI above = OVERBOUGHT |
| `RSI_OVERSOLD` | 30.0 | Sector RSI below = OVERSOLD |

---

## 12. Scheduler API Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/scheduler/forecast` | Generate monthly prediction envelopes. Optional `?ticker=`. Runs as background task (~2 min/ticker). |
| `POST` | `/scheduler/daily-review` | Run daily RL feedback loop. Optional `?ticker=&date=YYYY-MM-DD`. Requires envelope to exist. |
| `POST` | `/scheduler/backfill` | Catch-up: run daily reviews for all missing trading days this month. Used on fresh deployment. |
| `GET` | `/scheduler/status` | Per-ticker RL state: envelope exists?, feedback entries count, weight version, direction accuracy, weight drifts vs base. |

Auth: `X-Scheduler-Key` header must match `SCHEDULER_KEY` env var (open if not set).

**CLI equivalents:**

```bash
python -m services.scheduler.run_schedule forecast --ticker MARUTI
python -m services.scheduler.run_schedule forecast --sector banking_bfsi --ticker HDFCBANK SBIN
python -m services.scheduler.run_schedule daily-review --ticker MARUTI
python -m services.scheduler.run_schedule daily-review --sector it_sector --ticker TCS --date 2026-04-15
python -m services.scheduler.run_schedule feedback-status --ticker MARUTI
python -m services.scheduler.run_schedule start   # full daemon (all sectors)
```

---

## 13. Startup Self-Heal (Server Lifespan)

Runs on every deployment — makes the system self-bootstrapping:

```
1. Calendar first-run:
   if data/nse_holidays.json doesn't exist → calendar_updater.update_calendar()

2. RL self-heal (background daemon thread — server accepts requests immediately):
   For each SCHEDULER_TICKERS:
     a. If no envelope for current cycle → run generate_forecast() (background, ~2 min/ticker)
     b. Find missing trading-day reviews this month → run_daily_review() for each

3. BackgroundScheduler start (3 jobs):
   Job 1: rl_daily_review    — every weekday 4:30pm IST
   Job 2: rl_monthly_forecast — 1st of each month 9am IST
   Job 3: rl_calendar_update  — Dec 31 11pm IST (writes next year's NSE holidays)
```

**Multi-sector routing (added 2026-05):**
`_daily_review_job()` and `_monthly_forecast_job()` now call `get_active_tickers_with_sector()`
(from `services/api/log_buffer.py`) which returns `[{sym: str, sector: str}]`.
Both jobs pass `sector=` to `run_daily_review()` and `generate_forecast()`.

Result: BFSI, IT, and RE tickers are correctly routed to their sector orchestrators.
Previously all tickers defaulted to "automobile" regardless of `managed_tickers.json` sector field.

Per-ticker timeout: 180 seconds (ThreadPoolExecutor). ThesisReviewer LLM calls cannot block the loop.

---

## Dynamic Ticker Management (No Redeploy Required)

Tickers are managed at runtime via `data/managed_tickers.json` and the following API endpoints.
The scheduler reads this file on every run — changes take effect immediately.

### API Endpoints

| Endpoint | Method | Behaviour |
|---|---|---|
| `/ui/tickers/managed` | GET | List all managed tickers with sector, enabled flag |
| `/ui/tickers/managed` | PUT | Replace entire list (validates sectors) |
| `/ui/tickers/managed/{sym}` | POST | Add ticker: auto-detect sector, validate on NSE, trigger envelope async |
| `/ui/tickers/managed/{sym}` | DELETE | Remove ticker + clean up `data/predictions/{sector}/{sym}/` |
| `/ui/tickers/managed/{sym}/toggle` | PATCH | Enable/disable (preserves all RL data) |
| `/ui/tickers/managed/{sym}/generate-envelope` | POST | Trigger envelope generation immediately (mid-month adds) |

### Sector Auto-Detection
`SectorRegistry.resolve(ticker)` is the source of truth for sector assignment.
If the user provides a sector that conflicts with the registry, the registry wins and a warning is logged.
This prevents wrong orchestrator routing (e.g., HDFCBANK with sector="automobile" would use the wrong agents).

### RL Data Lifecycle

| Action | Effect |
|---|---|
| Add ticker | Envelope generated async in background. RL learning starts that night. |
| Disable ticker | Stops scheduling. All prediction/feedback/ledger data preserved. |
| Delete ticker | Removes from list AND deletes `data/predictions/{sector}/{sym}/` (shutil.rmtree). |

### Valid Sectors
`_get_valid_sectors()` reads from `SectorRegistry.enabled_sectors()` — dynamic, no hardcoding.
Currently enabled: `automobile`, `banking_bfsi`, `it_sector`, `renewable_energy`.

**NSE Calendar:** `nse_calendar.py` loads `data/nse_holidays.json` (dynamic) with hardcoded 2025-2026 fallback. `nse_calendar.reload_holidays()` hot-reloads after `calendar_updater.py` writes new data — no restart needed.

---

## 14. Static vs LLM Boundary — Master Table

| Component | File | Type | Method | Notes |
|---|---|---|---|---|
| `RegimeDetector.detect()` | `core/intelligence/regime/detector.py` | **STATIC** | VIX/FII/RSI threshold rules | No LLM |
| `WeightAdapter.update()` | `core/intelligence/rl/agents/weight_adapter.py` | **STATIC** | 3-stage formula | Fully deterministic |
| `ConvictionTracker` | `core/intelligence/rl/conviction/tracker.py` | **STATIC** | streak formula | min(0.25, (days-4)×0.025) |
| `PromptEnhancer.enhance()` | `core/intelligence/prompt_enhancer/enhancer.py` | **STATIC** | Template dict lookup | miss_counter → query strings |
| `SeasonalCalendar.get_context()` | `core/intelligence/seasonal/calendar.py` | **STATIC** | YAML + ledger read | No LLM |
| `SeasonalValidator.validate_pattern()` | `core/intelligence/seasonal/validator.py` | **STATIC** | State machine | SEEDED → VALIDATED |
| `classify_direction()` | `core/intelligence/rl/agents/feedback_agent.py` | **STATIC** | RL_FLAT_THRESHOLD_PCT=0.3 | UP/DOWN/FLAT |
| `MissType penalty multiplier` | `core/schemas/feedback.py` | **STATIC** | Dict lookup | `MISS_TYPE_PENALTY_MULTIPLIER` |
| `Confidence decay` | `core/schemas/feedback.py` | **STATIC** | `conf×(0.98)^months` | Floor 0.10 |
| `Lesson scope widening` | `core/intelligence/rl/agents/feedback_agent.py` | **STATIC** | Rule-based in merge | stock→sector auto-widen |
| `Cross-ticker confidence boost` | `core/intelligence/rl/stores/ledger_propagator.py` | **STATIC** | +0.05 per new ticker | propagate_to_shared_ledger |
| `Lesson tiered assembly` | `core/intelligence/rl/stores/ledger_propagator.py` | **STATIC** | T1 top-6, T2 top-3, T3 top-2 | For FeedbackAgent context |
| `price_interpolator` | `core/intelligence/rl/algorithms/forecast/` | **STATIC** | verdict→monthly%→linear | Phase 5 extraction target |
| `confidence_decay (forecast)` | `core/intelligence/rl/algorithms/forecast/` | **STATIC** | 0.5%/day formula | Phase 5 extraction target |
| `FeedbackAgent.run()` | `core/intelligence/rl/agents/feedback_agent.py` | **LLM** | qwen, temp=0.3, 1500 tokens | Classifies miss, extracts lessons |
| `merge_lessons_into_ledger()` | `core/intelligence/rl/agents/feedback_agent.py` | **STATIC** | After LLM returns | Dedup, blend, propagate |

---

## 15. Phase 6 — Sector-Agnostic Design

Phase 6 removed all automobile-specific coupling from the RL feedback loop.

| Change | Old (Phase 5) | New (Phase 6) |
|---|---|---|
| System prompt | Static `SYSTEM_PROMPT` string | `build_system_prompt(sector, agent_names)` — dynamic per sector |
| Agent names in prompt | Hardcoded automobile list | Derived from `fb_input.predicted_agent_scores.keys()` at runtime |
| `_run_todays_agent_scores()` | Hardcoded `AutomobileAgentOrchestrator` | Routes by sector: automobile → orchestrator; others → `importlib.import_module(f"graphs.{sector}.graph")` |
| `run_daily_review()` | No sector parameter | Accepts `sector` param; CLI gains `--sector` flag |
| Persistent JSON files | No `sector` field | All files (`WeightMemory`, `LearningLedger`, `PredictionEnvelope`, `DailyFeedbackLog`) carry `sector` field; old files without it default to `"automobile"` via Pydantic |

**Multi-sector CLI (Phase 6+):**

```bash
python -m scripts.daily_review --sector banking_bfsi --ticker HDFCBANK SBIN
python -m scripts.daily_review --sector it_sector --ticker TCS INFY
python -m scripts.daily_review --sector renewable_energy --ticker ADANIGREEN NTPC
python -m scripts.generate_forecast --sector renewable_energy --ticker ADANIGREEN NTPC
```

---

## 16. Known Gaps in Current RL System

| # | Gap | Impact | Status |
|---|---|---|---|
| G1 | Seasonal patterns reactive, not pre-seeded | 1-2yr loss before patterns learned for new sectors | Fixed by P1 (seeds exist for all 4 sectors) |
| G2 | Sector-wide/market-wide lessons not propagated cross-ticker | Knowledge siloed per ticker | Fixed by P2 |
| G3 | No momentum exhaustion / mean-reversion prior | BUY streak has no counter-signal; subscriber trust risk | Fixed by P3 |
| G4 | CONTEXT_SEARCH_QUERIES static; miss_counter ignored | Agents don't search for known blind spots | Fixed by P4 |
| G5 | Weight adaptation is regime-agnostic | Wrong agent amplified during crises | Fixed by P5 |
| G6 | Forecast path is linear interpolation | Constant drift, misrepresents uncertainty | Open — Phase 8 (Monte Carlo) |
| G7 | max_total_drift_from_base fixed at 0.15 forever | Too tight after 6+ months of data | Open — revisit Month 6 with weight-history data |
| G8 | Seasonal lesson decay rate same as macro | Seasons don't change; macro regimes do — unfair decay | **Fixed** — category-specific decay rates + occurrence damping (Section 20) |
| G9 | Historical avg return always None at month-start | PriceInterpolator LLM had no calibration data | **Fixed 2026-05-17** — now reads last 6 cycles |
| G10 | Conviction streak RSI proxy was pattern_analysis score | Wrong abstraction — composite score ≠ RSI | **Fixed 2026-05-17** — now uses `regime_snapshot.sector_rsi` |
| G11 | Tavily called every day (1,056/month) | Over free-tier limit | **Fixed 2026-05-17** — monthly disk cache (48/month) |
| G12 | Full 9-agent re-run on every correct+small-error day | ~70% of LLM calls were wasted | **Fixed 2026-05-17** — early-exit guard in Step 4 |
| G13 | ThesisReviewer flat 2% threshold | Over-fires on volatile stocks, under-fires on stable | **Fixed 2026-05-17** — ATR-relative threshold |
| G14 | Seasonal validation ran every day during seasonal period | O(seeds×log) in daily hot path | **Fixed 2026-05-17** — month-end only |
| G15 | Stale single-ticker lessons promoted to market_wide permanently | Pollutes Tier 3 FeedbackAgent context | **Fixed 2026-05-17** — weekly downgrade cron |
| — | Probability bands on forecasts (not single price) | Needs volatility modelling | Phase 8 target |
| — | Off-market signals (block deals, pre-open) | Intraday complexity | Phase 8 target |
| — | Subscriber prediction feedback loop | Needs frontend + identity layer | Phase 9 target |
| — | Backtesting on historical data | No historical envelope data yet | Available naturally after Month 6 |
| — | F&O expiry effects | Options data sourcing (paid APIs) | Phase 8 target |
| — | Lesson scope narrowing (market→sector→stock) | Lessons only accumulate credibility, can't narrow | Open — design question |
| — | Seasonal threshold deltas not structured in WeightMemory | In weight_history reason string only | Open |

---

## 17. Before vs After Capability Map

| Dimension | LLM Browse Tools (Perplexity/GPT+web) | StockAgent P5+P6 | StockAgent + P1–P5 |
|---|---|---|---|
| Session memory | None | Per-ticker JSON, persistent | Same + shared sector/market ledgers |
| Seasonal knowledge | One-shot if user asks | Reactive (discovered from misses) | **Pre-seeded** + RL-validated |
| Agent weight adaptation | N/A | Accuracy-based (7-day rolling) | Accuracy × **regime multiplier** |
| Cross-ticker learning | None | Schema ready; not propagated | **Active propagation**, 3-tier |
| Momentum exhaustion | None | None | **Conviction streak** + reversion prior |
| Search query self-improvement | None | None | **miss_counter → enhanced queries** |
| Market regime awareness | Static | Static | **VIX + FII + RSI** regime detection |
| Causal miss attribution | None | 7-type taxonomy + penalty weights | Same + **shared pattern library** |
| Forecast uncertainty | Single point estimate | Linear confidence decay | **Streak-adjusted, regime-adjusted** |
| Lesson confidence validity | N/A | Time decay (0.02/month) | Time decay + **seasonal exemption** |

**Knowledge compounding timeline:**

```
Month 1:   Seasonal seeds active immediately (P1)
           Base learned weights + regime detection (P5)

Month 2:   First RL-confirmed seasonal reinforcements
           Shared sector ledger accumulating from 3–5 tickers (P2)
           Prompt enhancements from first month's miss_counter (P4)

Month 3:   Conviction streaks trackable (P3 data accumulates)
           Cross-ticker lessons start reinforcing sector ledger
           Weight adaptation has enough observations to widen drift bounds

Month 6:   Sector ledger has 50–80 validated patterns across all tickers
           Seasonal seeds 70%+ validated by RL data
           Enhanced search queries consistently reducing known blind spots

Month 12:  Proprietary seasonal calendar + learned sector rulebook
           Regime multipliers tunable from historical regime/accuracy data
           Miss rate on known patterns (in ledger) should approach near-zero
```

---

## 19. Key File Locations

| Component | File |
|---|---|
| Regime detector | `core/intelligence/regime/detector.py` |
| Regime multipliers (config) | `core/config/settings/base.py` → `REGIME_MULTIPLIERS` |
| PromptEnhancer | `core/intelligence/prompt_enhancer/enhancer.py` |
| Daily feedback loop | `core/intelligence/rl/workflows/daily_review.py` |
| Generate forecast | `core/intelligence/rl/workflows/generate_forecast.py` |
| Prediction store (JSON R/W) | `core/intelligence/rl/stores/prediction_store.py` |
| Ledger propagator (P2) | `core/intelligence/rl/stores/ledger_propagator.py` |
| Conviction tracker (P3) | `core/intelligence/rl/conviction/tracker.py` |
| Seasonal calendar (P1) | `core/intelligence/seasonal/calendar.py` |
| Seasonal validator (P1) | `core/intelligence/seasonal/validator.py` |
| Seasonal seeds (P1) | `core/intelligence/seasonal/seeds/{sector}.yaml` |
| FeedbackAgent | `core/intelligence/rl/agents/feedback_agent.py` |
| WeightAdapter | `core/intelligence/rl/agents/weight_adapter.py` |
| **ThesisReviewer** | `core/intelligence/rl/agents/thesis_reviewer.py` |
| **PriceInterpolator** | `core/intelligence/rl/algorithms/price_interpolator.py` |
| All RL schemas | `core/schemas/feedback.py` (real) or `src/backend/shared/schemas/feedback.py` (src path) |
| NSE calendar | `core/intelligence/rl/nse_calendar.py` |

---

## 20. Section 6 — Category-Specific Lesson Confidence Decay

### Problem with flat 0.02/month

The previous uniform decay rate treated a macro lesson (volatile, half-life ~50 days) identically to a seasonal lesson (calendar-driven, repeats annually) and a fundamental pattern (earnings cycle, semi-structural). A macro lesson about "RBI surprise suppresses demand" would still appear at 70% confidence 18 months after it was last seen — in a completely different rate cycle — while a seasonal pattern about Shravan-period demand weakness was decaying at the same rate despite being calendar-invariant.

### New decay model

**Two factors multiply together:**

```
effective_rate = LESSON_DECAY_RATES[category] / sqrt(occurrences)
decayed_confidence = stored_confidence × (1 - effective_rate) ^ months_inactive
result = max(0.10, decayed_confidence)
```

**Rate table** — `src/backend/shared/schemas/feedback.py → LESSON_DECAY_RATES`:

| Category | Base rate/month | Rationale |
|---|---|---|
| `seasonal` | 0.000 | Decay-exempt — calendar patterns repeat annually unchanged |
| `data_availability` | 0.005 | Data release calendars rarely change (FADA publishes on 10th, always) |
| `fundamental` | 0.008 | Earnings/business cycle patterns — semi-structural, quarter-to-quarter |
| `technical` | 0.015 | Chart patterns shift with volatility regime but are reasonably persistent |
| `sentiment` | 0.020 | Previous default; sentiment half-life ~50 days |
| `macro` | 0.030 | Domestic macro regimes (RBI cycle, FII flow) are transitional |
| `global_macro` | 0.040 | Global macro (Fed, crude, USD) moves fastest, least persistent |

**Occurrence damping — why sqrt(n):**

A macro lesson confirmed 9 independent times is not a transient regime pattern — it has become a structural behavioral observation. The sqrt formula gives diminishing returns: doubling confirmations halves the rate, but each additional confirmation matters less.

```
macro lesson, confidence=0.75, 3 months inactive:
  1× confirmed:  rate=0.030, eff_conf = 0.75 × (0.970³) ≈ 0.683
  4× confirmed:  rate=0.015, eff_conf = 0.75 × (0.985³) ≈ 0.717
  9× confirmed:  rate=0.010, eff_conf = 0.75 × (0.990³) ≈ 0.728

A macro lesson confirmed 25× reaches the structural band:
  rate = 0.030/√25 = 0.006/month ≈ equivalent to a fundamental pattern (0.008)
```

**Floor = 0.10:** Lessons are never fully discarded automatically. A lesson at 0.10 is still injected into the FeedbackAgent prompt but as weak historical background, naturally deprioritised by the T1/T2/T3 effective-confidence ranking.

**Test file:** `tests/unit/intelligence/rl/test_lesson_decay.py` — 28 tests covering all 7 categories, occurrence damping, floor enforcement, and numeric correctness.

---

## 21. Step 7 — Conditional Thesis Review After Significant Miss

### Problem with mechanical re-weighting

After a >2% prediction miss, the existing system re-weights agents and revises remaining forecasts. But if the reason for the miss was a fundamentally broken underlying assumption (e.g., "crude oil stable ~$82" as a key assumption, but crude just spiked 8%), then every subsequent BUY forecast inherits a structurally wrong premise. Re-weighting only adjusts agent influence; it does not re-examine whether the original 30-day thesis is still valid.

### Trigger conditions

```
ThesisReviewer fires when:
  abs(price_error_pct) > 2.0%          → large absolute miss
  OR
  direction_correct = False             → called direction wrong
  AND miss_type ∈ {direction_flip, model_bias}  → structural (not external shock)
```

Specifically NOT triggered by: `timing`, `magnitude`, `external_shock`, `data_gap`, `data_stale` below the 2% threshold. These are partial misses or fault-free events that don't invalidate the thesis.

### LLM input and output

The LLM receives (~250 tokens):
- Original `key_assumptions` from the prediction envelope (e.g., `["crude stable ~$82", "FADA dispatch +6% MoM"]`)
- Today's miss analysis: `miss_type`, `missed_factors`, `over_weighted_factors`
- Current market context (first 400 chars)

The LLM returns `ThesisReview` (~80 tokens):

```json
{
  "assumptions_invalidated": ["crude stable ~$82"],
  "assumptions_still_valid": ["FADA dispatch +6% MoM"],
  "thesis_intact": false,
  "revised_narrative": "RBI surprise + crude spike invalidated the low-cost thesis.",
  "horizon_confidence_multiplier": 0.70
}
```

### horizon_confidence_multiplier

This is a global multiplier applied to ALL remaining forecast confidences, separate from `horizon_confidence_adjustment`:

| Multiplier | Meaning | Example trigger |
|---|---|---|
| 1.00 | Thesis intact — minor re-weighting only | Small direction error, no assumption broken |
| 0.85 | One assumption broken, recovery plausible | RBI rate hold (unexpected), but demand trend intact |
| 0.70 | Core assumption invalidated, high uncertainty | Crude spike +8%, invalidating input-cost stability |
| 0.50 | Thesis fundamentally wrong | Policy reversal making the entire sector thesis obsolete |
| 0.30 (floor) | Deep uncertainty — forecasts are unreliable | Cannot go below this floor |

The multiplier compounds with existing dampening: a forecast that was already at `confidence=0.60` after reversion prior and horizon decay becomes `0.60 × 0.70 = 0.42` — NEUTRAL territory. This accurately reflects that a broken-thesis BUY forecast is no longer a high-conviction call.

### Safety contract

`ThesisReviewer.review()` catches all exceptions and returns `ThesisReview(thesis_intact=True, horizon_confidence_multiplier=1.0)` on any failure. The daily review cycle is never blocked by a thesis review failure.

**Schema:** `ThesisReview` in `src/backend/shared/schemas/feedback.py`. Persisted in `FeedbackEntry.thesis_review` — visible in the feedback log for audit.

**Test file:** `tests/unit/intelligence/rl/test_thesis_reviewer.py` — 32 tests covering trigger conditions, schema bounds, JSON parse safety, and revision integration.

---

## 22. Section 8 — PromptEnhancer: Sector Templates + LLM Fallback

### Problem with the original single template map

`MISS_FACTOR_TO_QUERY_TEMPLATE` had 5 entries, all automobile-specific. For Banking/BFSI, IT, and Renewable Energy, every miss factor fell through to "no template → skipped silently". The self-regulating miss_counter loop was effectively disabled for 3 of the 4 active sectors.

### Resolution order (per factor per agent)

```
1. SECTOR_MISS_FACTOR_TEMPLATES[sector][factor]    ← sector-specific (takes priority)
2. MISS_FACTOR_TO_QUERY_TEMPLATE[factor]           ← generic cross-sector fallback
3. _generate_queries_llm(factor, ticker, sector)   ← LLM (only when both maps miss)
```

The LLM path fires at most once per (factor, agent) pair per month — and only for factors not covered by any template. For a banking ticker with `GNPA_slippage` in its miss_counter, step 1 fires (banking template exists). For a novel factor like `NPA_recognition_cycle_change` that no template covers, the LLM generates 2 date-qualified, sector-appropriate queries.

### Sector template coverage

| Sector | Miss factors covered | Example factor → agent |
|---|---|---|
| `banking_bfsi` | 10 factors | `GNPA_slippage` → fundamentals + risk |
| `it_sector` | 10 factors | `attrition_spike` → fundamentals |
| `renewable_energy` | 10 factors | `DISCOM_payment_delay` → risk + fundamentals |

All templates include `{ticker}`, `{month}`, `{year}` placeholders substituted at runtime. Time-sensitive queries (dispatch data, NPA slippage) always embed current month/year to prevent Serper returning SEO-optimised 2022 articles.

### _guess_primary_agent heuristic

When the LLM path fires for an unknown factor, the heuristic resolves the primary agent from factor keyword patterns. Priority order (most specific first):

```
RE-sector policy keywords (mnre, fame, pli, subsidy, tariff) → sentiment_policy
Banking fundamental keywords (gnpa, nim, npa, slippage, pcr) → fundamentals
FII/DII/institutional keywords → institutional (banking) | risk_macro (others)
RBI/rate/repo/mpc keywords → macro_policy (banking) | risk_macro (others)
Revenue/margin/earnings/attrition/deal/capacity keywords → fundamentals
DISCOM/curtailment/execution/pledge keywords → risk
Technical/RSI/MACD/breakout keywords → pattern_analysis
...
Sector default → fundamentals (banking/IT/RE) | risk_macro (automobile)
```

Two bugs were found and fixed during testing: (1) `MNRE_policy_reversal` was routing to `risk_macro` because "policy" matched the generic RBI/policy check before the RE-specific MNRE check; (2) `_generate_queries_llm` exceptions were not caught at the `enhance()` level, allowing a failing monkey-patched function to propagate.

**Test file:** `tests/unit/intelligence/rl/test_enhancer_v2.py` — 47 tests covering sector template structure, resolution priority, date substitution, agent routing, and LLM fallback safety.

---

## 23. Section 9 — LLM-Calibrated Price Interpolator

### Problem with static verdict_monthly_pct

```python
# Old: universal for every stock in every regime
{"STRONG BUY": 8.0, "BUY": 4.0, "NEUTRAL": 0.5, "SELL": -3.0, "STRONG SELL": -7.0}
```

HDFC Bank (14-day ATR ~0.8%, low beta) and ADANIGREEN (14-day ATR ~3.5%, high beta, policy-driven) shared the same +4% BUY expectation. A BUY on ADANIGREEN when MNRE auctions are accelerating is realistically a +8–12% move. A BUY on HDFC Bank in a stable rate environment is realistically +2–3%. The static table is wrong for both.

### ForecastProfile

```python
class ForecastProfile:
    monthly_return_pct: float          # [-20, 20] — LLM-calibrated to ATR and sector
    path_shape: Literal[               # how the move distributes over 30 days
        "linear",       # uniform drift (fallback)
        "front_loaded", # 60% of move in first 10 days (near-term catalyst)
        "back_loaded",  # 80% of move in days 11–30 (catalyst is 2+ weeks away)
        "volatile",     # linear drift + ±ATR noise per day
    ]
    confidence_band_daily_pct: float   # [0.1, 5.0] — daily ±uncertainty width
    source: Literal["llm", "static"]   # audit field
```

### LLM inputs (once per month-start per ticker, ~200 tokens)

| Input | Source | Why it matters |
|---|---|---|
| `atr_pct` | yfinance 14-day ATR / price | Primary calibration signal — volatile stock needs wider return range |
| `regime_label` | RegimeDetector | MACRO_CRISIS → narrower expected move; RISK_ON → amplify BUY expectation |
| `conviction_drivers` | FinalReport.conviction_drivers | Near-term catalyst in drivers → front_loaded shape |
| `historical_avg_return_pct` | Median of past FeedbackLog entries for same verdict | Ground truth after Month 3 |

### Path shape examples (BUY, +5%, base ₹10,000)

```
Shape           Day 1    Day 10   Day 20   Day 30   Interpretation
─────────────────────────────────────────────────────────────────
linear          10017    10167    10333    10500    Uniform drift
front_loaded    10100    10357    10429    10500    60% of ₹500 in first 10 days
back_loaded     10007    10067    10283    10500    80% of ₹500 in last 20 days
volatile        10045    10255    10390    10448    Drift + ±ATR noise (deterministic seed)
```

### Static fallback (Month 1, LLM unavailable)

The static dict is preserved but now ATR-scaled, making even the fallback stock-specific:

```
scaled_pct = base_static_pct × max(0.5, min(2.5, atr_pct / 1.5))

HDFC Bank  ATR=0.8%: BUY → 4.0 × (0.8/1.5=0.53) → 2.12%  (conservative, low-beta)
ADANIGREEN ATR=3.5%: BUY → 4.0 × (3.5/1.5=2.33, capped 2.5) → 10.0% (volatile RE stock)
```

### Safety guards in _parse()

- Sign enforcement: BUY with negative LLM output → flipped positive; SELL with positive → flipped negative
- Bounds clamping: `monthly_return_pct` → `[-20, 20]`; `confidence_band_daily_pct` → `[0.1, 5.0]`
- Invalid `path_shape` → default `"linear"`
- Any JSON parse failure → `_static_fallback()` returned, `source="static"`

### compute_historical_avg_return()

After Month 3, this provides empirical calibration. It takes the **median** (not mean) of `price_error_pct` entries in the FeedbackLog where `predicted_verdict` matches the current verdict. Median is used because outlier misses (external shocks) would skew the mean. Returns `None` when fewer than 3 matching entries exist — LLM then calibrates purely from ATR and regime, without historical bias.

**Test file:** `tests/unit/intelligence/rl/test_price_interpolator.py` — 67 tests covering schema bounds, static fallback scaling, all 4 path shapes, LLM parse safety, ATR computation, and historical return calculation.
| Calendar updater | `core/intelligence/rl/calendar_updater.py` |

---

## RL Store Schemas — Quick Reference

> Full schemas in `src/backend/shared/schemas/feedback.py`. Serialised by `core/intelligence/rl/stores/prediction_store.py`.

### File layout
```
data/predictions/{sector}/{TICKER}/
├── {TICKER}_{YYYY-MM}_prediction_envelope.json   ← monthly, reset each cycle
├── {TICKER}_{YYYY-MM}_daily_feedback_log.json    ← monthly, reset each cycle
├── {TICKER}_agent_weight_memory.json             ← persistent across all cycles
└── {TICKER}_learning_ledger.json                 ← persistent across all cycles
```

### FeedbackEntry key fields (daily_feedback_log.json)

| Field | Type | Purpose |
|---|---|---|
| `date` | `str` ISO | Trading day under review |
| `predicted_close` / `actual_close` | `float` | Core comparison pair |
| `price_error_pct` | `float` | `(actual - predicted) / predicted * 100` |
| `direction_correct` | `bool` | Primary WeightAdapter hit-rate signal |
| `regime_label` | `str` | Market regime at time of review (NORMAL / RISK_OFF / MACRO_CRISIS) |
| `volume_vs_20d_avg` | `float \| None` | `>2.0` = institutional; `<0.5` = noise |
| `miss_analysis` | `MissAnalysis \| None` | Root-cause from FeedbackAgent |
| `revised_context` | `RevisedContext \| None` | Forward watch_signals, headline |
| `thesis_review` | `ThesisReview \| None` | Set only on >2% error or direction_flip |
| `lessons_generated` | `list[str]` | Lesson IDs added to ledger |

### MissType penalty multipliers

| Miss type | Penalty | Rationale |
|---|---|---|
| `data_gap` / `data_stale` / `external_shock` | 0.0× | Not model's fault |
| `timing` | 0.5× lag-scaled | Right direction, wrong timing |
| `magnitude` | 0.25× | Right direction, wrong size |
| `model_bias` / `direction_flip` | 1.0× | Structural failure |
| `llm_unavailable` | 0.0× | LLM down — degraded output, no penalty applied |

### market_context_today — what FeedbackAgent receives (Step 4)

As of 2026-05-21: combined from two sources per ticker per day:

```
Serper get_news_context(ticker, days=2)       → editorial reaction, market news
NseIndiaApi announcements(ticker, days=2)     → official NSE filings (results, SEBI, actions)

Combined → FeedbackAgentInput.market_context_today
```

Prior to fix (pre-2026-05-21): `get_news_context` import was broken — FeedbackAgent always received `"Market context unavailable."` → all lessons were generated without real context. Fixed in error-handling audit commit `fix(news): log DEBUG on date parse failure`.

### ConvictionStreak

After `RL_STREAK_WARNING_THRESHOLD` (default 8) consecutive same-direction verdicts: inject warning block into FeedbackAgent prompt. `reversion_prior` formula: `min(streak_days × 0.02, 0.30)` applied as confidence discount.

### Error Handling (2026-05-21)

| Issue | Fix |
|---|---|
| `_write_json()` OSError leaves orphaned `.tmp` | Cleaned up in `finally` block; raises `RuntimeError` |
| `_read_json()` corrupt JSON | Narrowed to `JSONDecodeError\|OSError`; logs ERROR, returns `None` |
| `FeedbackAgent.run()` LLM crash | Returns `FeedbackAgentOutput(miss_type="data_gap")` — daily review does not crash |
