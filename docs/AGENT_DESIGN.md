# Agent Design Reference — All Sectors

> Last updated: 2026-04-18
> Automobile: 8 agents · Banking/BFSI: 6 agents · IT Sector: 8 agents · Renewable Energy: 6 agents
> All sectors run as independent LangGraph graphs. Automobile additionally supports the legacy ThreadPoolExecutor path.

---

## 1. Architecture Overview

```
                    LangGraph Multi-Sector System
                              │
              Input: graph.invoke({"ticker": "SYMBOL"})
                              │
          ┌───────────────────┼───────────────────┬─────────────────────┐
          │                   │                   │                     │
   automobile          banking_bfsi           it_sector        renewable_energy
    8 agents             6 agents             8 agents            6 agents
          │                   │                   │                     │
    resolve_ticker      resolve_ticker      resolve_ticker       resolve_ticker
          │                   │                   │                     │
    input_rail          input_rail          input_rail           input_rail
          │                   │                   │                     │
   [Send × 8]           [Send × 6]          [Send × 8]           [Send × 6]
   run_agent            run_agent           run_agent            run_agent
    (parallel)           (parallel)          (parallel)           (parallel)
          │                   │                   │                     │
      aggregate           aggregate           aggregate            aggregate
          │                   │                   │                     │
      FinalReport         FinalReport         FinalReport          FinalReport

All graphs share: BaseAgent · ContextBuilder · macro_cache · LangGraph node factories
```

---

## 2. Shared Infrastructure

### 2.1 BaseAgent (`agents/base_agent.py`)

All sector agents inherit from `BaseAgent`. It owns LLM client initialisation, retry logic, JSON parsing, and context assembly.

| Property / Method | Purpose |
|---|---|
| `agent_name` (abstract) | Unique snake_case identifier within a sector e.g. `"fundamentals"` |
| `sector` (overridable, default `""`) | Routes `ContextBuilder` to the correct `_build_{sector}_{agent_name}` method |
| `run(query)` | Sync entry point — gathers context, calls LLM, parses output |
| `run_async(query)` | Async variant using `AsyncOpenAI`; context gathered via `asyncio.to_thread` |
| `_gather_context(query)` | Priority: RAG → ContextBuilder (live data) → minimal stub |
| `_rag_retrieve(query)` | Active only when `RAG_ENABLED=true`; queries ChromaDB |

**Sector routing:** Each new-sector agent overrides `sector`:
```python
@property
def sector(self) -> str:
    return "bfsi"   # or "it" / "re"
```
Automobile agents return the default `""` — existing behaviour unchanged.

### 2.2 ContextBuilder (`tools/context_builder.py`)

Single class, routes each `(sector, agent_name)` pair to the right data fetchers.

**Routing order:**
```
_build_{sector}_{agent_name}   ← sector-specific (e.g. _build_bfsi_fundamentals)
  → _build_{agent_name}        ← generic/automobile fallback (e.g. _build_pattern_analysis)
    → _build_generic           ← bare ticker string, no API calls
```

**Available fetchers used by builders:**

| Fetcher | Returns | Cost |
|---|---|---|
| `get_fundamentals_context(ticker)` | Revenue, EBITDA, margins, shareholding via yfinance | Free |
| `get_technical_context(ticker)` | RSI, MACD, Bollinger Bands, support/resistance | Free |
| `get_macro_context()` | INR/USD, repo rate, crude oil via yfinance | Free |
| `fetch_news_context(queries)` | Google snippets via Serper, max `SERPER_MAX_QUERIES=3` per call | 2,500/month free |
| `fetch_tavily_context(queries)` | Full extracted page text, used for policy/circular PDFs | 1,000/month free |

### 2.3 Macro Cache (`tools/macro_cache.py`)

In-memory TTL dictionary shared across all agents. Prevents repeating identical sector-level Serper queries for each stock in a batch.

