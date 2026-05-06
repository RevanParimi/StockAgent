# Codebase Reference

> Ground-truth map of every module, its real path, and its public API.
> Updated: 2026-05-06 · reflects Phases 0–4 refactor (src/ layout, 4 sectors, BaseSectorOrchestrator)
> Previous structure at docs/CODEBASE.md (pre-refactor snapshot)

---

## Directory Layout (current — post Phase 0–4)

```
StockAI-Main/
├── main.py                          # CLI entry: python main.py <ticker>
├── requirements.txt
├── pyproject.toml                   # pythonpath=[".", "src"] — both legacy + new imports work
├── langgraph.json                   # sector graph registry → src/backend/sectors/*/pipeline/graph.py
├── docs/                            # all .md documentation files
│
├── src/                             # NEW home for all refactored Python
│   └── backend/
│       ├── shared/                  # cross-sector shared code
│       │   ├── schemas/
│       │   │   ├── pipeline.py      # StockQuery, AgentOutput, FinalReport, WeightedAgentScore, PipelineRun
│       │   │   └── feedback.py      # ALL RL schemas (MissType, Lesson, WeightMemory, etc.)
│       │   ├── pipeline/
│       │   │   ├── base_agent.py    # BaseAgent ABC — sector-agnostic
│       │   │   ├── base_orchestrator.py  # BaseSectorOrchestrator ABC (ticker resolve, LangGraph, RL weights, logging)
│       │   │   ├── signal_aggregator.py  # SignalAggregator — weighted LLM fusion → FinalReport
│       │   │   └── graphs/
│       │   │       ├── nodes.py     # make_dispatch_fn, make_run_agent_node, make_aggregate_node
│       │   │       ├── rails.py     # conflict_rail, input_rail, output_rail
│       │   │       └── state.py     # GraphState
│       │   ├── prompts/
│       │   │   ├── orchestrator.py       # Ticker resolution prompt
│       │   │   ├── signal_aggregator.py  # Verdict synthesis prompt
│       │   │   └── feedback_agent.py     # RL miss analysis prompt
│       │   ├── config/
│       │   │   ├── settings/
│       │   │   │   ├── base.py      # ALL shared constants: LLM, API keys, score thresholds
│       │   │   │   └── __init__.py
│       │   │   └── rag_config.py
│       │   ├── data/                # ← WILL BE POPULATED IN PHASE 7
│       │   │   ├── fetchers/        # (currently stubs — real files still at services/data/fetchers/)
│       │   │   ├── stores/          # (currently stubs — real files still at services/data/stores/)
│       │   │   └── cache/           # (currently stubs — real files still at services/data/cache/)
│       │   └── clients/             # ← WILL BE POPULATED IN PHASE 7
│       │                            # (currently stubs — real files still at services/clients/)
│       │
│       ├── sectors/
│       │   ├── __init__.py          # detect_sector(ticker) → sector key; get_orchestrator(sector) → class
│       │   │
│       │   ├── automobile/          # ✅ FULLY IMPLEMENTED
│       │   │   ├── agents/          # 9 files: sales_demand, fundamentals, raw_materials,
│       │   │   │                    #   pattern_analysis, sentiment, policy_regulatory,
│       │   │   │                    #   competitive_intel, risk_macro, valuation_catalyst
│       │   │   ├── prompts/         # 9 matching prompt files with SYSTEM_PROMPT + ANALYSIS_PROMPT
│       │   │   ├── schemas/
│       │   │   │   └── sub_scores.py  # 9 sub-score Pydantic models (sector-specific dimensions)
│       │   │   ├── config/
│       │   │   │   ├── settings.py  # AGENT_WEIGHTS, TICKERS, PEER_TICKERS, data URLs
│       │   │   │   └── registry.py  # AGENTS dict + WEIGHTS (9 instances)
│       │   │   ├── data/
│       │   │   │   ├── fetchers/    # vahan_fada.py stub (FADA/SIAM/Vahan fetcher — implement in Phase 7)
│       │   │   │   └── context/
│       │   │   │       └── builder.py  # AutomobileContextBuilder — 9 _build_* methods
│       │   │   └── pipeline/
│       │   │       ├── orchestrator.py  # AutomobileAgentOrchestrator(BaseSectorOrchestrator)
│       │   │       └── graph.py         # LangGraph StateGraph for automobile
│       │   │
│       │   ├── banking_bfsi/        # ✅ SCAFFOLDED — prompts + agents ready, fetchers are stubs
│       │   │   ├── agents/          # 6 files: fundamentals, risk, macro_policy, institutional,
│       │   │   │                    #   pattern_analysis, universe_setup
│       │   │   ├── prompts/         # 6 matching prompt files
│       │   │   ├── schemas/
│       │   │   │   └── sub_scores.py  # 6 sub-score models (NPA, NIM, CRAR, etc.)
│       │   │   ├── config/
│       │   │   │   ├── settings.py  # HDFC, ICICI, SBIN, KOTAKBANK, AXISBANK tickers; weights
│       │   │   │   └── registry.py  # AGENTS dict (6 instances)
│       │   │   ├── data/
│       │   │   │   ├── fetchers/    # rbi_data.py + npa_metrics.py (stubs — implement in Phase 7)
│       │   │   │   └── context/
│       │   │   │       └── builder.py  # BankingBfsiContextBuilder — 6 _build_* methods
│       │   │   └── pipeline/
│       │   │       ├── orchestrator.py  # BankingAgentOrchestrator(BaseSectorOrchestrator)
│       │   │       └── graph.py
│       │   │
│       │   ├── it_sector/           # ✅ SCAFFOLDED — prompts + agents ready, fetchers are stubs
│       │   │   ├── agents/          # 8 files: fundamentals, global_macro, risk_macro, peer_benchmark,
│       │   │   │                    #   pattern_analysis, sentiment, transcript_nlp, insider_smart_money
│       │   │   ├── prompts/         # 8 matching prompt files
│       │   │   ├── schemas/
│       │   │   │   └── sub_scores.py  # 8 sub-score models (deal_wins, attrition, visa_risk, etc.)
│       │   │   ├── config/
│       │   │   │   ├── settings.py  # TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM tickers; weights
│       │   │   │   └── registry.py  # AGENTS dict (8 instances)
│       │   │   ├── data/
│       │   │   │   ├── fetchers/    # deal_wins.py + transcript.py (stubs — implement in Phase 7)
│       │   │   │   └── context/
│       │   │   │       └── builder.py  # ItSectorContextBuilder — 8 _build_* methods
│       │   │   └── pipeline/
│       │   │       ├── orchestrator.py  # ITAgentOrchestrator(BaseSectorOrchestrator)
│       │   │       └── graph.py
│       │   │
│       │   └── renewable_energy/    # ✅ SCAFFOLDED — prompts + agents ready, fetchers are stubs
│       │       ├── agents/          # 6 files: fundamentals, business, valuation, sentiment_policy,
│       │       │                    #   technical, risk
│       │       ├── prompts/         # 6 matching prompt files
│       │       ├── schemas/
│       │       │   └── sub_scores.py  # 6 sub-score models (CUF, DSCR, EV/MW, DISCOM, etc.)
│       │       ├── config/
│       │       │   ├── settings.py  # ADANIGREEN, TATAPOWER, TORNTPOWER tickers; weights
│       │       │   └── registry.py  # AGENTS dict (6 instances)
│       │       ├── data/
│       │       │   ├── fetchers/    # mnre_data.py (stub — implement in Phase 7)
│       │       │   └── context/
│       │       │       └── builder.py  # Renewable_energyContextBuilder — 6 _build_* methods
│       │       └── pipeline/
│       │           ├── orchestrator.py  # RenewableAgentOrchestrator(BaseSectorOrchestrator)
│       │           └── graph.py
│       │
│       ├── intelligence/            # ← WILL BE POPULATED IN PHASE 5
│       │   ├── rl/
│       │   │   ├── algorithms/      # EMPTY STUBS — extraction happens in Phase 5
│       │   │   │   ├── weight_adaptation/  # bias_detector, hit_rate_tracker, penalty_calculator, weight_normalizer
│       │   │   │   ├── conviction/         # streak_tracker, reversion_prior, rsi_divergence
│       │   │   │   ├── forecast/           # envelope_builder, confidence_decay, price_interpolator
│       │   │   │   └── feedback/           # miss_classifier, lesson_extractor, lesson_merger
│       │   │   ├── agents/          # EMPTY STUBS — real files still at core/intelligence/rl/agents/
│       │   │   ├── regime/
│       │   │   │   └── signals/     # EMPTY STUBS — vix, fii_proxy, sector_rsi extraction in Phase 5
│       │   │   ├── seasonal/
│       │   │   │   └── seeds/       # EMPTY — YAML seed files created in Phase 5
│       │   │   ├── calendar/        # EMPTY STUBS — nse_calendar + updater moved in Phase 5
│       │   │   ├── stores/          # EMPTY STUBS — real files still at core/intelligence/rl/stores/
│       │   │   └── workflows/       # EMPTY STUBS — real files still at core/intelligence/rl/workflows/
│       │   ├── chat/                # ← WILL BE POPULATED IN PHASE 6
│       │   │   ├── engine.py        # (STUB — chat logic extracted in Phase 6)
│       │   │   ├── context/         # ticker_context.py + history_context.py
│       │   │   ├── algorithms/      # intent_detector.py + entity_extractor.py
│       │   │   └── prompts/         # system.py
│       │   ├── rag/                 # (still at core/intelligence/rag/ — move in later phase)
│       │   └── technical/           # (still at core/intelligence/algorithms/ — move in later phase)
│       │
│       ├── api/                     # ← WILL BE POPULATED IN PHASE 7
│       │   └── routes/              # (stubs — real files still at services/api/routes/)
│       │
│       └── scheduler/               # ← WILL BE POPULATED IN PHASE 7
│           └── python/              # (stubs — real files still at services/scheduler/)
│
├── core/                            # LEGACY — being emptied phase by phase
│   │                                # Every file here is now a SHIM that re-exports from src/
│   ├── schemas/
│   │   ├── pipeline.py              # SHIM → src/backend/shared/schemas/pipeline.py
│   │   └── feedback.py              # SHIM → src/backend/shared/schemas/feedback.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py              # SHIM → src/backend/shared/config/settings/base.py
│   │   │   └── __init__.py          # SHIM
│   │   ├── rag_config.py            # SHIM → src/backend/shared/config/rag_config.py
│   │   └── prompts/
│   │       ├── automobile/          # SHIMS → src/backend/sectors/automobile/prompts/
│   │       └── shared/              # real files (orchestrator, signal_aggregator, feedback_agent)
│   ├── graphs/
│   │   ├── nodes.py                 # SHIM → src/backend/shared/pipeline/graphs/nodes.py
│   │   ├── rails.py                 # SHIM → src/backend/shared/pipeline/graphs/rails.py
│   │   └── state.py                 # SHIM → src/backend/shared/pipeline/graphs/state.py
│   ├── pipeline/
│   │   ├── base_agent.py            # SHIM → src/backend/shared/pipeline/base_agent.py
│   │   ├── orchestrator.py          # SHIM → src/backend/sectors/automobile/pipeline/orchestrator.py
│   │   └── signal_aggregator.py     # SHIM → src/backend/shared/pipeline/signal_aggregator.py
│   ├── sectors/
│   │   ├── automobile/
│   │   │   ├── {agents}.py          # SHIMS → src/backend/sectors/automobile/agents/
│   │   │   ├── graph.py             # SHIM → src/backend/sectors/automobile/pipeline/graph.py
│   │   │   └── registry.py          # SHIM → src/backend/sectors/automobile/config/registry.py
│   │   ├── banking/agents.py        # SHIM → src/backend/sectors/banking_bfsi/config/registry.py
│   │   ├── it/agents.py             # SHIM → src/backend/sectors/it_sector/config/registry.py
│   │   └── renewable/agents.py      # SHIM → src/backend/sectors/renewable_energy/config/registry.py
│   └── intelligence/                # REAL FILES — not yet moved (Phase 5 target)
│       ├── rl/
│       │   ├── agents/              # feedback_agent.py, weight_adapter.py  ← Phase 5
│       │   ├── conviction/          # tracker.py  ← Phase 5
│       │   ├── stores/              # prediction_store.py, ledger_propagator.py  ← Phase 5
│       │   ├── workflows/           # generate_forecast.py, daily_review.py  ← Phase 5
│       │   ├── nse_calendar.py      # ← Phase 5
│       │   └── calendar_updater.py  # ← Phase 5
│       ├── regime/detector.py       # ← Phase 5
│       ├── seasonal/                # calendar.py, validator.py  ← Phase 5
│       ├── rag/                     # ← later phase
│       └── algorithms/              # ← later phase
│
├── services/                        # LEGACY — being emptied phase by phase
│   ├── api/
│   │   ├── server.py                # real — lifespan, startup self-heal, BackgroundScheduler
│   │   └── routes/
│   │       ├── analyse.py           # UPDATED — sector auto-detect via detect_sector()
│   │       ├── stream.py            # UPDATED — sector routing applied
│   │       ├── history.py           # real
│   │       ├── scheduler_api.py     # real
│   │       └── ui_data.py           # real — /ui/* endpoints + /ui/chat  ← Phase 6 extracts chat
│   ├── clients/                     # real — llm_client.py, tavily_fetcher.py, alerting.py  ← Phase 7
│   ├── data/
│   │   ├── fetchers/                # real — fundamentals.py, macro.py, news.py  ← Phase 7
│   │   ├── stores/                  # real — score_store.py, run_logger.py, analysis_logger.py, api_usage.py  ← Phase 7
│   │   ├── cache/                   # real — macro_cache.py  ← Phase 7
│   │   └── context/builder.py       # real — ContextBuilder (all sectors _build_* methods)  ← Phase 7
│   └── scheduler/                   # real — python/scheduler.py + run_schedule.py  ← Phase 7
│
└── tests/
    ├── unit/                        # 323 tests — all pass
    ├── integration/
    └── contract/
```

