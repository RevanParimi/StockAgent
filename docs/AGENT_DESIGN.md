# Agent Design Reference

> Updated: 2026-04-19 · 9 automobile agents active · 3 other sectors stubbed

---

## Execution Architecture

```
AutomobileAgentOrchestrator.analyse(ticker)
       │
       ├─ _resolve_ticker()  →  LLM  →  StockQuery
       │
       ├─ ThreadPoolExecutor (9 workers, parallel)
       │     SalesDemandAgent.run()
       │     RawMaterialsAgent.run()
       │     FundamentalsAgent.run()
       │     PatternAnalysisAgent.run()
       │     SentimentAgent.run()
       │     PolicyRegulatoryAgent.run()
       │     CompetitiveIntelAgent.run()
       │     RiskMacroAgent.run()
       │     ValuationCatalystAgent.run()
       │
       └─ SignalAggregator.run()  →  FinalReport

Async path (FastAPI/WebSocket): analyse_async() uses asyncio.gather + AsyncOpenAI.
```

---

## BaseAgent (`core/pipeline/base_agent.py`)

All 9 agents inherit from `BaseAgent`. Subclasses implement 3 things:

| Abstract | Signature | Purpose |
|---|---|---|
| `agent_name` | `@property → str` | snake_case id, matches key in `AGENT_WEIGHTS` |
| `_build_prompt` | `(query, context) → (system_prompt, user_prompt)` | Assembles the LLM prompt |
| `_parse_output` | `(data: dict, ticker: str) → AgentOutput` | Parses JSON response into typed output |

**Context priority** in `_gather_context()`:
1. RAG retrieval — if `RAG_ENABLED=true` (disabled by default)
2. `ContextBuilder.build(agent_name, query)` — live data from fetchers
3. Generic stub — ticker + company name only (fallback when fetchers fail)

**Retry logic**: 3 attempts with exponential backoff on `APIError`, `RateLimitError`, `APITimeoutError`.

---

## 9 Automobile Agents

### 1. SalesDemandAgent
**Score dimensions:** FADA/SIAM dispatch · EV Vahan registrations · dealer inventory · export/import · used-car price index  
**Context:** Serper news (CONTEXT_SEARCH_QUERIES from `config/prompts/automobile/sales_demand.py`)  
**Schema:** `SalesDemandOutput` + `SalesDemandSubScores`

### 2. RawMaterialsAgent
**Score dimensions:** steel/aluminium · platinum/palladium · crude/polymer · power tariff · commodities trend  
**Context:** yfinance prices (SLX, AA, PPLT, PALL, CL=F, BZ=F) → `get_raw_materials_context()` + Serper (1 query)  
**Schema:** `RawMaterialsOutput` + `RawMaterialsSubScores`

### 3. FundamentalsAgent
**Score dimensions:** revenue/EBITDA delta · margin vs peers · order book · attrition/headcount · promoter/FII/DII flow  
**Context:** `get_fundamentals_context(ticker)` (yfinance quarterly financials) + Serper news  
**Schema:** `FundamentalsOutput` + `FundamentalsSubScores`  
**Note:** yfinance may 404 for newly-listed stocks (e.g. ATHERENERGY.NS) — falls back to LLM knowledge.

### 4. PatternAnalysisAgent
**Score dimensions:** price cycle position · seasonal pattern · RSI/MACD/BB · breakout/support zones · peer correlation  
**Context:** `get_technical_context(ticker)` → 10yr OHLCV → RSI, MACD, Bollinger, support/resistance, peer beta  
**Schema:** `PatternAnalysisOutput` + `PatternAnalysisSubScores`

### 5. SentimentAgent
**Score dimensions:** news NLP · management tone · Twitter/Reddit · YouTube spikes · dealer/consumer feedback  
**Context:** Serper news  
**Schema:** `SentimentOutput` + `SentimentSubScores`

