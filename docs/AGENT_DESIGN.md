# Agent Design Reference — Automobile Agent

> Last updated: 2026-04-17
> Automobile: 8 active agents (legacy ThreadPoolExecutor + new LangGraph graph)
> Banking/BFSI, IT Sector, Renewable Energy: LangGraph graphs only (see Section 10–12)

---

## 1. Architecture Overview

```
                        AUTOMOBILE AGENT
                              │
          ┌───────────────────┼───────────────────┐
          │          ThreadPoolExecutor            │
          │       (all agents run in parallel)     │
          │                                        │
    ┌─────┴──────┐  ┌──────────┐  ┌─────────────┐ │
    │Sales&Demand│  │   Raw    │  │ Financial & │ │
    │  (Serper)  │  │Materials │  │   Market    │ │
    └────────────┘  │(yfinance)│  │ (yfinance + │ │
                    └──────────┘  │   Serper)   │ │
    ┌────────────┐                └─────────────┘ │
    │  Pattern   │  ┌──────────┐  ┌─────────────┐ │
    │ Analysis   │  │ Policy & │  │ Competitive │ │
    │ (yfinance) │  │Regulatory│  │    Intel    │ │
    └────────────┘  │(Tavily + │  │  (Serper)   │ │
                    │ Serper)  │  └─────────────┘ │
    ┌────────────┐  └──────────┘                  │
    │ Risk&Macro │                                 │
    │(yfinance + │──────────────────────────────── ┘
    │  Serper /  │
    │macro cache)│
    └────────────┘
          │
    ┌─────┴──────┐
    │  Signal    │
    │ Aggregator │  ← weighted fusion + conflict resolution (LLM)
    └─────┬──────┘
          │
    ┌─────┴──────┐
    │  Final     │
    │  Report    │  verdict + score + investment thesis
    └────────────┘
```

---

## 2. Per-Agent Design

### 2.1 Sales & Demand Agent
**Purpose:** Retail dispatch velocity and demand-side signals.

| Item | Detail |
|---|---|
| `agent_name` | `sales_demand` |
| Weight | 0.18 |
| Data sources | Serper (3 calls) |
| Context tokens | ~825 |
| Prompt + output | ~800 |
| Total tokens | **~1,625** |
| LLM calls | 1 |

**Sub-scores:**
- `fada_siam_dispatch` — wholesale vs retail trend
- `ev_segment_vahan` — EV registration growth
- `dealer_inventory` — channel inventory health
- `export_import` — DGFT export volume
- `used_car_price_index` — Cars24/CarDekho demand proxy

---

### 2.2 Raw Materials Agent *(new)*
**Purpose:** Input cost pressure from metals, energy, and commodities affecting OEM margins.

| Item | Detail |
|---|---|
| `agent_name` | `raw_materials` |
| Weight | 0.10 |
| Data sources | yfinance (Steel SLX, Aluminium AA, Platinum PPLT, Palladium PALL, Crude CL=F) + Serper (1 call: power tariff) |
| Context tokens | ~495 |
| Prompt + output | ~800 |
| Total tokens | **~1,295** |
| LLM calls | 1 |

**Sub-scores:**
- `steel_aluminium` — body/frame cost pressure
- `platinum_palladium` — catalytic converter cost (ICE OEMs)
- `crude_oil_polymer` — polymer/rubber cost + fuel price signal
- `power_tariff` — EV TCO impact via electricity cost
- `commodities_trend` — overall 3-month direction composite

---

### 2.3 Financial & Market Agent
**Purpose:** Fundamental financial performance and capital market signals.

| Item | Detail |
|---|---|
| `agent_name` | `fundamentals` |
| Weight | 0.20 |
| Data sources | yfinance (quarterly financials, shareholding, company info) + Serper (2 calls) |
| Context tokens | ~1,320 |
| Prompt + output | ~900 |
| Total tokens | **~2,220** |
| LLM calls | 1 |

