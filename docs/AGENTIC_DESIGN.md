# Agentic Design Reference

> All agents, tasks, metrics, data sources, static vs LLM responsibilities.
> Minimize plain text — prefer tables and trees.
> Updated: 2026-05-19 · Covers automobile (full) + 3 live sectors + RL + Chat agents (3-node LangGraph).

---

## 1. Agent Taxonomy

```
StockAgent Agents
├── Analysis Agents  (sector-specific, run monthly + on-demand)
│   ├── Automobile       9 agents  ✅ FULLY IMPLEMENTED
│   ├── Banking/BFSI     6 agents  ✅ CONTEXT BUILDER EXTENDED
│   ├── IT Sector        8 agents  ✅ CONTEXT BUILDER EXTENDED
│   └── Renewable Energy 6 agents  ✅ CONTEXT BUILDER EXTENDED
│
├── RL Agents  (cross-sector, run daily automated post-market)
│   ├── FeedbackAgent     [LLM]    daily root-cause analysis
│   ├── WeightAdapter     [STATIC] deterministic weight adjustment
│   └── ThesisReviewer    [LLM]    conditional post-miss thesis validation
│
└── Chat Agent  (on-demand via /ui/chat)  ✅ REDESIGNED
    ├── DispatchNode      [LLM]    query decomposition + tier detection
    ├── ExecutorNode      [STATIC] parallel async tool execution
    └── SynthesizeNode    [LLM]    tier-adaptive streaming response
```

---

## 2. BaseAgent Architecture

All sector analysis agents inherit from `BaseAgent` (`src/backend/shared/pipeline/base_agent.py`).

**Three abstract methods each subclass must implement:**

| Method | Signature | Purpose |
|---|---|---|
| `agent_name` | `@property → str` | snake_case id, matches key in `AGENT_WEIGHTS` |
| `_build_prompt` | `(query, context) → (system_prompt, user_prompt)` | Assembles LLM prompt from template + context |
| `_parse_output` | `(data: dict, ticker: str) → AgentOutput` | Parses LLM JSON → typed AgentOutput |

**Context Priority Chain (STATIC — no LLM):**

```
BaseAgent._gather_context(query)
  ├── Check 1: RAG_ENABLED=true?
  │   → YES: RAGRetriever.retrieve(search_query) → ChromaDB top-K + optional reranker
  ├── Check 2: ContextBuilder.build(agent_name, query) → live data from fetchers
  └── FALLBACK: "Stock: MARUTI | Date: 2026-05-17 | Note: Live data unavailable."
```

**Retry logic (STATIC):** 3 attempts, exponential backoff on `APIError`, `RateLimitError`, `APITimeoutError`.

**Failure fallback (STATIC):** `AgentOutput(overall_score=0.5, error=str(exc))` — pipeline never crashes.

**PromptEnhancer integration (P4):**
```
BaseAgent.run(query):
  base_queries   = CONTEXT_SEARCH_QUERIES (static prompt file)
  agent_extra    = PredictionStore.load_enhancements(ticker, cycle_id).get(agent_name, [])
  all_queries    = base_queries + agent_extra[:2]  → passed to context fetchers
```

---

## 3. LangGraph Execution Architecture

```
BaseSectorOrchestrator.analyse_async(ticker)
  │
  ▼
_resolve_ticker()  [LLM: temp=0.0, deterministic]
  "Tata Motors" → StockQuery(ticker="TATAMOTORS", company_name="Tata Motors Ltd", exchange="NSE")
  Fallback: raw input used as ticker if LLM fails
  │
  ▼
_load_learned_weights(ticker)  [STATIC: reads agent_weight_memory.json]
  Returns None if no RL data yet (uses settings.AGENT_WEIGHTS defaults)
  │
  ▼
LangGraph StateGraph (src/backend/sectors/{sector}/pipeline/graph.py)
  ┌── resolve_ticker ──────────────────────────────────────────────────┐
  │                                                                     │
  │   input_rail  [STATIC: yfinance fast_info check, non-blocking]     │
  │                                                                     │
  │   make_dispatch_fn → list[Send]  (conditional_edges, fan-out)      │
  │   ┌─────┬─────┬─────┬────────────────────────────────────────────┐  │
  │   ↓     ↓     ↓     ↓                                            │  │
  │   run_agent × N  [parallel, RetryPolicy(max_attempts=2)]          │  │
  │   │  output_rail inside each: clamp score [0,1], inject summary   │  │
  │   │  writes {agent_name: AgentOutput} via _merge_dicts reducer    │  │
  │   └──────────────────────────────────────────────── fan-in ───────┘  │
  │                                                                     │
  │   aggregate  [conflict_rail: spread > 0.35 → LLM re-resolution]    │
  │              [SignalAggregator.run(learned_weights) → FinalReport]  │
  └─────────────────────────────────────────────────────────────────────┘
  │
  ▼
END → state["final_report"] = FinalReport
```

**Three-Rail Safety Layer (all STATIC, all non-blocking):**

| Rail | Where | Trigger | Action |
|---|---|---|---|
| `input_rail` | Before fan-out | Bad ticker / yfinance not found | Append to rail_errors; continue |
| `output_rail` | Inside `run_agent` | Score out of [0,1], empty summary | Clamp; inject placeholder |
| `conflict_rail` | Inside `aggregate` | Pairwise score spread > 0.35 | Trigger LLM re-resolution |

**Sync vs Async paths:**

| Path | When | Mechanism | LLM client |
|---|---|---|---|
| Sync | CLI / APScheduler | LangGraph with threading | `openai.OpenAI` (sync) |
| Async | FastAPI / WebSocket | `graph.astream_events()` | `AsyncOpenAI` coroutine |

**Multi-sector graph comparison:**

| Graph | Agents | Key weight | Unique signal / data |
|---|---|---|---|
| `automobile` | 9 | fundamentals 0.18 | sales_demand (FADA/Vahan), competitive_intel (EV share) |
| `banking_bfsi` | 6 | fundamentals 0.25 | NPA/NIM/CASA, RBI MPC rate cycle |
| `it_sector` | 8 | fundamentals 0.25 | US tech spend, visa risk, transcript NLP |
| `renewable_energy` | 6 | fundamentals 0.30 | CUF/DSCR/EV-MW, MNRE auctions, DISCOM risk |

**LangGraph known design weaknesses (backlog):**

| # | Issue | Severity | Fix |
|---|---|---|---|
| 1 | `ContextBuilder` not sector-aware (P0) | High | Add `_build_{sector}_{agent}` routing branches |
| 2 | `BaseAgent._rag_retrieve` falls back to "automobile India" for unknown agents (P0) | High | Add `sector` parameter or override per-class |
| 3 | `run_agent` calls sync `agent.run()` — threading, not asyncio (P1) | Medium | Switch to `agent.run_async()` + `async def run_agent` nodes |
| 4 | `input_rail` makes blocking yfinance network call before fan-out (P1) | Medium | Wrap in `asyncio.to_thread` or skip on `FAST_MODE=true` |
| 5 | Agent name collision across sectors (`"fundamentals"` in all 4) (P2) | Low | No immediate problem; prefix names if cross-sector reporting added |
| 6 | No CLI / FastAPI entry point for non-automobile sectors (P1) | Medium | Add `--sector` flag on `main.py` + `POST /analyse/{sector}` route |
| 7 | Usage logging skipped if JSON parse fails post-LLM call (P2) | Low | Move `log_llm_call` before `json.loads` in aggregate node |

