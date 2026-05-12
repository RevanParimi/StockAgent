# RL Feedback Log Structures

> Four JSON files form the persistent memory of the RL feedback loop.
> Each file serves a distinct role: one is a working forecast sheet, one is a
> daily evidence ledger, one is an earned-trust register, and one is a
> long-term pattern knowledge base.
>
> All four are defined in `src/backend/shared/schemas/feedback.py` and
> serialised / deserialised by `core/intelligence/rl/stores/prediction_store.py`.

---

## File Locations

```
data/predictions/{sector}/{TICKER}/
├── {TICKER}_{YYYY-MM}_prediction_envelope.json   ← monthly, reset each cycle
├── {TICKER}_{YYYY-MM}_daily_feedback_log.json    ← monthly, reset each cycle
├── {TICKER}_agent_weight_memory.json             ← persistent across all cycles
└── {TICKER}_learning_ledger.json                 ← persistent across all cycles
```

**Example (MARUTI, automobile sector, May 2026):**
```
data/predictions/automobile/MARUTI/
├── MARUTI_2026-05_prediction_envelope.json
├── MARUTI_2026-05_daily_feedback_log.json
├── MARUTI_agent_weight_memory.json
└── MARUTI_learning_ledger.json
```

---

## How the Four Files Interconnect

```
generate_forecast.py (month start)
    │
    ├─ reads  → agent_weight_memory.json        (which weights to use)
    ├─ reads  → learning_ledger.json            (existing lessons for prompt context)
    └─ writes → prediction_envelope.json        (30-day forecast sheet)

daily_review.py (every trading day)
    │
    ├─ reads  → prediction_envelope.json        (today's predicted close + agent scores)
    ├─ reads  → agent_weight_memory.json        (current weight version)
    ├─ reads  → learning_ledger.json            (active lessons for FeedbackAgent prompt)
    ├─ calls  → FeedbackAgent LLM              (miss analysis + new lessons)
    ├─ calls  → WeightAdapter (deterministic)   (update weights from accuracy)
    ├─ updates→ prediction_envelope.json        (revise remaining daily rows)
    ├─ appends→ daily_feedback_log.json         (one FeedbackEntry per day)
    ├─ updates→ agent_weight_memory.json        (new weight version)
    └─ updates→ learning_ledger.json            (merge new lessons)
```

---

## 1. Prediction Envelope

**File:** `{TICKER}_{YYYY-MM}_prediction_envelope.json`
**Written:** once at month start by `generate_forecast.py`
**Updated:** daily by `daily_review.py` (revision of remaining rows)
**Schema class:** `PredictionEnvelope`

### Why it exists

The prediction envelope is the "living forecast sheet". It holds the full 30-day
forward price path generated at the start of each monthly cycle. Every trading day,
`daily_review.py` compares today's actual close against the day's predicted close,
then revises the remaining rows in light of what was learned. This makes the forecast
self-correcting rather than a static one-shot guess.

### Top-level fields

| Field | Type | Why stored |
|---|---|---|
| `ticker` | `str` | Identity — which stock this envelope covers |
| `sector` | `str` | Which sector graph (agent list) generated the forecast |
| `cycle_id` | `str` | e.g. `"MARUTI_2026-05"` — links envelope to its feedback log |
| `generated_at` | `str` (ISO date) | Audit trail — when this forecast was generated |
| `base_close` | `float` | Day-0 actual close — all `predicted_change_pct` values are relative to this |
| `weight_version_used` | `int` | Which `WeightMemory` version was active — lets you see which learned weights drove the forecast |
| `forecast_profile_shape` | `str` | `"linear"` / `"front_loaded"` / `"back_loaded"` / `"volatile"` — how expected returns are distributed over 30 days |
| `forecast_profile_monthly_pct` | `float` | LLM-calibrated expected monthly return % for this ticker/verdict combination |
| `forecast_profile_source` | `str` | `"llm"` if calibrated by PriceInterpolator LLM call, `"static"` if fallback |
| `conviction_streak` | `ConvictionStreak` | Mean-reversion guard — tracks consecutive same-direction verdicts |

**Real example (MARUTI 2026-05):**
```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-05",
  "generated_at": "2026-05-09",
  "base_close": 13726.0,
  "weight_version_used": 0,
  "forecast_profile_shape": "linear",
  "forecast_profile_monthly_pct": 0.0,
  "forecast_profile_source": "static"
}
```