---

## Sector Registry (`src/backend/sectors/__init__.py`)

```python
detect_sector("HDFCBANK")   → "banking_bfsi"
detect_sector("TCS")        → "it_sector"
detect_sector("ADANIGREEN") → "renewable_energy"
detect_sector("MARUTI")     → "automobile"   # default fallback

get_orchestrator("banking_bfsi")    → BankingAgentOrchestrator
get_orchestrator("it_sector")       → ITAgentOrchestrator
get_orchestrator("renewable_energy")→ RenewableAgentOrchestrator
get_orchestrator("automobile")      → AutomobileAgentOrchestrator
```

**POST /analyse** and **WS /ws/stream** both call `detect_sector(ticker)` automatically. Pass `sector` in the request body to override.

---

## BaseSectorOrchestrator (`src/backend/shared/pipeline/base_orchestrator.py`)

All 4 sector orchestrators extend this. It handles:
1. `_resolve_ticker()` — LLM + Serper fallback → `StockQuery`
2. `_load_learned_weights()` — loads `WeightMemory` from RL store per ticker
3. `analyse()` / `analyse_async()` — full pipeline: resolve → agents → aggregate → log
4. `_run_via_graph()` / `_run_via_graph_async()` — LangGraph worker pool dispatch

Sector orchestrators only define:
- `SECTOR_NAME: str`
- `self._sub_agents: dict`  (set before `super().__init__()`)