---

## 4. Automobile Sector — 9 Agents ✅

**Base weights (must sum to 1.0), defined in `src/backend/sectors/automobile/config/settings.py`:**

| Agent key | Base weight | Class file | Prompt file |
|---|---|---|---|
| `fundamentals` | **0.18** | `agents/fundamentals.py` | `prompts/fundamentals.py` |
| `sales_demand` | **0.16** | `agents/sales_demand.py` | `prompts/sales_demand.py` |
| `risk_macro` | **0.13** | `agents/risk_macro.py` | `prompts/risk_macro.py` |
| `pattern_analysis` | **0.12** | `agents/pattern_analysis.py` | `prompts/pattern_analysis.py` |
| `valuation_catalyst` | **0.10** | `agents/valuation_catalyst.py` | `prompts/valuation_catalyst.py` |
| `policy_regulatory` | **0.09** | `agents/policy_regulatory.py` | `prompts/policy_regulatory.py` |
| `raw_materials` | **0.09** | `agents/raw_materials.py` | `prompts/raw_materials.py` |
| `competitive_intel` | **0.09** | `agents/competitive_intel.py` | `prompts/competitive_intel.py` |
| `sentiment` | **0.04** | `agents/sentiment.py` | `prompts/sentiment.py` |

All paths are under `src/backend/sectors/automobile/`.

---

### 4.1 FundamentalsAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | revenue_ebitda_delta, margin_vs_peers, deal_wins_order_book, attrition_headcount, promoter_fii_dii_flow |
| **Context** | `get_fundamentals_context(ticker)` via yfinance quarterly P&L + Serper news |
| **yfinance** | ✓ `quarterly_income_stmt`, `balance_sheet`, `institutional_holders` |
| **Serper calls** | up to 3 |
| **Schema** | `FundamentalsOutput` + `FundamentalsSubScores` |
| **Known gap** | yfinance NSE returns annual snapshots, not QoQ deltas; screener.in needed for structured quarterly data |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"{ticker} quarterly results revenue EBITDA {quarter} {year}"`, `"{ticker} margin EBITDA comparison peers {year}"`, `"{company_name} order book pipeline deal wins {year}"`, `"{company_name} headcount attrition employees {year}"`, `"{ticker} promoter shareholding FII DII {quarter} {year}"` |

---

### 4.2 SalesDemandAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | fada_siam_dispatch, ev_segment_vahan, dealer_inventory, export_import, used_car_price_index |
| **Context** | `fetch_news_context()` via Serper only |
| **yfinance** | ✗ |
| **Serper calls** | up to 3 (5 queries defined, capped by `SERPER_MAX_QUERIES=3`) |
| **Schema** | `SalesDemandOutput` + `SalesDemandSubScores` |
| **Known gap** | No direct FADA/SIAM/Vahan API — Serper search proxy only |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"{ticker} FADA monthly retail sales {month} {year}"`, `"{ticker} SIAM dispatch data {year}"`, `"{ticker} EV registration Vahan {year}"`, `"{company_name} dealer inventory channel check"`, `"India automobile export {ticker} DGFT {year}"`, `"used car price index Cars24 CarDekho {year}"` |

---

### 4.3 RiskMacroAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | inr_usd_crude_exposure, commodity_prices, rbi_repo_emi_impact, emission_policy_risk, global_geopolitical_risk |
| **Global geopolitical risk sub-weights (LLM-judged)** | oil price shock 40%, FII outflow 30%, INR depreciation 20%, supply chain disruption 10% |
| **Context** | `get_macro_context()` via yfinance (INR=X, CL=F, SLX, AA) + `macro_cache` OR Serper |
| **yfinance tickers** | `INR=X` (INR/USD), `CL=F` (WTI crude), `BZ=F` (Brent), `SLX` (steel ETF), `AA` (aluminium proxy) |
| **Serper calls** | 3 on cache MISS → 0 on cache HIT |
| **Cache** | `get_macro_cache("automobile")` — TTL 2h, sector-level (shared across all auto tickers) |
| **Schema** | `RiskMacroOutput` + `RiskMacroSubScores` |
| **RBI repo rate** | Serper live fetch (regex from MPC news), 60-day thread-locked cache, fallback to settings.RBI_REPO_RATE_PCT=5.25% (2026-02-07, stance=neutral) | ✅ FIXED 2026-05-19 |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"INR USD exchange rate {date} India automobile exports"`, `"steel aluminium rubber prices India {month} {year}"`, `"RBI repo rate {year} auto loan EMI demand impact"`, `"India emission norms BS6 CAFE {company_name} compliance {year}"`, `"global geopolitical risk oil FII outflow India auto sector {year}"` |

---

### 4.4 PatternAnalysisAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | price_cycle_position, seasonal_sales_pattern, rsi_macd_bb, breakout_support_zone, peer_correlation |
| **Context** | `get_technical_context(ticker)` → yfinance 10yr OHLCV → RSI(14), MACD(12,26,9), BB(20,2σ), support/resistance, Nifty Auto correlation |
| **yfinance** | ✓ `period="10y"` OHLCV + `^CNXAUTO` |
| **Serper calls** | **0** — yfinance only (most API-efficient agent) |
| **C++ acceleration** | `stockindicators.pyd` via pybind11; fallback to pure Python if absent (`_USE_CPP=False`) |
| **Schema** | `PatternAnalysisOutput` + `PatternAnalysisSubScores` |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | Defined but ContextBuilder uses yfinance only for this agent |

---

### 4.5 SentimentAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | news_nlp, management_tone, twitter_reddit_sentiment, youtube_view_spikes, dealer_consumer_feedback |
| **Context** | `fetch_news_context()` via Serper |
| **yfinance** | ✗ |
| **Serper calls** | up to 3 |
| **Schema** | `SentimentOutput` + `SentimentSubScores` |
| **Known gap** | No Twitter/Reddit/YouTube API wired; Serper proxy only |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"{company_name} news sentiment {month} {year}"`, `"{ticker} earnings call transcript management tone {quarter} {year}"`, `"{company_name} Twitter Reddit investor sentiment {year}"`, `"{company_name} new model launch YouTube reviews views {year}"`, `"{company_name} dealer consumer feedback complaints {year}"` |

---

### 4.6 PolicyRegulatoryAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | fame_ev_subsidy, emission_norms, union_budget_duties, pli_scheme, state_ev_incentives |
| **Context** | Tavily full-page (government circulars, PDFs) + Serper news |
| **yfinance** | ✗ |
| **Serper calls** | up to 3 |
| **Tavily calls** | up to 2 (only agent that uses Tavily — reserved for full policy document depth) |
| **Schema** | `PolicyRegulatoryOutput` + `PolicyRegulatorySubScores` |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"{company_name} FAME EV subsidy eligibility {year}"`, `"BS7 CAFE emission norms India automobile {year}"`, `"Union Budget import duties automobile PLI scheme {year}"`, `"{ticker} PLI incentive realization timeline {year}"`, `"state EV incentives registration waiver road tax {year}"` |

---

### 4.7 RawMaterialsAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | steel_aluminium, platinum_palladium, crude_polymer, power_tariff, commodity_trend_3m |
| **Context** | `get_raw_materials_context()` via yfinance prices + `fetch_news_context(max_queries=1)` |
| **yfinance tickers** | `SLX` (steel), `AA` (aluminium), `PPLT` (platinum), `PALL` (palladium), `CL=F` (crude), `BZ=F` (Brent) |
| **Rubber** | ~~^TOCOM_RUBBER~~ (delisted). Now: Serper MCX news search via `_fetch_rubber_price_via_news()`, 4-hour module-level cache (`_RUBBER_CACHE`) | direction-based (up/down %), not absolute price |
| **Serper calls** | 1 |
| **Schema** | `RawMaterialsOutput` + `RawMaterialsSubScores` |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"steel aluminium commodity prices India automobile {month} {year}"` (1 query only) |