### ConvictionStreak

Tracks consecutive days where the same directional verdict (BUY/STRONG BUY or SELL/STRONG SELL)
was issued. After ~5–7 consecutive bullish days, stocks revert more often than they continue.
The `reversion_prior` (0.0–0.30) is applied as a confidence discount to remaining forecasts.

```json
"conviction_streak": {
  "current_verdict": "BUY",
  "streak_days": 4,
  "streak_start_date": "2026-05-11",
  "max_streak_seen": 6,
  "reversion_prior": 0.08
}
```

`streak_days = 4` → `reversion_prior ≈ 0.08` means each remaining day's confidence is
multiplied by `(1 - 0.08)` to discount the "too bullish for too long" risk.

### DailyForecast (each row in `daily_forecasts[]`)

| Field | Type | Why stored |
|---|---|---|
| `day` | `int` | 1-indexed position in the 30-day envelope |
| `date` | `str` | ISO trading date — used as key for daily_review lookup |
| `predicted_close` | `float` | The price target for this specific date |
| `predicted_change_pct` | `float` | `(predicted_close - base_close) / base_close * 100` — derived, stored for fast retrieval |
| `predicted_verdict` | `str` | `BUY` / `SELL` / `NEUTRAL` — the directional call for this day |
| `predicted_agent_scores` | `dict[str, float]` | Composite score per agent at time of forecast generation — needed to compute `agent_score_drift` in feedback |
| `predicted_agent_subscores` | `dict[str, dict[str, float]]` | Per-agent sub-dimension scores (e.g. `fundamentals.revenue_growth: 0.72`) — populated when available so FeedbackAgent can see WHICH sub-signal drifted, not just the composite |
| `confidence` | `float` | 0.0–1.0 — decreasing over the 30-day horizon as uncertainty compounds |
| `key_assumptions` | `list[str]` | Top 3 conviction drivers frozen at forecast time — ThesisReviewer checks these on significant misses |
| `revised` | `bool` | `True` after daily_review updates this row |
| `revision_count` | `int` | How many times this specific day has been revised — detects oscillation |

**Why `predicted_agent_subscores` was added:**
The FeedbackAgent prompt originally received only the composite score change
(e.g. `risk_macro drifted -0.18`). But that composite is the average of 5 sub-signals.
A -0.18 from `risk_macro` could be driven entirely by `rbi_repo_emi_impact` while
`global_geopolitical_risk` was stable — these require completely different lessons.
Sub-scores close this gap, allowing the LLM to attribute misses precisely.

---

## 2. Daily Feedback Log

**File:** `{TICKER}_{YYYY-MM}_daily_feedback_log.json`
**Written:** daily by `daily_review.py` (one entry appended per trading day)
**Read:** by `WeightAdapter` (rolling accuracy windows), `FeedbackAgent` (active lessons),
`generate_forecast.py` (historical return computation for PriceInterpolator)
**Schema class:** `DailyFeedbackLog`

### Why it exists

The feedback log is the evidence base for all learning. Every trading day produces one
`FeedbackEntry`: predicted vs actual close, miss analysis from the FeedbackAgent LLM,
generated lessons, and the weight version applied. The log is the input to `WeightAdapter`
which scans the last 5/10/21 trading-day windows to compute rolling hit rates.

### Top-level fields

| Field | Type | Why stored |
|---|---|---|
| `ticker` | `str` | Identity |
| `sector` | `str` | Sector context |
| `cycle_id` | `str` | Links to the prediction envelope that this log evaluates |
| `entries` | `list[FeedbackEntry]` | One row per trading day |

### FeedbackEntry (each row in `entries[]`)

