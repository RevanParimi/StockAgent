# RL Reference — StockAI Adaptive Prediction Loop

> Auto-generated 2026-05-01 08:00 by `scripts/generate_rl_reference.py`
> Re-run after any config or template change to keep this file current.

---

## 1. System Overview

StockAI uses a **Reinforcement-style Feedback Loop** that runs daily after market close.
Predictions are made monthly; every day the system compares predicted vs actual close price,
identifies what the model missed, adjusts agent weights, and revises future forecasts.

### Phase Progression

| Phase | Feature                          | Status        | Tests |
|-------|----------------------------------|---------------|-------|
| P1    | SeasonalCalendar                 | ✅ Done        | 38    |
| P2    | Shared Ledger Propagation        | ✅ Done        | 39    |
| P3    | Conviction / Duration Envelope   | ✅ Done        | 55    |
| P4    | PromptEnhancer (miss → queries)  | ✅ Done        | 33    |
| P5    | Regime Multiplier                | ✅ Done        | 55    |

---

## 2. Daily Feedback Loop (8 Steps)

Runs every weekday at **16:30 IST / 11:00 UTC** via cron (`0 11 * * 1-5`).

```
Step 0   RegimeDetector → classify market (VIX / FII proxy / Sector RSI)
Step 1   Load PredictionEnvelope → predicted_close + assumptions
Step 2   Fetch actual closing price via yfinance
Step 3   Compute error metrics (price_error_pct, direction_correct)
Step 4   FeedbackAgent → miss_type + miss analysis + raw lessons
         └─ Inject streak warning if ConvictionStreak ≥ 8
         └─ Inject regime narrative (non-NORMAL regimes only)
Step 5   WeightAdapter → adjust agent weights (miss_type-aware)
Step 5.5 Apply regime multipliers → ephemeral effective weights (NOT stored)
Step 6   LearningLedger → merge/deduplicate lessons + scope/last_seen
Step 7   Revise remaining forecasts with regime_effective_weights
Step 8   Append entry to daily_feedback_log
```

**Key invariant:** regime multipliers are ephemeral — applied per-day but never written
to `weight_memory.json`. Learned weights drift slowly; regime weights are daily overlays.

---

## 3. Agent Roster

| Agent               | Role                                                    |
|---------------------|---------------------------------------------------------|
| risk_macro          | Macro risk: VIX, FII flows, crude, INR, RBI             |
| fundamentals        | Quarterly financials, revenue, margins, EPS             |
| sales_demand        | Vehicle sales data (FADA / SIAM / VAHAN), demand trends |
| sentiment           | News NLP, analyst ratings, social signals               |
| pattern_analysis    | Technical patterns, RSI, MACD, Bollinger Bands          |
| competitive_intel   | Peer OEM price/volume comparison, market share          |
| valuation_catalyst  | P/E, EV/EBITDA, upcoming catalysts                      |
| raw_materials       | Crude, steel, aluminium, rubber, palladium input costs  |
| policy_regulatory   | GST, EV mandates, import duties, CAFE norms             |

---

## 4. Regime Detection (P5)

### Signals

| Signal          | Source        | Ticker      | Fallback | Meaning                               |
|-----------------|---------------|-------------|----------|---------------------------------------|
| India VIX       | yfinance      | ^INDIAVIX   | 17.0      | Market fear gauge                     |
| FII Proxy (5d)  | yfinance      | ^NSEI       | 0.0      | Nifty 50 five-day momentum as FII proxy|
| Sector RSI(14)  | yfinance      | ^CNX*       | 50.0     | Wilder EWM RSI on sector index        |

### Thresholds

| Threshold                  | Value  |
|----------------------------|--------|
| VIX volatile (high-vol)    | > 22   |
| VIX calm (low-vol)         | < 14   |
| FII proxy threshold        | ±1.0%  |
| RSI overbought             | > 70   |
| RSI oversold               | < 30   |