---

### 4.8 CompetitiveIntelAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | ev_market_share, new_model_pipeline, jv_acquisitions, adas_safety_ratings, competitive_position |
| **Context** | `fetch_news_context()` via Serper |
| **yfinance** | ✗ |
| **Serper calls** | up to 3 |
| **Schema** | `CompetitiveIntelOutput` + `CompetitiveIntelSubScores` |
| **CONTEXT_SEARCH_QUERIES (STATIC)** | `"{company_name} EV market share India {year}"`, `"{company_name} new model launch pipeline {year}"`, `"{company_name} JV acquisition technology partnership {year}"`, `"{company_name} BNAP NCAP safety rating ADAS {year}"`, `"{company_name} competitive position market share {month} {year}"` |

---

### 4.9 ValuationCatalystAgent

| Dimension | Detail |
|---|---|
| **5 score dimensions (LLM)** | pe_vs_5yr_history, pe_vs_peer_median, discount_reason_clarity, catalyst_strength, price_target_confidence |
| **Extra output fields (LLM)** | fair_value_estimate, current_discount_pct, discount_reason, recovery_catalysts[], price_target, recovery_timeline_quarters |
| **Context** | `_build_valuation_catalyst` — implemented in ContextBuilder ✅ |
| **yfinance** | ✓ (via context builder) |
| **Serper calls** | per ContextBuilder routing |
| **Schema** | `ValuationCatalystOutput` + `ValuationCatalystSubScores` |
| **Output bubbles up** | 5 extra fields flow to `FinalReport` via SignalAggregator (price_target, recovery_timeline_quarters, undervalued_by_pct, discount_reason, recovery_catalysts) |

---

### 4.10 Business Model Context Injection (all 9 agents)

All 9 automobile agents receive `{business_model_context}` injected into their prompt via
`get_business_model_context(ticker)` from `src/backend/sectors/automobile/config/settings.py`.

| Tier | Source | Cache | Quality |
|---|---|---|---|
| Known OEM (8 tickers) | Curated `BUSINESS_MODEL_SNAPSHOTS` dict | In-memory (no API) | Highest — manually maintained |
| Unknown ticker | Serper search: `"{ticker} business model revenue portfolio India automobile 2026"` | 30-day disk cache: `data/oem_profiles/{TICKER}.json` | Good — news-based |
| Serper fails | `BUSINESS_MODEL_SNAPSHOT_DEFAULT` | N/A | Generic fallback |

**Curated OEMs:** MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, ASHOKLEY, TVSMOTORS

**Margin anchors are RELATIVE descriptions** (not hardcoded %) to avoid stale data.
Example: "Industry-leading margins vs peers; rubber/steel/crude are primary levers" not "~19% EBITDA".

**Source tag in prompt:** `[source: curated]` | `[source: news-cache 2026-05-19]` | `[source: generic-default]`

---

## 5. Banking/BFSI Sector — 6 Agents ✅

All agents inherit BaseAgent. CONTEXT_SEARCH_QUERIES defined. ContextBuilder extended with 6 `_build_bfsi_*` routing methods. `rbi_data.py` + `npa_metrics.py` fetchers raise `NotImplementedError` (Phase 7 target).

| Agent key | Base weight | 5 Score Dimensions (LLM) | Sub-score schema | Key gap |
|---|---|---|---|---|
| `fundamentals` | 0.25 | asset_quality, net_interest (NIM/CASA), capital_adequacy (CRAR), profitability (RoA/RoE), loan_mix | `BFSIFundamentalsAgentSubScores` | NPA/NIM structured data (RBI DBIE) not wired |
| `risk` | 0.20 | credit_risk, market_risk, operational_risk, regulatory_risk, liquidity_risk | `BFSIRiskAgentSubScores` | RBI stress test data |
| `macro_policy` | 0.20 | rbi_policy, liquidity_conditions, credit_growth, inflation_impact, forex_impact | `BFSIMacroPolicyAgentSubScores` | RBI press releases not scraped |
| `institutional` | 0.15 | fii_dii_flows, promoter_holding, institutional_ownership, block_deals, shareholding_trend | `BFSIInstitutionalAgentSubScores` | NSE shareholding data (quarterly) |
| `pattern_analysis` | 0.12 | price_cycle, rsi_macd_bb, support_resistance, sector_correlation, technical_trend | `BFSIPatternAgentSubScores` | yfinance OHLCV works; zero new wiring needed |
| `universe_setup` | 0.08 | sector_overview, peer_positioning, valuation_relative, catalyst_pipeline, risk_reward | `BFSIUniverseAgentSubScores` | General research; LLM knowledge sufficient |

**Supported tickers:** HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANKBARODA, PNB, CANARABANK, FEDERALBNK, IDFCFIRSTB, BANDHANBNK, RBLBANK, YESBANK, HDFCAMC, BAJAJFINSV, BAJFINANCE, MUTHOOTFIN, CHOLAFIN

---

## 6. IT Sector — 8 Agents ✅

`deal_wins.py` + `transcript.py` fetchers raise `NotImplementedError` (Phase 7 target). ContextBuilder extended with 8 `_build_it_*` routing methods.

| Agent key | Base weight | 5 Score Dimensions (LLM) | Sub-score schema |
|---|---|---|---|
| `fundamentals` | 0.25 | revenue_growth (CC), ebit_margins (8Q), deal_wins (TCV), attrition_headcount, fii_dii_valuation | `ITFundamentalsAgentSubScores` |
| `global_macro` | 0.20 | us_tech_spending, client_sector_mix, currency_headwinds, global_it_demand, macro_sensitivity | `ITGlobalMacroAgentSubScores` |
| `risk_macro` | 0.15 | visa_risk, pricing_pressure, client_concentration, regulatory_risk, margin_risk | `ITRiskMacroAgentSubScores` |
| `peer_benchmark` | 0.12 | revenue_growth_vs_peers, margin_vs_peers, deal_win_rate, valuation_vs_peers, employee_metrics | `ITPeerBenchmarkAgentSubScores` |
| `pattern_analysis` | 0.10 | price_cycle, rsi_macd_bb, support_resistance, sector_correlation, technical_trend | `ITPatternAgentSubScores` |
| `sentiment` | 0.08 | news_nlp, management_tone, analyst_coverage, social_sentiment, client_feedback | `ITSentimentAgentSubScores` |
| `transcript_nlp` | 0.06 | management_confidence, guidance_tone, client_commentary, margin_guidance, deal_pipeline_tone | `ITTranscriptNLPAgentSubScores` |
| `insider_smart_money` | 0.04 | insider_buying, smart_money_flows, block_deals, institutional_positioning, promoter_activity | `ITInsiderAgentSubScores` |

**Supported tickers:** TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT, LTTS, KPITTECH, TATAELXSI, NIIT, MASTEK, HEXAWARE

---

## 7. Renewable Energy Sector — 6 Agents ✅

`mnre_data.py` fetcher raises `NotImplementedError` (Phase 7 target). ContextBuilder extended with 6 `_build_re_*` routing methods.