```
main.py _micro_search_loop()   (background daemon, every 4 hours)
     │
     ├── fetch 2 queries → set_macro_cache("automobile", text)
     ├── fetch 2 queries → set_macro_cache("bfsi", text)
     └── fetch 2 queries → set_macro_cache("it", text)

Per-analysis:
     ContextBuilder._build_risk_macro()    → get_macro_cache("automobile") → HIT saves 3 Serper
     ContextBuilder._build_macro_policy()  → get_macro_cache("bfsi")       → HIT saves 3 Serper
     ContextBuilder._build_it_risk_macro() → get_macro_cache("it")         → HIT saves 3 Serper
```

RE sector is **excluded** — MNRE auctions, DISCOM payments, and grid signals are per-company, not sector-wide. No shared cache benefit.

**Budget:** `3 sectors × 2 queries × 6 cycles × 30 days = 1,080 Serper calls/month` from the loop.
**Savings:** `3 calls saved × 5 tickers × 3 sectors × 22 days = 990 calls/month saved` when loop is running.

---

## 3. Automobile Sector

**Graph:** `graphs/automobile/graph.py` | **Entry:** `langgraph.json → "automobile"`
**Legacy path:** `agents/orchestrator.py` via ThreadPoolExecutor (still active)

### 3.1 Agent Registry & Weights

| Agent | `agent_name` | `sector` | Weight |
|---|---|:---:|:---:|
| Sales & Demand | `sales_demand` | `""` | **0.18** |
| Raw Materials | `raw_materials` | `""` | **0.10** |
| Fundamentals | `fundamentals` | `""` | **0.20** |
| Pattern Analysis | `pattern_analysis` | `""` | **0.13** |
| Policy & Regulatory | `policy_regulatory` | `""` | **0.10** |
| Competitive Intel | `competitive_intel` | `""` | **0.10** |
| Risk & Macro | `risk_macro` | `""` | **0.15** |
| Sentiment | `sentiment` | `""` | **0.04** |

### 3.2 Per-Agent Design

#### Sales & Demand
**Purpose:** Retail dispatch velocity and demand-side signals.

| Item | Detail |
|---|---|
| Data sources | Serper (3 calls) |
| Context tokens | ~825 |
| Total tokens | **~1,625** |

Sub-scores: `fada_siam_dispatch` · `ev_segment_vahan` · `dealer_inventory` · `export_import` · `used_car_price_index`

---

#### Raw Materials
**Purpose:** Input cost pressure from metals, energy, and commodities.

| Item | Detail |
|---|---|
| Data sources | yfinance (Steel SLX, Aluminium AA, Platinum PPLT, Palladium PALL, Crude CL=F) + Serper (1 call) |
| Context tokens | ~495 |
| Total tokens | **~1,295** |

Sub-scores: `steel_aluminium` · `platinum_palladium` · `crude_oil_polymer` · `power_tariff` · `commodities_trend`

---

#### Fundamentals
**Purpose:** Financial performance and capital market signals.

| Item | Detail |
|---|---|
| Data sources | yfinance (quarterly financials, shareholding) + Serper (2 calls) |
| Context tokens | ~1,320 |
| Total tokens | **~2,220** |

Sub-scores: `revenue_ebitda_delta` · `margin_vs_peers` · `order_book_pipeline` · `attrition_headcount` · `promoter_fii_dii_flow`

---

#### Pattern Analysis
**Purpose:** Technical price cycle, momentum, and mean-reversion signals.

| Item | Detail |
|---|---|
| Data sources | yfinance only (0 Serper calls) |
| Context tokens | ~440 |
| Total tokens | **~1,240** |

Sub-scores: `price_cycle_position` · `seasonal_pattern` · `rsi_macd_bb` · `breakout_support_zone` · `peer_correlation`

---

#### Policy & Regulatory
**Purpose:** Government policy signals — EV subsidies, emission norms, budgetary incentives.

| Item | Detail |
|---|---|
| Data sources | **Tavily** (2 calls: FAME/EV subsidy, emission norms) + Serper (3 calls) |
| Context tokens | ~2,825 |
| Total tokens | **~3,725** |

Sub-scores: `fame_ev_subsidy` · `emission_norms` · `union_budget_duties` · `pli_scheme` · `state_ev_incentives`

**Why Tavily?** FAME circular PDFs and BS7/CAFE documents contain tabular data that a 2-line snippet misses.

---

