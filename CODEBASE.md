# Codebase Reference

> Ground-truth map for new developers and new Claude sessions.
> Everything needed to understand, navigate, and extend StockAgent.
> Updated: 2026-05-08 · Phases 0–9 + Evolution P1–P5 complete.
> Previous snapshots: docs/CODEBASE.md (April 2026 layout)

---

## 1. What This System Does

**StockAgent** analyses NSE/BSE-listed Indian stocks across 4 sectors. It runs up to 9 specialist AI agents in parallel, fuses their outputs through a weighted Signal Aggregator, and — critically — reviews its own predictions every trading day to get smarter over time via a persistent RL feedback loop.

**Key differentiators vs one-shot LLM tools:**
- Per-ticker JSON memory that survives month rollovers
- Agent credibility weights earned by real accuracy (not config)
- 30-day living forecast revised daily as reality unfolds
- Lesson library compounds — after 6 months it knows stock-specific patterns

---

## 2. Multi-Language Stack

| Language | Module | Port | Role |
|---|---|---|---|
| **Python** | 9 LLM agents, orchestrator, RL loop, FastAPI | 8000 (Railway) / 8001 (local) | Core intelligence |
| **TypeScript** | Bun + Hono gateway, WS proxy, analysis cron | 3000 (public) | API gateway |
| **C++** | RSI / MACD / Bollinger Bands via pybind11 | in-process `.pyd` | Fast indicators |
| **React (Babel)** | Prototype frontend dashboard | `/app/index.html` | Deployed UI |
| **React + Vite** | Dev frontend dashboard | 5173 (dev) | Dev UI (not deployed) |
| **C#** | Quartz.NET scheduler + EF Core | 5000 (optional) | Alt persistence |

**Language boundary rule:** All cross-language calls are JSON over HTTP. The C++ extension is the only in-process FFI (pybind11 — silent fallback to pure Python if `.pyd` absent).

---

## 3. Full Directory Layout