| Agent key | Base weight | 5 Score Dimensions (LLM) | Key metrics | Sub-score schema |
|---|---|---|---|---|
| `fundamentals` | 0.30 | revenue_growth, ebitda_margin, debt_service (DSCR), capacity_utilisation (CUF), fii_dii | DSCR, CUF | `REFundamentalsAgentSubScores` |
| `business` | 0.25 | order_book, project_pipeline, auction_wins (MNRE), ppa_health, execution_risk | EV/MW, PPA | `REBusinessAgentSubScores` |
| `valuation` | 0.20 | ev_mw, pe_vs_peers, price_to_book, dividend_yield, catalysts | EV/MW | `REValuationAgentSubScores` |
| `sentiment_policy` | 0.10 | mnre_policy, renewable_targets, state_offtake, cop_sentiment, green_hydrogen | DISCOM health | `RESentimentPolicyAgentSubScores` |
| `technical` | 0.10 | price_cycle, rsi_macd_bb, support_resistance, sector_correlation, volume | — | `RETechnicalAgentSubScores` |
| `risk` | 0.05 | discom_payment_risk, regulatory_risk, weather_risk, financing_risk, competition | DISCOM delay | `RERiskAgentSubScores` |

**Supported tickers:** ADANIGREEN, TATAPOWER, TORNTPOWER, CESC, SJVN, NHPC, NTPC, POWERGRID, ADANIPOWER, JSWENERGY, INOXGREEN, WAAREEENER

---

## 8. SignalAggregator — Static + LLM Boundary

**File:** `src/backend/shared/pipeline/signal_aggregator.py`

```
Step 1 [STATIC]:  composite = Σ(agent.overall_score × weight) / Σ(weights)
                  Uses learned_weights if provided, else settings.AGENT_WEIGHTS

Step 2 [STATIC]:  Conflict detection
                  For every pair: if |score_A - score_B| ≥ 0.30 → conflict_flags
                  WHY 0.30: meaningful disagreement (e.g. BUY vs NEUTRAL range)

Step 3 [LLM]:     LLM call with all scores + weights + composite + conflict list
                  Input: AGGREGATION_PROMPT
                  Output (JSON): {verdict, final_score, conviction_drivers, top_risks,
                                  investment_thesis, conflicts_resolved}
                  Model: qwen/qwen3-235b-a22b via OpenRouter

Step 4 [STATIC]:  Extract valuation fields from valuation_catalyst agent output
                  → populate FinalReport.price_target, .recovery_timeline_quarters, etc.

Step 5 [STATIC]:  Map final_score → verdict (if not explicitly returned by LLM)
```

**Verdict Thresholds (STATIC — from settings.SCORE_THRESHOLDS):**

| Verdict | Score range |
|---|---|
| `STRONG BUY` | 0.75 – 1.00 |
| `BUY` | 0.55 – 0.75 |
| `NEUTRAL` | 0.40 – 0.55 |
| `SELL` | 0.20 – 0.40 |
| `STRONG SELL` | 0.00 – 0.20 |

**Scoring example (automobile):**

```
Agent            Score   Weight   Weighted
sales_demand     0.72  × 0.16  = 0.1152
raw_materials    0.60  × 0.09  = 0.0540
fundamentals     0.68  × 0.18  = 0.1224
pattern_analysis 0.63  × 0.12  = 0.0756
sentiment        0.70  × 0.04  = 0.0280
policy_regulatory0.65  × 0.09  = 0.0585
competitive_intel0.62  × 0.09  = 0.0558
risk_macro       0.58  × 0.13  = 0.0754
valuation_catal. 0.71  × 0.10  = 0.0710
                          ──────────────
composite = 0.6559 / 1.00 = 0.656  → BUY
```

**Weight priority chain:**

```
1. Explicitly injected by generate_forecast.py / daily_review.py
2. RL WeightMemory.effective_weights() — auto-loaded by _load_learned_weights(ticker)
3. settings.AGENT_WEIGHTS config defaults
```

---

## 9. RL Agents

### 9.1 FeedbackAgent *(LLM)*

**File:** `core/intelligence/rl/agents/feedback_agent.py`

Not a subclass of BaseAgent — takes `FeedbackAgentInput` rather than `StockQuery`.

| | Detail |
|---|---|
| **Model** | qwen/qwen3-235b-a22b via OpenRouter |
| **Temperature** | 0.3 (surfaces non-obvious cross-signal patterns) |
| **max_tokens** | 1500 (structured RevisedContext requires extra space) |
| **response_format** | `{"type": "json_object"}` (guarantees parseable JSON) |
| **System prompt** | Dynamically built: `build_system_prompt(sector, agent_names)` — no hardcoded agent names |

**Two public methods:**

```python
run(fb_input: FeedbackAgentInput, ledger: LearningLedger) → FeedbackAgentOutput
    # LLM call → classify miss type, identify missed factors, generate lessons

merge_lessons_into_ledger(output: FeedbackAgentOutput, ledger: LearningLedger)
    → (updated_ledger, lesson_ids)  [STATIC: dedup/blend/propagate]
```

**What is STATIC vs LLM in FeedbackAgent:**

| Task | Type | Notes |
|---|---|---|
| `classify_direction()` | STATIC | UP/DOWN/FLAT via RL_FLAT_THRESHOLD_PCT=0.3 |
| `is_direction_correct()` | STATIC | BUY→UP, SELL→DOWN, NEUTRAL→always ok |
| `_parse()` output | STATIC | JSON → FeedbackAgentOutput, handles backward-compat |
| LLM call itself | **LLM** | Determines miss_type, missed_factors, lessons, revised_context |
| `merge_lessons_into_ledger()` | STATIC | Dedup by pattern, blend confidence 0.70×existing+0.30×incoming |
| `propagate to shared/market ledger` | STATIC | Routing by lesson.scope |
| `contributing_tickers boost +0.05` | STATIC | Per new confirming ticker |
| Analyst distrust enforcement | STATIC | System prompt rule — never cite analyst targets |

### 9.2 WeightAdapter *(STATIC — no LLM)*

**File:** `core/intelligence/rl/agents/weight_adapter.py`

```
update(weight_memory, feedback_log, todays_primary_miss_agent, todays_miss_type)
  → WeightMemory (new version)

Three stages (all STATIC):
  Stage 1: _compute_accuracy()
    - Reads last WEIGHT_ACCURACY_WINDOW=7 entries from feedback_log
    - For each agent: direction_hits / total (credits NO_PENALTY_MISS_TYPES on wrong days)
    - Returns dict[agent, AgentAccuracy]

  Stage 2: _compute_deltas()
    - hit_rate ≥ 0.70 → +0.02
    - hit_rate ≤ 0.40 → -0.03
    - consecutive primary_miss_agent streak ≥ 2 → extra -0.05
    - All deltas × MISS_TYPE_PENALTY_MULTIPLIER[miss_type]

  Stage 3: _apply_deltas()
    - clamp each delta to ±WEIGHT_MAX_STEP (0.05)
    - clamp each weight to base ± WEIGHT_MAX_DRIFT (0.15)
    - renormalize all weights to sum 1.0

Result: WeightMemory gets new version number + WeightHistoryEntry with reason string
```

### 9.3 ThesisReviewer *(LLM — conditional)*

**File:** `core/intelligence/rl/agents/thesis_reviewer.py`

