# Codebase Reference

> Ground-truth map of every module, its real path, and its public API.
> Updated: 2026-05-07 · reflects Phases 0–9 + UI changes (agentic chat, nav redesign, dark theme, prototype restructure)
> Previous snapshot: docs/CODEBASE.md

---

## Directory Layout (current — post Phase 0–9)

```
StockAI-Main/
├── main.py                          # CLI: python main.py <ticker> — sector auto-detected
├── requirements.txt
├── pyproject.toml                   # pythonpath=[".", "src"] — both legacy + new imports resolve
├── langgraph.json                   # sector graph registry → src/backend/sectors/*/pipeline/graph.py
├── docs/                            # all .md documentation + phase plans
│
├── src/
│   ├── backend/
│   │   ├── shared/                  # cross-sector shared code
│   │   │   ├── schemas/
│   │   │   │   ├── pipeline.py      # StockQuery, AgentOutput, FinalReport, WeightedAgentScore, PipelineRun
│   │   │   │   └── feedback.py      # ALL RL schemas (MissType, Lesson, WeightMemory, etc.)
│   │   │   ├── pipeline/
│   │   │   │   ├── base_agent.py         # BaseAgent ABC — sector-agnostic
│   │   │   │   ├── base_orchestrator.py  # BaseSectorOrchestrator ABC
│   │   │   │   ├── signal_aggregator.py  # SignalAggregator — weighted LLM fusion → FinalReport
│   │   │   │   └── graphs/
│   │   │   │       ├── nodes.py     # make_dispatch_fn, make_run_agent_node, make_aggregate_node
│   │   │   │       ├── rails.py     # conflict_rail, input_rail, output_rail
│   │   │   │       └── state.py     # GraphState
│   │   │   ├── prompts/
│   │   │   │   ├── orchestrator.py       # Ticker resolution prompt
│   │   │   │   ├── signal_aggregator.py  # Verdict synthesis prompt
│   │   │   │   └── feedback_agent.py     # RL miss analysis prompt
│   │   │   ├── config/
│   │   │   │   ├── settings/
│   │   │   │   │   ├── base.py      # ALL shared constants: LLM, API keys, score thresholds
│   │   │   │   │   └── __init__.py
│   │   │   │   └── rag_config.py
│   │   │   ├── data/                # FORWARD SHIMS → services/data/ (Phase 7 will move real files)
│   │   │   │   ├── fetchers/        # fundamentals.py, macro.py, news.py
│   │   │   │   ├── stores/          # score_store.py, run_logger.py, analysis_logger.py, api_usage.py
│   │   │   │   └── cache/           # macro_cache.py
│   │   │   └── clients/             # FORWARD SHIMS → services/clients/ (Phase 7)
│   │   │                            # llm_client.py, tavily_fetcher.py, alerting.py
│   │   │
│   │   ├── sectors/
│   │   │   ├── __init__.py          # detect_sector(ticker) → key; get_orchestrator(sector) → class
│   │   │   │
│   │   │   ├── automobile/          # ✅ FULLY IMPLEMENTED
│   │   │   │   ├── agents/          # 9 files (one per agent)
│   │   │   │   ├── prompts/         # 9 files with SYSTEM_PROMPT + ANALYSIS_PROMPT
│   │   │   │   ├── schemas/sub_scores.py  # 9 Pydantic sub-score models
│   │   │   │   ├── config/settings.py     # AGENT_WEIGHTS, TICKERS, PEER_TICKERS
│   │   │   │   ├── config/registry.py     # AGENTS dict (9 instances) + WEIGHTS
│   │   │   │   ├── data/fetchers/vahan_fada.py   # stub — implement Phase 7
│   │   │   │   ├── data/context/builder.py       # AutomobileContextBuilder (9 _build_* methods)
│   │   │   │   └── pipeline/
│   │   │   │       ├── orchestrator.py  # AutomobileAgentOrchestrator(BaseSectorOrchestrator)
│   │   │   │       └── graph.py         # LangGraph StateGraph
│   │   │   │
│   │   │   ├── banking_bfsi/        # ✅ SCAFFOLDED — agents + prompts ready, fetchers are stubs
│   │   │   │   ├── agents/          # 6 files: fundamentals, risk, macro_policy, institutional,
│   │   │   │   │                    #   pattern_analysis, universe_setup
│   │   │   │   ├── prompts/         # 6 matching files
│   │   │   │   ├── schemas/sub_scores.py  # 6 models (NPA, NIM, CRAR, etc.)
│   │   │   │   ├── config/settings.py     # HDFC, ICICI, SBIN, KOTAKBANK, AXISBANK…
│   │   │   │   ├── config/registry.py     # AGENTS dict (6 instances)
│   │   │   │   ├── data/fetchers/rbi_data.py      # stub — implement Phase 7
│   │   │   │   ├── data/fetchers/npa_metrics.py   # stub — implement Phase 7
│   │   │   │   ├── data/context/builder.py        # BankingBfsiContextBuilder (6 _build_* methods)
│   │   │   │   └── pipeline/
│   │   │   │       ├── orchestrator.py  # BankingAgentOrchestrator(BaseSectorOrchestrator)
│   │   │   │       └── graph.py
│   │   │   │
│   │   │   ├── it_sector/           # ✅ SCAFFOLDED — agents + prompts ready, fetchers are stubs
│   │   │   │   ├── agents/          # 8 files: fundamentals, global_macro, risk_macro,
│   │   │   │   │                    #   peer_benchmark, pattern_analysis, sentiment,
│   │   │   │   │                    #   transcript_nlp, insider_smart_money
│   │   │   │   ├── prompts/         # 8 matching files
│   │   │   │   ├── schemas/sub_scores.py  # 8 models (deal_wins, attrition, visa_risk…)
│   │   │   │   ├── config/settings.py     # TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM…
│   │   │   │   ├── config/registry.py     # AGENTS dict (8 instances)
│   │   │   │   ├── data/fetchers/deal_wins.py   # stub — implement Phase 7
│   │   │   │   ├── data/fetchers/transcript.py  # stub — implement Phase 7
│   │   │   │   ├── data/context/builder.py      # ItSectorContextBuilder (8 _build_* methods)
│   │   │   │   └── pipeline/
│   │   │   │       ├── orchestrator.py  # ITAgentOrchestrator(BaseSectorOrchestrator)
│   │   │   │       └── graph.py
│   │   │   │
│   │   │   └── renewable_energy/    # ✅ SCAFFOLDED — agents + prompts ready, fetchers are stubs
│   │   │       ├── agents/          # 6 files: fundamentals, business, valuation,
│   │   │       │                    #   sentiment_policy, technical, risk
│   │   │       ├── prompts/         # 6 matching files
│   │   │       ├── schemas/sub_scores.py  # 6 models (CUF, DSCR, EV/MW, DISCOM…)
│   │   │       ├── config/settings.py     # ADANIGREEN, TATAPOWER, TORNTPOWER, SJVN…
│   │   │       ├── config/registry.py     # AGENTS dict (6 instances)
│   │   │       ├── data/fetchers/mnre_data.py  # stub — implement Phase 7
│   │   │       ├── data/context/builder.py     # Renewable_energyContextBuilder (6 _build_*)
│   │   │       └── pipeline/
│   │   │           ├── orchestrator.py  # RenewableAgentOrchestrator(BaseSectorOrchestrator)
│   │   │           └── graph.py
│   │   │
│   │   ├── intelligence/            # ← Phase 5 (RL decomposition) + Phase 6 (chat)
│   │   │   ├── rl/
│   │   │   │   ├── algorithms/      # EMPTY STUBS — populate in Phase 5
│   │   │   │   │   ├── weight_adaptation/  # bias_detector, hit_rate_tracker, penalty_calculator, weight_normalizer
│   │   │   │   │   ├── conviction/         # streak_tracker, reversion_prior, rsi_divergence
│   │   │   │   │   ├── forecast/           # envelope_builder, confidence_decay, price_interpolator
│   │   │   │   │   └── feedback/           # miss_classifier, lesson_extractor, lesson_merger
│   │   │   │   ├── agents/          # EMPTY STUBS — real files at core/intelligence/rl/agents/
│   │   │   │   ├── regime/signals/  # EMPTY STUBS — vix.py, fii_proxy.py, sector_rsi.py (Phase 5)
│   │   │   │   ├── seasonal/seeds/  # EMPTY — 4 YAML files to create in Phase 5
│   │   │   │   ├── calendar/        # EMPTY STUBS — nse_calendar.py + updater.py (Phase 5)
│   │   │   │   ├── stores/          # EMPTY STUBS — prediction_store.py, ledger_propagator.py
│   │   │   │   └── workflows/       # EMPTY STUBS — generate_forecast.py, daily_review.py
│   │   │   ├── chat/                # ← Phase 6 — EMPTY STUBS
│   │   │   │   ├── engine.py        # chat router
│   │   │   │   ├── context/         # ticker_context.py + history_context.py
│   │   │   │   ├── algorithms/      # intent_detector.py + entity_extractor.py
│   │   │   │   └── prompts/system.py
│   │   │   ├── rag/                 # still at core/intelligence/rag/ — later phase
│   │   │   └── technical/           # still at core/intelligence/algorithms/ — later phase
│   │   │
│   │   ├── api/routes/              # EMPTY STUBS — real routes at services/api/routes/ (Phase 7)
│   │   └── scheduler/python/        # EMPTY STUBS — real scheduler at services/scheduler/ (Phase 7)
│   │
│   └── frontend/
│       ├── web/                     # ✅ Production Vite+React app (Phase 8)
│       │   ├── package.json         # React 18 + Vite 5 + Zustand + Recharts + Three.js
│       │   ├── vite.config.ts       # Dev proxy: /api /ui /analyse /history /ws → :8000
│       │   ├── tsconfig.json
│       │   └── src/
│       │       ├── main.tsx         # ReactDOM.createRoot entry point
│       │       ├── App.tsx          # BrowserRouter + lazy pages + bootstrap on mount
│       │       ├── types/
│       │       │   └── api.ts       # TypeScript mirror of all backend schemas
│       │       │                    # FinalReport, AgentOutput, BootstrapData, StreamEvent,
│       │       │                    # Verdict, Sector, TickerRow, AgentMeta, CategoryItem…
│       │       │                    # + detectSector(ticker): Sector client-side helper
│       │       ├── stores/
│       │       │   ├── analysisStore.ts  # Zustand: phase, agentProgress, report, elapsed, wsRef
│       │       │   ├── watchlistStore.ts # Zustand: symbols, live TickerRow[], add/remove via API
│       │       │   └── sectorStore.ts    # Zustand: activeSector, bootstrapData, trending, liveData
│       │       ├── features/
│       │       │   ├── analysis/
│       │       │   │   ├── useAnalysis.ts      # WebSocket hook + POST /analyse fallback
│       │       │   │   └── useAgentProgress.ts # per-agent display state derived from store
│       │       │   ├── chatbot/
│       │       │   │   └── useChatHistory.ts   # in-session conversation + /ui/chat calls
│       │       │   └── watchlist/              # (placeholder)
│       │       ├── components/
│       │       │   ├── shared/
│       │       │   │   ├── ui/        # GlassCard, GlowButton, VerdictBadge, AnimatedCounter,
│       │       │   │   │              # LoadingPulse, AddTickerModal, QuickDrawer, StockCard,
│       │       │   │   │              # WatchlistManager
│       │       │   │   ├── charts/    # ScoreGauge, AgentRadar, HistoryLine, MiniSparkline,
│       │       │   │   │              # VerdictDonut, CompareChart
│       │       │   │   ├── layout/    # AppLayout, Sidebar, MarketBar, BottomNav, PageTransition
│       │       │   │   └── analysis/  # VerdictReveal, ThesisCard, ConvictionPanel, AgentCard,
│       │       │   │                  # AgentScoreTable, ConflictsPanel, StreamProgress, TickerSearch
│       │       │   └── sector/
│       │       │       └── automobile/CategoryCard.tsx  # EV/Mass-market/Premium category card
│       │       └── pages/
│       │           ├── home/         # TodayPane, WatchlistPane, TrendingPane stubs
│       │           ├── agents/       # AgentCard grid + Pipeline stubs
│       │           ├── analysis/     # VerdictReveal + agent grid (wired to useAnalysis)
│       │           ├── portfolio/    # stub — pending broker API integration
│       │           └── learn/        # stub — static educational content
│       │
│       └── prototypes/              # ✅ DEPLOYED BABEL PROTOTYPE (React 18 + Babel, no build step)
│           │                        # Live at: stockagent-ai.up.railway.app/app/index.html
│           │                        # Served by services/api/server.py StaticFiles mount at /app
│           ├── index.html           # App entry — TWEAK_DEFAULTS (theme:'light'), App component
│           ├── styles.css           # All CSS vars incl. navy dark theme ([data-theme="dark"])
│           ├── home.jsx             # Home page + TopNav (pill bar, ThemeToggle, mobile bottom nav)
│           ├── agents-page.jsx      # Agents page
│           ├── portfolio.jsx        # Portfolio page
│           ├── learn.jsx            # Learn page
│           ├── analytics.jsx        # Analytics page (RL performance, Power BI OData)
│           ├── logs.jsx             # Live log stream (SSE /ui/logs/stream)
│           ├── prompt-lab.jsx       # Prompt editor + GitHub deploy schedule UI
│           ├── auth.jsx             # Auth screen
│           ├── data.jsx             # Bootstrap data fetch + window.* globals
│           ├── icons.jsx            # SVG icon library
│           ├── sphere.jsx           # Three.js animated sphere orb
│           └── tweaks-panel.jsx     # useTweaks hook + TweaksPanel component
│
├── core/                            # LEGACY — being emptied phase by phase
│   │                                # All moved files are now SHIMS re-exporting from src/
│   ├── schemas/pipeline.py          # SHIM → src/backend/shared/schemas/pipeline.py
│   ├── schemas/feedback.py          # SHIM → src/backend/shared/schemas/feedback.py
│   ├── config/settings/base.py      # SHIM → src/backend/shared/config/settings/base.py
│   ├── config/rag_config.py         # SHIM → src/backend/shared/config/rag_config.py
│   ├── config/prompts/automobile/   # SHIMS → src/backend/sectors/automobile/prompts/
│   ├── graphs/{nodes,rails,state}.py # SHIMS → src/backend/shared/pipeline/graphs/
│   ├── pipeline/base_agent.py       # SHIM → src/backend/shared/pipeline/base_agent.py
│   ├── pipeline/orchestrator.py     # SHIM → src/backend/sectors/automobile/pipeline/orchestrator.py
│   ├── pipeline/signal_aggregator.py # SHIM → src/backend/shared/pipeline/signal_aggregator.py
│   ├── sectors/automobile/{agents}  # SHIMS → src/backend/sectors/automobile/agents/
│   ├── sectors/automobile/graph.py  # SHIM → src/backend/sectors/automobile/pipeline/graph.py
│   ├── sectors/automobile/registry.py # SHIM → src/backend/sectors/automobile/config/registry.py
│   ├── sectors/banking/agents.py    # SHIM → src/backend/sectors/banking_bfsi/config/registry.py
│   ├── sectors/it/agents.py         # SHIM → src/backend/sectors/it_sector/config/registry.py
│   ├── sectors/renewable/agents.py  # SHIM → src/backend/sectors/renewable_energy/config/registry.py
│   └── intelligence/                # REAL FILES — Phase 5 target
│       ├── rl/agents/               # feedback_agent.py, weight_adapter.py
│       ├── rl/conviction/           # tracker.py
│       ├── rl/stores/               # prediction_store.py, ledger_propagator.py
│       ├── rl/workflows/            # generate_forecast.py, daily_review.py
│       ├── rl/nse_calendar.py
│       ├── rl/calendar_updater.py
│       ├── regime/detector.py
│       ├── seasonal/                # calendar.py, validator.py
│       ├── rag/                     # later phase
│       └── algorithms/              # later phase
│
├── services/                        # LEGACY — being emptied phase by phase
│   ├── api/
│   │   ├── server.py                # real — lifespan, startup self-heal, BackgroundScheduler
│   │   └── routes/
│   │       ├── analyse.py           # sector-aware: detect_sector() → get_orchestrator()
│   │       ├── stream.py            # sector-aware WebSocket
│   │       ├── history.py           # real
│   │       ├── scheduler_api.py     # real
│   │       └── ui_data.py           # real — /ui/* + /ui/chat → Phase 6 extracts chat
│   ├── clients/                     # real — Phase 7 target
│   ├── data/
│   │   ├── fetchers/                # real — Phase 7 target
│   │   ├── stores/                  # real — Phase 7 target
│   │   ├── cache/                   # real — Phase 7 target
│   │   └── context/builder.py       # real — Phase 7 target
│   └── scheduler/                   # real — Phase 7 target
│
└── tests/
    ├── unit/
    │   ├── (original files)         # still exist — imported through shims
    │   ├── shared/                  # test_schemas, test_signal_aggregator, test_config
    │   │                            # (imports updated to backend.shared.* paths)
    │   ├── sectors/
    │   │   ├── automobile/          # test_agents (30 tests), test_prompts
    │   │   ├── banking_bfsi/        # test_agents (30 parametrized tests — 6 agents)
    │   │   ├── it_sector/           # test_agents (32 parametrized tests — 8 agents)
    │   │   └── renewable_energy/    # test_agents (24 parametrized tests — 6 agents)
    │   └── intelligence/
    │       ├── rl/                  # test_algorithms (stubs + 4 live math tests),
    │       │                        # + moved: test_conviction, test_regime, test_seasonal,
    │       │                        #   test_shared_ledger, test_enhancer
    │       └── chat/                # test_intent_detector, test_entity_extractor
    │                                # (parametrized skip stubs — populate in Phase 6)
    ├── integration/
    │   ├── test_sector_routing.py   # 19 tests: detect_sector + get_orchestrator all 4 sectors
    │   └── (original files)
    └── contract/
        └── (original files)

Test baseline: 777 passed, 29 skipped (skipped = Phase 6 stubs), 0 failed
```