```
StockAgent-main/
├── main.py                          ← CLI: python main.py <ticker>
├── requirements.txt
├── pyproject.toml                   ← pythonpath=[".", "src"] — legacy + new imports resolve
├── langgraph.json                   ← sector graph registry → src/backend/sectors/*/pipeline/graph.py
├── docs/                            ← all .md documentation
│   ├── RL_DESIGN.md                 ← RL loop: formulas, flows, schemas, static vs LLM ★
│   ├── AGENTIC_DESIGN.md            ← all agents: tasks, metrics, data sources, gaps ★
│   ├── PHASE_5_6_7_PLAN.md          ← implementation plan: algorithm extractions, data layer move
│   └── (archived: FLOW.md, AGENT_DESIGN.md, SOLUTION_DESIGN.md, API_SOURCES.md, RL_*.md)
│
├── src/
│   ├── backend/
│   │   ├── shared/                  ← cross-sector shared code
│   │   │   ├── schemas/
│   │   │   │   ├── pipeline.py      ← StockQuery, AgentOutput, FinalReport, WeightedAgentScore
│   │   │   │   └── feedback.py      ← ALL RL schemas (MissType, Lesson, WeightMemory, etc.)
│   │   │   ├── pipeline/
│   │   │   │   ├── base_agent.py         ← BaseAgent ABC — sector-agnostic
│   │   │   │   ├── base_orchestrator.py  ← BaseSectorOrchestrator ABC
│   │   │   │   ├── signal_aggregator.py  ← SignalAggregator — weighted LLM fusion → FinalReport
│   │   │   │   └── graphs/
│   │   │   │       ├── nodes.py     ← make_dispatch_fn, make_run_agent_node, make_aggregate_node
│   │   │   │       ├── rails.py     ← conflict_rail, input_rail, output_rail
│   │   │   │       └── state.py     ← GraphState (TypedDict with merge reducers)
│   │   │   ├── prompts/
│   │   │   │   ├── orchestrator.py        ← Ticker resolution prompt
│   │   │   │   ├── signal_aggregator.py   ← Verdict synthesis prompt
│   │   │   │   └── feedback_agent.py      ← RL miss analysis prompt (dynamic per sector)
│   │   │   ├── config/
│   │   │   │   └── settings/base.py       ← ALL shared constants: LLM, API keys, weights, RL
│   │   │   ├── data/                      ← FORWARD SHIMS → services/data/ (real until Phase 7)
│   │   │   │   ├── fetchers/              ← fundamentals.py, macro.py, news.py
│   │   │   │   ├── stores/                ← score_store.py, run_logger.py, analysis_logger.py
│   │   │   │   └── cache/                 ← macro_cache.py
│   │   │   └── clients/                   ← FORWARD SHIMS → services/clients/ (real until Phase 7)
│   │   │                                  ← llm_client.py, tavily_fetcher.py, alerting.py
│   │   │
│   │   ├── sectors/
│   │   │   ├── __init__.py          ← detect_sector(ticker) + get_orchestrator(sector)
│   │   │   ├── automobile/          ← ✅ FULLY IMPLEMENTED (9 agents, RL loop live)
│   │   │   │   ├── agents/          ← 9 files: one agent class per file
│   │   │   │   ├── prompts/         ← 9 files: SYSTEM_PROMPT + ANALYSIS_PROMPT + CONTEXT_SEARCH_QUERIES
│   │   │   │   ├── schemas/sub_scores.py  ← 9 Pydantic sub-score models
│   │   │   │   ├── config/settings.py     ← AGENT_WEIGHTS, TICKERS, PEER_TICKERS
│   │   │   │   ├── config/registry.py     ← AGENTS dict (9 instances) + WEIGHTS
│   │   │   │   ├── data/fetchers/vahan_fada.py   ← stub (Phase 7 target)
│   │   │   │   ├── data/context/builder.py       ← AutomobileContextBuilder
│   │   │   │   └── pipeline/
│   │   │   │       ├── orchestrator.py  ← AutomobileAgentOrchestrator(BaseSectorOrchestrator)
│   │   │   │       └── graph.py         ← LangGraph StateGraph
│   │   │   │
│   │   │   ├── banking_bfsi/        ← 🔶 SCAFFOLDED (agents + prompts ready, fetchers stubs)
│   │   │   │   ├── agents/          ← 6 files: fundamentals, risk, macro_policy, institutional,
│   │   │   │   │                    ←          pattern_analysis, universe_setup
│   │   │   │   ├── prompts/         ← 6 matching files
│   │   │   │   ├── schemas/sub_scores.py  ← 6 models (NPA, NIM, CRAR, etc.)
│   │   │   │   ├── data/fetchers/rbi_data.py     ← stub (Phase 7 target)
│   │   │   │   ├── data/fetchers/npa_metrics.py  ← stub (Phase 7 target)
│   │   │   │   └── pipeline/orchestrator.py + graph.py
│   │   │   │
│   │   │   ├── it_sector/           ← 🔶 SCAFFOLDED
│   │   │   │   ├── agents/          ← 8 files: fundamentals, global_macro, risk_macro,
│   │   │   │   │                    ←          peer_benchmark, pattern_analysis, sentiment,
│   │   │   │   │                    ←          transcript_nlp, insider_smart_money
│   │   │   │   ├── prompts/         ← 8 matching files
│   │   │   │   ├── schemas/sub_scores.py  ← 8 models (deal_wins, attrition, visa_risk, etc.)
│   │   │   │   ├── data/fetchers/deal_wins.py   ← stub (Phase 7 target)
│   │   │   │   ├── data/fetchers/transcript.py  ← stub (Phase 7 target)
│   │   │   │   └── pipeline/orchestrator.py + graph.py
│   │   │   │
│   │   │   └── renewable_energy/    ← 🔶 SCAFFOLDED
│   │   │       ├── agents/          ← 6 files: fundamentals, business, valuation,
│   │   │       │                    ←          sentiment_policy, technical, risk
│   │   │       ├── prompts/         ← 6 matching files
│   │   │       ├── schemas/sub_scores.py  ← 6 models (CUF, DSCR, EV/MW, DISCOM, etc.)
│   │   │       ├── data/fetchers/mnre_data.py  ← stub (Phase 7 target)
│   │   │       └── pipeline/orchestrator.py + graph.py
│   │   │
│   │   ├── intelligence/
│   │   │   ├── rl/
│   │   │   │   ├── agents/          ← feedback_agent.py, weight_adapter.py
│   │   │   │   ├── conviction/      ← tracker.py (mean-reversion prior)
│   │   │   │   ├── stores/          ← prediction_store.py, ledger_propagator.py
│   │   │   │   ├── workflows/       ← daily_review.py (8-step loop), generate_forecast.py
│   │   │   │   ├── nse_calendar.py  ← dynamic NSE holiday loading
│   │   │   │   ├── calendar_updater.py ← Dec 31 job; writes data/nse_holidays.json
│   │   │   │   └── algorithms/      ← Phase 5 extraction target (weight_adaptation/,
│   │   │   │                        ←   conviction/, forecast/, feedback/, regime/signals/)
│   │   │   ├── chat/                ← Phase 6 stubs: engine.py, context/, algorithms/, prompts/
│   │   │   ├── seasonal/            ← calendar.py, validator.py, seeds/{sector}.yaml (P1)
│   │   │   ├── regime/              ← detector.py (P5)
│   │   │   ├── prompt_enhancer/     ← enhancer.py (P4)
│   │   │   ├── rag/                 ← ChromaDB + sentence-transformers (disabled by default)
│   │   │   └── algorithms/          ← indicators/fetcher.py (RSI/MACD/BB, C++ or pure Python)
│   │   │
│   │   ├── api/routes/              ← STUBS pointing to real services/api/routes/
│   │   └── scheduler/python/        ← STUBS pointing to real services/scheduler/
│   │
│   └── frontend/
│       ├── web/                     ← Vite+React app (dev build — NOT deployed)
│       │   ├── package.json         ← React 18 + Vite 5 + Zustand + Recharts + Three.js
│       │   ├── vite.config.ts       ← Dev proxy: /api /ui /analyse /history /ws → :8000
│       │   └── src/
│       │       ├── types/api.ts     ← TypeScript mirror of all backend Pydantic schemas
│       │       ├── stores/          ← analysisStore, watchlistStore, sectorStore (Zustand)
│       │       ├── features/        ← useAnalysis.ts, useAgentProgress.ts, useChatHistory.ts
│       │       ├── components/      ← shared/ui/, shared/charts/, layout/, analysis/
│       │       └── pages/           ← home/, agents/, analysis/, portfolio/, learn/ (stubs)
│       │
│       └── prototypes/              ← ✅ DEPLOYED Babel prototype (no build step)
│           │                        ← Live: stockagent-ai.up.railway.app/app/index.html
│           │                        ← Served by services/api/server.py StaticFiles at /app
│           ├── index.html           ← App entry: TWEAK_DEFAULTS, App component, NavChip
│           ├── styles.css           ← All CSS vars: light theme + dark [data-theme="dark"]
│           ├── data.jsx             ← Sets window.* mock globals → fetches /ui/bootstrap
│           ├── home.jsx             ← Home + TopNav + TodayPane + WatchlistPane + drawers
│           ├── agents-page.jsx      ← AgentsPage, AgentCard, AgentDrawer, Pipeline
│           ├── portfolio.jsx        ← PortfolioPage (100% mock — no backend wiring)
│           ├── learn.jsx            ← LearnPage (100% static educational content)
│           ├── analytics.jsx        ← RL performance, Power BI OData feed
│           ├── logs.jsx             ← Live log stream (SSE /ui/logs/stream)
│           ├── prompt-lab.jsx       ← Prompt editor + GitHub deploy schedule UI
│           ├── auth.jsx             ← Auth screen (mock — no backend)
│           ├── sphere.jsx           ← Three.js animated orb + ChatOverlay
│           ├── icons.jsx            ← SVG icon library (window.Icon)
│           └── tweaks-panel.jsx     ← useTweaks hook + dev-only TweaksPanel
│
├── core/                            ← LEGACY — shims re-exporting from src/backend/
│   ├── schemas/                     ← SHIMS → src/backend/shared/schemas/
│   ├── config/                      ← SHIMS → src/backend/shared/config/
│   ├── graphs/                      ← SHIMS → src/backend/shared/pipeline/graphs/
│   ├── pipeline/                    ← SHIMS → src/backend/shared/pipeline/
│   ├── sectors/automobile/          ← SHIMS → src/backend/sectors/automobile/
│   ├── sectors/banking|it|renewable ← SHIMS → src/backend/sectors/*/config/registry.py
│   └── intelligence/                ← REAL FILES (Phase 5 target for move to src/)
│       ├── rl/                      ← feedback_agent, weight_adapter, stores, workflows
│       ├── regime/                  ← detector.py
│       ├── seasonal/                ← calendar.py, validator.py, seeds/
│       ├── prompt_enhancer/         ← enhancer.py
│       └── algorithms/indicators/   ← fetcher.py (C++ dispatch)
│
├── services/                        ← REAL runtime files (Phase 7 moves to src/backend/)
│   ├── api/
│   │   ├── server.py                ← REAL FastAPI app + lifespan + BackgroundScheduler
│   │   └── routes/
│   │       ├── analyse.py           ← POST /analyse (sector-aware)
│   │       ├── stream.py            ← WS /ws/stream (sector-aware)
│   │       ├── history.py           ← GET /history/*
│   │       ├── scheduler_api.py     ← POST /scheduler/* + GET /scheduler/status
│   │       └── ui_data.py           ← ALL /ui/* routes including /ui/chat agentic loop
│   ├── clients/                     ← llm_client.py, tavily_fetcher.py, alerting.py
│   ├── data/
│   │   ├── fetchers/                ← fundamentals.py, macro.py, news.py
│   │   ├── stores/                  ← score_store.py, run_logger.py, analysis_logger.py, api_usage.py
│   │   ├── cache/                   ← macro_cache.py
│   │   └── context/builder.py       ← ContextBuilder.build(agent_name, query) → str
│   └── scheduler/
│       ├── python/scheduler.py      ← APScheduler: RL daily review (4:30pm IST weekdays)
│       └── run_schedule.py          ← CLI: forecast / daily-review / feedback-status / start
│
├── data/                            ← Runtime only — gitignored
│   ├── scores.db                    ← SQLite: all FinalReport history
│   ├── nse_holidays.json            ← NSE holidays by year (written by calendar_updater)
│   ├── agent_weights.json           ← User-overridden agent weights (UI sliders)
│   ├── agent_tasks.json             ← User-toggled task flags (UI toggles)
│   ├── watchlist.json               ← User-saved watchlist tickers
│   ├── category_tickers.json        ← Category → tickers mapping (editable via API)
│   └── predictions/                 ← RL memory (see docs/RL_DESIGN.md §3 for full layout)
│
└── tests/
    ├── unit/
    │   ├── shared/                  ← test_schemas, test_signal_aggregator, test_config
    │   ├── sectors/
    │   │   ├── automobile/          ← test_agents (30 tests), test_prompts
    │   │   ├── banking_bfsi/        ← test_agents (30 parametrized tests — 6 agents)
    │   │   ├── it_sector/           ← test_agents (32 parametrized tests — 8 agents)
    │   │   └── renewable_energy/    ← test_agents (24 parametrized tests — 6 agents)
    │   └── intelligence/rl/         ← test_algorithms stubs + 4 live math tests
    ├── integration/
    │   └── test_sector_routing.py   ← 19 tests: detect_sector + get_orchestrator all 4 sectors
    └── contract/                    ← test_phase0–4: LLM migration, C++, TS, C#

Test baseline: 777 passed, 29 skipped (Phase 6 stubs), 0 failed
```