| | Detail |
|---|---|
| **Trigger** | `should_review()`: `\|price_error\| > max(1.5%, 1.5 × atr_pct)` OR `direction_correct=False AND miss_type in {direction_flip, model_bias}` |
| **ATR method** | `_compute_atr_pct(ticker)` — 14-day ATR as % via yfinance; returns 0.0 on failure (uses floor) |
| **Model** | qwen/qwen3-235b-a22b via OpenRouter |
| **Temperature** | 0.1 |
| **max_tokens** | 300 |
| **response_format** | `json_object` |
| **Output** | `ThesisReview(thesis_intact, horizon_confidence_multiplier [0.3–1.0], assumptions_invalidated, revised_narrative)` |
| **Safe default** | On any failure: `thesis_intact=True, multiplier=1.0` — never blocks daily review |
| **Frequency** | ~1-3× per month per ticker (only on significant misses) |
| **Telemetry** | Appends to `data/predictions/{sector}/{ticker}/thesis_calls.jsonl` |
| **Calibration** | `multiplier` applied as global discount to all remaining 30-day forecasts |

**Trigger decision tree:**

```
should_review(price_error_pct, atr_pct, direction_correct, miss_type)
  ├── |price_error| > max(1.5%, 1.5 × atr_pct)  → True  (size trigger)
  ├── direction_correct=False
  │   AND miss_type in {direction_flip, model_bias}  → True  (structural trigger)
  └── otherwise  → False  (skip — no LLM call)
```

---

## 10. Chat Engine — 3-Node LangGraph Pipeline ✅

**File:** `services/api/chat_graph.py`

**Pipeline:** `dispatch → executor → synthesize → END`

**Session persistence:** MemorySaver checkpointer, keyed by `thread_id = session_id`

**SSE event stream order:**

```
dispatch → tool_start → tool_result → thinking → token → done
```

### 10.1 Node Details

**Node 1 — dispatch [LLM]**

| | Detail |
|---|---|
| **Model** | qwen, temp=0.0 |
| **Purpose** | Detects user tier; decomposes query into structured tasks JSON |
| **Outputs** | `tasks[]`, `user_tier`, `browsing_strategy` |
| **Fallback** | `_DISPATCH_FALLBACK_TASKS` on LLM failure |
| **Profile load** | Reads `data/user_profiles/{session_id}.json` (via `user_profile.load_profile()`) |

**Node 2 — executor [STATIC — 0 LLM tokens]**

| | Detail |
|---|---|
| **Mechanism** | `asyncio.gather()` — all tasks in parallel |
| **SSE events emitted** | `tool_start`, `tool_result` |
| **LLM usage** | None |

**Node 3 — synthesize [LLM]**

| | Detail |
|---|---|
| **Model** | qwen, streaming |
| **SSE events emitted** | `thinking` (filtered `<think>` blocks), `token`, `done` |
| **Tier-adaptive format** | `casual`: 3-4 plain sentences · `active`: price + direction + headlines ≤150 words · `expert`: regime, conviction, raw metrics, no cap |
| **Post-turn** | Saves/updates user profile after completion |
| **Filter** | `<think>` blocks stripped from streaming output |

### 10.2 User Profiling System

**File:** `services/api/user_profile.py`

| | Detail |
|---|---|
| **Tiers** | `casual` (plain language) · `active` (market terms) · `expert` (regime/signals) |
| **Persistence** | `data/user_profiles/{session_id}.json` |
| **Fields** | `detected_tier`, `tier_confidence`, `sessions_seen`, `topics_seen`, `last_seen` |
| **Lifecycle** | Loaded by dispatch node; updated by synthesize node after each turn |

### 10.3 Tool Catalogue

| Tool | Type | Data source |
|---|---|---|
| `get_live_price` | STATIC | yfinance `fast_info` |
| `get_historical_prices` | STATIC | yfinance OHLCV, close-to-close % change |
| `get_sector_snapshot` | STATIC | SQLite ScoreStore |
| `get_stock_analysis` | STATIC | SQLite ScoreStore, latest verdict |
| `get_analysis_history` | STATIC | SQLite ScoreStore, last N days |
| `get_rl_prediction` | STATIC | `data/predictions/{sector}/{ticker}/` JSON |
| `get_rl_insights` | STATIC | RL weight memory JSON |
| `get_macro_news` | STATIC | Macro cache + yfinance macros |
| `search_market_news` | STATIC | Serper (India-biased) |
| `run_agent_analysis` | LLM | Full 9-agent sector pipeline (~45s) |

---

## 11. ContextBuilder Routing

**File:** `services/data/context/builder.py`

**Lookup precedence:** `_build_{sector}_{agent_name}` → `_build_{agent_name}` → `_build_generic`

**Automobile methods (9 ✅):**

| Method | Fetchers called | Serper calls |
|---|---|---|
| `_build_sales_demand` | `fetch_news_context(queries)` | up to 3 |
| `_build_fundamentals` | `get_fundamentals_context(ticker)` + `fetch_news_context()` | up to 3 |
| `_build_pattern_analysis` | `get_technical_context(ticker)` → RSI, MACD, BB, support/resistance | **0** |
| `_build_sentiment` | `fetch_news_context(queries)` | up to 3 |
| `_build_risk_macro` | `get_macro_context()` + `macro_cache` | 3 on miss, 0 on hit |
| `_build_raw_materials` | `get_raw_materials_context()` + `fetch_news_context(max_queries=1)` | 1 |
| `_build_policy_regulatory` | `fetch_tavily_context()` + `fetch_news_context()` | 3 + 2 Tavily |
| `_build_competitive_intel` | `fetch_news_context(queries)` | up to 3 |
| `_build_valuation_catalyst` | yfinance financials + `fetch_news_context()` | up to 3 |

**BFSI methods (6 ✅):**

| Method | Purpose |
|---|---|
| `_build_bfsi_fundamentals` | NIM/CASA/CRAR context via yfinance + Serper |
| `_build_bfsi_risk` | Credit/liquidity risk context |
| `_build_bfsi_pattern_analysis` | yfinance OHLCV technical context |
| `_build_bfsi_institutional` | Shareholding + FII/DII flows |
| `_build_bfsi_universe_setup` | Sector overview context |
| `_build_macro_policy` | RBI policy news via Serper |

**IT methods (8 ✅):**

| Method | Purpose |
|---|---|
| `_build_it_fundamentals` | Revenue/deal wins/attrition context |
| `_build_global_macro` | US tech spend + currency context |
| `_build_it_risk_macro` | Visa/pricing/concentration risk context |
| `_build_peer_benchmark` | Peer comparison via Serper |
| `_build_it_pattern_analysis` | yfinance OHLCV technical context |
| `_build_it_sentiment` | News/analyst coverage context |
| `_build_transcript_nlp` | Management tone + guidance context |
| `_build_insider_smart_money` | Insider + block deal context |

**RE methods (6 ✅):**

| Method | Purpose |
|---|---|
| `_build_re_fundamentals` | DSCR/CUF/revenue context |
| `_build_business` | Order book + MNRE auction context |
| `_build_valuation` | EV/MW + peer valuation context |
| `_build_sentiment_policy` | MNRE policy + state offtake context |
| `_build_technical` | yfinance OHLCV technical context |
| `_build_re_risk` | DISCOM + regulatory risk context |

**Fallback:**

| Method | Fetchers called | Serper calls |
|---|---|---|
| `_build_generic` | Minimal stub: ticker + company name only | 0 |

**Macro cache architecture (STATIC):**