---

## Agent Pipeline (per sector)

```
POST /analyse or WS /ws/stream
    ↓
detect_sector(ticker) → OrchestratorClass
    ↓
BaseSectorOrchestrator.analyse_async(ticker)
    1. _resolve_ticker() → StockQuery
    2. _load_learned_weights(ticker) → dict | None   [from RL WeightMemory]
    3. LangGraph worker pool → N agents run in PARALLEL
         BaseAgent.run(query)
           _gather_context() → sector ContextBuilder.build(agent_name, query)
           _build_prompt()   → (system, user) from sector prompts/
           _call_llm()       → OpenRouter JSON
           _parse_output()   → AgentOutput subtype
    4. SignalAggregator.run(learned_weights) → FinalReport
    5. log_run_summary, log_usage, log_analysis
```

---

## Schemas

### `src/backend/shared/schemas/pipeline.py`
```
StockQuery(ticker, company_name, exchange, analysis_date)
AgentOutput — base: agent, ticker, overall_score, key_positives, key_risks, summary, data_freshness, error
FinalReport — ticker, company_name, final_score, verdict, weighted_agent_scores, conflicts_resolved,
              conviction_drivers, top_risks, executive_summary, investment_thesis, report_date,
              price_target, recovery_timeline_quarters, undervalued_by_pct, discount_reason,
              recovery_catalysts, agent_outputs
WeightedAgentScore — raw, weight, weighted
PipelineRun — run_id, query, report, status, duration_seconds, errors
```