---

## Sector Registry (`src/backend/sectors/__init__.py`)

```python
# Auto-detect from ticker symbol
detect_sector("HDFCBANK")    → "banking_bfsi"
detect_sector("TCS")         → "it_sector"
detect_sector("ADANIGREEN")  → "renewable_energy"
detect_sector("MARUTI")      → "automobile"    # default fallback for unknown tickers

# Get the orchestrator class for a sector
get_orchestrator("automobile")      → AutomobileAgentOrchestrator
get_orchestrator("banking_bfsi")    → BankingAgentOrchestrator
get_orchestrator("it_sector")       → ITAgentOrchestrator
get_orchestrator("renewable_energy")→ RenewableAgentOrchestrator
```

**Banking BFSI tickers:** HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANKBARODA, PNB, CANARABANK, FEDERALBNK, IDFCFIRSTB, BANDHANBNK, RBLBANK, YESBANK, HDFCAMC, BAJAJFINSV, BAJFINANCE, MUTHOOTFIN, CHOLAFIN

**IT tickers:** TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT, LTTS, KPITTECH, TATAELXSI, NIIT, MASTEK, HEXAWARE

**Renewable tickers:** ADANIGREEN, TATAPOWER, TORNTPOWER, CESC, SJVN, NHPC, NTPC, POWERGRID, ADANIPOWER, JSWENERGY, INOXGREEN, WAAREEENER