### 6. PolicyRegulatoryAgent
**Score dimensions:** FAME/EV subsidy · emission norms · union budget duties · PLI scheme · state EV incentives  
**Context:** Tavily full-page (policy PDFs, government circulars) + Serper  
**Schema:** `PolicyRegulatoryOutput` + `PolicyRegulatorySubScores`

### 7. CompetitiveIntelAgent
**Score dimensions:** EV market share · new model pipeline · JV/acquisitions · ADAS/safety ratings · competitive position  
**Context:** Serper news  
**Schema:** `CompetitiveIntelOutput` + `CompetitiveIntelSubScores`

### 8. RiskMacroAgent
**Score dimensions:** INR/USD & crude exposure · commodity prices · RBI repo/EMI impact · emission policy risk · **global geopolitical risk**  
**Global geopolitical risk** covers 4 channels: oil supply shock · FII outflow · INR depreciation · supply chain disruption (China semiconductors/EV components)  
**Context:** `get_macro_context()` (yfinance: INR=X, CL=F, SLX, AA) + macro_cache OR Serper  
**Schema:** `RiskMacroOutput` + `RiskMacroSubScores`  
**Macro cache:** `get_macro_cache("automobile")` — pre-populated by `--micro-loop` flag; saves 3 Serper calls per run.

### 9. ValuationCatalystAgent *(Gap 2, added eaf52ab)*
**Score dimensions:** P/E discount vs 5yr history · P/E discount vs peer median · discount reason clarity · catalyst strength · price target confidence  
**Context:** `_build_generic` (ContextBuilder method not yet implemented — uses LLM knowledge only)  
**Schema:** `ValuationCatalystOutput` + `ValuationCatalystSubScores`  
**Extra output fields:** `fair_value_estimate`, `current_discount_pct`, `discount_reason`, `recovery_catalysts[]`, `price_target`, `recovery_timeline_quarters`  
**These 5 fields bubble up to `FinalReport`** via SignalAggregator (Gap 3 fix).

---

## SignalAggregator (`core/pipeline/signal_aggregator.py`)

1. Applies `AGENT_WEIGHTS` (or `learned_weights` from RL loop) to each agent's `overall_score`
2. Detects conflicts: any pair with score delta ≥ 0.30 → flagged
3. LLM call with all scores + conflicts → JSON: `{verdict, final_score, conviction_drivers, top_risks, investment_thesis, conflicts_resolved}`
4. Extracts valuation fields from `valuation_catalyst` output → populates `FinalReport`
5. Returns `FinalReport`

**Verdict thresholds** (from `settings.SCORE_THRESHOLDS`):

| Verdict | Score range |
|---|---|
| STRONG BUY | 0.75 – 1.00 |
| BUY | 0.55 – 0.75 |
| NEUTRAL | 0.40 – 0.55 |
| SELL | 0.20 – 0.40 |
| STRONG SELL | 0.00 – 0.20 |

---

## Other Sectors (Stubs)

Banking/BFSI, IT, Renewable Energy sectors have `agents.py` and `graph.py` files under `core/sectors/{sector}/` but agent logic is not implemented — they inherit from BaseAgent with placeholder `_parse_output`.

Sector routing is not yet wired in the orchestrator — all tickers run automobile agents.

---

## RL Feedback Loop (`intelligence/rl/`)

| Module | Role |
|---|---|
| `stores/prediction_store.py` | Saves `{ticker, run_id, verdict, final_score, date}` |
| `agents/feedback_agent.py` | After N days: compares prediction vs actual price move, generates accuracy signal |
| `agents/weight_adapter.py` | Updates `AGENT_WEIGHTS` based on which agents were most predictive |
| `workflows/generate_forecast.py` | Pre-injects learned weights into orchestrator before a run |
| `workflows/daily_review.py` | Scheduled daily: process predictions older than review_window, update weights |

Activate by setting `learned_weights` on the orchestrator:
```python
orchestrator._aggregator_weights = weight_adapter.get_weights(ticker)
```
