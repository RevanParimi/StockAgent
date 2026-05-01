"""
scripts/generate_rl_reference.py
==================================
Generates RL_REFERENCE.md from live source imports.

Run any time configs or templates change:
    python -m scripts.generate_rl_reference

Output: RL_REFERENCE.md (project root)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import settings
from core.intelligence.prompt_enhancer.enhancer import MISS_FACTOR_TO_QUERY_TEMPLATE
from core.intelligence.rl.conviction.tracker import STREAK_WARNING_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENTS: list[str] = [
    "risk_macro",
    "fundamentals",
    "sales_demand",
    "sentiment",
    "pattern_analysis",
    "competitive_intel",
    "valuation_catalyst",
    "raw_materials",
    "policy_regulatory",
]

REGIMES: list[str] = [
    "MACRO_CRISIS",
    "RISK_OFF",
    "NORMAL",
    "RISK_ON",
    "MOMENTUM_EXTENDED",
    "OVERSOLD",
]

REGIME_CONDITIONS: dict[str, str] = {
    "MACRO_CRISIS":       f"VIX > 22  AND  Nifty-5d < −1.0%",
    "RISK_OFF":           f"VIX > 22  OR  (14≤VIX≤22 AND Nifty-5d < −1.0%)",
    "MOMENTUM_EXTENDED":  f"VIX < 14  AND  Nifty-5d > +1.0%  AND  Sector RSI > 70",
    "RISK_ON":            f"VIX < 22  AND  Nifty-5d > +1.0%  AND  Sector RSI < 70",
    "OVERSOLD":           f"Sector RSI < 30  (macro-independent)",
    "NORMAL":             f"everything else",
}

REGIME_INTENT: dict[str, str] = {
    "MACRO_CRISIS":       "Elevate macro risk; discount demand & sentiment",
    "RISK_OFF":           "Upweight macro risk; slight discount on demand",
    "NORMAL":             "Base learned weights; no adjustment",
    "RISK_ON":            "Elevate fundamentals, demand, sentiment",
    "MOMENTUM_EXTENDED":  "Pattern analysis up (mean-reversion); sentiment down",
    "OVERSOLD":           "Pattern analysis strongly up (bounce detection)",
}


def _multiplier_table() -> str:
    m = settings.REGIME_MULTIPLIERS
    col_w = 20

    header = "| Agent               |" + "".join(f" {r:<{col_w}}|" for r in REGIMES)
    sep    = "|---------------------|" + "".join(f"-{'-'*col_w}-|" for r in REGIMES)
    rows   = []
    for agent in AGENTS:
        cells = "".join(
            f" {m.get(regime, {}).get(agent, 1.0):<{col_w}.2f}|"
            for regime in REGIMES
        )
        rows.append(f"| {agent:<19} |{cells}")

    return "\n".join([header, sep, *rows])


def _template_table() -> str:
    lines = ["| Miss Factor               | Agent           | Query Template                                          |",
             "|---------------------------|-----------------|----------------------------------------------------------|"]
    for factor, agent_map in MISS_FACTOR_TO_QUERY_TEMPLATE.items():
        for i, (agent, template) in enumerate(agent_map.items()):
            f_col = factor if i == 0 else ""
            lines.append(f"| {f_col:<25} | {agent:<15} | {template:<56} |")
    return "\n".join(lines)


def _weight_config_table() -> str:
    rows = [
        ("WEIGHT_MAX_STEP",           settings.WEIGHT_MAX_STEP,          "Max weight change per daily step (per agent)"),
        ("WEIGHT_MAX_DRIFT",          settings.WEIGHT_MAX_DRIFT,         "Max total drift from base weight"),
        ("WEIGHT_MIN_OBSERVATIONS",   settings.WEIGHT_MIN_OBSERVATIONS,  "Min days before adaptation activates"),
        ("WEIGHT_ACCURACY_WINDOW",    settings.WEIGHT_ACCURACY_WINDOW,   "Rolling window (days) for hit-rate calc"),
        ("WEIGHT_BOOST_HIT_RATE",     settings.WEIGHT_BOOST_HIT_RATE,    "Hit-rate ≥ this → weight boost"),
        ("WEIGHT_PENALTY_HIT_RATE",   settings.WEIGHT_PENALTY_HIT_RATE,  "Hit-rate ≤ this → weight penalty"),
        ("FORECAST_HORIZON_DAYS",     settings.FORECAST_HORIZON_DAYS,    "Days forward to forecast on month-start"),
    ]
    lines = ["| Setting                    | Value  | Description                                   |",
             "|----------------------------|--------|-----------------------------------------------|"]
    for name, val, desc in rows:
        lines.append(f"| `{name:<26}` | {str(val):<6} | {desc:<45} |")
    return "\n".join(lines)


def _regime_signal_table() -> str:
    lines = [
        "| Signal          | Source        | Ticker      | Fallback | Meaning                               |",
        "|-----------------|---------------|-------------|----------|---------------------------------------|",
        f"| India VIX       | yfinance      | ^INDIAVIX   | {settings.VIX_FALLBACK:.1f}      | Market fear gauge                     |",
        f"| FII Proxy (5d)  | yfinance      | ^NSEI       | {settings.FII_PROXY_FALLBACK:.1f}      | Nifty 50 five-day momentum as FII proxy|",
        f"| Sector RSI(14)  | yfinance      | ^CNX*       | {settings.RSI_FALLBACK:.1f}     | Wilder EWM RSI on sector index        |",
    ]
    return "\n".join(lines)


def _sector_ticker_table() -> str:
    lines = ["| Sector          | RSI Ticker    |",
             "|-----------------|---------------|"]
    for sector, ticker in settings.REGIME_SECTOR_TICKERS.items():
        lines.append(f"| {sector:<15} | {ticker:<13} |")
    lines.append(f"| *(fallback)*    | {settings.REGIME_SECTOR_FALLBACK_TICKER:<13} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

def build_document() -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# RL Reference — StockAI Adaptive Prediction Loop

> Auto-generated {ts} by `scripts/generate_rl_reference.py`
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

Runs every weekday at **16:30 IST / 11:00 UTC** via cron (`{settings.FEEDBACK_CRON}`).

```
Step 0   RegimeDetector → classify market (VIX / FII proxy / Sector RSI)
Step 1   Load PredictionEnvelope → predicted_close + assumptions
Step 2   Fetch actual closing price via yfinance
Step 3   Compute error metrics (price_error_pct, direction_correct)
Step 4   FeedbackAgent → miss_type + miss analysis + raw lessons
         └─ Inject streak warning if ConvictionStreak ≥ {STREAK_WARNING_THRESHOLD}
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

{_regime_signal_table()}

### Thresholds

| Threshold                  | Value  |
|----------------------------|--------|
| VIX volatile (high-vol)    | > {settings.VIX_VOLATILE_THRESHOLD:.0f}   |
| VIX calm (low-vol)         | < {settings.VIX_LOW_VOL_THRESHOLD:.0f}   |
| FII proxy threshold        | ±{settings.FII_PROXY_THRESHOLD_PCT:.1f}%  |
| RSI overbought             | > {settings.RSI_OVERBOUGHT:.0f}   |
| RSI oversold               | < {settings.RSI_OVERSOLD:.0f}   |

### Classification Rules (priority order — first match wins)

| Priority | Label              | Condition                                        | Intent                                     |
|----------|--------------------|--------------------------------------------------|--------------------------------------------|
| 1        | MACRO_CRISIS       | {REGIME_CONDITIONS["MACRO_CRISIS"]:<48} | {REGIME_INTENT["MACRO_CRISIS"]:<42} |
| 2        | RISK_OFF           | {REGIME_CONDITIONS["RISK_OFF"]:<48} | {REGIME_INTENT["RISK_OFF"]:<42} |
| 3        | MOMENTUM_EXTENDED  | {REGIME_CONDITIONS["MOMENTUM_EXTENDED"]:<48} | {REGIME_INTENT["MOMENTUM_EXTENDED"]:<42} |
| 4        | RISK_ON            | {REGIME_CONDITIONS["RISK_ON"]:<48} | {REGIME_INTENT["RISK_ON"]:<42} |
| 5        | OVERSOLD           | {REGIME_CONDITIONS["OVERSOLD"]:<48} | {REGIME_INTENT["OVERSOLD"]:<42} |
| 6        | NORMAL             | {REGIME_CONDITIONS["NORMAL"]:<48} | {REGIME_INTENT["NORMAL"]:<42} |

### Sector RSI Tickers

{_sector_ticker_table()}

---

## 5. Regime Multiplier Table (P5)

Applied on top of learned `WeightMemory` weights, then renormalised to sum = 1.0.
Formula: `effective_weight[agent] = learned[agent] × multiplier[agent] / Σ(all raw)`

{_multiplier_table()}

**Reading the table:** values > 1.0 boost an agent's effective weight; < 1.0 discount it.
All 1.0 (NORMAL) = base learned weights, no adjustment.

---

## 6. P4 — Prompt Enhancement (miss_counter → Search Queries)

Runs once per **month-start** in `generate_forecast.py`.
Reads `miss_counter` from `LearningLedger`, takes top-{settings.SERPER_MAX_QUERIES} missed factors,
maps them to extra RAG search queries injected into each agent's `_rag_retrieve()`.

Queries are cached per-cycle at:
`data/predictions/{{sector}}/{{ticker}}/{{cycle_id}}_prompt_enhancements.json`

### Miss Factor → Query Template Map

Placeholders: `{{ticker}}` `{{date}}` `{{month}}` `{{year}}`

{_template_table()}

**Self-regulating:** if queries find the missing data, miss_count stays flat → factor falls
out of top-N next cycle → deprioritised automatically. No special reset code needed.

---

## 7. Weight Adaptation Config (P5 — RL core)

{_weight_config_table()}

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
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    out = ROOT / "RL_REFERENCE.md"
    out.write_text(build_document(), encoding="utf-8")
    print(f"Generated: {out}")


if __name__ == "__main__":
    main()