**All other tickers → automobile** (default)

**POST /analyse** and **WS /ws/stream** auto-detect sector. Pass `sector` in request body to override.

**main.py** uses `detect_sector(args.ticker) → get_orchestrator(sector) → orchestrator.analyse(ticker)`.

---

## BaseSectorOrchestrator (`src/backend/shared/pipeline/base_orchestrator.py`)

All 4 sector orchestrators extend this. Handles:
1. `_resolve_ticker()` — LLM + Serper fallback → `StockQuery`
2. `_load_learned_weights(ticker)` — reads `WeightMemory` from RL store; returns `None` if no data yet
3. `analyse()` / `analyse_async()` — full pipeline: resolve → agents → aggregate → log
4. `_run_via_graph()` / `_run_via_graph_async()` — LangGraph worker pool dispatch

Sector orchestrators only define:
```python
class MyOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "my_sector"
    def __init__(self):
        self._sub_agents = { "agent_key": AgentInstance(), ... }
        super().__init__()
```

---

## Frontend Architecture (`src/frontend/web/`)

### TypeScript API Contract (`src/types/api.ts`)
Mirrors backend Pydantic schemas — always keep in sync when backend changes:

```typescript
FinalReport        — final_score, verdict, weighted_agent_scores, conviction_drivers,
                     top_risks, executive_summary, investment_thesis, price_target…
AgentOutput        — agent, ticker, overall_score, key_positives, key_risks, summary
BootstrapData      — AGENTS, TICKERS, WATCHLIST, MARKET_TODAY, TRENDING, SUGGESTIONS,
                     CATEGORIES, CHAT_SEEDS, AGENT_TASK_FLAGS, _liveData, _fetchedAt
StreamEvent        — agent_progress | complete | error (union discriminated by .event)
Verdict            — 'STRONG BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG SELL'
Sector             — 'automobile' | 'banking_bfsi' | 'it_sector' | 'renewable_energy'
detectSector(t)    — client-side ticker-to-sector mapping (mirrors backend detect_sector)
```