**Sub-scores:**
- `revenue_ebitda_delta` — QoQ/YoY revenue and margin trajectory
- `margin_vs_peers` — EBITDA margin vs sector peers
- `order_book_pipeline` — volume growth, geo mix, market share
- `attrition_headcount` — employee signal (proxy for capex/growth intent)
- `promoter_fii_dii_flow` — institutional conviction signal

---

### 2.4 Pattern Analysis Agent
**Purpose:** Technical price cycle, momentum, and mean-reversion signals.

| Item | Detail |
|---|---|
| `agent_name` | `pattern_analysis` |
| Weight | 0.13 |
| Data sources | yfinance only (0 Serper calls) |
| Context tokens | ~440 |
| Prompt + output | ~800 |
| Total tokens | **~1,240** |
| LLM calls | 1 |

**Sub-scores:**
- `price_cycle_position` — 10yr historical cycle phase
- `seasonal_pattern` — month-of-year return averages
- `rsi_macd_bb` — RSI(14), MACD crossover, Bollinger %B
- `breakout_support_zone` — distance from support/resistance
- `peer_correlation` — beta and Pearson corr vs Nifty Auto

---

### 2.5 Policy & Regulatory Agent *(new)*
**Purpose:** Government policy signals — EV subsidies, emission norms, budgetary incentives.

| Item | Detail |
|---|---|
| `agent_name` | `policy_regulatory` |
| Weight | 0.10 |
| Data sources | **Tavily** (2 calls: FAME/EV subsidy, emission norms) + Serper (3 calls: budget duties, PLI, state EV) |
| Context tokens | ~2,825 |
| Prompt + output | ~900 |
| Total tokens | **~3,725** |
| LLM calls | 1 |

**Why Tavily here?** FAME circular PDFs and BS7/CAFE regulation documents contain tabular data and exact disbursement figures that a 2-line snippet misses. Full-page extraction materially improves LLM accuracy on this agent.

**Sub-scores:**
- `fame_ev_subsidy` — FAME II/III disbursement pace and OEM eligibility
- `emission_norms` — BS7/CAFE compliance risk or opportunity
- `union_budget_duties` — component duty changes impacting BOM cost
- `pli_scheme` — PLI utilization and incentive realization
- `state_ev_incentives` — state-level EV incentive coverage for target markets

---

### 2.6 Competitive Intel Agent *(new)*
**Purpose:** EV competitive landscape, model launches, M&A, and safety ratings.

| Item | Detail |
|---|---|
| `agent_name` | `competitive_intel` |
| Weight | 0.10 |
| Data sources | Serper (4 calls: EV share, model launches, JV/M&A, ADAS/NCAP) |
| Context tokens | ~1,100 |
| Prompt + output | ~800 |
| Total tokens | **~1,900** |
| LLM calls | 1 |

**Sub-scores:**
- `ev_market_share` — Tata/BYD/Ather/Ola/MG relative positioning
- `new_model_pipeline` — upcoming launches and pricing strategy
- `jv_acquisitions` — partnerships and M&A signals
- `adas_safety_ratings` — BNAP/NCAP scores vs peers
- `competitive_position` — overall relative moat assessment

---

### 2.7 Risk & Macro Agent
**Purpose:** Macro-economic and geopolitical risk factors.

| Item | Detail |
|---|---|
| `agent_name` | `risk_macro` |
| Weight | 0.15 |
| Data sources | yfinance (macro tickers) + Serper (3 calls — **cached via micro loop**) |
| Context tokens | ~1,125 (cache HIT) / ~1,925 (cache MISS) |
| Prompt + output | ~800 |
| Total tokens | **~1,925 / ~1,100** |
| LLM calls | 1 |

**Cache behaviour:** The 3 Serper calls (INR/USD, commodities, RBI repo) are sector-level — same result for MARUTI as TATAMOTORS on the same day. The micro search loop pre-fetches these every 4 hours and stores them in `tools/macro_cache.py`. Cache HIT saves 3 Serper calls per analysis.

**Sub-scores:**
- `inr_usd_crude_exposure` — currency and oil price risk
- `commodity_prices` — input cost macro direction
- `rbi_repo_emi_impact` — interest rate effect on auto loan demand
- `emission_policy_risk` — overlap with policy agent (macro angle)
- `geopolitical_china_risk` — component import dependency risk