| Field | Type | Why stored |
|---|---|---|
| `day` | `int` | Day number within the 30-day cycle |
| `date` | `str` | ISO date — used as key for lookup and rolling window filtering |
| `predicted_close` | `float` | What was predicted |
| `actual_close` | `float` | What actually happened |
| `price_error_pct` | `float` | `(actual - predicted) / predicted * 100` — the error magnitude |
| `predicted_verdict` | `str` | The verdict in force for this day |
| `actual_direction` | `"UP"` / `"DOWN"` / `"FLAT"` | Derived from actual vs predicted with ATR-relative ±0.3% threshold |
| `direction_correct` | `bool` | Primary signal used by WeightAdapter for hit-rate computation |
| `regime_label` | `str` | Market regime active at time of review (NORMAL / RISK_OFF / MACRO_CRISIS / etc.) — enables regime-stratified accuracy analysis: "risk_macro is 71% accurate in NORMAL but only 44% in MACRO_CRISIS" |
| `volume_vs_20d_avg` | `float \| None` | Today's volume relative to 20-day average — `>2.0` signals institutional activity; `<0.5` suggests noise; guides lesson scope |
| `miss_analysis` | `MissAnalysis \| None` | Root-cause breakdown from FeedbackAgent LLM |
| `timing` | `TimingAccuracy \| None` | Was the predicted move early, on-time, or late? |
| `revised_context` | `RevisedContext \| None` | Forward-looking structured outlook from FeedbackAgent |
| `thesis_review` | `ThesisReview \| None` | Set only on significant misses (|error| > 2% or direction_flip/model_bias) — whether the month's core thesis is still valid |
| `lessons_generated` | `list[str]` | Lesson IDs added to the learning ledger this day — audit link |
| `weight_adjustment_applied` | `str` | e.g. `"v4"` — human-readable audit reference to WeightMemory version |

**Example FeedbackEntry (constructed, illustrative):**
```json
{
  "day": 3,
  "date": "2026-05-13",
  "predicted_close": 13780.98,
  "actual_close": 13510.00,
  "price_error_pct": -1.96,
  "predicted_verdict": "BUY",
  "actual_direction": "DOWN",
  "direction_correct": false,
  "regime_label": "RISK_OFF",
  "volume_vs_20d_avg": 2.4,
  "miss_analysis": {
    "primary_miss_agent": "risk_macro",
    "miss_type": "direction_flip",
    "missed_factors": ["FII_outflow_spike", "USD_INR_breakout"],
    "over_weighted_factors": ["sales_demand"],
    "agent_score_drift": {
      "risk_macro": -0.22,
      "fundamentals": -0.05
    },
    "predicted_subscores_significant": {
      "risk_macro": {
        "inr_usd_crude_exposure": 0.60,
        "rbi_repo_emi_impact": 0.55
      }
    },
    "actual_subscores_significant": {
      "risk_macro": {
        "inr_usd_crude_exposure": 0.28,
        "rbi_repo_emi_impact": 0.50
      }
    }
  },
  "lessons_generated": ["L003"],
  "weight_adjustment_applied": "v2"
}
```

### MissAnalysis — the root-cause record

| Field | Type | Why |
|---|---|---|
| `primary_miss_agent` | `str` | The agent blamed by FeedbackAgent LLM — WeightAdapter applies bias penalty to this agent |
| `miss_type` | `MissType` | Classification drives penalty multiplier (see below) |
| `missed_factors` | `list[str]` | Real-world signals not captured — fed into `LearningLedger.miss_counter` and `miss_events` |
| `over_weighted_factors` | `list[str]` | Signals trusted too much — inform future lesson rules |
| `agent_score_drift` | `dict[str, float]` | Per-agent composite delta: `today_score - predicted_score`. Positive = bullish signal missed; Negative = risk underestimated |
| `predicted_subscores_significant` | `dict` | Sub-scores frozen at forecast time for significant drifters — needed so FeedbackAgent can say "revenue_growth fell from 0.72 to 0.42" not just "fundamentals drifted -0.07" |
| `actual_subscores_significant` | `dict` | Today's sub-scores for the same agents — paired with predicted to compute sub-dimension drift |

### MissType penalty multipliers

| Miss type | Penalty multiplier | Rationale |
|---|---|---|
| `data_gap` | 0.0 × | Data wasn't published at forecast time — model had no signal to use |
| `data_stale` | 0.0 × | Hardcoded value used (e.g. RBI rate not refreshed) — data pipeline issue, not model fault |
| `external_shock` | 0.0 × | Black-swan event (earthquake, war escalation) — unforeseeable by design |
| `timing` | 0.5 × (lag-scaled) | Direction correct but move arrived 3–7 trading days early/late — partial penalty |
| `magnitude` | 0.25 × | Direction correct but extent of move was wrong — minor penalty |
| `model_bias` | 1.0 × | Agent consistently over/under-estimates a specific signal — structural failure |
| `direction_flip` | 1.0 × | Completely wrong direction, no external cause — full penalty |

### TimingAccuracy