### Zustand Stores

| Store | State | Key actions |
|---|---|---|
| `analysisStore` | phase, agentProgress, report, elapsed, wsRef | `startAnalysis`, `handleEvent`, `reset` |
| `watchlistStore` | symbols, tickers (live prices), loading | `fetchWatchlist`, `addTicker`, `removeTicker` |
| `sectorStore` | activeSector, bootstrapData, trending, liveData | `loadBootstrap`, `loadTrending`, `setActiveSector` |

### Custom Hooks (features/)

| Hook | File | What it does |
|---|---|---|
| `useAnalysis()` | `features/analysis/useAnalysis.ts` | Opens `wss://*/ws/stream?ticker=X`, falls back to `POST /analyse`. Drives analysisStore. |
| `useAgentProgress()` | `features/analysis/useAgentProgress.ts` | Derives per-agent display state (done, score, isRunning) from analysisStore. |
| `useChatHistory()` | `features/chatbot/useChatHistory.ts` | Manages in-session message list, sends history to `POST /ui/chat`. |

---

## Agent Pipeline (per sector)

```
POST /analyse or WS /ws/stream
    ↓
detect_sector(ticker) → OrchestratorClass
    ↓
BaseSectorOrchestrator.analyse_async(ticker)
    1. _resolve_ticker() → StockQuery      [LLM + Serper fallback]
    2. _load_learned_weights(ticker)       [from RL WeightMemory if available]
    3. LangGraph worker pool → N agents in PARALLEL
         BaseAgent.run(query)
           _gather_context() → SectorContextBuilder.build(agent_name, query)
           _build_prompt()   → (system, user) from sector/prompts/{agent}.py
           _call_llm()       → OpenRouter → JSON
           _parse_output()   → AgentOutput
    4. SignalAggregator.run(learned_weights) → FinalReport
    5. log_run_summary / log_usage / log_analysis
```