---

## 3. Token Budget Summary

| Agent | Context | Prompt | Output | **Total** |
|---|:---:|:---:|:---:|:---:|
| sales_demand | 825 | 300 | 500 | **1,625** |
| raw_materials | 495 | 300 | 500 | **1,295** |
| fundamentals | 1,320 | 300 | 600 | **2,220** |
| pattern_analysis | 440 | 300 | 500 | **1,240** |
| policy_regulatory | 2,825 | 300 | 600 | **3,725** |
| competitive_intel | 1,100 | 300 | 500 | **1,900** |
| risk_macro (warm) | 1,125 | 300 | 500 | **1,925** |
| signal_aggregator | 400 | 300 | 600 | **1,300** |
| **TOTAL per run** | | | | **~15,230** |

Groq free tier: 6,000 tokens/min. At 1 ticker per 3 minutes → well within limit.

---

## 4. Agent Weights

```python
AGENT_WEIGHTS = {
    "sales_demand":      0.18,   # retail velocity
    "raw_materials":     0.10,   # input cost pressure
    "fundamentals":      0.20,   # financial performance (highest weight)
    "pattern_analysis":  0.13,   # technicals
    "sentiment":         0.04,   # legacy — kept for backward compat
    "policy_regulatory": 0.10,   # policy tailwinds/headwinds
    "competitive_intel": 0.10,   # competitive moat
    "risk_macro":        0.15,   # macro risk
}
# Sum = 1.00
```

---

## 5. Data Flow — The 3-Source Architecture

```
Each agent context string assembled by ContextBuilder.build(agent_name, query)

    yfinance (free, unlimited)
    ─────────────────────────
    Price OHLCV → RSI/MACD/BB/support/resistance
    Quarterly P&L → revenue, EBITDA, QoQ/YoY
    Company info → P/E, P/B, market cap
    Macro tickers → crude, INR/USD, steel ETF, aluminium
    Metal ETFs → PPLT (platinum), PALL (palladium), SLX (steel), AA (aluminium)
    Peer data → correlation + beta vs ^CNXAUTO

    Serper (2,500/month)
    ─────────────────────
    Returns: title + 2-line snippet + URL per result
    Used by: Sales, Raw Materials, Financial, Competitive Intel, Risk & Macro
    Capped: 3 queries per agent (SERPER_MAX_QUERIES=3)
    Risk & Macro: 3 queries cached via macro_cache → saves 3 calls when warm

    Tavily (1,000/month)
    ─────────────────────
    Returns: full extracted page text (~800-1500 tokens per call)
    Used by: Policy & Regulatory agent ONLY (2 calls per analysis)
    Reason: FAME circulars, BS7/CAFE standards need full document text
```

---

## 6. Serper Call Audit (per full analysis)

| Agent | Queries | Cacheable? | Net calls (warm) |
|---|:---:|:---:|:---:|
| sales_demand | 3 | No (company-specific) | 3 |
| raw_materials | 1 | No (power tariff = generic) | 1 |
| fundamentals | 2 | No (company-specific) | 2 |
| pattern_analysis | 0 | — | 0 |
| policy_regulatory | 3 | Partly (budget/PLI = sector) | 3 |
| competitive_intel | 4 | No (company-specific) | 4 |
| risk_macro | 3 | **Yes → macro cache** | **0 (warm)** |
| **Total** | **16** | | **13 (warm) / 16 (cold)** |

> With `SERPER_MAX_QUERIES=3` cap and warm cache: **9 Serper calls per analysis** in steady state.
> Actual max (all agents hit limit): 16 calls/analysis → 1,760/month for 110 analyses → still under 2,500 limit.

---

## 10. Banking & BFSI Sector Agents

**Graph:** `graphs/banking_bfsi/graph.py` | **Entry:** `langgraph.json → "banking_bfsi"`

**Architecture:** 6 specialist agents in parallel → Signal Aggregator → FinalReport

```
START → resolve_ticker → input_rail → [Send × 6] → run_agent (parallel)
      → aggregate → END
```