Tracks whether the predicted price move materialised at the right time in the 30-day window.
Used by `WeightAdapter` to apply lag-tolerance: moves that are ≤3 trading days off earn
zero penalty; 4–7 days off earn 20% of the normal penalty; >7 days earns 50%.

```json
"timing": {
  "predicted_peak_day": 7,
  "actual_move_start_day": 11,
  "lag_days": 4,
  "assessment": "late"
}
```

### RevisedContext — structured forward outlook

Replaces the old single-sentence `revised_context` string. Used by the next day's
`FeedbackAgentInput.previous_watch_signals` to close the monitoring loop:
"You flagged these yesterday — did any materialise?"

```json
"revised_context": {
  "headline": "FII outflow pressure may persist through Friday; fundamentals intact medium-term.",
  "risks_next_7_days": ["USD/INR above 84.5", "FII net selling > ₹2000 Cr"],
  "catalysts_next_7_days": ["FADA monthly sales data release (10th)", "RBI pause confirmation"],
  "watch_signals": ["Nifty Auto index RSI below 40", "crude above $92"],
  "horizon_confidence_adjustment": -0.05
}
```

### ThesisReview — core thesis validity check

Produced only when `|price_error_pct| > 2.0%` OR `direction_correct=False AND miss_type in
{direction_flip, model_bias}`. The ThesisReviewer LLM call (~250 input tokens, ~80 output)
checks whether the key assumptions frozen in `DailyForecast.key_assumptions` are still valid.

```json
"thesis_review": {
  "assumptions_invalidated": ["Favorable policy environment (CAFE-III timeline brought forward)"],
  "assumptions_still_valid": ["Strong sales and demand", "Solid fundamentals"],
  "thesis_intact": false,
  "revised_narrative": "Policy risk elevated. Retain BUY but confidence haircut applied.",
  "horizon_confidence_multiplier": 0.75
}
```

`horizon_confidence_multiplier = 0.75` means every remaining DailyForecast in the envelope
gets its `confidence` multiplied by 0.75 — a 25% haircut across the board, not just today.

---

## 3. Agent Weight Memory

**File:** `{TICKER}_agent_weight_memory.json`
**Persists:** across all monthly cycles for this ticker
**Written:** at month-start (`generate_forecast.py` initialises if missing), daily (`daily_review.py` after WeightAdapter updates)
**Schema class:** `WeightMemory`

### Why it exists

Agent weights are how the system encodes earned trust. If `risk_macro` has been correct
12 of the last 14 trading days, it should have higher influence over the final verdict than
`sentiment` which has been right 6 of 14. The weight memory persists this earned trust
across monthly cycles so a stock's history accumulates rather than resetting each month.

### Top-level fields

| Field | Type | Why stored |
|---|---|---|
| `ticker` | `str` | Identity |
| `sector` | `str` | Sector determines the agent list |
| `last_updated` | `str` | ISO date — audit trail |
| `weight_version` | `int` | Monotonically incrementing — links each `WeightHistoryEntry` to a specific update event |
| `current_weights` | `dict[str, float]` | The actively used weights — sum to 1.0; `SignalAggregator` reads these |
| `base_weights` | `dict[str, float]` | Original config defaults — never mutated; used as bounds anchor: `current ∈ [base - 0.15, base + 0.15]` |
| `agent_accuracy` | `dict[str, AgentAccuracy]` | Rolling hit rates per agent — read by WeightAdapter to compute deltas |
| `weight_history` | `list[WeightHistoryEntry]` | Full audit trail of every weight change — why, what changed, what accuracy was |
| `regime_accuracy` | `dict[str, dict[str, AgentAccuracy]]` | Per-regime breakdown: `{regime_label: {agent_name: AgentAccuracy}}` — enables "risk_macro accuracy in MACRO_CRISIS vs NORMAL" comparisons |
| `adjustment_bounds` | `dict` | Deprecated — bounds are now read from `settings.WEIGHT_MAX_STEP` and `settings.WEIGHT_MAX_DRIFT`; kept for backward compatibility with existing JSON files |

**Real example (MARUTI, version 0 — cycle just started):**
```json
{
  "ticker": "MARUTI",
  "sector": "automobile",
  "last_updated": "2026-05-09",
  "weight_version": 0,
  "current_weights": {
    "sales_demand": 0.15,
    "raw_materials": 0.09,
    "fundamentals": 0.18,
    "pattern_analysis": 0.11,
    "sentiment": 0.04,
    "policy_regulatory": 0.09,
    "competitive_intel": 0.09,
    "risk_macro": 0.13,
    "valuation_catalyst": 0.12
  },
  "base_weights": { "...same as current_weights at initialisation..." }
}
```