### Classification Rules (priority order — first match wins)

| Priority | Label              | Condition                                        | Intent                                     |
|----------|--------------------|--------------------------------------------------|--------------------------------------------|
| 1        | MACRO_CRISIS       | VIX > 22  AND  Nifty-5d < −1.0%                  | Elevate macro risk; discount demand & sentiment |
| 2        | RISK_OFF           | VIX > 22  OR  (14≤VIX≤22 AND Nifty-5d < −1.0%)   | Upweight macro risk; slight discount on demand |
| 3        | MOMENTUM_EXTENDED  | VIX < 14  AND  Nifty-5d > +1.0%  AND  Sector RSI > 70 | Pattern analysis up (mean-reversion); sentiment down |
| 4        | RISK_ON            | VIX < 22  AND  Nifty-5d > +1.0%  AND  Sector RSI < 70 | Elevate fundamentals, demand, sentiment    |
| 5        | OVERSOLD           | Sector RSI < 30  (macro-independent)             | Pattern analysis strongly up (bounce detection) |
| 6        | NORMAL             | everything else                                  | Base learned weights; no adjustment        |

### Sector RSI Tickers

| Sector          | RSI Ticker    |
|-----------------|---------------|
| automobile      | ^CNXAUTO      |
| banking_bfsi    | ^NSEBANK      |
| it_sector       | ^CNXIT        |
| renewable_energy | ^CNXENERGY    |
| *(fallback)*    | ^NSEI         |

---

## 5. Regime Multiplier Table (P5)

Applied on top of learned `WeightMemory` weights, then renormalised to sum = 1.0.
Formula: `effective_weight[agent] = learned[agent] × multiplier[agent] / Σ(all raw)`

| Agent               | MACRO_CRISIS        | RISK_OFF            | NORMAL              | RISK_ON             | MOMENTUM_EXTENDED   | OVERSOLD            |
|---------------------|----------------------|----------------------|----------------------|----------------------|----------------------|----------------------|
| risk_macro          | 1.40                | 1.20                | 1.00                | 0.90                | 0.85                | 1.10                |
| fundamentals        | 0.80                | 0.90                | 1.00                | 1.10                | 1.05                | 1.00                |
| sales_demand        | 0.70                | 0.85                | 1.00                | 1.10                | 0.95                | 1.00                |
| sentiment           | 0.80                | 0.90                | 1.00                | 1.15                | 0.80                | 0.90                |
| pattern_analysis    | 0.90                | 0.95                | 1.00                | 0.95                | 1.20                | 1.30                |
| competitive_intel   | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                |
| valuation_catalyst  | 0.90                | 0.95                | 1.00                | 1.10                | 1.10                | 1.05                |
| raw_materials       | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                |
| policy_regulatory   | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                | 1.00                |

**Reading the table:** values > 1.0 boost an agent's effective weight; < 1.0 discount it.
All 1.0 (NORMAL) = base learned weights, no adjustment.

---

## 6. P4 — Prompt Enhancement (miss_counter → Search Queries)

Runs once per **month-start** in `generate_forecast.py`.
Reads `miss_counter` from `LearningLedger`, takes top-3 missed factors,
maps them to extra RAG search queries injected into each agent's `_rag_retrieve()`.

Queries are cached per-cycle at:
`data/predictions/{sector}/{ticker}/{cycle_id}_prompt_enhancements.json`

### Miss Factor → Query Template Map

Placeholders: `{ticker}` `{date}` `{month}` `{year}`