### `src/backend/shared/schemas/feedback.py`
```
MissType — data_gap | data_stale | external_shock (0×) | timing (0.5×) | magnitude (0.25×)
           model_bias | direction_flip (1.0×)
LessonScope — stock_specific | sector_wide | market_wide
PredictionEnvelope — 30-day forecast sheet per cycle per ticker
DailyFeedbackLog — daily miss analysis entries per cycle
WeightMemory — learned agent weights + audit trail — PERSISTS across cycles
LearningLedger — accumulated pattern lessons — PERSISTS across cycles
ConvictionStreak — current_verdict, streak_days, reversion_prior (0–0.30)
RegimeSnapshot — regime_label (6 states), multipliers, narrative
SeasonalPattern — months, day_range, agents_affected deltas, confidence
```

### Sector-specific sub-scores (`src/backend/sectors/{sector}/schemas/sub_scores.py`)

| Sector | Sub-score models |
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

### Daily Review Flow (8 steps)
```
APScheduler 4:30pm IST weekdays → run_daily_review(ticker, date)
  1. Load PredictionEnvelope + today's forecast row
  2. Fetch actual close (yfinance)
  3. Compute error metrics (price_error_pct, direction_correct, timing_lag)
  4. P4 PromptEnhancer: load saved blindspots → inject into FeedbackAgentInput
  5. FeedbackAgent.run() → miss_type, primary_miss_agent, new_lessons, revised_context
  6. WeightAdapter.update() → WeightMemory v(N+1) [deterministic, no LLM]
  6.5 (ephemeral) RegimeDetector → apply regime multipliers to today's weights only
  7. ConvictionTracker → update streak + reversion_prior
  8. Revise remaining forecasts (confidence × (1 - reversion_prior × 0.5))
  9. Merge new lessons → LearningLedger → propagate to sector/market ledgers
  9.5 SeasonalValidator → feed result back to LearningLedger (invalidate/boost)
```