#### Competitive Intel
**Purpose:** EV competitive landscape, model launches, M&A, safety ratings.

| Item | Detail |
|---|---|
| Data sources | Serper (4 calls) |
| Context tokens | ~1,100 |
| Total tokens | **~1,900** |

Sub-scores: `ev_market_share` · `new_model_pipeline` · `jv_acquisitions` · `adas_safety_ratings` · `competitive_position`

---

#### Risk & Macro
**Purpose:** Macro-economic and geopolitical risk factors.

| Item | Detail |
|---|---|
| Data sources | yfinance (macro tickers) + Serper (3 calls — **cached via micro loop, key `"automobile"`**) |
| Context tokens | ~1,125 (cache HIT) / ~1,925 (cache MISS) |
| Total tokens | **~1,925 / ~1,100** |

Sub-scores: `inr_usd_crude_exposure` · `commodity_prices` · `rbi_repo_emi_impact` · `emission_policy_risk` · `geopolitical_china_risk`

**Cache behaviour:** The 3 Serper calls (INR/USD, commodities, RBI repo) are sector-level — same for MARUTI and TATAMOTORS on the same day. `_micro_search_loop()` in `main.py` pre-fetches these every 4 hours and caches under key `"automobile"`.

---

### 3.3 Token Budget

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

### 3.4 Serper Call Audit

| Agent | Queries | Cacheable? | Net calls (warm) |
|---|:---:|:---:|:---:|
| sales_demand | 3 | No | 3 |
| raw_materials | 1 | No | 1 |
| fundamentals | 2 | No | 2 |
| pattern_analysis | 0 | — | 0 |
| policy_regulatory | 3 | Partly | 3 |
| competitive_intel | 4 | No | 4 |
| risk_macro | 3 | **Yes → `"automobile"` cache** | **0 (warm)** |
| **Total** | **16** | | **13 (warm) / 16 (cold)** |

> With `SERPER_MAX_QUERIES=3` cap and warm macro cache: **9 net Serper calls** per analysis in steady state.

---

## 4. Banking & BFSI Sector

**Graph:** `graphs/banking_bfsi/graph.py` | **Entry:** `langgraph.json → "banking_bfsi"`

```
START → resolve_ticker → input_rail → [Send × 6] → run_agent (parallel) → aggregate → END
```

### 4.1 Agent Registry & Weights

| Agent | `agent_name` | `sector` | Weight | Context method |
|---|---|:---:|:---:|---|
| Fundamentals | `fundamentals` | `"bfsi"` | **0.25** | `_build_bfsi_fundamentals` |
| Risk | `risk` | `"bfsi"` | **0.20** | `_build_bfsi_risk` |
| Macro & Policy | `macro_policy` | `"bfsi"` | **0.20** | `_build_macro_policy` |
| Institutional | `institutional` | `"bfsi"` | **0.15** | `_build_institutional` |
| Pattern Analysis | `pattern_analysis` | `"bfsi"` | **0.15** | `_build_pattern_analysis` (shared yfinance) |
| Universe Setup | `universe_setup` | `"bfsi"` | **0.05** | `_build_universe_setup` |

### 4.2 Sub-score Definitions

**Fundamentals:** `asset_quality` (Gross/Net NPA, PCR) · `net_interest` (NIM 8Q trend, CASA) · `capital_adequacy` (CRAR/CET1) · `profitability` (RoA, RoE, credit cost) · `loan_mix` (retail/corporate/MSME)

**Risk:** `asset_quality_trend` (SMA slippage, restructured book) · `concentration_risk` (top-5 borrowers) · `deposit_stability` (wholesale %, CASA trend) · `regulatory_risk` (RBI/SEBI penalties) · `macro_sensitivity` (rate sensitivity, FX)

**Macro & Policy:** `rbi_rate_cycle` (repo, MPC stance) · `system_credit` (credit/deposit growth YoY) · `liquidity_conditions` (LAF, CRR/SLR) · `regulatory_actions` (circulars, IRDAI) · `fiscal_policy` (govt borrowing, PSU recap, IBC)

