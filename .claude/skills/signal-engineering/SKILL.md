---
name: signal-engineering
description: Use for designing signals, combining them, weighting them, backtesting, walk-forward validation, regime-aware logic, signal conflict resolution, factor design, alpha decay analysis, or any work where the deliverable is a quantitative signal or a method for producing one. Triggers: signal, factor, alpha, backtest, walk-forward, sharpe, drawdown, regime, signal aggregation, ensemble, conflict resolution, lookback, lookahead bias.
---

# Signal Engineering

How signals get designed, combined, validated, and surfaced. The skill that ensures the tool produces signals that hold up out-of-sample, not just on the training data.

Read `PROJECT.md` for asset scope, time horizons supported, and current signal taxonomy.

## North star

A signal that worked in backtest but fails live almost always failed because of one of three things: lookahead bias, overfitting, or regime change. Engineer against all three from day one. A small honest backtest beats a large dishonest one.

## Signal taxonomy

Signals fall into broad families. A multi-asset tool needs at least these:

- **Fundamental** — earnings, growth, valuation ratios, balance sheet health, sector-specific KPIs (NIM/CASA for banks, ARR for IT, same-store sales for retail).
- **Technical** — price/volume patterns, moving averages, RSI/MACD/ADX, volatility, support/resistance, breakouts.
- **Derivatives** — OI buildup/unwinding, PCR, IV percentile, max pain, futures premium/discount, options skew.
- **Flow** — FII/DII daily and cumulative, block deals, MF holdings changes, promoter buying/selling, pledge changes.
- **Macro** — RBI policy, inflation, currency, commodity prices, global cues, yield curve.
- **Sentiment** — news polarity, social media, analyst revisions, search trends. Hardest to validate; easiest to fool yourself with.
- **Event** — corporate actions, results, regulatory changes, expiry effects, index inclusion/exclusion.

Tag every signal with its family, time horizon (intraday/swing/positional/long-term), asset applicability, and required data sources.

## Signal design rules

**Definition before code.** Write down what the signal is, why it should work, what it predicts (direction, magnitude, probability), over what horizon, with what expected hit rate. If you can't write this in three sentences, the signal isn't ready to code.

**Lookahead bias is the silent killer.** Every signal at time `t` uses only data available at time `t`. Earnings announced after market close on Tuesday are not available for Tuesday's signal — they're Wednesday's data at earliest. Point-in-time data is the only honest data.

**Survivorship bias.** Backtests on the current Nifty 50 ignore the stocks that fell out of it. Use the historical index composition, not today's.

**Sample size.** A signal that fired 12 times in 5 years has no statistical meaning. Either widen the universe, lengthen the window, or accept that you have a hypothesis, not a signal.

## Combining signals

Three honest patterns:

1. **Voting / consensus** — multiple signals agree → higher confidence. Simple, transparent, robust. Default starting point.
2. **Weighted score** — each signal gets a weight, score is a linear combination. Weights from theory or in-sample optimization (with walk-forward validation, never on the test set).
3. **Conditional / regime-aware** — different signal weights in different regimes. Most powerful, most prone to overfitting. Needs the strongest validation discipline.

What does *not* work as well as people think: stacking ensembles trained on backtest data, neural-net combinations of signals, "let the model figure it out." These overfit aggressively in finance.

## Conflict resolution

When two signals disagree (technical says buy, fundamental says expensive), don't average them into mush. Define the resolution rule explicitly: which signal dominates, in which regime, with what confidence threshold. Document the rule. When the rule fails, you have a debuggable failure, not a vague one.

For a multi-sector tool: cross-sector aggregation needs explicit logic. Bank Nifty bullish + IT bearish + Auto bullish ≠ "market bullish." Sector weights, sector rotation signals, and macro overrides need their own layer above individual stock signals.

## Backtesting discipline

- **Train/validation/test split.** Train on the oldest data, validate on middle, test on most recent. Touch the test set once, at the end. Touching it twice contaminates everything.
- **Walk-forward** is the honest validation. Train on 2018-2020, validate on 2021. Train on 2018-2021, validate on 2022. Train on 2018-2022, validate on 2023. Performance averaged across folds.
- **Realistic costs.** Brokerage, STT, exchange fees, GST, slippage. Slippage is the easiest to underestimate. Liquid stocks at small size: maybe 5 bps. Illiquid stocks or large size: 50+ bps. Options can be brutal.
- **Realistic execution.** You don't get the open price. You don't get the close price. Build in execution delay matching the strategy's time horizon.
- **Multiple metrics.** Sharpe is not enough. Look at max drawdown, drawdown duration, Calmar, hit rate, average win vs average loss, worst month. A 1.5 Sharpe with 40% drawdown is unfundable.

## Live vs backtest divergence

When the live signal underperforms the backtest, run through this in order:

1. Lookahead bias — did production data arrive at the same lag as backtest data?
2. Survivorship — did backtest universe include delisted/excluded names that production doesn't see?
3. Costs — are real fills matching backtest assumptions?
4. Regime — has the market regime shifted since the backtest window?
5. Overfitting — did the signal work only on the specific historical window tested?
6. Bug — did the live implementation diverge from the backtest implementation?