---

## Schemas

### `src/backend/shared/schemas/pipeline.py`
```
StockQuery(ticker, company_name, exchange, analysis_date)
AgentOutput — agent, ticker, overall_score [0–1], key_positives, key_risks, summary, data_freshness, error
FinalReport — ticker, company_name, final_score [0–1], verdict,
              weighted_agent_scores, conflicts_resolved, conviction_drivers, top_risks,
              executive_summary, investment_thesis, report_date,
              price_target, recovery_timeline_quarters, undervalued_by_pct,
              discount_reason, recovery_catalysts, agent_outputs
WeightedAgentScore — raw, weight, weighted
PipelineRun — run_id, query, report, status, duration_seconds, errors
```

### `src/backend/shared/schemas/feedback.py`
```
MissType — data_gap | data_stale | external_shock (0×penalty)
           timing (0.5×) | magnitude (0.25×) | model_bias | direction_flip (1.0×)
LessonScope — stock_specific | sector_wide | market_wide
PredictionEnvelope — 30-day forecast sheet per cycle per ticker
DailyFeedbackLog — daily miss analysis entries per cycle
WeightMemory — learned agent weights + audit trail — PERMANENT across cycles
LearningLedger — accumulated pattern lessons — PERMANENT across cycles
ConvictionStreak — current_verdict, streak_days, reversion_prior (0–0.30)
RegimeSnapshot — regime_label (6 states), multipliers (ephemeral), narrative
SeasonalPattern — months, day_range, agents_affected deltas, confidence
```