### Regime Multiplier Design (intentionally ephemeral)
Regime adjustments are NOT persisted to WeightMemory. They reflect short-term market
conditions that flip within days. Baking them in would contaminate long-term accuracy.
Applied to Step 7 (forecast revision) then discarded.

---

## Sector Agent Counts + Weights

| Sector | Agents | Key weights |
|---|---|---|
| automobile | 9 | fundamentals 0.18, sales_demand 0.15, risk_macro 0.13 |
| banking_bfsi | 6 | fundamentals 0.25, risk 0.20, macro_policy 0.20 |
| it_sector | 8 | fundamentals 0.25, global_macro 0.20, risk_macro 0.15 |
| renewable_energy | 6 | fundamentals 0.30, business 0.25, valuation 0.20 |

---

## API Endpoints (current — post Phase 0–4)

### Analysis
| Method | Path | Notes |
|---|---|---|
| `POST` | `/analyse` | Body: `{ticker, sector?, output_format?}`. Sector auto-detected if omitted. |
| `WS` | `/ws/stream?ticker=X` | Sector auto-detected. Streams `agent_progress` events + `complete`. |

### History
| Method | Path | Notes |
|---|---|---|
| `GET` | `/history/{ticker}` | SQLite score history. |
| `GET` | `/history/{ticker}/latest` | Most recent FinalReport for ticker. |