### WeightHistoryEntry — structured version log

Each time `WeightAdapter.update()` runs and produces non-zero deltas, a new entry is appended.
This is the full audit log for explainability: why did the model become more cautious on
`risk_macro`?

```json
{
  "version": 4,
  "date": "2026-05-15",
  "weights": {
    "sales_demand": 0.162,
    "risk_macro": 0.158,
    "fundamentals": 0.174
  },
  "reason": "risk_macro: Δ+0.02 (hits=6/7); sales_demand: Δ-0.03 (hits=3/7)",
  "deltas": {
    "risk_macro": 0.02,
    "sales_demand": -0.03
  },
  "accuracy_snapshot": {
    "risk_macro": 0.857,
    "sales_demand": 0.429,
    "fundamentals": 0.714
  },
  "regime_at_update": "RISK_OFF"
}
```

`deltas` is structured (not embedded in `reason` text) so it can be parsed programmatically
for trend analysis and the monthly recalibration LLM call.

### AgentAccuracy — rolling hit rate record

```json
"agent_accuracy": {
  "risk_macro": {
    "direction_hits": 6,
    "total": 7,
    "avg_error": 0.032,
    "monthly_snapshot_history": [
      {
        "month": "2026-04",
        "hit_rate": 0.714,
        "total": 21,
        "dominant_regime": "NORMAL"
      }
    ]
  }
}
```

`monthly_snapshot_history` is a rolling 12-entry deque. It allows a future monthly
recalibration LLM call to see the trend: "Was `risk_macro` improving from 62% → 71% → 85%
or degrading?" A single number cannot answer this.

### Weight adaptation logic (deterministic — no LLM)

```
hit_rate ≥ WEIGHT_BOOST_HIT_RATE (0.70)  → +0.02 (boost)
hit_rate ≤ WEIGHT_PENALTY_HIT_RATE (0.40) → -0.03 (penalty)

If agent = primary_miss_agent AND miss_type not in {data_gap, data_stale, external_shock}:
  bias_score = weighted_miss_rate across [5, 10, 21] trading-day windows
  if bias_score ≥ 0.55: apply bias_penalty (scaled, up to -0.05)

All deltas clamped to ±WEIGHT_MAX_STEP (0.05) per update.
Total drift from base capped at ±WEIGHT_MAX_DRIFT (0.15).
Re-normalised to sum to 1.0 after every update.
```

Seasonal periods shift thresholds via `SeasonalPattern.accuracy_threshold_delta`:
during festive season `{"sales_demand": +0.08}` raises the bar for sales_demand to earn
a boost — it's expected to do well, so mere correctness doesn't warrant extra weight.

---

## 4. Learning Ledger

**File:** `{TICKER}_learning_ledger.json`
**Persists:** across all monthly cycles
**Written:** daily by `daily_review.py` (FeedbackAgent lessons merged in) and at month rollover
**Read:** by `generate_forecast.py` (T1/T2/T3 summary for FeedbackAgent prompt),
`PromptEnhancer` (miss_counter for search query generation)
**Schema class:** `LearningLedger`

### Why it exists