**Institutional:** `fii_dii_flow` (net buying 1M/3M) · `promoter_holding` (stake, pledge %) · `insider_trades` (ESOP, open-market) · `analyst_changes` (rating upgrades/downgrades) · `institutional_conc` (MF holding %)

**Pattern Analysis:** `price_cycle` · `momentum` (RSI/MACD/BB) · `breakout_zones` · `relative_strength` (vs Nifty Bank/PSU Bank) · `volume_pattern`

**Universe Setup:** `index_weight` · `peer_positioning` · `market_cap_tier` · `corporate_actions` · `rebalancing_risk`

### 4.3 Context Wiring

All 6 agents receive live data. `ContextBuilder` routes via `sector="bfsi"`:

| Agent | Fetchers used |
|---|---|
| `fundamentals` | `get_fundamentals_context()` (yfinance) + Serper (NPA/NIM/CASA news) |
| `risk` | Serper (NPA slippage, concentration, deposit risk news) |
| `macro_policy` | `get_macro_context()` (yfinance) + macro cache + Serper (RBI/SEBI news) |
| `institutional` | `get_fundamentals_context()` (shareholding) + Serper (FII/DII news) |
| `pattern_analysis` | `get_technical_context()` (yfinance only) |
| `universe_setup` | Serper (Nifty Bank index, peer comparison news) |

### 4.4 Macro Cache

`_build_macro_policy()` calls `get_macro_cache("bfsi")` before fetching Serper. Key `"bfsi"` is populated by `_micro_search_loop()` in `main.py` every 4 hours:

```
Query 1: "RBI MPC repo rate decision India banking system credit growth CASA deposit liquidity"
Query 2: "Indian banking NPA slippage credit quality SEBI RBI regulatory action PSU private NBFC"
```

Cache HIT saves 3 Serper calls per analysis. Applies identically whether analysing HDFCBANK or KOTAKBANK on the same day.

### 4.5 Serper Call Audit

| Agent | Queries | Cacheable? | Net calls (warm) |
|---|:---:|:---:|:---:|
| fundamentals | 3 | No | 3 |
| risk | 3 | No | 3 |
| macro_policy | 3 | **Yes → `"bfsi"` cache** | **0 (warm)** |
| institutional | 3 | No | 3 |
| pattern_analysis | 0 | — | 0 |
| universe_setup | 3 | No | 3 |
| **Total** | **15** | | **12 (warm) / 15 (cold)** |

---

## 5. IT Sector

**Graph:** `graphs/it_sector/graph.py` | **Entry:** `langgraph.json → "it_sector"`

```
START → resolve_ticker → input_rail → [Send × 8] → run_agent (parallel) → aggregate → END
```

### 5.1 Agent Registry & Weights

| Agent | `agent_name` | `sector` | Weight | Context method |
|---|---|:---:|:---:|---|
| Fundamentals | `fundamentals` | `"it"` | **0.25** | `_build_it_fundamentals` |
| Global Macro | `global_macro` | `"it"` | **0.20** | `_build_global_macro` |
| Risk & Macro | `risk_macro` | `"it"` | **0.15** | `_build_it_risk_macro` |
| Peer Benchmark | `peer_benchmark` | `"it"` | **0.15** | `_build_peer_benchmark` |
| Pattern Analysis | `pattern_analysis` | `"it"` | **0.10** | `_build_pattern_analysis` (shared yfinance) |
| Sentiment | `sentiment` | `"it"` | **0.08** | `_build_it_sentiment` |
| Transcript NLP | `transcript_nlp` | `"it"` | **0.04** | `_build_transcript_nlp` |
| Insider/Smart Money | `insider_smart_money` | `"it"` | **0.03** | `_build_insider_smart_money` |

### 5.2 Sub-score Definitions

**Fundamentals:** `revenue_growth` (CC growth QoQ/YoY) · `ebit_margins` (8Q trend) · `deal_wins` (TCV, large deals) · `attrition` (trailing 12M %) · `valuation` (P/E, EV/Revenue, PEG)

**Global Macro:** `us_tech_spend` · `fed_rate_impact` · `usd_inr` · `geopolitical` (US-China tech war) · `ma_activity`