### UI Data (`/ui/*`)
| Method | Path | Notes |
|---|---|---|
| `GET` | `/ui/bootstrap` | All UI data in one shot. |
| `PUT` | `/ui/agents/weights` | Persist user-tuned weights. |
| `GET/PUT` | `/ui/agents/tasks` | Persist task enabled/disabled flags. |
| `GET/PUT` | `/ui/watchlist` | With live yfinance prices on GET. |
| `GET` | `/ui/nifty-ranges?range=` | Sparkline data (1W/1M/3M/6M/1Y). |
| `GET` | `/ui/search?q=` | 16 tickers + DB theses + yfinance fallback. |
| `GET` | `/ui/trending` | Score-delta movers from DB. |
| `GET` | `/ui/learnings` | RL-derived lesson cards. |
| `POST` | `/ui/chat` | LLM chat with conversation history. ← Phase 6 extracts to chat engine. |
| `GET/PUT` | `/ui/categories/{key}/tickers` | Category stock management. |

### Scheduler
| Method | Path | Notes |
|---|---|---|
| `GET` | `/scheduler/status` | Job list + last run times. |
| `POST` | `/scheduler/forecast` | Trigger manual forecast generation. |
| `POST` | `/scheduler/daily-review` | Trigger manual daily review. |
| `GET` | `/health` | Railway health check. |

---

## Key Settings (`src/backend/shared/config/settings/base.py`)

```python
LLM_MODEL            = "qwen/qwen3-235b-a22b"
OPENROUTER_BASE_URL  = "https://openrouter.ai/api/v1"
AGENT_TIMEOUT_SECONDS = 120
YFINANCE_SUFFIX      = ".NS"
SCORE_DB_PATH        = "data/scores.db"
PREDICTION_DATA_DIR  = "data/predictions"
FORECAST_HORIZON_DAYS = 30
FEEDBACK_CRON        = "0 11 * * 1-5"   # 4:30pm IST weekdays
RL_FLAT_THRESHOLD_PCT = 0.3              # configurable direction threshold
```

---

## Shim Convention (backward compatibility during migration)

Every file that has been moved leaves a shim at the old path:
```python
# -- MIGRATION SHIM --
# Real: src/backend/shared/schemas/pipeline.py
from backend.shared.schemas.pipeline import *  # noqa: F401, F403
from backend.shared.schemas.pipeline import FinalReport, ...  # explicit re-exports
```

This means all `from core.schemas.pipeline import ...` statements in tests and legacy code
continue to work without modification throughout the migration.

---

## Known Issues (from CODEBASE.md pre-refactor)

1. **Newly-listed stocks** (ATHERENERGY): yfinance `.NS` returns 404 — agents fall back to LLM hallucination.
2. **RBI repo rate**: hardcoded static value in `services/data/fetchers/macro.py` — update manually or wire RBI API.
3. **valuation_catalyst context**: `_build_valuation_catalyst` in `services/data/context/builder.py` imports from `tools.yfinance_fetcher` which may not exist — verify path.
4. **Banking/IT/Renewable sector fetcher stubs**: `rbi_data.py`, `npa_metrics.py`, `deal_wins.py`, `transcript.py`, `mnre_data.py` are stubs that raise `NotImplementedError` — implement in Phase 7.
5. **NSE holidays 2026**: preliminary dates hardcoded — exact dates update via `calendar_updater.py` on Dec 31.
6. **Seasonal seed YAMLs**: `src/backend/intelligence/rl/seasonal/seeds/` directory exists but all 4 YAML files are empty — populate in Phase 5.
7. **Phase 7 shims pending removal**: ~30 shims across `core/` and `services/` will be deleted in Phase 7 once all imports updated.