### Agent Registry

| Agent | `agent_name` | Weight | Key dimensions |
|---|---|:---:|---|
| Fundamentals | `fundamentals` | **0.25** | NPA/NIM/CASA/CRAR/RoA |
| Risk | `risk` | **0.20** | Asset quality trend, concentration, deposit stability |
| Macro & Policy | `macro_policy` | **0.20** | RBI MPC, system credit growth, SEBI circulars |
| Institutional | `institutional` | **0.15** | FII/DII flows, promoter stake, insider trades |
| Pattern Analysis | `pattern_analysis` | **0.15** | 10yr cycle, rate-cut seasonality, RSI/MACD/BB |
| Universe Setup | `universe_setup` | **0.05** | Index weight, peer grouping, corporate actions |

### Sub-score definitions

**Fundamentals:**
- `asset_quality` — Gross/Net NPA %, PCR
- `net_interest` — NIM 8-quarter trend, CASA ratio
- `capital_adequacy` — CRAR/CET1 vs RBI floor
- `profitability` — RoA, RoE, credit cost, cost-to-income
- `loan_mix` — Retail/corporate split, secured/unsecured, MSME %

**Risk:**
- `asset_quality_trend` — SMA slippage, restructured book
- `concentration_risk` — Top-5 borrower exposure
- `deposit_stability` — Wholesale deposit %, CASA trend
- `regulatory_risk` — RBI/SEBI penalties pending
- `macro_sensitivity` — Rate sensitivity, FX exposure

**Macro & Policy:**
- `rbi_rate_cycle` — Repo rate trajectory, MPC stance
- `system_credit` — System credit/deposit growth YoY
- `liquidity_conditions` — LAF corridor, CRR/SLR impact
- `regulatory_actions` — Recent circulars, IRDAI
- `fiscal_policy` — Govt borrowing, PSU bank recap, IBC pace

**Institutional:**
- `fii_dii_flow` — Net buying 1M/3M windows
- `promoter_holding` — Stake change, pledge %
- `insider_trades` — ESOP exercises, open-market trades
- `analyst_changes` — Rating upgrades/downgrades
- `institutional_conc` — MF holding %, top-10 ownership

**Pattern Analysis:**
- `price_cycle` — 10yr cycle position, rate-cut rally seasonality
- `momentum` — RSI(14d), MACD, Bollinger Band position
- `breakout_zones` — Support/resistance vs Nifty Bank
- `relative_strength` — Performance vs Nifty Bank/PSU Bank
- `volume_pattern` — OBV trend, accumulation/distribution

**Universe Setup:**
- `index_weight` — Nifty Bank / PSU Bank weight
- `peer_positioning` — Rank vs PSU/Private/SFB/NBFC peers
- `market_cap_tier` — Large/mid/small, free-float
- `corporate_actions` — Splits, bonuses, rights, mergers
- `rebalancing_risk` — Index inclusion/exclusion probability

### Context gap (known limitation)
`ContextBuilder` does not yet route BFSI agent names → all 6 agents receive the stub context fallback until sector-specific fetchers are added. Priority order for phase-2 data wiring: `fundamentals` (yfinance NPA proxy) → `macro_policy` (RBI MPC scraper) → `pattern_analysis` (yfinance only, zero effort).

---

## 11. IT Sector Agents

**Graph:** `graphs/it_sector/graph.py` | **Entry:** `langgraph.json → "it_sector"`

**Architecture:** 8 specialist agents in parallel → Signal Aggregator → FinalReport

### Agent Registry

| Agent | `agent_name` | Weight | Key dimensions |
|---|---|:---:|---|
| Fundamentals | `fundamentals` | **0.25** | Revenue growth, EBIT margin, TCV, attrition |
| Global Macro | `global_macro` | **0.20** | US tech spend, Fed rates, USD/INR, US-China risk |
| Risk & Macro | `risk_macro` | **0.15** | H1B/L1 visa, AI disruption, client concentration |
| Peer Benchmark | `peer_benchmark` | **0.15** | TCS/Infosys/HCL/Wipro relative metrics |
| Pattern Analysis | `pattern_analysis` | **0.10** | 10yr cycles, RSI/MACD/BB, Nifty IT correlation |
| Sentiment | `sentiment` | **0.08** | AI narrative, layoff signals, management tone |
| Transcript NLP | `transcript_nlp` | **0.04** | Earnings call language, guidance tone |
| Insider/Smart Money | `insider_smart_money` | **0.03** | Promoter activity, smart money flow, block deals |