**Risk & Macro:** `visa_risk` (H1B/L1 denial rates) · `ai_disruption` (GenAI revenue at risk) · `client_concentration` (top-5 %) · `fx_hedge` · `talent_risk`

**Peer Benchmark:** `revenue_growth_rank` · `margin_rank` · `deal_momentum_rank` · `return_metrics_rank` · `valuation_gap` (vs peer median P/E)

**Transcript NLP:** `guidance_tone` · `demand_signals` · `margin_commentary` · `ai_deal_mentions` · `analyst_qa_tone`

**Insider/Smart Money:** `promoter_activity` · `director_trades` · `smart_money_flow` (Tier-1 MF) · `short_interest` · `block_deals`

### 5.3 Context Wiring

All 8 agents receive live data. `ContextBuilder` routes via `sector="it"`:

| Agent | Fetchers used |
|---|---|
| `fundamentals` | `get_fundamentals_context()` (yfinance) + Serper (revenue, deal, attrition news) |
| `global_macro` | `get_macro_context()` (yfinance INR/USD) + Serper (US IT spend, Fed news) |
| `risk_macro` | `get_macro_context()` + macro cache + Serper (visa, AI disruption news) |
| `peer_benchmark` | `get_fundamentals_context()` (yfinance) + Serper (TCS/Infosys peer comparison) |
| `pattern_analysis` | `get_technical_context()` (yfinance only) |
| `sentiment` | Serper (AI narrative, layoff signals, management tone) |
| `transcript_nlp` | **Tavily** (2 calls: earnings transcript) + Serper (2 calls: guidance news) |
| `insider_smart_money` | `get_fundamentals_context()` (shareholding) + Serper (insider trade news) |

### 5.4 Macro Cache

`_build_it_risk_macro()` calls `get_macro_cache("it")` before fetching Serper. Key `"it"` is populated by `_micro_search_loop()` in `main.py` every 4 hours:

```
Query 1: "US IT spending enterprise software cloud capex Federal Reserve rate USD INR exchange rate Indian IT"
Query 2: "H1B visa India IT sector GenAI AI deal demand TCS Infosys Wipro HCL quarterly results outlook"
```

Cache HIT saves 3 Serper calls per analysis. Same Fed rate / USD/INR context applies to TCS, Infosys, and Wipro on the same day.

### 5.5 Serper Call Audit

| Agent | Queries | Cacheable? | Tavily? | Net Serper (warm) |
|---|:---:|:---:|:---:|:---:|
| fundamentals | 3 | No | — | 3 |
| global_macro | 3 | No | — | 3 |
| risk_macro | 3 | **Yes → `"it"` cache** | — | **0 (warm)** |
| peer_benchmark | 3 | No | — | 3 |
| pattern_analysis | 0 | — | — | 0 |
| sentiment | 3 | No | — | 3 |
| transcript_nlp | 2 | No | **2 calls** | 2 |
| insider_smart_money | 3 | No | — | 3 |
| **Total** | **20** | | **2 Tavily** | **17 (warm) / 20 (cold)** |

---

## 6. Renewable Energy Sector

**Graph:** `graphs/renewable_energy/graph.py` | **Entry:** `langgraph.json → "renewable_energy"`

```
START → resolve_ticker → input_rail → [Send × 6] → run_agent (parallel) → aggregate → END
```

### 6.1 Agent Registry & Weights

| Agent | `agent_name` | `sector` | Weight | Context method |
|---|---|:---:|:---:|---|
| Fundamentals | `fundamentals` | `"re"` | **0.30** | `_build_re_fundamentals` |
| Business Quality | `business` | `"re"` | **0.25** | `_build_business` |
| Valuation | `valuation` | `"re"` | **0.20** | `_build_valuation` |
| Sentiment & Policy | `sentiment_policy` | `"re"` | **0.15** | `_build_sentiment_policy` |
| Technical | `technical` | `"re"` | **0.10** | `_build_technical` |
| Risk *(monitor only)* | `risk` | `"re"` | **0.00** | `_build_re_risk` |

> **Risk agent design intent:** weight=0 means its score never moves the verdict. It runs in parallel and its `key_risks` surface directly in `FinalReport.top_risks`. It is a monitor, not a decision-maker.