### Sector Sub-score Models

| Sector | Sub-score models (one per agent) |
|---|---|
| automobile | SalesDemandSubScores, FundamentalsSubScores, PatternAnalysisSubScores, SentimentSubScores, RiskMacroSubScores, RawMaterialsSubScores, PolicyRegulatorySubScores, CompetitiveIntelSubScores, ValuationCatalystSubScores |
| banking_bfsi | BFSIFundamentalsAgentSubScores, BFSIRiskAgentSubScores, BFSIMacroPolicyAgentSubScores, BFSIInstitutionalAgentSubScores, BFSIPatternAgentSubScores, BFSIUniverseAgentSubScores |
| it_sector | ITFundamentalsAgentSubScores, ITGlobalMacroAgentSubScores, ITRiskMacroAgentSubScores, ITPeerBenchmarkAgentSubScores, ITPatternAgentSubScores, ITSentimentAgentSubScores, ITTranscriptNLPAgentSubScores, ITInsiderAgentSubScores |
| renewable_energy | REFundamentalsAgentSubScores, REBusinessAgentSubScores, REValuationAgentSubScores, RESentimentPolicyAgentSubScores, RETechnicalAgentSubScores, RERiskAgentSubScores |

---

## RL Feedback Loop (core/intelligence/rl/ — Phase 5 target)

### 4 Persistent Files per Ticker
```
data/predictions/{sector}/{TICKER}/
  {TICKER}_{YYYY-MM}_prediction_envelope.json    ← monthly; archived each cycle
  {TICKER}_{YYYY-MM}_daily_feedback_log.json     ← monthly; archived each cycle
  {TICKER}_agent_weight_memory.json              ← PERMANENT across cycles
  {TICKER}_learning_ledger.json                  ← PERMANENT across cycles
```

### 9-Step Daily Review Flow
```
APScheduler 4:30pm IST weekdays → run_daily_review(ticker, date)
  1. Load PredictionEnvelope + today's forecast row
  2. Fetch actual close via yfinance
  3. Compute error metrics (price_error_pct, direction_correct, timing_lag)
  4. P4 PromptEnhancer: load saved blindspots → inject into FeedbackAgentInput
  5. FeedbackAgent.run() → miss_type, primary_miss_agent, new_lessons, revised_context
  6. WeightAdapter.update() → WeightMemory v(N+1) [deterministic, no LLM]
  6.5 (ephemeral) RegimeDetector → apply regime multipliers (NOT persisted to WeightMemory)
  7. ConvictionTracker → update streak + reversion_prior
  8. Revise remaining forecasts: confidence × (1 − reversion_prior × 0.5)
  9. Merge new lessons → LearningLedger → propagate to sector/market ledgers (3-tier)
  9.5 SeasonalValidator → feed result back to LearningLedger (invalidate bad / boost confirmed)
```

