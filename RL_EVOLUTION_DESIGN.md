# RL Feedback Evolution — Gap Analysis & Implementation Design

> **Scope:** Extends Phase 5 + Phase 6 of `RL_FEEDBACK_DESIGN.md`.
> All four sectors: automobile · banking_bfsi · it_sector · renewable_energy
> Target: a system that compounds knowledge with runtime, not just accuracy.

---

## Table of Contents

1. [System Assessment](#1-system-assessment)
2. [Gap Register](#2-gap-register)
3. [Priority 1 — SeasonalCalendar Module](#3-priority-1--seasonalcalendar-module)
4. [Priority 2 — Shared Sector + Market Ledger Propagation](#4-priority-2--shared-sector--market-ledger-propagation)
5. [Priority 3 — Conviction Duration & Mean Reversion Prior](#5-priority-3--conviction-duration--mean-reversion-prior)
6. [Priority 4 — PromptEnhancer: miss_counter → Search Queries](#6-priority-4--promptenhancer-miss_counter--search-queries)
7. [Priority 5 — Context-Conditional Regime Multiplier](#7-priority-5--context-conditional-regime-multiplier)
8. [Integration Build Order](#8-integration-build-order)
9. [Before vs After Capability Map](#9-before-vs-after-capability-map)

---

## 1. System Assessment

### What Is Already Strong

| Component | Why It Works |
|---|---|
| 4-file JSON memory (envelope · log · weights · ledger) | Persistent across cycles; audit trail for every decision |
| Miss taxonomy (7 types, penalty multipliers) | Correct epistemics — absolves agents for exogenous shocks |
| Per-ticker weight isolation | MARUTI's learned weights never corrupt TCS's weights |
| Lesson scope (stock/sector/market) | Schema is ready; propagation plumbing is the missing piece |
| Confidence decay (0.02/month floor 0.10) | Prevents stale lessons from misleading the LLM |
| Timing accuracy (lag_days, assessment) | Captures a dimension most RL stock systems ignore |
| Analyst distrust rule | Disciplined exclusion of broker consensus |
| Bounded adaptation (±0.15 from base, ±0.05 per step) | Prevents runaway drift in early-data months |

### What Is Factually Broken or Missing

```
┌─ REACTIVE when should be PROACTIVE ─────────────────────────────────┐
│  Seasonal patterns only discovered AFTER a miss.                     │
│  December car clearance learned December of year 2, not year 1.     │
└──────────────────────────────────────────────────────────────────────┘

┌─ LEARNED but never APPLIED cross-ticker ─────────────────────────────┐
│  scope=sector_wide lessons stored in MARUTI's ledger.                │
│  TATAMOTORS daily review never reads MARUTI's ledger.                │
└──────────────────────────────────────────────────────────────────────┘

┌─ KNOWS what was missed, never LOOKS for it next time ────────────────┐
│  miss_counter["crude_oil_spike"] = 5 for MARUTI.                     │
│  sales_demand CONTEXT_SEARCH_QUERIES unchanged since month 1.        │
└──────────────────────────────────────────────────────────────────────┘

┌─ NO protection against MOMENTUM EXHAUSTION ──────────────────────────┐
│  10 consecutive BUY days → no mean-reversion prior.                  │
│  System can ride a trend into a cliff edge with high confidence.     │
└──────────────────────────────────────────────────────────────────────┘

┌─ WEIGHTS are accuracy-averaged, not REGIME-AWARE ────────────────────┐
│  risk_macro weight = f(hit_rate over 7 days).                        │
│  Macro crisis day: risk_macro should always dominate.                │
│  System has no concept of market regime.                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Gap Register

| # | Gap | Current State | Impact | Type |
|---|---|---|---|---|
| G1 | Seasonal patterns reactive, not pre-seeded | Discovered only after miss | High — 1–2yr loss before patterns learned | Missing |
| G2 | Sector-wide / market-wide lessons not propagated cross-ticker | Stored in one ticker's ledger only | High — knowledge siloed | Missing |
| G3 | No momentum exhaustion / mean-reversion prior | BUY streak has no counter-signal | High — subscriber trust risk on reversals | Missing |
| G4 | CONTEXT_SEARCH_QUERIES static; miss_counter ignored | Agents don't search for known blind spots | Medium — forecasts miss own known gaps | Missing |
| G5 | Weight adaptation is regime-agnostic | hit_rate is the only signal | Medium — wrong agent amplified during crises | Tweak |
| G6 | Forecast path is linear interpolation | Constant drift, linear confidence decay | Medium — misrepresents uncertainty | Tweak |
| G7 | max_total_drift_from_base fixed at 0.15 forever | Too tight after 6+ months of data | Low — limits long-run adaptation | Tweak |
| G8 | Seasonal lesson decay rate same as macro | Seasons don't change; macro regimes do | Low — seasons unfairly decay | Tweak |

---

## 3. Priority 1 — SeasonalCalendar Module

### Problem Statement

The `seasonal` lesson category exists in the schema but is discovered reactively. A stock analysed for the first time in April cannot know that December is systematically different for automobile stocks without having been wrong in December first. Pre-existing domain knowledge must be injected, then continuously validated and refined by the RL loop — not discovered from zero.

### Design: Two-Layer Seasonal Architecture

```
Layer 1: Pre-seeded domain knowledge (human-authored, per sector)
         Written once. Never auto-deleted. Can be reinforced or invalidated.

Layer 2: RL-discovered seasonal lessons (auto-generated from misses)
         Written by FeedbackAgent when miss_type = seasonal.
         Reinforces or contradicts Layer 1 entries.

         Both layers merged at forecast generation time.
```

### File Layout

```
core/
└── intelligence/
    └── seasonal/
        ├── __init__.py
        ├── calendar.py              ← SeasonalCalendar class (loads + queries)
        ├── validator.py             ← SeasonalValidator (checks if rules fired correctly)
        └── seeds/
            ├── automobile.yaml      ← Pre-seeded patterns for auto sector
            ├── banking_bfsi.yaml    ← Pre-seeded patterns for BFSI
            ├── it_sector.yaml       ← Pre-seeded patterns for IT
            └── renewable_energy.yaml
```

### Seed File Schema (YAML)

```yaml
# core/intelligence/seasonal/seeds/automobile.yaml

sector: automobile
version: "1.0"
last_reviewed: "2026-04-30"

patterns:
  - id: "SEA_AUTO_001"
    name: "december_model_clearance"
    months: [12]
    days_of_month: null          # entire month
    direction_bias: "neutral_short_bearish_long"
    magnitude_pct: -3.0          # typical underperformance vs index
    confidence: 0.75
    rationale: >
      New model year launches in January. Dealers aggressively discount
      outgoing models in December to clear inventory. High volume but
      compresses margins. Short-term neutral; long-term OEM realization bearish.
    agents_affected:
      sales_demand: -0.08        # discount sales_demand score this month
      fundamentals: -0.05        # margin compression
    scope: sector_wide
    validated_by_rl: false       # flipped to true once RL confirms ≥2 cycles

  - id: "SEA_AUTO_002"
    name: "navratri_diwali_peak"
    months: [10, 11]
    days_of_month: null
    direction_bias: "positive"
    magnitude_pct: +5.0
    confidence: 0.80
    rationale: >
      Navratri / Dussehra / Diwali window. Highest retail registration months.
      "Buy the rumour, sell the news" risk: stock often peaks 2 weeks before
      Diwali when news flow is peak bullish, then corrects post-festival.
    agents_affected:
      sales_demand: +0.10
      sentiment: +0.08
    peak_before_end_days: 14     # peak typically 14 days before month end
    scope: sector_wide
    validated_by_rl: false

  - id: "SEA_AUTO_003"
    name: "shravan_inauspicious_north_india"
    months: [7, 8]
    days_of_month: null
    direction_bias: "negative"
    magnitude_pct: -2.5
    confidence: 0.65
    rationale: >
      Shravan month (Hindu lunar calendar — typically July/Aug).
      North India buyers avoid major purchases. Retail volumes drop 8-12%.
      Exact dates shift year to year; treat as probabilistic, not fixed.
    agents_affected:
      sales_demand: -0.07
    scope: sector_wide
    validated_by_rl: false
    lunar_calendar_dependency: true  # dates shift annually; treat with lower weight

  - id: "SEA_AUTO_004"
    name: "q4_march_wholesale_push"
    months: [3]
    days_of_month: null
    direction_bias: "deceptive_positive"
    magnitude_pct: +2.0
    confidence: 0.70
    rationale: >
      OEMs push wholesale dispatches in March for year-end targets.
      SIAM wholesale data looks strong. Retail (FADA) often lags.
      Dealer inventory bloats in April. sales_demand agent sees wholesale
      spike and over-optimizes. Discount the wholesale component specifically.
    agents_affected:
      sales_demand: -0.06          # discount the FADA/SIAM wholesale sub-score
    scope: sector_wide
    validated_by_rl: false
```

### SeasonalCalendar Class Interface

```python
# core/intelligence/seasonal/calendar.py

class SeasonalCalendar:
    """
    Loads pre-seeded seasonal patterns and merges with RL-discovered seasonal
    lessons from the learning ledger. Produces a SeasonalContext for any date.
    """

    def __init__(self, sector: str):
        self.sector  = sector
        self._seeds  = self._load_seeds(sector)      # from YAML

    def get_context(
        self,
        target_date: date,
        learning_ledger: LearningLedger,
    ) -> SeasonalContext:
        """
        Returns:
          active_seeds      — pre-seeded patterns active on target_date
          active_rl_lessons — seasonal lessons from ledger active this period
          agent_adjustments — merged dict of agent score deltas to apply
          narrative         — one-sentence context string for LLM injection
        """

    def validate_pattern(
        self,
        pattern_id: str,
        feedback_log: DailyFeedbackLog,
    ) -> ValidationResult:
        """
        Checks if a seeded pattern fired correctly in the feedback log.
        Increments validated_by_rl=True once ≥2 confirmed cycles.
        Marks pattern invalid if it contradicts observed data ≥3 times.
        """
```

### SeasonalContext Data Model

```python
class SeasonalContext(BaseModel):
    target_date:       date
    active_seeds:      list[SeasonedPattern]   # from YAML
    active_rl_lessons: list[Lesson]            # from learning_ledger (category=seasonal)
    agent_adjustments: dict[str, float]        # merged: seed + rl, conflicts averaged
    narrative:         str                     # injected into LLM prompt
    confidence_modifier: float                 # added to forecast confidence base
```

### Integration Points

```
generate_forecast.py
  │
  ├── SeasonalCalendar(sector).get_context(first_trading_day, ledger)
  │     └── returns agent_adjustments per day for the envelope
  │
  └── _build_daily_forecasts()
        └── for each DailyForecast row:
              apply seasonal agent_adjustments when month/day matches
              append seasonal narrative to key_assumptions[]

daily_review.py
  │
  ├── SeasonalCalendar.get_context(today, ledger) injected into FeedbackAgent prompt
  │     └── prevents FeedbackAgent from "discovering" patterns that are already seeded
  │
  └── SeasonalValidator.validate_pattern() called after feedback_log updated
        └── marks seeds validated_by_rl once RL data confirms them
```

### Seed Validation State Machine

```
   SEEDED (confident=0.75, validated=false)
         │
         │  FeedbackAgent detects seasonal lesson for same pattern
         ▼
   REINFORCED (confidence += 0.05, occurrences += 1)
         │
         │  ≥2 full cycles confirm
         ▼
   VALIDATED (validated_by_rl = true, confidence locked ≥0.75)
         │
         │  ≥3 cycles where pattern does NOT fire
         ▼
   INVALIDATED (still_valid = false, no longer injected)
```

### Seed Table by Sector (Summary)

#### Automobile

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_AUTO_001 | december_model_clearance | Dec | Bearish (margin) | 0.75 |
| SEA_AUTO_002 | navratri_diwali_peak | Oct–Nov | Positive | 0.80 |
| SEA_AUTO_003 | shravan_inauspicious | Jul–Aug | Negative | 0.65 |
| SEA_AUTO_004 | q4_march_wholesale_push | Mar | Deceptive positive | 0.70 |
| SEA_AUTO_005 | budget_week_policy_wait | Jan week 4–Feb week 1 | Cautious/wait | 0.60 |
| SEA_AUTO_006 | april_new_year_launch_hype | Apr | Positive sentiment | 0.65 |

#### Banking / BFSI

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_BFSI_001 | march_year_end_credit_push | Mar | Positive | 0.75 |
| SEA_BFSI_002 | rbi_mpc_meeting_week | Bimonthly | Cautious | 0.80 |
| SEA_BFSI_003 | q1_npa_recognition_risk | Apr | Negative | 0.65 |
| SEA_BFSI_004 | budget_banking_policy | Feb | Positive/Volatile | 0.70 |

#### IT Sector

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_IT_001 | us_tech_earnings_spillover | Jan, Apr, Jul, Oct | Correlated | 0.75 |
| SEA_IT_002 | q1_attrition_cost_peak | Apr–May | Negative margin | 0.65 |
| SEA_IT_003 | us_budget_uncertainty | Sep–Oct | Cautious | 0.70 |
| SEA_IT_004 | inr_weakening_tailwind | Any | Revenue positive | 0.60 |

#### Renewable Energy

| ID | Name | Months | Bias | Confidence |
|---|---|---|---|---|
| SEA_RE_001 | monsoon_solar_generation_dip | Jun–Sep | Output negative | 0.80 |
| SEA_RE_002 | cop_climate_summit_hype | Oct–Nov | Sentiment positive | 0.65 |
| SEA_RE_003 | year_end_capex_push | Oct–Dec | Order book positive | 0.70 |
| SEA_RE_004 | tariff_revision_q1 | Jan–Feb | Policy risk | 0.60 |

---

## 4. Priority 2 — Shared Sector + Market Ledger Propagation

### Problem Statement

Lessons with `scope=sector_wide` and `scope=market_wide` are written into a single ticker's ledger. No other ticker reads them. The lesson "on RBI policy days, risk_macro signal dominates" learned from HDFCBANK's failures is not available when forecasting SBIN — even though both tickers are in `banking_bfsi` and would benefit identically.

### Current State vs Target State

```
CURRENT:
  data/predictions/
    banking_bfsi/
      HDFCBANK/
        HDFCBANK_learning_ledger.json     ← scope=sector_wide lessons trapped here
      SBIN/
        SBIN_learning_ledger.json         ← starts empty; never reads HDFCBANK lessons

TARGET:
  data/predictions/
    banking_bfsi/
      _shared_ledger.json                 ← scope=sector_wide lessons from all tickers
    _market_ledger.json                   ← scope=market_wide from all sectors
    banking_bfsi/
      HDFCBANK/
        HDFCBANK_learning_ledger.json     ← scope=stock_specific only
      SBIN/
        SBIN_learning_ledger.json         ← scope=stock_specific only
```

### Ledger Read Hierarchy (per ticker, per daily review)

```
FeedbackAgent.run() context assembly:

  ┌─────────────────────────────────────────────────────────┐
  │  TIER 1 (most specific, highest weight)                  │
  │  ticker_learning_ledger.json                             │
  │  scope=stock_specific lessons ONLY                       │
  │  active_lessons_summary() → top 6 by eff_confidence     │
  ├─────────────────────────────────────────────────────────┤
  │  TIER 2 (sector-level)                                   │
  │  _shared_ledger.json (sector folder)                     │
  │  scope=sector_wide lessons, all tickers in this sector   │
  │  active_lessons_summary() → top 3 by eff_confidence     │
  ├─────────────────────────────────────────────────────────┤
  │  TIER 3 (market-level)                                   │
  │  _market_ledger.json (root predictions folder)           │
  │  scope=market_wide, all sectors                          │
  │  active_lessons_summary() → top 2 by eff_confidence     │
  └─────────────────────────────────────────────────────────┘
              │
              ▼
  Combined active_lessons_summary injected into FEEDBACK_PROMPT
  (max 11 lessons total, ranked by tier then eff_confidence)
```

### Write Path: Lesson Routing

```
FeedbackAgent output → merge_lessons_into_ledger()
          │
          ├── lesson.scope == "stock_specific"
          │         └── write to TICKER_learning_ledger.json
          │
          ├── lesson.scope == "sector_wide"
          │         ├── write to TICKER_learning_ledger.json (source record)
          │         └── propagate to SECTOR/_shared_ledger.json
          │                   (deduplicate by pattern name)
          │
          └── lesson.scope == "market_wide"
                    ├── write to TICKER_learning_ledger.json (source record)
                    ├── propagate to SECTOR/_shared_ledger.json
                    └── propagate to ROOT/_market_ledger.json
                              (deduplicate by pattern name)
```

### PredictionStore API Extensions

```python
class PredictionStore:

    # --- NEW methods ---

    def load_sector_ledger(self) -> LearningLedger:
        """
        Load data/predictions/{sector}/_shared_ledger.json
        Returns empty LearningLedger if file doesn't exist yet.
        """

    def save_sector_ledger(self, ledger: LearningLedger) -> None:
        """Atomic write to _shared_ledger.json"""

    def load_market_ledger(self) -> LearningLedger:
        """
        Load data/predictions/_market_ledger.json
        Shared across all sectors.
        """

    def save_market_ledger(self, ledger: LearningLedger) -> None:
        """Atomic write to _market_ledger.json"""

    def load_all_ledgers(self) -> tuple[LearningLedger, LearningLedger, LearningLedger]:
        """
        Returns (ticker_ledger, sector_ledger, market_ledger) in one call.
        Called at the start of daily_review and generate_forecast.
        """
```

### Lesson Deduplication Logic (Shared Ledgers)

```python
def propagate_to_shared_ledger(
    lesson: Lesson,
    shared_ledger: LearningLedger,
    source_ticker: str,
) -> LearningLedger:
    """
    If same pattern already in shared_ledger:
      - increment occurrences
      - blend confidence: new = 0.7 × existing + 0.3 × incoming
      - update last_seen
      - append source_ticker to contributing_tickers[]
    Else:
      - add lesson with contributing_tickers = [source_ticker]
    """
```

### Schema Addition: contributing_tickers

```python
class Lesson(BaseModel):
    lesson_id:             str
    date_learned:          str
    category:              LessonCategory
    pattern:               str
    observation:           str
    rule:                  str
    confidence:            float
    occurrences:           int
    still_valid:           bool
    scope:                 LessonScope
    last_seen:             str
    contributing_tickers:  list[str] = []    # NEW — which tickers confirmed this lesson
```

### Cross-Ticker Confidence Boost Rule

```
A sector-wide lesson gains +0.05 confidence boost each time a NEW ticker confirms it.

Example:
  L_SEC_001 "RBI_policy_day → risk_macro dominant" learned from HDFCBANK (conf=0.72)
  SBIN daily review confirms same pattern → confidence bumps to 0.77
  AXISBANK confirms → confidence bumps to 0.82
  After 3 tickers independently confirm: lesson is promoted from sector_wide to validated

This prevents single-ticker noise from becoming sector-wide truth too quickly.
```

---

## 5. Priority 3 — Conviction Duration & Mean Reversion Prior

### Problem Statement

The system has no awareness of how long it has been issuing the same verdict. A `STRONG BUY` streak of 15 days carries zero accumulated risk signal — the system will issue day 16 with the same confidence as day 1. In reality, sustained one-directional momentum increases the probability of correction.

This is not a news signal. It comes entirely from the state of the `PredictionEnvelope` and price structure.

### Conviction Duration Counter

```python
# Add to PredictionEnvelope
class PredictionEnvelope(BaseModel):
    ...
    conviction_streak: ConvictionStreak = ConvictionStreak()    # NEW

class ConvictionStreak(BaseModel):
    current_verdict:   str   = ""      # "BUY", "STRONG BUY", etc.
    streak_days:       int   = 0       # consecutive days with same verdict direction
    streak_start_date: str   = ""      # when the streak began
    max_streak_seen:   int   = 0       # historical max for this ticker this cycle
    reversion_prior:   float = 0.0     # 0.0-0.30, increases with streak length
```

### Reversion Prior Formula

```
streak_days     reversion_prior     interpretation
─────────────   ────────────────    ─────────────────────────────────
0 – 4           0.00                Normal operation; no modifier
5 – 7           0.05                Mild caution; flag in narrative
8 – 10          0.10                Moderate risk; reduce confidence
11 – 14         0.15                Elevated risk; watch RSI divergence
15 – 20         0.20                High risk; add reversion warning
≥ 21            0.25 (cap)          Maximum prior; reversion expected

Formula:
  reversion_prior = min(0.25, max(0, (streak_days - 4) × 0.025))

Applied to forecast confidence:
  adjusted_confidence = base_confidence × (1.0 - reversion_prior × 0.5)
  (dampened — prior alone cannot halve confidence; it's a signal, not a verdict)
```

### RSI Divergence Amplifier

When `pattern_analysis` agent's `rsi_macd_bb` sub-score contradicts the verdict direction AND streak ≥ 8, multiply the reversion_prior by 1.5.

```
Condition:
  verdict = "BUY" AND rsi_macd_bb sub_score < 0.40
  → RSI showing overbought while we're calling BUY
  → reversion_prior × 1.5 (capped at 0.30)

Condition:
  verdict = "SELL" AND rsi_macd_bb sub_score > 0.60
  → RSI showing oversold while we're calling SELL
  → reversion_prior × 1.5 (capped at 0.30)
```

### Integration in daily_review.py

```
Step 7 (Revise remaining forecasts) — CURRENT:
  re-run SignalAggregator with updated weights
  apply active lesson rules inline
  update prediction_envelope.json

Step 7 (Revise remaining forecasts) — WITH P3:
  re-run SignalAggregator with updated weights
  ┌─ compute conviction streak from envelope ─────────────────────────┐
  │  streak = count consecutive days with same verdict direction       │
  │  reversion_prior = _compute_reversion_prior(streak)               │
  │  rsi_amplify = _check_rsi_divergence(todays_agent_scores)         │
  │  final_prior = min(0.30, reversion_prior × rsi_amplify)           │
  └───────────────────────────────────────────────────────────────────┘
  apply active lesson rules inline
  apply reversion_prior to remaining forecast confidence
  update conviction_streak in envelope
  update prediction_envelope.json
```

### FeedbackAgent Prompt Addition (P3)

```python
# Appended to FEEDBACK_PROMPT when streak ≥ 8

STREAK_WARNING_BLOCK = """
--- CONVICTION STREAK ALERT ---
This stock has issued {verdict} for {streak_days} consecutive days.
Reversion prior is currently {reversion_prior:.0%}.
Explicitly assess whether momentum exhaustion signals are present:
  - RSI divergence (price high / RSI lower high)
  - Volume declining on up days (distribution pattern)
  - Delivery percentage drop on price rise (futures-driven)
  - Relative underperformance vs sector index in last 3 sessions
If any of these are present in market_context_today, classify accordingly
and reduce horizon_confidence_adjustment.
"""
```

### Conviction Streak in feedback-status Dashboard

```
=== Conviction Streak ===
  Current verdict   : STRONG BUY (streak: 12 days)
  Streak start      : 2026-04-14
  Reversion prior   : 0.20  ⚠ ELEVATED
  RSI amplifier     : 1.5×  (rsi_macd_bb=0.38 < 0.40 threshold)
  Effective prior   : 0.25 (cap applied)
  Confidence dampen : −12.5% applied to remaining 18 forecast days
```

---

## 6. Priority 4 — PromptEnhancer: miss_counter → Search Queries

### Problem Statement

Each agent's `CONTEXT_SEARCH_QUERIES` are static strings written at development time. After 3 months of feedback loops, `miss_counter` in `learning_ledger.json` contains the top factors this stock consistently missed. The agents are never told to search for these specifically.

```
Example after 3 months — MARUTI learning_ledger.miss_counter:
  {
    "FII_outflow_spike":       5,
    "crude_oil_spot_price":    4,
    "RBI_policy_surprise":     3,
    "month_end_inventory_flush": 2,
    "INR_depreciation":        2
  }

Current state: sales_demand CONTEXT_SEARCH_QUERIES unchanged since day 1.
Target state:  top 3 miss factors → injected as additional search queries.
```

### PromptEnhancer Module

```
core/
└── intelligence/
    └── prompt_enhancer/
        ├── __init__.py
        └── enhancer.py          ← PromptEnhancer class
```

### PromptEnhancer Logic

```python
class PromptEnhancer:
    """
    Reads miss_counter from a ticker's learning ledger and generates
    additional context search queries for each agent.

    Called once per month-start (generate_forecast.py), not daily.
    Output is cached in a per-ticker enhancement file for the month.
    """

    MISS_FACTOR_TO_QUERY_TEMPLATE: dict[str, dict[str, str]] = {
        "FII_outflow_spike": {
            "risk_macro":   "{ticker} FII DII net flows provisional {date}",
            "sentiment":    "FII selling India equity {month} {year}",
        },
        "crude_oil_spot_price": {
            "raw_materials": "Brent crude spot price today {date}",
            "risk_macro":    "crude oil impact Indian automobile sector {month}",
        },
        "RBI_policy_surprise": {
            "risk_macro":    "RBI MPC meeting upcoming schedule {year}",
            "fundamentals":  "RBI repo rate decision impact auto loan rates",
        },
        "INR_depreciation": {
            "risk_macro":    "USD INR exchange rate {date}",
            "raw_materials": "INR depreciation impact import cost automobile {year}",
        },
        "month_end_inventory_flush": {
            "sales_demand":  "{ticker} dealer inventory days channel check {month}",
        },
        # ... extensible; new entries added as FeedbackAgent discovers new patterns
    }

    def enhance(
        self,
        ticker: str,
        learning_ledger: LearningLedger,
        top_n: int = 3,
    ) -> dict[str, list[str]]:
        """
        Returns: {agent_name: [additional_query_1, additional_query_2, ...]}

        Only returns queries for the top_n miss factors.
        Queries are appended to the agent's base CONTEXT_SEARCH_QUERIES at runtime.
        """

    def save_enhancements(
        self,
        ticker: str,
        sector: str,
        enhancements: dict[str, list[str]],
        cycle_id: str,
    ) -> None:
        """
        Saves to: data/predictions/{sector}/{ticker}/{ticker}_{cycle}_prompt_enhancements.json
        Loaded by each agent at BaseAgent.run() time.
        """
```

### Enhanced Search Query Assembly (Runtime)

```
BaseAgent.run(query):
  │
  ├── base_queries = CONTEXT_SEARCH_QUERIES   (static, from prompt file)
  │
  ├── enhancement_file = PredictionStore.load_enhancements(ticker, cycle_id)
  │     └── {agent_name: [query1, query2]} or {} if first cycle
  │
  ├── agent_extra = enhancement_file.get(self.agent_name, [])
  │
  └── all_queries = base_queries + agent_extra
        └── passed to RAG retriever / search tool
```

### Enhancement File Schema

```json
{
  "ticker": "MARUTI",
  "cycle_id": "MARUTI_2026-04",
  "generated_at": "2026-04-01",
  "based_on_miss_counter": {
    "FII_outflow_spike": 5,
    "crude_oil_spot_price": 4,
    "RBI_policy_surprise": 3
  },
  "agent_enhancements": {
    "risk_macro": [
      "MARUTI FII DII net flows provisional {date}",
      "RBI MPC meeting upcoming schedule 2026",
      "Brent crude spot price today {date}"
    ],
    "sales_demand": [
      "MARUTI dealer inventory days channel check {month}"
    ],
    "raw_materials": [
      "Brent crude spot price today {date}",
      "INR depreciation impact import cost automobile 2026"
    ]
  }
}
```

### Feedback Loop (Enhancement Self-Improvement)

```
Month N: miss_counter = {crude: 4, FII: 3}
         → PromptEnhancer adds crude / FII queries to risk_macro

Month N+1 daily_review:
  → If crude still appears in missed_factors: miss_counter["crude"] increments
       → Enhancement stays and gets higher priority

  → If crude no longer appears in missed_factors (query found the data):
       → miss_counter["crude"] stays flat or drops
       → Enhancement deprioritised next cycle (rank drops below top_n)

This makes the enhancement queries self-regulating.
```

---

## 7. Priority 5 — Context-Conditional Regime Multiplier

### Problem Statement

Current weight adaptation is a rolling accuracy calculation over 7 days. It treats all 7 days as equally important and has no concept of what market conditions prevailed. On a macro-shock day, `risk_macro` should dominate regardless of its recent 7-day average accuracy.

### Regime Detection (Lightweight, No New Agents)

```
RegimeDetector reads 3 cheap signals (all from yfinance or existing data):

  Signal 1: India VIX
    └── VIX > 22   → VOLATILE_MACRO regime
    └── VIX < 14   → LOW_VOL_TRENDING regime
    └── 14–22      → NORMAL regime

  Signal 2: FII Net Flow (7-day rolling from existing DII data)
    └── Net outflow > ₹5,000Cr over 5 days → MACRO_RISK regime flag
    └── Net inflow  > ₹5,000Cr over 5 days → RISK_ON flag

  Signal 3: Sector RSI (Nifty Auto / Nifty Bank / Nifty IT / Nifty 50)
    └── RSI > 70   → OVERBOUGHT flag (momentum exhaustion risk)
    └── RSI < 30   → OVERSOLD flag (mean reversion opportunity)

Regime = combination of the above (3 signals → 4 regime classifications)
```

### Regime Classification Table

| VIX | FII Flow | Sector RSI | Regime Label | Implication |
|---|---|---|---|---|
| > 22 | Outflow | Any | `MACRO_CRISIS` | risk_macro dominates |
| 14–22 | Outflow | Any | `RISK_OFF` | risk_macro elevated |
| 14–22 | Neutral | 30–70 | `NORMAL` | base weights apply |
| 14–22 | Inflow | Any | `RISK_ON` | sentiment/fundamentals elevated |
| < 14 | Inflow | > 70 | `MOMENTUM_EXTENDED` | mean reversion prior active |
| Any | Any | < 30 | `OVERSOLD` | pattern_analysis elevated |

### Regime Multiplier Table (Applied on Top of Learned Weights)

```
                    MACRO    RISK     NORMAL   RISK     MOMENTUM  OVERSOLD
Agent               CRISIS   OFF               ON       EXTENDED
─────────────────   ──────   ──────   ──────   ──────   ────────  ────────
risk_macro          1.40     1.20     1.00     0.90     0.85      1.10
fundamentals        0.80     0.90     1.00     1.10     1.05      1.00
sales_demand        0.70     0.85     1.00     1.10     0.95      1.00
sentiment           0.80     0.90     1.00     1.15     0.80      0.90
pattern_analysis    0.90     0.95     1.00     0.95     1.20      1.30
competitive_intel   1.00     1.00     1.00     1.00     1.00      1.00
valuation_catalyst  0.90     0.95     1.00     1.10     1.10      1.05

Notes:
  - Multipliers applied AFTER learned weight adaptation.
  - Effective weight = learned_weight × regime_multiplier, then renormalize.
  - Multipliers are config constants (not learned); tuned by sector over time.
  - Regime multipliers do NOT affect weight_memory.json — they are daily modifiers only.
```

### Effective Weight Computation (Full Flow)

```
WeightMemory.current_weights
        │
        │  (static learning from accuracy)
        ▼
  learned_weights = {risk_macro: 0.22, fundamentals: 0.24, ...}
        │
        │  RegimeDetector.detect(date) → regime = MACRO_CRISIS
        ▼
  regime_multipliers = REGIME_MULTIPLIER_TABLE["MACRO_CRISIS"]
        │
  raw_effective = {
    agent: learned_weights[agent] × regime_multipliers[agent]
    for agent in agents
  }
        │
        │  renormalize (sum must = 1.0)
        ▼
  effective_weights = {risk_macro: 0.29, fundamentals: 0.18, ...}
        │
        ▼
  SignalAggregator.run(... learned_weights=effective_weights ...)
```

### RegimeDetector Class Interface

```python
class RegimeDetector:
    """
    Lightweight regime classifier from market microdata.
    No LLM call. Reads yfinance and existing indicator fetcher.
    """

    def detect(self, as_of_date: date, sector: str) -> RegimeSnapshot:
        """
        Returns RegimeSnapshot with:
          regime_label:      str  (one of 6 labels above)
          vix_value:         float
          fii_net_flow_7d:   float  (₹ Crore)
          sector_rsi:        float
          multipliers:       dict[str, float]  (per agent)
          narrative:         str   (one sentence for LLM injection)
        """

    def _get_vix(self, date: date) -> float:
        """India VIX from yfinance ticker ^INDIAVIX"""

    def _get_sector_rsi(self, sector: str, date: date) -> float:
        """
        Nifty Auto (^CNXAUTO) / Nifty Bank (^NSEBANK) /
        Nifty IT (^CNXIT) / Nifty 50 (^NSEI)
        RSI(14) computed from price history.
        """
```

### Config Constants (settings.py additions)

```python
# Phase 7 — Regime Multipliers
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "MACRO_CRISIS": {
        "risk_macro": 1.40, "fundamentals": 0.80,
        "sales_demand": 0.70, "sentiment": 0.80,
        "pattern_analysis": 0.90,
    },
    "RISK_OFF": {
        "risk_macro": 1.20, "fundamentals": 0.90,
        "sales_demand": 0.85, "sentiment": 0.90,
        "pattern_analysis": 0.95,
    },
    "NORMAL": {
        k: 1.00 for k in AGENT_NAMES   # passthrough
    },
    "RISK_ON": {
        "risk_macro": 0.90, "fundamentals": 1.10,
        "sales_demand": 1.10, "sentiment": 1.15,
        "pattern_analysis": 0.95,
    },
    "MOMENTUM_EXTENDED": {
        "risk_macro": 0.85, "fundamentals": 1.05,
        "sales_demand": 0.95, "sentiment": 0.80,
        "pattern_analysis": 1.20,
    },
    "OVERSOLD": {
        "risk_macro": 1.10, "fundamentals": 1.00,
        "sales_demand": 1.00, "sentiment": 0.90,
        "pattern_analysis": 1.30,
    },
}

VIX_VOLATILE_THRESHOLD:  float = 22.0
VIX_LOW_VOL_THRESHOLD:   float = 14.0
FII_OUTFLOW_THRESHOLD:   float = -5000.0   # ₹ Crore, 5-day net
FII_INFLOW_THRESHOLD:    float = +5000.0
RSI_OVERBOUGHT:          float = 70.0
RSI_OVERSOLD:            float = 30.0
```

---

## 8. Integration Build Order

### Dependency Graph

```
P1 (SeasonalCalendar)
  ├── Reads: learning_ledger.json (existing)
  ├── Writes: seasonal/seeds/*.yaml (new)
  └── No dependency on P2, P3, P4, P5
          │
P2 (Shared Ledger Propagation)
  ├── Reads: ticker_learning_ledger.json (existing)
  ├── Writes: _shared_ledger.json, _market_ledger.json (new)
  ├── Modifies: PredictionStore, feedback_agent.py
  └── No dependency on P1, P3, P4, P5
          │
P3 (Conviction Duration)
  ├── Reads: PredictionEnvelope (existing)
  ├── Modifies: PredictionEnvelope schema, daily_review.py, generate_forecast.py
  └── No dependency on P1, P2; ENHANCES output for P5
          │
P4 (PromptEnhancer)
  ├── Reads: learning_ledger.json (existing)
  ├── Writes: *_prompt_enhancements.json (new)
  ├── Modifies: BaseAgent.run(), PredictionStore
  └── Depends on P2 being live (sector ledger = richer miss_counter)
          │
P5 (Regime Multiplier)
  ├── Reads: yfinance VIX + sector index (new data source)
  ├── Modifies: WeightAdapter.update() or SignalAggregator call site
  └── Depends on P3 (ConvictionStreak needed for MOMENTUM_EXTENDED detection)
```

### Sprint / Milestone Table

| Priority | New Files | Modified Files | Test File | Estimated Complexity |
|---|---|---|---|---|
| P1 SeasonalCalendar | `seasonal/calendar.py`, `seasonal/validator.py`, `seasonal/seeds/*.yaml` | `generate_forecast.py`, `daily_review.py` | `tests/test_seasonal.py` | Medium |
| P2 Shared Ledger | `stores/prediction_store.py` (+3 methods) | `feedback_agent.py`, `daily_review.py` | `tests/test_shared_ledger.py` | Medium |
| P3 Conviction Duration | Schema: `ConvictionStreak` | `generate_forecast.py`, `daily_review.py`, `feedback_schemas.py` | `tests/test_conviction.py` | Low |
| P4 PromptEnhancer | `prompt_enhancer/enhancer.py` | `base_agent.py`, `prediction_store.py` | `tests/test_enhancer.py` | Low |
| P5 Regime Multiplier | `regime/detector.py` | `weight_adapter.py` or `signal_aggregator.py`, `settings.py` | `tests/test_regime.py` | Medium–High |

### File Tree (Post-Implementation)

```
core/
├── intelligence/
│   ├── seasonal/                          ← NEW (P1)
│   │   ├── __init__.py
│   │   ├── calendar.py
│   │   ├── validator.py
│   │   └── seeds/
│   │       ├── automobile.yaml
│   │       ├── banking_bfsi.yaml
│   │       ├── it_sector.yaml
│   │       └── renewable_energy.yaml
│   │
│   ├── prompt_enhancer/                   ← NEW (P4)
│   │   ├── __init__.py
│   │   └── enhancer.py
│   │
│   ├── regime/                            ← NEW (P5)
│   │   ├── __init__.py
│   │   └── detector.py
│   │
│   └── rl/
│       ├── agents/
│       │   ├── feedback_agent.py          ← MODIFIED (P2: shared ledger read)
│       │   └── weight_adapter.py          ← MODIFIED (P5: regime multiplier)
│       ├── stores/
│       │   └── prediction_store.py        ← MODIFIED (P2: shared/market ledger; P4: enhancements)
│       └── workflows/
│           ├── daily_review.py            ← MODIFIED (P1, P2, P3, P5)
│           └── generate_forecast.py       ← MODIFIED (P1, P3, P4)
│
├── pipeline/
│   └── base_agent.py                      ← MODIFIED (P4: load enhancements)
│
└── schemas/
    └── feedback.py                        ← MODIFIED (P2: contributing_tickers; P3: ConvictionStreak)

data/predictions/
├── _market_ledger.json                    ← NEW (P2) — scope=market_wide
├── automobile/
│   ├── _shared_ledger.json                ← NEW (P2) — scope=sector_wide
│   └── MARUTI/
│       ├── MARUTI_2026-04_prediction_envelope.json
│       ├── MARUTI_2026-04_daily_feedback_log.json
│       ├── MARUTI_2026-04_prompt_enhancements.json  ← NEW (P4)
│       ├── MARUTI_agent_weight_memory.json
│       └── MARUTI_learning_ledger.json
└── banking_bfsi/
    ├── _shared_ledger.json                ← NEW (P2)
    └── HDFCBANK/
        └── ...
```

---

## 9. Before vs After Capability Map

### System Comparison

| Dimension | LLM Browse Tools (Perplexity, GPT+web) | StockAgent Phase 5+6 (Current) | StockAgent + P1–P5 (Target) |
|---|---|---|---|
| Session memory | None | Per-ticker JSON, persistent | Same + shared sector/market |
| Seasonal knowledge | One-shot if user asks | Reactive (discovered from misses) | Pre-seeded + RL-validated |
| Agent weight adaptation | N/A | Accuracy-based (7-day rolling) | Accuracy × regime multiplier |
| Cross-ticker learning | None | Schema ready; not propagated | Active propagation, 3-tier |
| Momentum exhaustion | None | None | Conviction streak + reversion prior |
| Search query self-improvement | None | None | miss_counter → enhanced queries |
| Market regime awareness | Static | Static | VIX + FII + RSI regime detection |
| Causal miss attribution | None | 7-type taxonomy + penalty weights | Same + shared pattern library |
| Forecast uncertainty | Single point estimate | Linear confidence decay | Streak-adjusted, regime-adjusted |
| Lesson confidence validity | N/A | Time decay (0.02/month) | Time decay + seasonal exemption |

### Knowledge Compounding Timeline (Target)

```
Month 1:   Seasonal seeds active immediately (P1 live from day 1)
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

### Honest Gaps That Remain (Post P1–P5)

| Gap | Why Not Addressed | Future Path |
|---|---|---|
| Probability bands on forecasts (not single price) | Needs volatility modelling; separate workstream | Phase 8: Monte Carlo price paths using realised vol |
| Off-market signals (block deals, pre-open session) | Data availability + intraday complexity | Phase 8: NSE bulk deal API integration |
| Subscriber prediction feedback loop | Needs frontend + identity layer | Phase 9: Subscriber accuracy tracking |
| Backtesting on historical data | No historical envelope data yet (need 6+ months live) | Available naturally after Month 6 |
| F&O expiry effects | Options data sourcing (paid APIs needed) | Phase 8: NSE F&O OI + PCR integration |

---

*Document created: 2026-04-30 · Extends RL_FEEDBACK_DESIGN.md Phases 5 & 6*