```
micro_search_loop() → set_macro_cache("automobile", text)
                        TTL = MACRO_CACHE_TTL_HOURS (2h)

ContextBuilder._build_risk_macro():
  get_macro_cache("automobile")
    HIT  → skip all 3 Serper calls for risk_macro
    MISS → run 3 Serper calls, populate cache
```

---

## 12. Static vs LLM Classification — Master Table

| Component | Type | File | Method | Key notes |
|---|---|---|---|---|
| `detect_sector(ticker)` | **STATIC** | `src/backend/sectors/__init__.py` | Hardcoded ticker sets | Default → automobile |
| `CONTEXT_SEARCH_QUERIES` | **STATIC** | Each `prompts/{agent}.py` | Hardcoded keyword strings | Capped by `SERPER_MAX_QUERIES=3` |
| `_resolve_ticker()` | **LLM** | `base_orchestrator.py` | qwen, temp=0.0 | Free text → NSE ticker |
| `_load_learned_weights()` | **STATIC** | `base_orchestrator.py` | JSON file read | Returns None if no data yet |
| Sector analysis agents (×9/8/6) | **LLM** | `sectors/{sector}/agents/*.py` | qwen, temp=0.2 | Score 5 dimensions + overall |
| `AgentOutput.ticker_vs_peers` | **String field** | `sectors/automobile/agents/*.py` | `_parse_output()` | Numeric peer comparison e.g. "MARUTI EBITDA 8.6% vs TATA 10.5% vs M&M 11.2%" |
| `AgentOutput.bull_case_if` | **String field** | above | `_parse_output()` | Specific catalyst for +0.15 score: "e-Vitara 8% EV share by FY27" |
| `AgentOutput.bear_case_if` | **String field** | above | `_parse_output()` | Specific risk for -0.15 score: "Crude >$90 compresses margin 100-150bps" |
| `AgentOutput.what_changed` | **String field** | above | `_parse_output()` | Material cycle delta: "FII +120bps; attrition 2.8%→2.3%" |
| `AgentOutput.data_confidence` | **STATIC** `float [0,1]` | above | `_parse_output()` | 0.3=sparse; 0.7=multiple data points; 1.0=direct verified |
| `SignalAggregator._build_narrative_block()` | **STATIC** | `shared/pipeline/signal_aggregator.py` | Collates agent bull/bear/what_changed | Passed as `{agent_narratives}` to aggregation LLM prompt |
| `SignalAggregator` weight fusion | **STATIC** | `shared/pipeline/signal_aggregator.py` | Weighted sum | `Σ(score × weight)` |
| `SignalAggregator` conflict detection | **STATIC** | above | `delta ≥ 0.30` threshold | Fixed constant |
| `SignalAggregator` verdict synthesis | **LLM** | above | qwen | After conflict detection |
| `FeedbackAgent` miss classification | **LLM** | `rl/agents/feedback_agent.py` | qwen, temp=0.3 | Classifies into 7 miss types |
| `classify_direction()` | **STATIC** | above | `RL_FLAT_THRESHOLD_PCT=0.3` | UP/DOWN/FLAT |
| `merge_lessons_into_ledger()` | **STATIC** | above | Dedup/blend formula | After LLM returns |
| `WeightAdapter.update()` | **STATIC** | `rl/agents/weight_adapter.py` | 3-stage math | Fully deterministic |
| `MISS_TYPE_PENALTY_MULTIPLIER` | **STATIC** | `core/schemas/feedback.py` | Dict lookup | 0.0/0.25/0.5/1.0 |
| `ThesisReviewer.should_review()` | **STATIC** | `rl/agents/thesis_reviewer.py` | ATR-relative threshold | Fires on structural miss or size trigger |
| `ThesisReviewer._compute_atr_pct()` | **STATIC** | above | 14-day ATR via yfinance | Returns 0.0 on failure |
| `ThesisReviewer.review()` | **LLM** | above | qwen, temp=0.1 | Post-miss thesis validation |
| `RegimeDetector.detect()` | **STATIC** | `regime/detector.py` | VIX/FII/RSI thresholds | No LLM |
| Regime multiplier table | **STATIC** | `settings/base.py` | Config constant | Never persisted |
| `ConvictionTracker` | **STATIC** | `rl/conviction/tracker.py` | `min(0.25,(days-4)×0.025)` | Formula |
| RSI divergence amplifier | **STATIC** | above | ×1.5 when streak≥8 + RSI contrast | Cap 0.30 |
| `PromptEnhancer.enhance()` | **STATIC** | `prompt_enhancer/enhancer.py` | Template dict lookup | miss_counter → query strings |
| `SeasonalCalendar.get_context()` | **STATIC** | `seasonal/calendar.py` | YAML + ledger read | No LLM |
| `SeasonalValidator.validate_pattern()` | **STATIC** | `seasonal/validator.py` | State machine | SEEDED→VALIDATED |
| Confidence decay | **STATIC** | `core/schemas/feedback.py` | `conf×(0.98)^months` | Floor 0.10 |
| Cross-ticker boost +0.05 | **STATIC** | `rl/stores/ledger_propagator.py` | Per confirming ticker | propagate_to_shared |
| `input_rail` | **STATIC** | `shared/pipeline/graphs/rails.py` | yfinance fast_info | Non-blocking |
| `output_rail` | **STATIC** | above | Clamp score [0,1] | Non-blocking |
| `conflict_rail` | **STATIC** | above | Spread > 0.35 | Triggers LLM re-resolution |
| `DispatchNode` (chat) | **LLM** | `chat_graph.py` | qwen, temp=0.0 | Query decomposition + tier detection |
| `ExecutorNode` (chat) | **STATIC** | above | `asyncio.gather()` | Parallel tool execution, 0 LLM tokens |
| `SynthesizeNode` (chat) | **LLM** | above | qwen, streaming | Tier-aware response |
| `user_profile.load_profile()` | **STATIC** | `user_profile.py` | JSON file read | Returns defaults if missing |
| `user_profile.save_profile()` | **STATIC** | above | JSON file write | Merges topics, increments sessions |
| `_should_skip_agent_rerun()` | **STATIC** | `daily_review.py` | threshold 0.5% | Skip if direction correct + small error |
| Tavily disk cache | **STATIC** | `tavily_fetcher.py` | MD5 hash + month | Cache key = sorted_queries + YYYY-MM |
| `record_llm_call()` | **STATIC** | `llm_client.py` | JSONL append | `outputs/llm_log/{date}.jsonl` |
| `run_month_end_validation()` | **STATIC** | `month_end_validation.py` | Last trading day only | Validates seasonal patterns vs feedback |

---

## 13. Serper API Budget

**Per-run call count (automobile, 9 agents, macro cache warm):**

| Agent | Serper calls | Notes |
|---|---|---|
| sales_demand | 3 | Per-ticker news |
| fundamentals | 3 | Per-ticker news |
| pattern_analysis | 0 | yfinance only |
| sentiment | 3 | Per-ticker news |
| risk_macro | 0 (warm) / 3 (cold) | Sector macro cache (2h TTL) |
| rubber (NEW) | 0 | Cached 4h in `_RUBBER_CACHE` — 1 Serper/4h shared across all tickers |
| policy_regulatory | 3 | Per-ticker news + 2 Tavily (96% disk cache) |
| raw_materials | 1 | 1 Serper + yfinance (CL=F, BZ=F cached daily in `_COMMODITY_CACHE`) |
| competitive_intel | 3 | Per-ticker news |
| valuation_catalyst | 0 | yfinance only (`_COMMODITY_CACHE`) |
| **Total warm** | **16** | Risk_macro cache hit; rubber shared |
| **Total cold** | **19** | Risk_macro cache miss |