---

## 4. Sector Registry

**File:** `src/backend/sectors/__init__.py`

```python
detect_sector("HDFCBANK")    → "banking_bfsi"
detect_sector("TCS")         → "it_sector"
detect_sector("ADANIGREEN")  → "renewable_energy"
detect_sector("MARUTI")      → "automobile"   # default fallback for unknown tickers

get_orchestrator("automobile")       → AutomobileAgentOrchestrator
get_orchestrator("banking_bfsi")     → BankingAgentOrchestrator
get_orchestrator("it_sector")        → ITAgentOrchestrator
get_orchestrator("renewable_energy") → RenewableAgentOrchestrator
```

**Detection is STATIC — pure ticker set lookups. No LLM involved.**

`POST /analyse` and `WS /ws/stream` auto-detect sector. Pass `sector` in request body to override.

**Supported tickers per sector:**

| Sector | Key tickers |
|---|---|
| automobile | MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO, HEROMOTOCO, EICHERMOT, TVSMOTORS, ASHOKLEY, ESCORTS, FORCEMOT (+ extended: APOLLOTYRE, MRF, CEATLTD, MOTHERSON, BOSCHLTD, BALKRISIND) |
| banking_bfsi | HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANKBARODA, PNB, CANARABANK, FEDERALBNK, IDFCFIRSTB, BANDHANBNK, RBLBANK, YESBANK, HDFCAMC, BAJAJFINSV, BAJFINANCE, MUTHOOTFIN, CHOLAFIN |
| it_sector | TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT, LTTS, KPITTECH, TATAELXSI, NIIT, MASTEK, HEXAWARE |
| renewable_energy | ADANIGREEN, TATAPOWER, TORNTPOWER, CESC, SJVN, NHPC, NTPC, POWERGRID, ADANIPOWER, JSWENERGY, INOXGREEN, WAAREEENER |

---

## 5. BaseSectorOrchestrator

**File:** `src/backend/shared/pipeline/base_orchestrator.py`

All 4 sector orchestrators extend this. Handles 4 responsibilities:

1. `_resolve_ticker(input)` — LLM + Serper fallback → `StockQuery`
2. `_load_learned_weights(ticker)` — reads `WeightMemory` from RL store; returns `None` if no data yet
3. `analyse()` / `analyse_async()` — full pipeline: resolve → agents → aggregate → log
4. `_run_via_graph()` / `_run_via_graph_async()` — LangGraph worker pool dispatch

**Weight priority chain:**
```
1. Explicitly injected (generate_forecast.py / daily_review.py)
2. RL WeightMemory.effective_weights() → auto-loaded by _load_learned_weights(ticker)
3. settings.AGENT_WEIGHTS config defaults
```

Each sector orchestrator only defines its agents:
```python
class AutomobileAgentOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "automobile"
    def __init__(self):
        self._sub_agents = {"sales_demand": SalesDemandAgent(), ...}  # 9 entries
        super().__init__()
```

---

## 6. Analysis Pipeline Flow

```
POST /analyse  or  WS /ws/stream?ticker=X
    ↓
detect_sector(ticker)  [STATIC: ticker set lookup]
    ↓
BaseSectorOrchestrator.analyse_async(ticker)
  1. _resolve_ticker()         [LLM: temp=0.0] → StockQuery(ticker, company_name, exchange)
  2. _load_learned_weights()   [STATIC: JSON read] → WeightMemory or None
  3. LangGraph worker pool → N agents in PARALLEL
       BaseAgent.run(query)
         _gather_context()  → ContextBuilder.build(agent_name, query)  [STATIC data fetch]
         _build_prompt()    → (system, user) from sector/prompts/{agent}.py
         _call_llm()        → OpenRouter → qwen → JSON string             [LLM]
         _parse_output()    → AgentOutput
  4. SignalAggregator.run(learned_weights) → FinalReport
       Step 1: Weighted composite [STATIC]
       Step 2: Conflict detection (delta ≥ 0.30) [STATIC]
       Step 3: LLM verdict synthesis [LLM]
       Step 4: Map score → verdict [STATIC]
  5. ScoreStore.save(report) → SQLite data/scores.db
  6. log_run_summary / log_usage / log_analysis
    ↓
FinalReport JSON → client
```

---

## 7. All Schemas

### `src/backend/shared/schemas/pipeline.py`

```
StockQuery          ticker, company_name, exchange="NSE", analysis_date=today
AgentOutput         agent, ticker, overall_score [0–1], key_positives[], key_risks[],
                    summary, data_freshness, error, raw_llm_response (excluded from serialisation)
FinalReport         ticker, company_name, final_score [0–1], verdict,
                    weighted_agent_scores {agent: WeightedAgentScore(raw, weight, weighted)},
                    conflicts_resolved[], conviction_drivers[], top_risks[],
                    executive_summary, investment_thesis, report_date,
                    price_target, recovery_timeline_quarters, undervalued_by_pct,
                    discount_reason, recovery_catalysts[], agent_outputs {agent_name: dict}
WeightedAgentScore  raw, weight, weighted
PipelineRun         run_id, query, report, status, duration_seconds, errors
```

### `src/backend/shared/schemas/feedback.py`

