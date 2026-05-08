# Agentic Design Reference

> All agents, tasks, metrics, data sources, static vs LLM responsibilities.
> Minimize plain text — prefer tables and trees.
> Updated: 2026-05-08 · Covers automobile (full) + 3 scaffolded sectors + RL + Chat agents.

---

## 1. Agent Taxonomy

```
StockAgent Agents
├── Analysis Agents  (sector-specific, run monthly + on-demand)
│   ├── Automobile       9 agents  ✅ FULLY IMPLEMENTED
│   ├── Banking/BFSI     6 agents  🔶 SCAFFOLDED (prompts ready, fetchers are stubs)
│   ├── IT Sector        8 agents  🔶 SCAFFOLDED
│   └── Renewable Energy 6 agents  🔶 SCAFFOLDED
│
├── RL Agents  (cross-sector, run daily automated post-market)
│   ├── FeedbackAgent     [LLM]    daily root-cause analysis
│   └── WeightAdapter     [STATIC] deterministic weight adjustment
│
└── Chat Agent  (on-demand via /ui/chat)
    ├── IntentDetector    [STATIC] regex + keyword (Phase 6 stubs exist)
    ├── EntityExtractor   [STATIC] ticker/agent pattern matching (Phase 6 stubs exist)
    └── ChatEngine        [LLM]    tool loop, max 4 rounds
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
  └── FALLBACK: "Stock: MARUTI | Date: 2026-05-08 | Note: Live data unavailable."
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
| **Known gap** | RBI repo rate is a hardcoded static value in `macro.py:get_rbi_repo_rate()` — needs live MPC scraping |
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
| **yfinance tickers** | `SLX` (steel), `AA` (aluminium), `PPLT` (platinum), `PALL` (palladium), `CL=F` (crude), `BZ=F` (Brent), `^TOCOM_RUBBER` (silently skipped if unavailable) |
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
| **Context** | `_build_generic` — NOT YET IMPLEMENTED in ContextBuilder → LLM knowledge only |
| **yfinance** | ✗ (via context builder; effectively none until implemented) |
| **Serper calls** | 0 (context builder fallback means no queries run) |
| **Schema** | `ValuationCatalystOutput` + `ValuationCatalystSubScores` |
| **Output bubbles up** | 5 extra fields flow to `FinalReport` via SignalAggregator (price_target, recovery_timeline_quarters, undervalued_by_pct, discount_reason, recovery_catalysts) |
| **Known gap** | `_build_valuation_catalyst` missing in ContextBuilder — ⚠️ relies entirely on LLM training knowledge |

---

## 5. Banking/BFSI Sector — 6 Agents 🔶

All agents inherit BaseAgent. CONTEXT_SEARCH_QUERIES defined. ContextBuilder not extended → LLM training knowledge fallback. `rbi_data.py` + `npa_metrics.py` fetchers raise `NotImplementedError` (Phase 7 target).

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

## 6. IT Sector — 8 Agents 🔶

`deal_wins.py` + `transcript.py` fetchers raise `NotImplementedError` (Phase 7 target).

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

## 7. Renewable Energy Sector — 6 Agents 🔶

`mnre_data.py` fetcher raises `NotImplementedError` (Phase 7 target).

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

---

## 10. Chat Engine (Phase 6)

Current state: `/ui/chat` endpoint in `services/api/routes/ui_data.py` has a working agentic tool loop. `src/backend/intelligence/chat/` directory exists with stub `__init__.py` files — full extraction is Phase 6.

### 10.1 Current `/ui/chat` — Agentic Tool Loop *(Implemented)*

**File:** `services/api/routes/ui_data.py`

```
POST /ui/chat
  body: {message: str, history: [{role, content}]}
  history capped at last 6 turns for token budget

Max 4 LLM rounds. Tools run in parallel via asyncio.gather:

┌─────────────────────────────────────────────────────────┐
│  Tool 1: get_live_price [STATIC data fetch]              │
│    → yfinance for NSE tickers + commodities             │
│    Symbols: {ticker}.NS, SI=F (silver), GC=F (gold),    │
│    CL=F (crude), ^NSEI (Nifty), USDINR=X, etc.         │
│                                                          │
│  Tool 2: search_market_news [STATIC API call]            │
│    → Tavily search_depth="basic"                        │
│    Any natural language query                           │
│                                                          │
│  Tool 3: get_stock_analysis [STATIC DB read]             │
│    → SQLite ScoreStore for tracked tickers              │
│    Returns latest FinalReport verdict + thesis           │
└─────────────────────────────────────────────────────────┘

System prompt rules (STATIC enforcement):
  - ALWAYS call get_live_price before answering price questions
  - ALWAYS call search_market_news for "why" questions
  - NEVER hallucinate prices