### 6.2 Sub-score Definitions

**Fundamentals:** `capacity_utilisation` (CUF % vs Solar 19-22%, Wind 28-35% benchmarks) · `ebitda_quality` (EBITDA/MW trend) · `debt_serviceability` (DSCR ≥1.2x) · `receivables` (<180 days ideal) · `leverage` (project D/E)

**Business:** `subsector_mix` (Solar/Wind/Hydro/Hybrid diversification) · `ppa_quality` (tariff, tenor, counterparty) · `pipeline_cred` (under-construction %, track record) · `customer_divers` (DISCOM state mix, C&I %) · `geography_spread` (MW by state, resource quality)

**Valuation:** `ev_per_mw` (vs Solar ₹4-6Cr/MW, Wind ₹5-8Cr/MW range) · `ev_ebitda` (vs 15-25x healthy range) · `tariff_vs_auction` (existing PPAs vs current MNRE L1) · `pipeline_dcf` (−25% haircut on unbuilt MW) · `implied_irr` (vs WACC, target ≥200bps spread)

**Sentiment & Policy:** `mnre_auction_health` · `budget_allocation` · `policy_tailwinds` (RPO, ISTS waiver) · `green_hydrogen` · `news_sentiment`

**Technical:** `moving_averages` (50/200-DMA golden/death cross) · `rsi_signal` (weekly RSI) · `macd_weekly` · `volume_catalyst` · `accumulation_zone`

**Risk:** `discom_credit` · `regulatory_change` (tariff re-negotiation) · `weather_resource` · `grid_integration` (curtailment %) · `commodity_input` (steel/copper capex)

### 6.3 Context Wiring

All 6 agents receive live data. `ContextBuilder` routes via `sector="re"`. No macro cache for RE — all signals are per-company:

| Agent | Fetchers used |
|---|---|
| `fundamentals` | `get_fundamentals_context()` (yfinance) + Serper (CUF, DSCR, receivables news) |
| `business` | Serper (PPA, pipeline, sub-sector mix news) |
| `valuation` | `get_fundamentals_context()` (yfinance) + Serper (EV/MW, MNRE tariff news) |
| `sentiment_policy` | **Tavily** (2 calls: MNRE circulars, ISTS waiver) + Serper (auction, Budget news) |
| `technical` | `get_technical_context()` (yfinance only, 0 Serper) |
| `risk` | Serper (DISCOM delays, curtailment, grid, commodity news) |

### 6.4 Serper Call Audit

| Agent | Queries | Cacheable? | Tavily? | Net Serper |
|---|:---:|:---:|:---:|:---:|
| fundamentals | 3 | No | — | 3 |
| business | 3 | No | — | 3 |
| valuation | 3 | No | — | 3 |
| sentiment_policy | 3 | No | **2 calls** | 3 |
| technical | 0 | — | — | 0 |
| risk | 3 | No | — | 3 |
| **Total** | **15** | | **2 Tavily** | **15** |

> No macro cache for RE — its macro signals (MNRE, DISCOM, grid) vary per company, not sector-wide.

---

## 7. Cross-Sector Comparison

| Property | Automobile | Banking/BFSI | IT | Renewable Energy |
|---|:---:|:---:|:---:|:---:|
| Agents | 8 | 6 | 8 | 6 |
| LangGraph graph | ✅ | ✅ | ✅ | ✅ |
| Legacy orchestrator | ✅ | ✗ | ✗ | ✗ |
| Serper/analysis (warm) | 9 | 12 | 17 | 15 |
| Tavily/analysis | 2 | 0 | 2 | 2 |
| Macro cache key | `"automobile"` | `"bfsi"` | `"it"` | None |
| Cache saves (5 tickers/day) | 450/month | 330/month | 330/month | 0 |
| Monitoring-only agent | ✗ | ✗ | ✗ | `risk` (weight=0) |
| Transcript NLP | ✗ | ✗ | ✅ (Tavily) | ✗ |
| Full policy doc retrieval | ✅ (FAME/BS7) | ✗ (P1 backlog) | ✗ | ✅ (MNRE) |