| Miss Factor               | Agent           | Query Template                                          |
|---------------------------|-----------------|----------------------------------------------------------|
| FII_outflow_spike         | risk_macro      | {ticker} FII DII net flows provisional {date}            |
|                           | sentiment       | FII selling India equity {month} {year}                  |
| crude_oil_spot_price      | raw_materials   | Brent crude spot price today {date}                      |
|                           | risk_macro      | crude oil impact Indian automobile sector {month}        |
| RBI_policy_surprise       | risk_macro      | RBI MPC meeting upcoming schedule {year}                 |
|                           | fundamentals    | RBI repo rate decision impact auto loan rates            |
| INR_depreciation          | risk_macro      | USD INR exchange rate {date}                             |
|                           | raw_materials   | INR depreciation impact import cost automobile {year}    |
| month_end_inventory_flush | sales_demand    | {ticker} dealer inventory days channel check {month}     |

**Self-regulating:** if queries find the missing data, miss_count stays flat → factor falls
out of top-N next cycle → deprioritised automatically. No special reset code needed.

---

## 7. Weight Adaptation Config (P5 — RL core)

| Setting                    | Value  | Description                                   |
|----------------------------|--------|-----------------------------------------------|
| `WEIGHT_MAX_STEP           ` | 0.05   | Max weight change per daily step (per agent)  |
| `WEIGHT_MAX_DRIFT          ` | 0.15   | Max total drift from base weight              |
| `WEIGHT_MIN_OBSERVATIONS   ` | 3      | Min days before adaptation activates          |
| `WEIGHT_ACCURACY_WINDOW    ` | 7      | Rolling window (days) for hit-rate calc       |
| `WEIGHT_BOOST_HIT_RATE     ` | 0.7    | Hit-rate ≥ this → weight boost                |
| `WEIGHT_PENALTY_HIT_RATE   ` | 0.4    | Hit-rate ≤ this → weight penalty              |
| `FORECAST_HORIZON_DAYS     ` | 30     | Days forward to forecast on month-start       |

---

## 8. Key File Locations

| Component                  | File                                                           |
|----------------------------|----------------------------------------------------------------|
| Regime detector            | `core/intelligence/regime/detector.py`                         |
| Regime multipliers (config)| `core/config/settings/base.py` → `REGIME_MULTIPLIERS`          |
| PromptEnhancer             | `core/intelligence/prompt_enhancer/enhancer.py`                |
| Daily feedback loop        | `core/intelligence/rl/workflows/daily_review.py`               |
| Generate forecast          | `core/intelligence/rl/workflows/generate_forecast.py`          |
| Weight memory              | `core/intelligence/rl/stores/weight_memory.py`                 |
| Prediction store           | `core/intelligence/rl/stores/prediction_store.py`              |
| Ledger propagator          | `core/intelligence/rl/stores/ledger_propagator.py`             |
| Conviction tracker         | `core/intelligence/rl/conviction/tracker.py`                   |
| Seasonal calendar          | `core/intelligence/seasonal/calendar.py`                       |
| Schemas (all models)       | `core/schemas/feedback.py`                                     |

---

## 9. Data Flow Diagram

```
Month-start
  generate_forecast.py
       │
       ├─ SeasonalCalendar      → seasonal_context injected into prompts
       ├─ LearningLedger        → load existing lessons
       ├─ PromptEnhancer (P4)   → miss_counter → extra search queries per agent
       └─ 9 Agents run in parallel
              └─ BaseAgent._rag_retrieve() appends extra_queries[:2]
              └─ PredictionEnvelope saved

Daily (after close)
  daily_review.py
       │
       ├─ Step 0: RegimeDetector (P5) → RegimeSnapshot (VIX, FII, RSI → label)
       ├─ Step 1-4: Load → Fetch actual → Compute error → FeedbackAgent
       │             └─ regime narrative injected into market_context (non-NORMAL)
       ├─ Step 5: WeightAdapter → update weight_memory.json
       ├─ Step 5.5: apply_regime_multipliers → ephemeral effective weights
       ├─ Step 6: LearningLedger → merge lessons + propagate to sector peers (P2)
       ├─ Step 7: Revise remaining forecasts with regime_effective_weights
       └─ Step 8: Append to daily_feedback_log.json
```