All RL schemas — see [docs/RL_DESIGN.md §10](RL_DESIGN.md#10-all-rl-schemas) for full detail.

Key types: `MissType`, `LessonScope`, `LessonCategory`, `TimingAccuracy`, `RevisedContext`,
`PredictionEnvelope`, `DailyFeedbackLog`, `WeightMemory`, `LearningLedger`, `ConvictionStreak`, `RegimeSnapshot`

### Sector Sub-score Models

| Sector | Sub-score models (one Pydantic class per agent) |
|---|---|
| automobile | SalesDemandSubScores, FundamentalsSubScores, PatternAnalysisSubScores, SentimentSubScores, RiskMacroSubScores, RawMaterialsSubScores, PolicyRegulatorySubScores, CompetitiveIntelSubScores, ValuationCatalystSubScores |
| banking_bfsi | BFSIFundamentalsAgentSubScores, BFSIRiskAgentSubScores, BFSIMacroPolicyAgentSubScores, BFSIInstitutionalAgentSubScores, BFSIPatternAgentSubScores, BFSIUniverseAgentSubScores |
| it_sector | ITFundamentalsAgentSubScores, ITGlobalMacroAgentSubScores, ITRiskMacroAgentSubScores, ITPeerBenchmarkAgentSubScores, ITPatternAgentSubScores, ITSentimentAgentSubScores, ITTranscriptNLPAgentSubScores, ITInsiderAgentSubScores |
| renewable_energy | REFundamentalsAgentSubScores, REBusinessAgentSubScores, REValuationAgentSubScores, RESentimentPolicyAgentSubScores, RETechnicalAgentSubScores, RERiskAgentSubScores |

---

## 8. All API Endpoints

### Analysis

| Method | Path | Notes |
|---|---|---|
| `POST` | `/analyse` | Body: `{ticker, sector?, output_format?}`. Sector auto-detected if omitted. Returns FinalReport JSON. |
| `WS` | `/ws/stream?ticker=X` | Sector auto-detected. Streams `agent_progress` events + `complete` with FinalReport. |

### History

| Method | Path | Notes |
|---|---|---|
| `GET` | `/history/{ticker}` | SQLite score history. Returns list of HistoryEntry (id, ticker, run_at, final_score, verdict, investment_thesis). |
| `GET` | `/history/{ticker}/latest` | Most recent FinalReport for ticker. |

### UI Data (`/ui/*`)

| Method | Path | Frontend caller | Notes |
|---|---|---|---|
| `GET` | `/ui/bootstrap` | `data.jsx` on page load | All UI data in one shot: AGENTS, TICKERS, WATCHLIST, MARKET_TODAY, TRENDING, SUGGESTIONS, CATEGORIES, CHAT_SEEDS, AGENT_TASK_FLAGS. |
| `GET/PUT` | `/ui/agents/weights` | `agents-page.jsx` on slider | Persists to `data/agent_weights.json`. Validates: 0–0.30 per agent, sum 0.95–1.05. |
| `GET/PUT` | `/ui/agents/tasks` | `agents-page.jsx` on toggle | Persists to `data/agent_tasks.json`. |
| `GET/PUT` | `/ui/watchlist` | `home.jsx` WatchlistPane | GET returns enriched tickers with live yfinance prices. PUT persists to `data/watchlist.json`. |
| `GET` | `/ui/nifty-ranges?range=` | `home.jsx` range tab click | Sparkline for 1W/1M/3M/6M/1Y via yfinance `^CNXAUTO`. |
| `GET` | `/ui/search?q=` | `home.jsx` TopNav 350ms debounce | 16 tickers + DB theses + yfinance fallback for unknown NSE symbols. |
| `GET` | `/ui/trending` | (bootstrap covers this) | Score-delta movers from DB (not price-change). |
| `GET` | `/ui/learnings` | `data.jsx` after bootstrap | RL-derived lesson cards from score history + feedback logs. |
| `POST` | `/ui/chat` | `sphere.jsx` on message send | Body: `{message, history:[{role,content}]}`. Agentic LLM tool loop (max 4 rounds). Tools: get_live_price (yfinance), search_market_news (Tavily), get_stock_analysis (SQLite). |
| `GET/PUT` | `/ui/categories/{key}/tickers` | Category management | Persisted to `data/category_tickers.json`. |
| `GET` | `/ui/categories` | CategoryCard / CategoryDrawer | All categories with resolved tickers[] and auto-computed count. |

### Scheduler (`/scheduler/*`)

All POST endpoints return 202 immediately and run work as background tasks.
Auth: `X-Scheduler-Key` header must match `SCHEDULER_KEY` env var.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/scheduler/forecast` | Generate monthly prediction envelopes. Optional `?ticker=`. ~2 min/ticker. |
| `POST` | `/scheduler/daily-review` | Run daily RL feedback loop. Optional `?ticker=&date=YYYY-MM-DD`. |
| `POST` | `/scheduler/backfill` | Catch-up daily reviews for all missing trading days this month. |
| `GET` | `/scheduler/status` | Per-ticker RL state: weight version, direction accuracy, weight drifts. |

### Health / Meta

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Railway health check. Returns `{status: "ok"}`. |
| `GET` | `/tickers` | Lists configured scheduler tickers. |

---

## 9. Server Startup Sequence (Lifespan)

`services/api/server.py` runs this on every deployment — server is self-bootstrapping:

```
1. Calendar first-run:
   if data/nse_holidays.json doesn't exist → calendar_updater.update_calendar()

2. RL self-heal (background daemon thread — server accepts requests immediately, 10s delay):
   For each SCHEDULER_TICKERS:
     a. No envelope for current cycle → run generate_forecast() background (~2 min/ticker)
     b. Find missing trading-day reviews → run run_daily_review() for each

3. BackgroundScheduler start (3 APScheduler jobs):
   Job 1: rl_daily_review      — every weekday 4:30pm IST (11:00 UTC)
   Job 2: rl_monthly_forecast  — 1st of each month 9:00am IST
   Job 3: rl_calendar_update   — Dec 31 11:00pm IST (writes next year's NSE holidays)
```

---

## 10. Frontend Architecture

### Prototype (DEPLOYED at `/app`) — `src/frontend/prototypes/`

Babel standalone — no build step. All `.jsx` files transpiled in-browser at page load.

**Script load order:**
```
styles.css → data.jsx → icons.jsx → sphere.jsx → auth.jsx → home.jsx
→ agents-page.jsx → portfolio.jsx → learn.jsx → analytics.jsx → logs.jsx
→ prompt-lab.jsx → tweaks-panel.jsx → inline <script> (App, ReactDOM.render)
```

**window.* Global State Map:**

| Global | Live source | Mock source | Always overwritten? |
|---|---|---|---|
| `window.AGENTS` | `/ui/bootstrap → AGENTS` | 9 hardcoded agent objects | ✅ Yes |
| `window.TICKERS` | `/ui/bootstrap → TICKERS` | 8 tickers with fake price/score | ✅ Yes |
| `window.WATCHLIST` | `/ui/bootstrap → WATCHLIST` | `["MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","EICHERMOT"]` | ✅ Yes |
| `window.MARKET_TODAY` | `/ui/bootstrap → MARKET_TODAY` | fake pulse + drivers | ✅ Yes |
| `window.TRENDING` | `/ui/bootstrap → TRENDING` | 4 hardcoded tickers | ✅ Yes (even if empty) |
| `window.SUGGESTIONS` | `/ui/bootstrap → SUGGESTIONS` | 3 hardcoded cards | ✅ Yes (if non-empty) |
| `window.CATEGORIES` | `/ui/bootstrap → CATEGORIES` | 6 categories | ✅ Yes |
| `window.CHAT_SEEDS` | `/ui/bootstrap → CHAT_SEEDS` | 4 seed questions | ✅ Yes |
| `window.PORTFOLIO` | Never overwritten | fully hardcoded | ❌ No endpoint |
| `window.PORTFOLIO_LEARNINGS` | `/ui/learnings` (if items > 0) | detailed lesson cards | Conditional |
| `window.LEARN_PATHS` | Never overwritten | 6 learning paths | ❌ No endpoint |
| `window.__apiReady` | true after bootstrap success | false | — |
| `window.__apiLive` | true if any analysis has run | false | — |

**Prototype pages:**

| File | Screen | Real data? |
|---|---|---|
| `home.jsx` | Home: TodayPane, WatchlistPane, TrendingPane, CategoryCards, AnalysisResultDrawer | ✅ Yes |
| `agents-page.jsx` | AgentsPage: Agent cards, drawers, weight sliders, task toggles, Pipeline | ✅ Yes |
| `portfolio.jsx` | PortfolioPage: Holdings, P&L, Learnings, Activity | ❌ 100% mock |
| `learn.jsx` | LearnPage: Learning paths, glossary, tips | ❌ 100% static |
| `analytics.jsx` | RL performance metrics, Power BI OData feed | ✅ Partial |
| `logs.jsx` | Live log stream (SSE `/ui/logs/stream`) | ✅ Yes |
| `prompt-lab.jsx` | Prompt editor + GitHub deploy schedule | ✅ Partial |
| `sphere.jsx` | ChatOverlay (`/ui/chat` agentic tool loop) | ✅ Yes |
| `auth.jsx` | Login screen | ❌ Mock (no backend auth) |

### Web Dev Build — `src/frontend/web/`

Not deployed. Dev-only Vite+React build.

**TypeScript API Contract** (`src/frontend/web/src/types/api.ts`) — mirrors backend Pydantic schemas:

```typescript
FinalReport        — final_score, verdict, weighted_agent_scores, conviction_drivers,
                     top_risks, executive_summary, investment_thesis, price_target, ...
AgentOutput        — agent, ticker, overall_score, key_positives, key_risks, summary
BootstrapData      — AGENTS, TICKERS, WATCHLIST, MARKET_TODAY, TRENDING, SUGGESTIONS,
                     CATEGORIES, CHAT_SEEDS, AGENT_TASK_FLAGS, _liveData, _fetchedAt
StreamEvent        — agent_progress | complete | error (union discriminated by .event)
Verdict            — 'STRONG BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG SELL'
Sector             — 'automobile' | 'banking_bfsi' | 'it_sector' | 'renewable_energy'
detectSector(t)    — client-side ticker-to-sector mapping (mirrors backend detect_sector)
```

**Zustand Stores:**

| Store | State | Key actions |
|---|---|---|
| `analysisStore` | phase, agentProgress, report, elapsed, wsRef | startAnalysis, handleEvent, reset |
| `watchlistStore` | symbols, tickers (live prices), loading | fetchWatchlist, addTicker, removeTicker |
| `sectorStore` | activeSector, bootstrapData, trending, liveData | loadBootstrap, loadTrending, setActiveSector |

**Custom Hooks:**

| Hook | File | What it does |
|---|---|---|
| `useAnalysis()` | `features/analysis/useAnalysis.ts` | Opens `wss://*/ws/stream?ticker=X`, falls back to `POST /analyse`. Drives analysisStore. |
| `useAgentProgress()` | `features/analysis/useAgentProgress.ts` | Derives per-agent display state from analysisStore. |
| `useChatHistory()` | `features/chatbot/useChatHistory.ts` | Manages in-session message list, sends to `POST /ui/chat`. |

---

## 11. Agentic Chat (`/ui/chat`)

**File:** `services/api/routes/ui_data.py`

Max 4 LLM rounds. Tools run in parallel via `asyncio.gather`:

| Tool | Implementation | Scope |
|---|---|---|
| `get_live_price` | `_chat_tool_get_live_price` → yfinance | NSE tickers + `SI=F` silver, `GC=F` gold, `CL=F` crude, `^NSEI`, `USDINR=X` |
| `search_market_news` | `_chat_tool_search_news` → Tavily `search_depth="basic"` | Any natural language query |
| `get_stock_analysis` | `_ctx_ticker_detail` → SQLite ScoreStore | Tracked tickers only |

**System prompt rules:**
- Always call `get_live_price` before answering price questions
- Always call `search_market_news` for "why" questions
- Never hallucinate prices

---

## 12. Dark/Light Theme System

**File:** `src/frontend/prototypes/styles.css`

Toggle: `window.__toggleTheme()` → `document.documentElement.setAttribute('data-theme', 'dark'|'light')`

Default: `TWEAK_DEFAULTS.theme = "light"` in `index.html`.

**Light theme key tokens (`:root`):**

| Variable | Value | Role |
|---|---|---|
| `--bg-base` | `#f6f7fb` | Page background |
| `--bg-surface` | `#ffffff` | Card background |
| `--bg-tinted` | `#eef2fb` | Tab bars, hover |
| `--border` | `#e2e8f0` | Default border |
| `--ink-1` | `#0f172a` | Primary text |
| `--ink-2` | `#475569` | Secondary text |
| `--cyan` | `#0891b2` | Brand accent, CTAs |
| `--violet` | `#7c3aed` | AI elements |
| `--buy-strong` | `#16a34a` | STRONG BUY |
| `--buy` | `#22c55e` | BUY |
| `--neutral` | `#d97706` | NEUTRAL |
| `--sell` | `#ea580c` | SELL |
| `--sell-strong` | `#dc2626` | STRONG SELL |

**Dark theme** (`[data-theme="dark"]`) uses navy-blue palette — not pitch black:
`--bg-base: #08111f`, `--bg-surface: #0d1a2e`, `--ink-1: #ddeeff`, `--ink-2: #7ea8cc`.

**Mobile breakpoints:**

| Breakpoint | Range | Key change |
|---|---|---|
| Desktop | ≥ 1024px | Right-side drawers, 3-col grids |
| Tablet | 768–1023px | 2-col agent grid, reduced padding |
| Mobile | < 768px | Bottom-sheet drawers, 1-col grids, 16px padding |

Drawers use `className="drawer-panel"` — CSS class controls all positioning. Mobile `!important` rules override inline `width`. Never add `position/top/right/bottom` as inline styles to a drawer.

---

## 13. LangGraph Multi-Sector Graphs

**Registry:** `langgraph.json`

```json
{
  "graphs": {
    "automobile":       "./src/backend/sectors/automobile/pipeline/graph.py:graph",
    "banking_bfsi":     "./src/backend/sectors/banking_bfsi/pipeline/graph.py:graph",
    "it_sector":        "./src/backend/sectors/it_sector/pipeline/graph.py:graph",
    "renewable_energy": "./src/backend/sectors/renewable_energy/pipeline/graph.py:graph"
  }
}
```

**Node topology** (identical for all 4 sectors — shared infrastructure in `src/backend/shared/pipeline/graphs/`):

```
graph.invoke({"ticker": "SYMBOL"})
  → resolve_ticker  [LLM: temp=0] → StockQuery
  → input_rail      [STATIC: yfinance fast_info check, non-blocking]
  → conditional_edges → make_dispatch_fn → list[Send]  (fan-out)
  → run_agent × N   [parallel, RetryPolicy(max_attempts=2)]
       output_rail inside: clamp score [0,1], inject placeholder summary
       writes {agent_name: AgentOutput} to agent_outputs via _merge_dicts reducer
  → aggregate       [conflict_rail + SignalAggregator → FinalReport]
  → END             state["final_report"] = FinalReport
```

**Programmatic invocation:**

```python
from src.backend.sectors.automobile.pipeline.graph import graph
result = graph.invoke({"ticker": "MARUTI"})
report = result["final_report"]
```

---

## 14. C++ Technical Indicators

**Files:** `core/intelligence/algorithms/indicators/fetcher.py`, `cpp/src/indicators.cpp`

**Dispatch logic in fetcher.py:**

```python
try:
    import stockindicators as _cpp_indicators
    _USE_CPP = True
except ImportError:
    _USE_CPP = False  # silent fallback to pure Python

def compute_rsi(close, period=14):
    if _USE_CPP:
        return _cpp_indicators.compute_rsi(close.tolist(), period)
    # pandas/numpy fallback ...
```

**Algorithm parity (C++ matches pandas within ±0.01):**

| Function | Python algorithm | C++ implementation |
|---|---|---|
| `compute_rsi` | `ewm(com=period-1, adjust=True)` | `ewm_adjusted()` — recursive num/den update |
| `compute_macd` | `ewm(span=n, adjust=False)` | `ewm_unadjusted()` — α·x + (1-α)·prev |
| `compute_bollinger_bands` | `rolling(n).std()` ddof=1 | Variance = (Σx² − n·μ²)/(n−1) |

**Build (Windows):** `powershell -ExecutionPolicy Bypass -File core/intelligence/algorithms/cpp/build_ext.ps1`
**Build (Linux/macOS):** `cmake -S cpp -B cpp/build && cmake --build cpp/build && cmake --install cpp/build`

---

## 15. RAG Pipeline

**Disabled by default** (`RAG_ENABLED=false` in `src/backend/shared/config/rag_config.py`).

**Enable:** `RAG_ENABLED=true` in `.env`.

**Ingestion:** `python scripts/ingest_documents.py --dir /path/to/docs`
→ PDF/TXT/MD → chunked (512 tokens, 64 overlap) → SentenceTransformer embeddings → ChromaDB at `data/chroma_db/`.

**Retrieval at runtime:**
```
BaseAgent._gather_context(query)
  → RAGRetriever.retrieve(search_query)
  → Embedder.embed() → ChromaDB cosine similarity → top-K chunks (threshold 0.75)
  → [optional] CrossEncoder reranking if RERANKER_ENABLED=true
  → chunks joined with "---" → context string injected into agent prompt
```

**When RAG is disabled** (default), agents use live data from ContextBuilder fetchers instead.

---

## 16. Configuration Reference

**File:** `src/backend/shared/config/settings/base.py` — override with env vars or `.env`.

**LLM:**

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | env var (required) | OpenRouter API key |
| `LLM_MODEL` | `qwen/qwen3-235b-a22b` | Model slug |
| `LLM_TEMPERATURE` | `0.2` | General agent creativity |
| `LLM_MAX_TOKENS` | `2048` | Per-call token limit |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Endpoint |

**Agent execution:**

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_TIMEOUT_SECONDS` | `120` | Per-agent wall-clock timeout |
| `MAX_RETRIES` | `3` | LLM retry attempts (exponential back-off) |
| `SERPER_MAX_QUERIES` | `3` | Serper calls per agent per run |
| `SCORE_THRESHOLDS` | see base.py | Score → verdict mapping |
| `YFINANCE_SUFFIX` | `.NS` | NSE suffix (`.BO` BSE fallback for 404s) |

**Data sources:**

| Variable | Default | Purpose |
|---|---|---|
| `SERPER_API_KEY` | env var (required) | Google search proxy (2,500/month free) |
| `TAVILY_API_KEY` | env var (required) | Full-page extraction — policy agent (1,000/month) |
| `NEWSAPI_KEY` | env var (optional) | Fallback when Serper fails (100/day free) |
| `SERPER_MONTHLY_LIMIT` | `2500` | Override monthly cap |
| `TAVILY_MONTHLY_LIMIT` | `1000` | Override monthly cap |

**RL Feedback Loop:**

| Variable | Default | Purpose |
|---|---|---|
| `PREDICTION_DATA_DIR` | `data/predictions` | Root for all RL JSON memory files |
| `FORECAST_HORIZON_DAYS` | `30` | Trading days per prediction envelope |
| `WEIGHT_MIN_OBSERVATIONS` | `3` | Days before weight adaptation activates |
| `WEIGHT_ACCURACY_WINDOW` | `7` | Rolling window for hit-rate calculation |
| `WEIGHT_MAX_STEP` | `0.05` | Max weight change per daily update |
| `WEIGHT_MAX_DRIFT` | `0.15` | Max total drift from base weight |
| `WEIGHT_BOOST_HIT_RATE` | `0.70` | Hit rate ≥ this → +0.02 boost |
| `WEIGHT_PENALTY_HIT_RATE` | `0.40` | Hit rate ≤ this → −0.03 penalty |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Daily review cron (4:30pm IST weekdays) |
| `RL_FLAT_THRESHOLD_PCT` | `0.3` | % threshold for UP/DOWN/FLAT classification |

**Technical indicators:**

| Variable | Default |
|---|---|
| `RSI_PERIOD` | `14` |
| `MACD_FAST / SLOW / SIGNAL` | `12 / 26 / 9` |
| `BB_PERIOD / BB_STD` | `20 / 2.0` |
| `PRICE_HISTORY_YEARS` | `10` |

---

## 17. Shim Convention

Every file moved from `core/` or `services/` to `src/backend/` leaves a backward-compat shim at the old path:

```python
# -- MIGRATION SHIM --
# Real: src/backend/shared/schemas/pipeline.py
from backend.shared.schemas.pipeline import *        # noqa: F401, F403
from backend.shared.schemas.pipeline import FinalReport, AgentOutput, StockQuery
```

**All `from core.schemas.pipeline import ...` and `from services.clients.llm_client import ...` continue to work.**

Forward shims at `src/backend/shared/clients/` and `src/backend/shared/data/` point to real `services/` files until Phase 7 moves them.

**Phase 7 target:** Delete all ~30 shims in `core/` and `services/` after updating all imports.
Run `grep -r "from core\.\|from services\." --include="*.py"` before deleting — must return zero results.

---

## 18. Data Sources

| Source | Returns | Free limit | Key var |
|---|---|---|---|
| **yfinance** | OHLCV, financials, macro prices, index data | Unlimited (unofficial) | None |
| **Serper** | Google search → title + snippet + URL | 2,500 calls/month | `SERPER_API_KEY` |
| **Tavily** | Google search → full extracted page text | 1,000 calls/month | `TAVILY_API_KEY` |
| **NewsAPI** | News articles from curated sources | 100 calls/day | `NEWSAPI_KEY` |
| **OpenRouter** | LLM inference (OpenAI-compatible) | Pay-per-token | `OPENROUTER_API_KEY` |

**API usage tracking:** `logs/api_usage.json` — monthly counters auto-reset each calendar month.

```python
from services.data.stores.api_usage import get_usage, record_call
get_usage()
# {"month": "2026-05", "serper": {"calls": 24, "limit": 2500, "remaining": 2476}}
```

**yfinance tickers used:**

| Ticker | Represents |
|---|---|
| `{TICKER}.NS` | NSE-listed stock |
| `{TICKER}.BO` | BSE fallback (for newly-listed stocks that 404 on .NS) |
| `CL=F` | WTI Crude Futures |
| `BZ=F` | Brent Crude Futures |
| `INR=X` | INR per USD |
| `SLX` | VanEck Steel ETF (steel price proxy) |
| `AA` | Alcoa (aluminium price direction proxy) |
| `PPLT` | Aberdeen Platinum ETF |
| `PALL` | Aberdeen Palladium ETF |
| `^CNXAUTO` | Nifty Auto index |
| `^NSEI` | Nifty 50 (FII proxy, regime detection) |
| `^INDIAVIX` | India VIX (regime detection) |
| `^NSEBANK` / `^CNXIT` / `^CNXENERGY` | Sector indices (regime detection RSI) |

---

## 19. Test Structure

```
tests/
├── unit/
│   ├── (original flat files)        ← imported through shims
│   ├── shared/                      ← test_schemas, test_signal_aggregator, test_config
│   ├── sectors/
│   │   ├── automobile/              ← test_agents (30 tests), test_prompts
│   │   ├── banking_bfsi/            ← test_agents (30 parametrized tests — 6 agents × 5 assertions)
│   │   ├── it_sector/               ← test_agents (32 parametrized tests — 8 agents × 4 assertions)
│   │   └── renewable_energy/        ← test_agents (24 parametrized tests — 6 agents × 4 assertions)
│   └── intelligence/
│       ├── rl/                      ← test_algorithms: stubs + 4 live math tests
│       │                            ←   (reversion prior, penalty multipliers, direction threshold, weight normalization)
│       └── chat/                    ← test_intent_detector, test_entity_extractor (parametrized skips — Phase 6)
├── integration/
│   └── test_sector_routing.py       ← 19 tests: detect_sector 23 tickers, get_orchestrator 4 sectors
└── contract/
    ├── test_phase0_llm_migration.py  ← Zero Groq references; OpenRouter wiring
    ├── test_phase1_indicators.py     ← C++ parity (25 tests) + fallback
    ├── test_phase3_typescript.py     ← Python-side JSON shape contracts
    └── test_phase4_csharp.py         ← C# proxy + cron contracts

Baseline: 777 passed, 29 skipped (Phase 6 stubs), 0 failed
```

**Run commands:**

```bash
pytest tests/ -v                                          # full suite
pytest tests/unit/ -v                                     # unit only
pytest tests/integration/ -v                              # integration only
pytest tests/contract/test_phase1_indicators.py -v        # C++ parity
pytest tests/ --cov=core --cov=services --cov-report=term-missing
```

All LLM and network calls are mocked — no API key needed for tests.

---

## 20. Deployment

**Live URL:** `https://stockagent-ai.up.railway.app/app/index.html`
(Note: `/index.html` → 404. Correct path is `/app/index.html`)

**Platform:** Railway (Docker). FastAPI + Uvicorn on port 8000. Volume at `/app/data`.

**Service start order (local dev):**

```bash
# 1. Python FastAPI (internal)
uvicorn services.api.server:app --port 8001 --reload

# 2. TypeScript gateway (public, REST + WS + analysis cron)
bun run services/gateway/src/index.ts          # port 3000

# 3. RL daily review scheduler (post-market, separate process)
python services/scheduler/python/scheduler.py

# 4. Frontend dev (optional — prototype is served at /app by FastAPI)
cd src/frontend/web && npm run dev             # port 5173
```

**Port map:**

| Service | Port | Protocol | Visible to |
|---|---|---|---|
| Python FastAPI | 8000 (Railway) / 8001 (local) | HTTP + WebSocket | Gateway + direct in Railway |
| TypeScript Gateway | 3000 | HTTP + WebSocket | Browser (local dev) |
| Vite dev server | 5173 | HTTP | Browser (local dev only) |
| APScheduler (RL review) | — | No HTTP | Internal Python process |
| C# Quartz.NET (optional) | 5000 | HTTP | Python (CSHARP_SCHEDULER_ENABLED=true) |

---

## 21. Known Issues

1. **Newly-listed stocks** (ATHERENERGY): yfinance `.NS` returns 404 → agents fall back to LLM hallucination. BSE `.BO` fallback added for common cases.
2. **RBI repo rate**: hardcoded static value in `services/data/fetchers/macro.py:get_rbi_repo_rate()` — update manually after each MPC decision or implement scraper.
3. **Sector fetcher stubs**: `vahan_fada.py`, `rbi_data.py`, `npa_metrics.py`, `deal_wins.py`, `transcript.py`, `mnre_data.py` raise `NotImplementedError` — implement in Phase 7.
4. **NSE holidays 2026**: preliminary dates hardcoded in `nse_calendar.py` — `calendar_updater.py` refreshes them Dec 31 automatically.
5. **Seasonal seed YAMLs**: `src/backend/intelligence/rl/seasonal/seeds/` directory exists but 4 YAML files content is minimal — populate in Phase 5.
6. **Phase 7 shims pending removal**: ~30 shims across `core/` and `services/` deleted in Phase 7-11 after full import update.
7. **Frontend Vite build stub pages**: `home/`, `agents/`, `portfolio/`, `learn/` in `src/frontend/web/` are minimal stubs — prototype is the deployed UI.
8. **Chat engine is stub**: `src/backend/intelligence/chat/` has only `__init__.py` files — Phase 6 wires intent detection + entity extraction. Current `/ui/chat` agentic tool loop is in `services/api/routes/ui_data.py` and works independently.
9. **TVSMOTORS yfinance symbol**: correct symbol is `TVSMOTOR.NS` (no trailing S). Fixed in `ui_data.py _ALL_TICKERS`.
10. **Valuation catalyst context**: `_build_valuation_catalyst` missing in ContextBuilder — relies entirely on LLM training knowledge.
11. **LangGraph ContextBuilder not sector-aware (P0)**: BFSI, IT, RE agents receive stub context only — `ContextBuilder` has no routing branches for new sector agent names. Agents rely on LLM training knowledge until wired.
12. **LangGraph sync agent.run() (P1)**: `run_agent` nodes call `agent.run()` synchronously — LangGraph parallelism is via threads. Should migrate to `agent.run_async()` + `async def run_agent` for clean coroutine concurrency under FastAPI event loop.
13. **No CLI/FastAPI sector routing (P1)**: No `--sector` flag on `main.py` and no `/analyse/{sector}` route. Users must invoke LangGraph graphs directly. Fix: add `POST /analyse/{sector}` route and `--sector` CLI flag.
14. **RAG retrieval falls back to "automobile India" for new sector agents (P2)**: `BaseAgent._rag_retrieve` has a hardcoded `prompt_modules` dict covering only automobile agents. New sector agents fall through to a generic automobile search query.
15. **Agent name collision across sectors (P2)**: `"fundamentals"` and `"pattern_analysis"` exist in all 4 sector registries. No immediate problem (graphs are isolated) but a future unified dashboard would see ambiguous keys.

---

## 22. Phase Status

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Groq → OpenRouter / Qwen migration | ✅ Complete |
| Phase 1 | C++ RSI / MACD / Bollinger Bands (pybind11) | ✅ Live (`_USE_CPP=True`) |
| Phase 2 | FastAPI bridge + WebSocket streaming | ✅ Complete |
| Phase 3 | TypeScript gateway (Bun + Hono) | ✅ Complete |
| Phase 4 | C# Quartz.NET scheduler (optional, feature-flagged) | 🔶 Scaffolded |
| Phase 5 | RL feedback loop — prediction envelope + daily review + weight adaptation | ✅ Complete |
| Phase 6 | RL improvements — miss taxonomy, lesson scope, timing accuracy, revised context | ✅ Complete |
| Phase 7 | Shared data layer move (services/ → src/backend/shared/data/) | ⏳ Pending |
| Phase 8 | Multi-sector restructure (automobile + 3 scaffolded sectors) | ✅ Complete |
| Phase 9 | Import path migration (core/ + services/ → src/backend/) + shims | ✅ Complete |
| **Evolution P1** | SeasonalCalendar — pre-seeded sector patterns | ✅ Complete |
| **Evolution P2** | Shared sector + market ledger cross-ticker propagation | ✅ Complete |
| **Evolution P3** | Conviction duration counter + mean-reversion prior | ✅ Complete |
| **Evolution P4** | PromptEnhancer — miss_counter auto-updates agent search queries | ✅ Complete |
| **Evolution P5** | Context-conditional regime multiplier (VIX + FII + RSI) | ✅ Complete |

**Next phases planned:** Phase 5 (RL decomposition into algorithm files), Phase 6 (chat engine extraction), Phase 7 (data layer move + sector fetchers), Phase 8 (shim removal).

---

## 23. Docker / Production Deployment

### DigitalOcean Droplet (recommended: $24/month, 4 GB RAM / 2 vCPU / 80 GB SSD)

Chosen over Railway for local file persistence (RL JSON ledgers + ChromaDB live on Docker named volumes).

**Named Docker volumes (survive `docker compose down && docker compose up --build`):**

| Volume | Mount | Contents |
|---|---|---|
| `stockagent_data` | `/app/data` | RL weight memory, learning ledgers, prediction envelopes, feedback logs, ChromaDB, scores.db |
| `stockagent_logs` | `/app/logs` | Application logs |
| `stockagent_out` | `/app/outputs` | Analysis reports |
| `caddy_data` | Caddy internal | TLS certificates (Let's Encrypt) |

**Cron schedule inside containers (`TZ=Asia/Kolkata`):**

| Job | Time (IST) | What it does |
|---|---|---|
| Daily RL review | 4:30 PM weekdays | Fetch actual close, run FeedbackAgent, update weights, revise forecasts |
| Monthly forecast | 9:00 AM 1st of month | Run all agents → generate 30-day PredictionEnvelope |
| NSE calendar update | 11:00 PM Dec 31 | Fetch next year's NSE holidays, write data/nse_holidays.json |

**Container topology:**

```
Caddy (reverse proxy, :80/:443)
  ├── python-api:8000    ← FastAPI + BackgroundScheduler (all 3 cron jobs embedded)
  └── typescript-gateway:3000 (optional for local dev; Railway serves Python directly)
```

**First-time setup:**

```bash
ssh root@YOUR_DROPLET_IP
curl -fsSL https://get.docker.com | sh && apt-get install -y docker-compose-plugin
git clone https://github.com/YOUR_USERNAME/StockAgent.git && cd StockAgent
cp .env.production .env && nano .env   # fill OPENROUTER_API_KEY, SERPER_API_KEY, TAVILY_API_KEY
docker compose up -d --build
docker compose logs python-api --tail 30
```

**Backup RL data before migration:**

```bash
docker run --rm -v stockagent_data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/stockagent_data_$(date +%Y%m%d).tar.gz /data
```

---

## 24. Quick Start

```bash
# 1. Install
pip install -r requirements.txt
cd services/gateway && bun install

# 2. Configure
cp .env.example .env
# Required:  OPENROUTER_API_KEY, SERPER_API_KEY, TAVILY_API_KEY
# Optional:  NEWSAPI_KEY, LLM_MODEL, SCHEDULER_KEY

# 3. One-off CLI analysis
python main.py MARUTI
python main.py TATAMOTORS --output markdown --save
python main.py --list-tickers

# 4. Start the stack
uvicorn services.api.server:app --port 8001 --reload  # Terminal 1
bun run services/gateway/src/index.ts                  # Terminal 2 (optional local gateway)
python services/scheduler/python/scheduler.py          # Terminal 3 (RL cron)

# 5. Open the UI
# http://localhost:8001/app/index.html  (prototype, served directly by FastAPI)

# 6. RL feedback commands
python -m services.scheduler.run_schedule forecast --ticker MARUTI
python -m services.scheduler.run_schedule daily-review --ticker MARUTI
python -m services.scheduler.run_schedule feedback-status --ticker MARUTI
python -m services.scheduler.run_schedule start    # full daemon

# 7. Build C++ indicators (optional, Windows)
powershell -ExecutionPolicy Bypass -File core/intelligence/algorithms/cpp/build_ext.ps1
# → stockindicators.cp313-win_amd64.pyd (auto-detected; pure-Python fallback if absent)
```