```

### 10.2 Planned Chat Engine (Phase 6) — Extraction from ui_data.py

**IntentDetector** (`chat/algorithms/intent_detector.py`): **STATIC** — pure regex + keyword matching

| Intent | Detection method (STATIC) |
|---|---|
| `compare_tickers` | Patterns: "compare X vs Y", "X or Y", "better" between tickers |
| `explain_agent` | Patterns: "what does {agent_name} do", "explain sales demand" |
| `score_query` | Keywords: "score", "rating", "verdict" + ticker |
| `predict` | Keywords: "will X go up", "target price", "forecast" |
| `analyze` | Keywords: "analyze X", "run analysis", "should I buy" |
| `generic` | Fallback — no pattern matched |

**EntityExtractor** (`chat/algorithms/entity_extractor.py`): **STATIC** — pattern matching against lists

```python
KNOWN_TICKERS = {all NSE tickers from sector settings}
KNOWN_AGENTS  = {"sales_demand", "fundamentals", "pattern_analysis", "risk_macro", ...}
# Output: Entities(tickers: list[str], agents: list[str], sector: str | None)
```

**ChatEngine** (`chat/engine.py`): **LLM** — routes based on STATIC intent + entity detection

---

## 11. ContextBuilder Routing

**File:** `services/data/context/builder.py`

**Lookup precedence:** `_build_{sector}_{agent_name}` → `_build_{agent_name}` → `_build_generic`

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
| `_build_valuation_catalyst` | ⚠️ NOT IMPLEMENTED → falls back to `_build_generic` | 0 |
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
| `SignalAggregator` weight fusion | **STATIC** | `shared/pipeline/signal_aggregator.py` | Weighted sum | `Σ(score × weight)` |
| `SignalAggregator` conflict detection | **STATIC** | above | `delta ≥ 0.30` threshold | Fixed constant |
| `SignalAggregator` verdict synthesis | **LLM** | above | qwen | After conflict detection |
| `FeedbackAgent` miss classification | **LLM** | `rl/agents/feedback_agent.py` | qwen, temp=0.3 | Classifies into 7 miss types |
| `classify_direction()` | **STATIC** | above | `RL_FLAT_THRESHOLD_PCT=0.3` | UP/DOWN/FLAT |
| `merge_lessons_into_ledger()` | **STATIC** | above | Dedup/blend formula | After LLM returns |
| `WeightAdapter.update()` | **STATIC** | `rl/agents/weight_adapter.py` | 3-stage math | Fully deterministic |
| `MISS_TYPE_PENALTY_MULTIPLIER` | **STATIC** | `core/schemas/feedback.py` | Dict lookup | 0.0/0.25/0.5/1.0 |
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
| `IntentDetector.classify()` | **STATIC** | `chat/algorithms/intent_detector.py` | Regex + keywords | Phase 6 (stub) |
| `EntityExtractor.extract()` | **STATIC** | `chat/algorithms/entity_extractor.py` | KNOWN_TICKERS set | Phase 6 (stub) |
| `ChatEngine.reply()` | **LLM** | `chat/engine.py` | qwen | With agentic tool loop |

---

## 13. Serper API Budget

**Per-run call count (automobile, 9 agents, no macro cache):**

| Agent | Serper calls | Cacheable? |
|---|---|---|
| sales_demand | 3 | No (per-ticker) |
| fundamentals | 3 | No (per-ticker) |
| pattern_analysis | **0** | n/a (yfinance only) |
| sentiment | 3 | No (per-ticker) |
| risk_macro | 3 cold / **0** warm | **Yes** (sector-level, TTL 2h) |
| policy_regulatory | 3 | No (per-ticker) |
| competitive_intel | 3 | No (per-ticker) |
| raw_materials | 1 | No |
| valuation_catalyst | 0 | No context builder |
| **Total (cold)** | **19** | |
| **Total (warm cache)** | **16** | |

**Monthly budget at 1 run/day, 5 tickers, with macro cache:**

```
Per-stock: 16 Serper + 2 Tavily
5 tickers/day × 22 trading days = 1760 Serper / month (70% of 2500 free tier)
```

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

**Budget math (5 tickers/day, with macro cache):**

| Usage | Formula | Calls/month |
|---|---|---|
| Per-stock analysis (warm) | 16 calls × 5 tickers × 22 days | 1,760 |
| Micro search overhead | 2 queries × 6 cycles × 22 days | 264 |
| **Total** | | **2,024 / 2,500** |
| Saved by macro cache vs no-cache | 3 calls × 5 tickers × 22 days | 330 saved |

---

## 14. Known Gaps Per Sector

**Automobile (live, high priority):**

| Gap | Agent | Fix path |
|---|---|---|
| RBI repo rate hardcoded | risk_macro | Scrape rbi.org.in or add Serper micro query |
| `_build_valuation_catalyst` not implemented | valuation_catalyst | Add to ContextBuilder; use yfinance financials |
| Vahan/FADA/SIAM structured data | sales_demand | Add `vahan_fada.py` fetcher using Serper proxy (Phase 7) |
| Nifty Auto peer correlation not computed | pattern_analysis | 10 lines of yfinance multi-ticker + `.corr()` |
| Emission query 4 skipped (SERPER_MAX=3) | risk_macro | Raise `SERPER_MAX_QUERIES` to 4 or move to dedicated fetcher |

**Banking/BFSI (scaffolded):**

| Gap | Agent | Fix path |
|---|---|---|
| `rbi_data.py` is a stub | fundamentals, macro_policy | Implement Serper news proxy for RBI press releases (Phase 7) |
| `npa_metrics.py` is a stub | fundamentals | Implement Tavily fetch for BSE/NSE quarterly NPA filings |
| ContextBuilder not extended | all 6 agents | Add `_build_bfsi_{agent}` routing branches in builder.py |

**IT Sector (scaffolded):**

| Gap | Agent | Fix path |
|---|---|---|
| `deal_wins.py` is a stub | fundamentals, transcript_nlp | Implement Serper + Tavily for TCV announcements (Phase 7) |
| `transcript.py` is a stub | transcript_nlp | Implement Tavily extraction on NSE IR pages |
| ContextBuilder not extended | all 8 agents | Add `_build_it_{agent}` routing branches |

**Renewable Energy (scaffolded):**

| Gap | Agent | Fix path |
|---|---|---|
| `mnre_data.py` is a stub | business, sentiment_policy | Implement Tavily fetch from mnre.gov.in/tenders |
| DISCOM payment data | risk | Fetch from PRAAPTI portal news |
| ContextBuilder not extended | all 6 agents | Add `_build_re_{agent}` routing branches |