The learning ledger is the long-term pattern memory. While the feedback log records events
("missed on day 3 because of FII outflow") the ledger records generalised rules
("when FII net sells exceed ₹2000 Cr in 3 days, risk_macro dominates over fundamentals
for MARUTI in the following 5 trading days"). Lessons survive across monthly cycle resets
and are injected into the FeedbackAgent prompt every day so the LLM's analysis is
informed by what was historically true for this specific stock.

### Top-level fields

| Field | Type | Why stored |
|---|---|---|
| `ticker` | `str` | Identity |
| `sector` | `str` | Sector context |
| `last_updated` | `str` | ISO date |
| `lessons` | `list[Lesson]` | All accumulated pattern rules |
| `miss_counter` | `dict[str, int]` | Legacy raw count dict — kept for backward compatibility with PromptEnhancer older code |
| `miss_events` | `dict[str, list[MissEvent]]` | Structured miss history — replaces raw dict; last 12 events per factor; stores miss_type so PromptEnhancer can skip `external_shock` events when generating search queries |
| `correction_counter` | `dict[str, int]` | Tracks times a lesson pattern was active AND direction was correct — approximate lesson effectiveness = corrections / (corrections + misses) |
| `confidence_decay_rate` | `float` | Deprecated legacy field (0.02); per-category rates from `LESSON_DECAY_RATES` are used instead |

### Lesson — one accumulated pattern rule

| Field | Type | Why stored |
|---|---|---|
| `lesson_id` | `str` | e.g. `"L001"` — referenced in `FeedbackEntry.lessons_generated` for audit |
| `date_learned` | `str` | ISO date first observed |
| `category` | `LessonCategory` | One of 7 categories (see below) — determines decay rate |
| `pattern` | `str` | Short machine-readable key e.g. `"FII_outflow_spike"` — used for deduplication |
| `observation` | `str` | What was observed in plain English |
| `rule` | `str` | The generalised rule extracted — must express INTENT not numeric delta |
| `confidence` | `float` | Raw confidence when last reinforced |
| `occurrences` | `int` | How many times this pattern has been confirmed |
| `still_valid` | `bool` | False when `invalidation_streak >= 3` — the pattern has been contradicted 3 consecutive cycles |
| `scope` | `LessonScope` | `stock_specific` / `sector_wide` / `market_wide` — controls whether lesson propagates to other tickers |
| `last_seen` | `str` | ISO date last reinforced — used as the reference date for decay computation |
| `contributing_tickers` | `list[str]` | If scope is `sector_wide`, which other tickers also observed this pattern |
| `semantic_tags` | `list[str]` | Controlled vocabulary tags for deduplication beyond exact pattern matching. e.g. both `"RBI_policy_day"` and `"RBI_surprise_hold"` carry tag `"central_bank_event"` and will be merged |
| `invalidation_streak` | `int` | Consecutive cycles where this lesson was contradicted. 0=healthy, 1=warn, 2=critical, 3=invalidated |
| `invalidation_reason` | `str` | Populated when `still_valid → False` — preserves why the rule stopped working |
| `invalidation_date` | `str` | ISO date of invalidation |

**Rule writing contract — critical:**
```
Good: "Prioritise risk_macro over fundamentals on RBI event days — macro dominates."
Bad:  "Boost risk_macro by +0.05 when RBI event detected."
```
The "bad" form stores a numeric delta that goes stale as weights evolve across cycles.
The "good" form expresses intent — the FeedbackAgent and ThesisReviewer can interpret
this appropriately regardless of the current weight values.

**Example lesson:**
```json
{
  "lesson_id": "L003",
  "date_learned": "2026-05-13",
  "category": "macro",
  "pattern": "FII_outflow_spike",
  "observation": "USD/INR broke 84.5, FII net sold ₹3200 Cr in one session. risk_macro score collapsed from 0.60 to 0.28.",
  "rule": "When FII net selling exceeds ₹2000 Cr in a single session AND USD/INR breaks a key level, treat risk_macro as the dominant signal for the following 3–5 trading days. Sales and fundamentals are secondary until FII flow stabilises.",
  "confidence": 0.72,
  "occurrences": 1,
  "still_valid": true,
  "scope": "sector_wide",
  "last_seen": "2026-05-13",
  "contributing_tickers": [],
  "semantic_tags": ["fii_flow", "currency", "sector=automobile"],
  "invalidation_streak": 0,
  "invalidation_reason": "",
  "invalidation_date": ""
}
```

### Lesson categories and decay rates

| Category | Base decay/month | Rationale |
|---|---|---|
| `seasonal` | 0.000 (exempt) | Calendar patterns repeat annually — December is always December |
| `data_availability` | 0.005 | Data publication calendars rarely change (FADA always on 10th) |
| `fundamental` | 0.008 | Earnings and business cycle patterns shift slowly |
| `technical` | 0.015 | Chart patterns shift with volatility regime over weeks |
| `sentiment` | 0.020 | News tone and social half-life is ~50 days |
| `macro` | 0.030 | Domestic macro regimes (RBI stance, FII flow direction) are transitional |
| `global_macro` | 0.040 | Global macro (Fed stance, crude, DXY) shifts fastest |

**Occurrence damping:** as a lesson accumulates more confirmed instances, its effective
decay rate slows via `sqrt(occurrences)` dampening. A macro lesson seen once decays at
0.030/month; seen 4 times it decays at 0.015/month; seen 9 times at 0.010/month.
Repeated confirmation makes patterns structural.

**Example — two lessons same category, different occurrence counts:**
```
L001: macro, FII_outflow_spike, occurrences=1  → decays at 0.030/month
L007: macro, RBI_policy_day,    occurrences=9  → decays at 0.010/month
```
After 6 months of inactivity:
- L001 `confidence = 0.72 × (0.970)^6 = 0.72 × 0.832 = 0.599`
- L007 `confidence = 0.80 × (0.990)^6 = 0.80 × 0.941 = 0.753`

The well-confirmed pattern stays relevant much longer.

### MissEvent — structured miss history

Replaces the raw `miss_counter: dict[str, int]` which could not distinguish
between 5 model_bias misses (fixable with better data) vs 5 external_shock misses
(unforeseeable — no amount of better data would help).

```json
"miss_events": {
  "FII_outflow_spike": [
    {"date": "2026-05-13", "miss_type": "direction_flip",  "cycle_id": "MARUTI_2026-05"},
    {"date": "2026-04-22", "miss_type": "model_bias",      "cycle_id": "MARUTI_2026-04"}
  ],
  "crude_price_shock": [
    {"date": "2026-03-15", "miss_type": "external_shock",  "cycle_id": "MARUTI_2026-03"}
  ]
}
```

`PromptEnhancer.enhance()` calls `ledger.penalizable_miss_count(factor)` which
counts only `model_bias` and `direction_flip` events. For `crude_price_shock` above,
`penalizable_miss_count = 0` — so no search queries are generated for that factor.
This prevents the system from hunting for "better crude oil data" after what was
simply an unforeseeable geopolitical event.

### How lessons reach the LLM — the three-tier summary

`LearningLedger.active_lessons_summary()` builds the text injected into every
`FeedbackAgentInput.active_lessons_summary`:

```
L001 [macro|sector_wide] FII_outflow_spike: When FII net selling exceeds ₹2000 Cr ...
  (eff_confidence=0.60, seen=1x)
L003 [seasonal|sector_wide] festive_quarter_demand: Q2 festive demand reliably lifts ...
  (eff_confidence=0.88, seen=4x)
L007 [macro|stock_specific] RBI_policy_day: Prioritise risk_macro on RBI event days ...
  (eff_confidence=0.75, seen=9x)
```

`eff_confidence` is the decay-adjusted value so the LLM naturally weights
L007 (well-confirmed, eff=0.75) more than L001 (first instance, eff=0.60)
without any extra instruction.

For larger ledgers, `daily_review.py` passes a three-tier summary instead:
- **T1 (high confidence, ≥0.70):** full rule text
- **T2 (medium, 0.40–0.70):** pattern key + one-line rule only
- **T3 (low, <0.40):** pattern key only — "weakly held, verify before applying"

This caps the lesson injection to a predictable token budget regardless of ledger size.

---

## Design Decisions Summary

| Decision | Rationale |
|---|---|
| Monthly envelope + persistent weight/ledger files | Forecasts reset monthly (fresh thesis); learning does not (accumulated trust and patterns persist) |
| `base_weights` never mutated | Bounds anchor — prevents accumulated drift from making weights meaningless over many cycles |
| `miss_type` in FeedbackEntry | Not all misses are model failures; `external_shock` must not reduce agent weights or waste search query budget |
| `regime_label` in FeedbackEntry | Without it, rolling hit rates mix NORMAL-day performance with MACRO_CRISIS-day performance, making the accuracy signal noisy |
| `predicted_agent_subscores` in DailyForecast | Composite agent scores obscure which sub-dimension drifted; sub-scores allow FeedbackAgent to generate precise, actionable lessons |
| `semantic_tags` on Lesson | Exact string match (`find_by_pattern`) misses semantic duplicates; `"RBI_policy_day"` and `"RBI_surprise_hold"` are the same lesson conceptually |
| `miss_events` list vs `miss_counter` dict | Raw counts lose miss_type information; PromptEnhancer needs to skip `external_shock` counts when generating search queries |
| `horizon_confidence_multiplier` in ThesisReview | A single significant miss should propagate uncertainty to all remaining forecasts, not just tomorrow's |
| `conviction_streak` in PredictionEnvelope | Sustained one-direction verdicts are statistically mean-reverting; the reversion_prior discounts remaining forecasts before the signal explicitly turns |