In most cases the answer is some combination of 1, 3, and 5.

## Alpha decay

Every signal degrades. Once a signal is widely known, it stops working. Build decay tracking: rolling 3-month performance vs full-sample performance, p-value of recent vs historical hit rate. When decay is statistically significant, the signal needs retiring or restructuring.

## What to log per signal

Signal name and version, asset, timestamp generated, timestamp valid-for, raw inputs, transformed features, output (direction/score/probability), confidence, regime context. This is the minimum required to debug a signal in production six months later.

## Hand-off triggers

- Task involves market mechanics, instruments, or compliance for the signal output → also load `market-domain`
- Task involves an LLM generating signal explanations or rationales → also load `ai-engineer`
- Task involves the storage, retrieval, or scaling of signal data → also load `system-design-engineer`
- Task is "the live signal is wrong / different from backtest" → also load `support-engineer`

---

## This project

### Current signal architecture

StockAgent uses **LLM-as-scorer** — each specialist agent fetches real-time data, then an LLM reads it and scores 5 domain-specific dimensions (0.0–1.0). The 5 dimension scores collapse into one `overall_score` per agent. No pure-quant signal computation beyond technical indicators.

### Automobile sector — active signal taxonomy

| Agent | Signal family | 5 dimensions scored |
|---|---|---|
| `sales_demand` | Fundamental/Flow | FADA/SIAM dispatch, EV Vahan, dealer inventory, exports, used-car price index |
| `raw_materials` | Macro | Steel/aluminium, platinum/palladium, crude/polymer, power tariff, commodity trend |
| `fundamentals` | Fundamental | Revenue/EBITDA delta, margin vs peers, order book, attrition/headcount, FII/DII flow |
| `pattern_analysis` | Technical | Price cycle position, seasonality, RSI/MACD/BB, breakout zones, peer correlation |
| `sentiment` | Sentiment | News NLP, management tone, Twitter/Reddit, YouTube spikes, dealer feedback |
| `policy_regulatory` | Event/Policy | FAME EV subsidy, emission norms, Union Budget duties, PLI scheme, state EV incentives |
| `competitive_intel` | Fundamental | EV market share, new model pipeline, JVs, ADAS ratings, competitive position |
| `risk_macro` | Macro | INR/USD/crude exposure, commodity prices, RBI repo/EMI, emission risk, geopolitical |
| `valuation_catalyst` | Fundamental/Technical | PE discount vs peers, technical trend, mean reversion, support zone, recovery signal |

### Live weights (from `sectors/automobile/registry.py` — authoritative)

| Agent | Weight |
|---|---|
| fundamentals | 0.18 |
| sales_demand | 0.16 |
| risk_macro | 0.13 |
| pattern_analysis | 0.12 |
| raw_materials | 0.09 |
| policy_regulatory | 0.09 |
| competitive_intel | 0.09 |
| valuation_catalyst | 0.10 |
| sentiment | 0.04 |

> Note: `config/settings/base.py` has slightly different weights — they're used only as a fallback in `SignalAggregator` when no `learned_weights` are passed. The registry weights are what the LangGraph graph actually uses.

### Conflict resolution (live implementation)

- **Threshold:** `CONFLICT_THRESHOLD = 0.30` (in both `core/graphs/rails.py` and `pipeline/signal_aggregator.py`)
- **Detection:** `conflict_rail()` — all pairs checked, any delta > 0.30 flags a conflict
- **Resolution:** LLM called with conflict pairs + all agent summaries; produces adjusted scores and explicit reasoning
- **Output:** `FinalReport.conflicts_resolved[]` — list of conflict explanations surfaced to user

### Technical indicators (computed, not LLM-scored)

Located in `core/intelligence/algorithms/indicators/fetcher.py`:
- RSI(14), MACD(12,26,9), Bollinger Bands(20, 2σ)
- Support/resistance (rolling 20-period)
- Seasonal monthly return patterns
- Peer correlation and beta vs `^CNXAUTO`
- Golden/death cross detection (50 vs 200 DMA)
- C++ extension (`stockindicators`) used if compiled; falls back to pure Python

### Verdict mapping (score → verdict)

| Score range | Verdict |
|---|---|
| 0.75 – 1.00 | STRONG BUY |
| 0.55 – 0.75 | BUY |
| 0.40 – 0.55 | NEUTRAL |
| 0.20 – 0.40 | SELL |
| 0.00 – 0.20 | STRONG SELL |

### RL feedback loop (Phase 5 — not yet active)

- Design: `intelligence/rl/` — adaptive weight learning based on prediction accuracy
- Mechanism: `WeightMemory` tracks agent direction accuracy over rolling 7-day window; boosts weight if hit rate ≥70%, penalises if ≤40%
- Max weight change per step: 0.05; max drift from base: 0.15
- **Not running** — `RL_ENABLED` defaults to false

### What's missing for honest signal validation

- No train/test split on historical verdicts
- No walk-forward backtest harness
- No alpha decay tracking
- No regime detection layer
- Backtesting is the biggest open gap before this tool can be trusted quantitatively