**RBI rate fetch:** 1 Serper/60 days (thread-locked `_RBI_CACHE`) — effectively 0/month.

**Macro Cache Architecture:**

```
micro_search_loop() (main.py, optional --micro-loop flag)
  ↓ runs 2 combined Serper queries per run (TTL = MACRO_CACHE_TTL_HOURS = 2h)
  Query 1: "Nifty Auto index India automobile sector outlook crude oil steel aluminium commodity prices"
  Query 2: "India EV policy electric vehicle incentives FADA retail dispatch RBI repo rate auto loan EMI"
  ↓ stored in get_macro_cache("automobile")

ContextBuilder._build_risk_macro():
  get_macro_cache("automobile")
    HIT  → uses cached text, skips all 3 Serper calls for risk_macro
    MISS → runs 3 Serper calls, populates cache
```

**Micro loop configuration:**

| Variable | Default | Purpose |
|---|---|---|
| `MICRO_CYCLES_PER_DAY` | 6 | Runs every ~4 hours |
| `MICRO_QUERIES_PER_RUN` | 2 | Combined Serper calls per cycle |
| `MACRO_CACHE_TTL_HOURS` | 2 | Cache time-to-live |

**Micro search loop (weekdays only — skips Sat/Sun):**
  3 sectors × 2 queries × 6 cycles × 22 trading days = **792 Serper/month**
  (Previous: 1,080/month when running on weekends)

**Monthly budget (5 tickers, 21 trading days):**

| Usage | Formula | Calls/month |
|---|---|---|
| Pre-market orchestrator (warm) | 16 × 5 tickers × 21 days | 1,680 |
| RL daily review (30% full rerun) | 0.3 × 16 × 5 × 21 | 504 |
| Micro loop (weekdays only) | 3 sectors × 2 × 6 × 22 | 792 |
| **Serper Total** | | **~2,976 / 2,500** ⚠️ |
| Tavily (disk cache) | 2 × 0.04 × 5 × 21 | **~8 / 1,000 (1%)** |

> ⚠️ Serper at 5 tickers exceeds free tier (2,500). Start with 3 tickers/day or upgrade plan.
> With 3 tickers: ~1,848 Serper/month (74% of quota).

---

## 14. Known Gaps Per Sector

**Automobile:**

| Gap | Agent | Fix path | Status |
|---|---|---|---|
| RBI repo rate | risk_macro | Serper live fetch, 60-day cache, settings fallback | ✅ FIXED |
| Rubber ticker ^TOCOM_RUBBER delisted | raw_materials | Serper MCX news proxy, 4h cache | ✅ FIXED |
| `_build_valuation_catalyst` not implemented | valuation_catalyst | Added to ContextBuilder | ✅ FIXED |
| Vahan/FADA/SIAM structured data | sales_demand | Serper proxy only | ❌ OPEN |
| Nifty Auto peer correlation | pattern_analysis | 10 lines of yfinance | ❌ OPEN |
| Emission query 4 skipped (SERPER_MAX=3) | risk_macro | Raise SERPER_MAX_QUERIES | ❌ OPEN |

**Banking/BFSI:**

| Gap | Agent | Fix path | Status |
|---|---|---|---|
| `rbi_data.py` stub | fundamentals, macro_policy | Serper news proxy | ❌ OPEN |
| `npa_metrics.py` stub | fundamentals | Tavily NPA filings | ❌ OPEN |
| ContextBuilder not extended | all 6 agents | — | ✅ FIXED |

**IT Sector:**

| Gap | Agent | Fix path | Status |
|---|---|---|---|
| `deal_wins.py` stub | fundamentals, transcript_nlp | Serper + Tavily | ❌ OPEN |
| `transcript.py` stub | transcript_nlp | Tavily NSE IR pages | ❌ OPEN |
| ContextBuilder not extended | all 8 agents | — | ✅ FIXED |

**Renewable Energy:**

| Gap | Agent | Fix path | Status |
|---|---|---|---|
| `mnre_data.py` stub | business, sentiment_policy | Tavily mnre.gov.in | ❌ OPEN |
| DISCOM payment data | risk | PRAAPTI portal | ❌ OPEN |
| ContextBuilder not extended | all 6 agents | — | ✅ FIXED |

---

## 10. News Data Strategy — Layer A (Macro) + Layer B (Per-Ticker)

### Layer A — RSS Macro Feed (background, scheduler-driven)

**Purpose:** Continuously populated macro/policy news cache. Feeds risk_macro, sentiment, policy_regulatory agents and the chat pipeline automatically.

**Sources (confirmed working 2026-05-21):**

| RSS Feed | Fresh articles/48h | Categories covered |
|---|---|---|
| ET Top Stories | ~44 | economic policy, budget, RBI/SEBI, global macro |
| LiveMint | ~35 | markets, economy, company news |
| BusinessLine | ~60 | markets, sector, policy, commodities |
| Investing.com India | ~10 | Nifty/Sensex, FII/DII, global signals |

**Architecture:** `MacroNewsFetcher.fetch_and_review(query_type)` → `ReviewAgent` (LLM: severity + impact_tags) → `MacroNewsCache` (`data/macro_news/YYYY-MM-DD_macro_feed.json`)

**Scheduler:** APScheduler inside FastAPI — market_hours runs (9am/12pm/3pm IST weekdays) use ET+LiveMint+BusinessLine; daily run (7:30am) includes all 4 feeds.

**Current fetch method:** RSS via `feedparser` (free, no API key). Fallback to Serper /news if RSS returns 0 articles.

**ReviewAgent (LLM):** Assigns `severity` (HIGH/MEDIUM/LOW) and `impact_tags` per article. `satisfied=False` on LLM failure — retry loop fires with refined queries (fixed 2026-05-21).

**Coverage by category:**

| Category | Articles/run | Status |
|---|---|---|
| rbi_policy | 4 | Covered |
| nifty_sensex | 46 | Covered |
| economy_budget | 11 | Covered |
| fii_dii | 7 | Covered |
| sector_news | 79 | Covered |

**What Layer A cannot cover:** Company-specific news, per-ticker editorial, analyst views.

---

### Layer B — Per-Ticker News (Serper + NseIndiaApi)

**Purpose:** Company-specific context fed into each agent's prompt during analysis.

#### Pre-fetch Architecture

```
analyse(ticker)
    │
    ▼  After _resolve_ticker(), before _run_via_graph()
_prefetch_nse_data(query)   [new method in base_orchestrator.py]
    ├── nse.announcements(ticker, days=7)    → regulatory filings, results filings
    ├── nse.boardMeetings(ticker)            → board meeting dates + subjects
    ├── nse.actions(ticker)                  → dividends, bonuses, splits with ex-dates
    └── stored in query.nse_data (dict)      → shared read-only across all 8 parallel agents

Each agent via ContextBuilder.build():
    ├── reads query.nse_data  (NseIndiaApi — official events)
    └── calls fetch_news_context(queries)   (Serper — editorial interpretation)
```

**NseIndiaApi session:** One NSE() instance per analysis run. `try/finally: nse.exit()`. Rate-limited to 3 req/sec — 0.4s sleep between each of the 3 calls. Async path uses `asyncio.to_thread`.