### Regime Multiplier Design
Regime adjustments (VIX, FII proxy, sector RSI) are **intentionally ephemeral** — applied to today's forecast revision only, never persisted to `WeightMemory`. Short-term noise would contaminate long-term accuracy weights.

---

## Sector Agent Counts + Weights

| Sector | Agents | Key weights |
|---|---|---|
| automobile | 9 | fundamentals 0.18, sales_demand 0.15, risk_macro 0.13 |
| banking_bfsi | 6 | fundamentals 0.25, risk 0.20, macro_policy 0.20 |
| it_sector | 8 | fundamentals 0.25, global_macro 0.20, risk_macro 0.15 |
| renewable_energy | 6 | fundamentals 0.30, business 0.25, valuation 0.20 |

---

## API Endpoints

### Analysis
| Method | Path | Notes |
|---|---|---|
| `POST` | `/analyse` | Body: `{ticker, sector?, output_format?}`. Sector auto-detected if omitted. |
| `WS` | `/ws/stream?ticker=X` | Sector auto-detected. Streams `agent_progress` events + `complete` with FinalReport. |

### History
| Method | Path | Notes |
|---|---|---|
| `GET` | `/history/{ticker}` | SQLite score history. Returns list of HistoryEntry. |
| `GET` | `/history/{ticker}/latest` | Most recent FinalReport for ticker. |

### UI Data (`/ui/*`)
| Method | Path | Notes |
|---|---|---|
| `GET` | `/ui/bootstrap` | All UI data in one shot (agents, tickers, market, trending, suggestions). |
| `GET/PUT` | `/ui/agents/weights` | Persist user-tuned agent weights (validates 0–0.30 each, sum 0.95–1.05). |
| `GET/PUT` | `/ui/agents/tasks` | Persist task enabled/disabled flags. |
| `GET/PUT` | `/ui/watchlist` | GET returns enriched ticker objects with live yfinance prices. |
| `GET` | `/ui/nifty-ranges?range=` | Sparkline for 1W/1M/3M/6M/1Y. |
| `GET` | `/ui/search?q=` | 16 tickers + DB theses + yfinance fallback for unknown NSE symbols. |
| `GET` | `/ui/trending` | Score-delta movers from DB (not price-change). |
| `GET` | `/ui/learnings` | RL-derived lesson cards from score history + feedback logs. |
| `POST` | `/ui/chat` | Body: `{message, history:[{role,content}]}`. **Agentic** — LLM tool loop (max 4 rounds) with 3 tools: `get_live_price` (yfinance NSE + commodities), `search_market_news` (Tavily), `get_stock_analysis` (local DB). |
| `GET/PUT` | `/ui/categories/{key}/tickers` | Category stock management (persisted to data/category_tickers.json). |
| `GET` | `/ui/categories` | All categories with resolved tickers[] and auto-computed count. |

### Scheduler
| Method | Path | Notes |
|---|---|---|
| `GET` | `/scheduler/status` | Job list + last run times. |
| `POST` | `/scheduler/forecast` | Trigger manual forecast generation. |
| `POST` | `/scheduler/daily-review` | Trigger manual daily review. |
| `GET` | `/health` | Railway health check. |

---

## Prototype UI — Key Components (`src/frontend/prototypes/`)

### TopNav (`home.jsx` — shared by all pages)
- **Desktop**: pill-shaped nav container (`borderRadius:999`) with cyan-blue gradient, white active chip + cyan glow
- **Mobile**: fixed bottom tab bar (`.mobile-bottom-nav`) — same cyan texture, icon + label tabs, active indicator bar at top edge, `env(safe-area-inset-bottom)` iOS safe area support
- **ThemeToggle**: sun/moon button beside bell icon (desktop) and beside hamburger (mobile). Calls `window.__toggleTheme` which is wired to `useTweaks` in `App`. `MutationObserver` keeps toggle in sync with TweaksPanel radio.
- **Theme persistence**: `App` exposes `window.__toggleTheme` and `window.__currentTheme` on every `tweaks.theme` change.

### Dark Theme (`styles.css`)
Navy-blue palette — not pitch black:
```
--bg-base:      #08111f   deep ocean navy
--bg-surface:   #0d1a2e   card navy
--bg-elevated:  #112238   raised elements
--bg-tinted:    #142948   hover/active highlight
--border:       #1a3354   navy border
--ink-1:        #ddeeff   cool blue-white text
--ink-2:        #7ea8cc   steel blue secondary
--ink-3:        #4a7090   muted blue-grey
```
Light theme is the default (`TWEAK_DEFAULTS.theme = "light"`).

### Agentic Chat (`/ui/chat`)
Tool loop in `services/api/routes/ui_data.py`. Max 4 LLM rounds. Tools run in parallel via `asyncio.gather`:

| Tool | Implementation | Symbols |
|---|---|---|
| `get_live_price` | `_chat_tool_get_live_price` → yfinance | NSE tickers + `SI=F` silver, `GC=F` gold, `CL=F` crude, `^NSEI` Nifty, `USDINR=X`, etc. |
| `search_market_news` | `_chat_tool_search_news` → Tavily `search_depth="basic"` | Any query |
| `get_stock_analysis` | `_ctx_ticker_detail` → local SQLite | Tracked tickers only |

System prompt enforces: always call `get_live_price` before answering price questions; always call `search_market_news` for "why" questions; never hallucinate prices.

---

## Key Settings (`src/backend/shared/config/settings/base.py`)

```python
LLM_MODEL              = "qwen/qwen3-235b-a22b"
OPENROUTER_BASE_URL    = "https://openrouter.ai/api/v1"
AGENT_TIMEOUT_SECONDS  = 120
YFINANCE_SUFFIX        = ".NS"
SCORE_DB_PATH          = "data/scores.db"
PREDICTION_DATA_DIR    = "data/predictions"
FORECAST_HORIZON_DAYS  = 30
FEEDBACK_CRON          = "0 11 * * 1-5"   # 4:30pm IST weekdays
RL_FLAT_THRESHOLD_PCT  = 0.3              # configurable direction threshold
```

---

## Shim Convention

Every moved file leaves a backward-compat shim at the old path:
```python
# -- MIGRATION SHIM --
# Real: src/backend/shared/schemas/pipeline.py
from backend.shared.schemas.pipeline import *        # noqa: F401, F403
from backend.shared.schemas.pipeline import FinalReport, ...
```

Forward shims at `src/backend/shared/clients/` and `src/backend/shared/data/` point to real `services/` files until Phase 7 moves them.

All `from core.schemas.pipeline import ...` and `from services.clients.llm_client import ...` statements continue to work through shims throughout the migration.

---

## Test Structure (post Phase 9)

```
tests/
├── unit/
│   ├── (original flat files)        # still exist; imported through shims
│   ├── shared/                      # test_schemas, test_signal_aggregator, test_config
│   │                                # all updated to backend.* import paths
│   ├── sectors/
│   │   ├── automobile/              # test_agents (imports → backend.sectors.automobile.agents.*)
│   │   ├── banking_bfsi/            # test_agents: 30 parametrized tests, 6 agents × 5 assertions
│   │   ├── it_sector/               # test_agents: 32 parametrized tests, 8 agents × 4 assertions
│   │   └── renewable_energy/        # test_agents: 24 parametrized tests, 6 agents × 4 assertions
│   └── intelligence/
│       ├── rl/                      # test_algorithms: stubs + 4 live math tests (reversion prior,
│       │                            #   penalty multipliers, direction threshold, weight normalization)
│       └── chat/                    # test_intent_detector + test_entity_extractor
│                                    # (parametrized skips — implement in Phase 6)
├── integration/
│   └── test_sector_routing.py       # 19 live tests:
│                                    # TestDetectSector: 23 tickers, case-insensitive, whitespace
│                                    # TestGetOrchestrator: correct class, extends Base, SECTOR_NAME
└── contract/
    └── (original files)

Baseline: 777 passed, 29 skipped (Phase 6 stubs), 0 failed
```

---

## Known Issues

1. **Newly-listed stocks** (ATHERENERGY): yfinance `.NS` returns 404 — agents fall back to LLM hallucination. No fix; add manual ticker override.
2. **RBI repo rate**: hardcoded static value in `services/data/fetchers/macro.py` — needs live RBI API (Phase 7).
3. **Sector fetcher stubs**: `vahan_fada.py`, `rbi_data.py`, `npa_metrics.py`, `deal_wins.py`, `transcript.py`, `mnre_data.py` raise `NotImplementedError` — implement in Phase 7.
4. **NSE holidays 2026**: preliminary dates hardcoded in `nse_calendar.py` — `calendar_updater.py` refreshes them on Dec 31.
5. **Seasonal seed YAMLs**: `src/backend/intelligence/rl/seasonal/seeds/` directory exists but 4 YAML files are empty — populate in Phase 5.
6. **Phase 7 shims pending removal**: ~30 shims across `core/` and `services/` deleted in Phase 7-11 after full import update.
7. **Frontend pages are stubs**: `home/`, `agents/`, `portfolio/`, `learn/` pages in `src/frontend/web/` are minimal — need full component wiring.
8. **Chat engine is stub**: `src/backend/intelligence/chat/engine.py` is empty — Phase 6 wires intent detection + entity extraction + real LLM routing. Note: `/ui/chat` already has a working agentic tool loop (yfinance + Tavily + DB) independent of this Phase 6 engine.