### Sub-score definitions (selected)

**Fundamentals:** `revenue_growth` · `ebit_margins` · `deal_wins` · `attrition` · `valuation`

**Global Macro:** `us_tech_spend` · `fed_rate_impact` · `usd_inr` · `geopolitical` · `ma_activity`

**Risk & Macro:** `visa_risk` · `ai_disruption` · `client_concentration` · `fx_hedge` · `talent_risk`

**Peer Benchmark:** `revenue_growth_rank` · `margin_rank` · `deal_momentum_rank` · `return_metrics_rank` · `valuation_gap`

**Transcript NLP:** `guidance_tone` · `demand_signals` · `margin_commentary` · `ai_deal_mentions` · `analyst_qa_tone`

### Context gap
`transcript_nlp` and `sentiment` agents will produce highest-quality output when connected to real earnings transcript sources (Screener.in, Tickertape). Currently fallback to Serper search proxy via stub context.

---

## 12. Renewable Energy Sector Agents

**Graph:** `graphs/renewable_energy/graph.py` | **Entry:** `langgraph.json → "renewable_energy"`

**Architecture:** 6 agents (5 scored + 1 monitoring-only) → Signal Aggregator → FinalReport

### Agent Registry

| Agent | `agent_name` | Weight | Key dimensions |
|---|---|:---:|---|
| Fundamentals | `fundamentals` | **0.30** | CUF vs benchmark, EBITDA/MW, DSCR, receivables, D/E |
| Business Quality | `business` | **0.25** | Sub-sector mix, PPA quality, pipeline credibility |
| Valuation | `valuation` | **0.20** | EV/MW, EV/EBITDA, tariff vs auction rates, implied IRR |
| Sentiment & Policy | `sentiment_policy` | **0.15** | MNRE auctions, Budget RE capex, green hydrogen |
| Technical | `technical` | **0.10** | 50/200-DMA, weekly RSI, MACD, accumulation zones |
| Risk *(monitor only)* | `risk` | **0.00** | DISCOM credit, regulatory change, weather, grid |

> **Risk agent design intent:** weight=0 means its score never moves the verdict. It runs in parallel and its `key_risks` surface directly in `FinalReport.top_risks` via the aggregator LLM. It is a monitor, not a decision-maker.

### Sub-score definitions (selected)

**Fundamentals:** `capacity_utilisation` (CUF %) · `ebitda_quality` (EBITDA/MW trend) · `debt_serviceability` (DSCR ≥1.2x) · `receivables` (<180 days) · `leverage` (project D/E)

**Business:** `subsector_mix` · `ppa_quality` (tariff + counterparty) · `pipeline_cred` · `customer_divers` · `geography_spread`

**Valuation:** `ev_per_mw` · `ev_ebitda` (15–25x range) · `tariff_vs_auction` · `pipeline_dcf` (−25% haircut) · `implied_irr` (vs WACC)

**Technical:** `moving_averages` (golden/death cross) · `rsi_signal` · `macd_weekly` · `volume_catalyst` · `accumulation_zone`

**Risk:** `discom_credit` · `regulatory_change` · `weather_resource` · `grid_integration` · `commodity_input`

### MNRE-specific data sources (phase-2 wiring targets)
| Signal | Source | Effort |
|---|---|---|
| Auction GW awarded | MNRE website (mnre.gov.in) | Medium — HTML scrape |
| L1 tariff trends | SECI/NTPC tender documents | Medium — PDF extract |
| DISCOM payment delays | PFC/REC reports | Low — quarterly PDF |
| CUF actuals | Company investor presentations | Medium — PDF extract |