**StockQuery schema addition:**
```python
nse_data: dict = Field(default_factory=dict)
# Structure: {"announcements": [...], "board_meetings": [...], "actions": [...],
#             "symbol_used": "HDFCBANK", "fetched_at": "...", "error": None}
```

#### Coverage Map Per Agent

| Agent | NseIndiaApi provides | Serper provides | Serper queries removed | Permanent gap |
|---|---|---|---|---|
| **fundamentals** | Results filings (`attchmntText`), board meeting dates | Analyst reaction, revenue commentary, EPS vs estimate | 1–2 quarterly results queries | Analyst earnings models, broker reports |
| **earnings** | Board meeting date, results filing timestamp | Earnings call tone, management guidance | 1 board meeting date query | Management call transcripts |
| **valuation_catalyst** | Dividend ex-date, bonus ratio, stock split details | Analyst target prices, P/E commentary, buyback expectations | 1 dividend/bonus news query | DCF models, broker NAV |
| **risk_macro** | SEBI disclosures, regulatory filings, ESOP allotments | Macro policy impact on company, sector risk headlines, debt news | 0 (supplements, not replaces) | Credit rating events, off-balance items |
| **sentiment** | Nothing | Brand news, CEO quotes, consumer sentiment | 0 (Serper only) | Twitter/Reddit/YouTube |
| **sales_demand** | Nothing | FADA dispatch, EV registrations, dealer inventory | 0 (Serper only) | Real-time Vahan portal |
| **pattern_analysis** | Nothing | Nothing (yfinance only) | 0 | — |
| **competitive_intel** | Nothing | Peer market share, EV competitors, deal wins | 0 (Serper only) | Proprietary market research |
| **policy_regulatory** | Regulatory filings (supplement) | SEBI/RBI policy news, compliance updates | 0 (supplements) | SEBI circular PDFs full-text |

#### Call Budget Per Ticker Analysis

| Source | Calls | Cost | Timing |
|---|---|---|---|
| NseIndiaApi `announcements()` | 1 | Free | Pre-fetch, once |
| NseIndiaApi `boardMeetings()` | 1 | Free | Pre-fetch, once |
| NseIndiaApi `actions()` | 1 | Free | Pre-fetch, once |
| Serper (after removing covered queries) | ~25–26 | Credits | Per agent, parallel |
| **Net Serper reduction** | **~4–5 calls saved** | **~15%** | — |

**RL daily review (per ticker per day):**

| Source | Calls | Purpose |
|---|---|---|
| Serper `get_news_context(ticker, days=2)` | 1 credit | Editorial market reaction for yesterday |
| NseIndiaApi `announcements(ticker, days=2)` | Free | Official regulatory events for yesterday |
| Combined → `FeedbackAgentInput.market_context_today` | — | FeedbackAgent gets real data (not "unavailable") |

#### Known Issues

| Issue | Status |
|---|---|
| `TATAMOTORS` announcements returns empty `[]` | `NSE_SYMBOL_OVERRIDES = {"TATAMOTORS": None}` — fallback to Serper-only for this ticker |
| NseIndiaApi down / NSE blocks session | `try/except` in `_prefetch_nse_data()` → `nse_data = {"error": str(exc), "announcements": [], ...}` → agents fall back to Serper-only |
| UI news panel (`ui_data.py`) | Not changed — `search_serper_news()` kept for the frontend live news display |

#### Permanent Gaps — Layer B

- Real-time intraday push news (no confirmed India-native API for NSE at any tested price point)
- Management call transcripts (no source)
- Social media sentiment (paid APIs only)
- Analyst research PDFs (Serper catches mentions only)
- Historical news >7 days (agents only see last 7 days)

---

## 11. Sector Routing

**Entry point:** `SectorRegistry.resolve(ticker)` → `SectorRegistry.get_handler(sector)` → orchestrator class

```
User ticker input
    │
    ▼
SectorRegistry.resolve(ticker)   [TICKER_SECTOR map, ~200 tickers + name-fragment fallback]
    │
    ▼
tier=backend → BackendOrchestratorClass   (Tier 1 — 4 production sectors)
tier=core    → CoreSectorAdapter           (Tier 2 — 23 sectors, disabled by default)
enabled=false → AutomobileAgentOrchestrator (safe degradation)
```

**Tier 1 — Production (always on):**

| Sector | Key | Agents | Orchestrator |
|---|---|---|---|
| Automobile & Auto Ancillaries | `automobile` | 9 | `AutomobileAgentOrchestrator` |
| Banking & BFSI | `banking_bfsi` | 6 | `BankingAgentOrchestrator` |
| IT & Technology | `it_sector` | 8 | `ITAgentOrchestrator` |
| Renewable Energy | `renewable_energy` | 6 | `RenewableAgentOrchestrator` |

**Tier 2 — Core sectors (8-pillar framework, disabled by default):** pharma, fmcg, metals, oilgas, capgoods, chemicals, defence, infra, insurance, realestate, agrochem, hospitality, logistics, media, retail, tech, telecom (23 total). Enable individually via registry. Agents: `business · fundamentals · valuation · technical · macro · risk · management · earnings`.

**Single source of truth for routing:** `TICKER_SECTOR` in `src/backend/sectors/registry.py` (~200 tickers). Sector `settings.TICKERS` (subset) is for scheduler load control only — it is intentionally smaller.

---

## 12. Known Gaps & Technical Backlog

| # | Item | File | Priority | Status |
|---|---|---|---|---|
| 1 | RBI repo rate live fetch | `macro.py` | CRITICAL | ✅ Fixed — env override `RBI_REPO_RATE_PCT`, 60-day staleness warning |
| 2 | Regime thresholds uncalibrated to NSE | `settings/base.py:293–385` | HIGH | ⚠️ Partially done — env-overridable but `regime_config.json` + hot-update endpoint not built |
| 3 | NSE holiday calendar ends 2026 | `nse_calendar.py` | HIGH | ⚠️ Monitor Dec 31 calendar_updater.py run |
| 4 | Sector score thresholds identical across sectors | `settings/base.py` | MEDIUM | ⬜ Backlog — add per-sector `SCORE_THRESHOLDS` |
| 5 | Technical indicator periods not backtested on NSE | `fetcher.py` | MEDIUM | ⬜ Backlog — 14 vs 9 RSI, 12/26 vs 8/17 MACD |
| 6 | Scheduler reads SCHEDULER_TICKERS env var, not managed_tickers.json | `scheduler.py` | MEDIUM | ⚠️ Partially done — reads managed_tickers.json with fallback to env var |
| 7 | Agent parse failure returns silent 0.5 | `base_agent.py` | MEDIUM | ⬜ Backlog — return explicit `AgentOutput.error="parse_failed"` |
| 8 | `external_shock` miss type never penalises | `schemas/feedback.py` | LOW | ⬜ Backlog — after 3 consecutive: apply 0.1× penalty |
| 9 | Feedback LLM temperature hardcoded 0.3 | `feedback_agent.py:56` | LOW | ⬜ Backlog — move to `settings.FEEDBACK_LLM_TEMPERATURE` |
| 10 | Error handling: all external calls now guarded | All fetchers/stores | DONE | ✅ Fixed — 14-file audit complete 2026-05-21 |

**Review schedule:**
- Every deploy: verify RBI rate freshness (`RBI_REPO_RATE_PCT` after each MPC decision)
- Monthly: review regime multiplier table vs actual VIX/FII behaviour
- Dec 31: monitor `calendar_updater.py` for 2027 holiday fetch
