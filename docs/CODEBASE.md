# Codebase Reference

> Ground-truth map of every module, its real path, and its public API.
> Updated: 2026-04-28 · reflects 4-folder restructure (core / services / frontend / tests)

---

## Directory Layout

```
StockAgent-main/
├── main.py                              # CLI entry point: python main.py <ticker>
├── requirements.txt
├── langgraph.json                       # LangGraph graph registry (→ core/sectors/)
│
├── core/                                # All Python backend source
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py                  # ALL settings/constants (LLM, weights, API keys, limits)
│   │   │   └── __init__.py              # re-exports base.py so `from core.config import settings` works
│   │   ├── rag_config.py                # shim → core/intelligence/rag/config.py
│   │   ├── prompts/
│   │   │   ├── automobile/              # 9 prompt files (one per agent)
│   │   │   └── shared/                  # orchestrator.py, signal_aggregator.py, feedback_agent.py
│   │   └── weights/                     # (stub — future learned weights)
│   │
│   ├── graphs/                          # LangGraph infrastructure
│   │   ├── nodes.py                     # make_dispatch_fn, make_run_agent_node
│   │   ├── rails.py                     # input_rail, output_rail, conflict_rail
│   │   └── state.py                     # GraphState
│   │
│   ├── pipeline/
│   │   ├── base_agent.py                # BaseAgent ABC — run(), run_async(), _gather_context()
│   │   ├── orchestrator.py              # AutomobileAgentOrchestrator — runs 9 agents in parallel
│   │   └── signal_aggregator.py         # SignalAggregator — weighted score → FinalReport
│   │
│   ├── schemas/
│   │   ├── pipeline.py                  # ALL Pydantic models (StockQuery, AgentOutput subtypes, FinalReport)
│   │   └── feedback.py                  # RL schemas: MissType, LessonScope, TimingAccuracy, RevisedContext, etc.
│   │
│   ├── sectors/
│   │   ├── automobile/                  # 9 agent classes + graph.py (registered in langgraph.json)
│   │   ├── banking/                     # stub agents (agents.py, graph.py)
│   │   ├── it/                          # stub agents
│   │   └── renewable/                   # stub agents
│   │
│   ├── intelligence/
│   │   ├── algorithms/indicators/
│   │   │   └── fetcher.py               # get_technical_context(), RSI/MACD/BB/support
│   │   ├── rag/
│   │   │   ├── config.py                # RAG_ENABLED=false by default
│   │   │   ├── core/embedder.py         # SentenceTransformer embeddings
│   │   │   ├── core/retriever.py        # ChromaDB / Pinecone / Qdrant
│   │   │   ├── core/vector_store.py     # Store management
│   │   │   └── ingestion/ingestion.py   # Ingest PDFs, earnings transcripts
│   │   └── rl/
│   │       ├── agents/feedback_agent.py   # 6th agent — daily root-cause LLM call
│   │       ├── agents/weight_adapter.py   # Deterministic weight adjustment (no LLM)
│   │       ├── stores/prediction_store.py # Reads/writes all 4 JSON memory files
│   │       └── workflows/
│   │           ├── daily_review.py        # Cron entry point — 8-step daily feedback loop
│   │           └── generate_forecast.py   # Month-start — generates 30-day prediction envelope
│   │
│   └── scripts/
│       ├── make_ppt.py                  # Generate PowerPoint from final report
│       └── sanity_rl.py                 # Layered RL smoke tests (run: python -m core.scripts.sanity_rl)
│
├── services/
│   ├── api/                             # FastAPI — port 8001 INTERNAL
│   │   ├── server.py                    # app + CORS (only allows :3000) + health endpoint
│   │   └── routes/
│   │       ├── analyse.py               # POST /analyse
│   │       ├── stream.py                # WS /ws/stream?ticker=X
│   │       └── history.py               # GET /history/{ticker}[/latest]
│   ├── gateway/                         # TypeScript gateway — port 3000 (public-facing)
│   │   └── src/
│   │       ├── index.ts                 # Hono app + Bun.serve
│   │       ├── routes/                  # analyse, history, health, scheduler
│   │       ├── ws/stream.ts             # Bidirectional WS proxy → :8001/ws/stream
│   │       └── jobs/analysis-cron.ts    # node-cron 8:30am IST → POST each ticker
│   ├── clients/
│   │   ├── llm_client.py               # get_llm_client(), get_async_llm_client() → OpenRouter
│   │   └── tavily_fetcher.py           # search_tavily(), fetch_tavily_context()
│   ├── data/
│   │   ├── cache/macro_cache.py        # set/get/clear_macro_cache(sector) — in-memory
│   │   ├── context/builder.py          # ContextBuilder.build(agent_name, query) → str
│   │   ├── fetchers/
│   │   │   ├── fundamentals.py         # get_financials(), get_fundamentals_context()
│   │   │   ├── macro.py                # get_macro_context(), get_raw_materials_context()
│   │   │   └── news.py                 # search_serper(), fetch_news_context()
│   │   └── stores/
│   │       ├── analysis_logger.py      # log_analysis() → logs/analysis_history.jsonl
│   │       ├── api_usage.py            # record_call(), get_usage(), monthly counters
│   │       ├── run_logger.py           # log_llm_call(), log_run_summary()
│   │       └── score_store.py          # SQLite score persistence for RL loop
│   ├── scheduler/
│   │   ├── python/scheduler.py         # APScheduler — RL daily review (4:30pm IST weekdays)
│   │   └── run_schedule.py             # CLI: forecast / daily-review / feedback-status / start
│   ├── csharp/                          # C# Quartz.NET scheduler (Phase 4)
│   └── typescript/                      # TypeScript helpers
│
├── frontend/                            # React 19 + Vite — port 5173
│   └── vite.config.ts                   # /api → :3000, /ws → :3000 (both via TS gateway)
│
└── tests/
    ├── unit/                            # Pure logic tests (no network/LLM)
    ├── integration/                     # Tests that hit local services (RAG, data fetchers)
    └── contract/                        # Cross-layer wiring tests (import paths, schema compat)
```

> **Runtime folders** (`data/`, `logs/`, `outputs/`) are created at runtime and gitignored.
> `data/predictions/<sector>/<ticker>/` holds all 4 RL JSON memory files.

---

## Runtime Architecture

```
Browser :5173 (Vite dev)
    │  /api/*  →  proxy  →  :3000
    │  /ws/*   →  proxy  →  :3000
    ▼
TypeScript Gateway (Bun + Hono)  :3000  — services/gateway/src/index.ts
    │  POST /api/analyse        → HTTP POST  :8001/analyse
    │  GET  /api/history/*      → HTTP GET   :8001/history/*
    │  GET  /health             → HTTP GET   :8001/health
    │  GET  /api/scheduler/status
    │  POST /api/scheduler/run-now
    │  WS   /ws/stream          → WS proxy   :8001/ws/stream
    │  cron "30 8 * * 1-5" IST  → POST :8001/analyse per ticker
    ▼
Python FastAPI (internal)  :8001  — services/api/server.py
    │  POST /analyse  →  AutomobileAgentOrchestrator
    │  WS   /ws/stream
    │  GET  /history/*  →  ScoreStore (SQLite → data/scores.db)

Python APScheduler  — services/scheduler/python/scheduler.py
    RL daily review only — weekdays 4:30pm IST (11:00 UTC)
    Imports core.intelligence.rl directly; cannot be an HTTP call.
```

**Start order:**
```bash
bun run services/gateway/src/index.ts           # TS gateway :3000
uvicorn services.api.server:app --port 8001     # Python internal :8001
python services/scheduler/python/scheduler.py   # RL review job
cd frontend && npm run dev                      # Vite :5173
```

---

## Key Settings (`core/config/settings/base.py`)

```python
LLM_MODEL            = "qwen/qwen3-235b-a22b"        # override via LLM_MODEL env var
OPENROUTER_BASE_URL  = "https://openrouter.ai/api/v1"
AGENT_TIMEOUT_SECONDS = 120
SERPER_MAX_QUERIES   = 3
NEWS_ARTICLES_PER_QUERY = 5
PRICE_HISTORY_YEARS  = 10

AGENT_WEIGHTS = {                  # must sum to 1.0
    "sales_demand":       0.16,
    "raw_materials":      0.09,
    "fundamentals":       0.18,
    "pattern_analysis":   0.12,
    "sentiment":          0.04,
    "policy_regulatory":  0.09,
    "competitive_intel":  0.09,
    "risk_macro":         0.13,
    "valuation_catalyst": 0.10,
}

SCORE_THRESHOLDS = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}

# Phase 5/6 RL settings
PREDICTION_DATA_DIR    = "data/predictions"
FORECAST_HORIZON_DAYS  = 30
WEIGHT_MIN_OBSERVATIONS = 3      # days before weight adaptation activates
WEIGHT_ACCURACY_WINDOW  = 7      # rolling window for direction accuracy
WEIGHT_MAX_STEP         = 0.05
WEIGHT_MAX_DRIFT        = 0.15
FEEDBACK_CRON           = "0 11 * * 1-5"   # 4:30pm IST = 11:00 UTC weekdays
```

---

## Schemas

### `core/schemas/pipeline.py` — Analysis pipeline models

```
StockQuery(ticker, company_name, exchange="NSE", analysis_date=today)

AgentOutput:
  agent, ticker, overall_score (0-1), key_positives[], key_risks[],
  summary, data_freshness, error, raw_llm_response (excluded from serialisation)

FinalReport:
  ticker, company_name, final_score, verdict  # STRONG BUY|BUY|NEUTRAL|SELL|STRONG SELL
  weighted_agent_scores {agent: WeightedAgentScore(raw, weight, weighted)}
  conflicts_resolved[], conviction_drivers[], top_risks[], investment_thesis, report_date
  price_target, recovery_timeline_quarters, undervalued_by_pct,
  discount_reason, recovery_catalysts[]
  agent_outputs {agent_name: dict}
```

### `core/schemas/feedback.py` — RL feedback loop models

```
MissType            data_gap | data_stale | external_shock (0× penalty)
                    timing (0.5×) | magnitude (0.25×)
                    model_bias | direction_flip (1.0×)

LessonScope         stock_specific | sector_wide | market_wide

LessonCategory      macro | global_macro | technical | sentiment
                    fundamental | seasonal | data_availability

TimingAccuracy      predicted_peak_day, actual_move_start_day, lag_days, assessment

RevisedContext      headline, risks_next_7_days[], catalysts_next_7_days[],
                    watch_signals[], horizon_confidence_adjustment

PredictionEnvelope  30-day forecast sheet (one per cycle, per ticker)
DailyFeedbackLog    daily miss analysis entries (one per cycle, per ticker)
WeightMemory        earned agent credibility — PERSISTS across cycles
LearningLedger      accumulated pattern lessons — PERSISTS across cycles
```

---

## 9 Agents — Execution & Data Sources

| Agent | Class file | Prompt file | Primary data |
|---|---|---|---|
| sales_demand | `core/sectors/automobile/sales_demand.py` | `core/config/prompts/automobile/sales_demand.py` | Serper news |
| raw_materials | `core/sectors/automobile/raw_materials.py` | `core/config/prompts/automobile/raw_materials.py` | yfinance (SLX, AA, PPLT, CL=F) + Serper |
| fundamentals | `core/sectors/automobile/fundamentals.py` | `core/config/prompts/automobile/fundamentals.py` | yfinance financials + Serper |
| pattern_analysis | `core/sectors/automobile/pattern_analysis.py` | `core/config/prompts/automobile/pattern_analysis.py` | yfinance OHLCV → RSI/MACD/BB |
| sentiment | `core/sectors/automobile/sentiment.py` | `core/config/prompts/automobile/sentiment.py` | Serper news |
| policy_regulatory | `core/sectors/automobile/policy_regulatory.py` | `core/config/prompts/automobile/policy_regulatory.py` | Tavily + Serper |
| competitive_intel | `core/sectors/automobile/competitive_intel.py` | `core/config/prompts/automobile/competitive_intel.py` | Serper news |
| risk_macro | `core/sectors/automobile/risk_macro.py` | `core/config/prompts/automobile/risk_macro.py` | yfinance macro + Serper + macro_cache |
| valuation_catalyst | `core/sectors/automobile/valuation_catalyst.py` | `core/config/prompts/automobile/valuation_catalyst.py` | Serper + fundamentals |

---

## Data Flow (per run)

```
main.py → AutomobileAgentOrchestrator.analyse(ticker)
  1. _resolve_ticker()      → LLM → StockQuery(ticker, company_name, exchange)
  2. LangGraph worker pool  → 9 agents run in PARALLEL
       BaseAgent.run(query)
         _gather_context() → ContextBuilder.build() → fetchers
         _build_prompt()   → (system_prompt, user_prompt)
         _call_llm_with_retry() → OpenRouter → JSON string
         _parse_output()   → AgentOutput subtype
         log_llm_call()    → logs/agent_calls.jsonl
  3. SignalAggregator.run()
       weighted_scores → composite → LLM → FinalReport
  4. log_run_summary()      → logs/run_summaries.jsonl
  5. log_usage_summary()    → logs/api_usage.json
```

---

## RL Feedback Loop — Data Files

```
data/predictions/
  <sector>/
    <TICKER>/
      <TICKER>_<YYYY-MM>_prediction_envelope.json   ← monthly (archived each cycle)
      <TICKER>_<YYYY-MM>_daily_feedback_log.json    ← monthly (archived each cycle)
      <TICKER>_agent_weight_memory.json             ← PERMANENT (persists across cycles)
      <TICKER>_learning_ledger.json                 ← PERMANENT (persists across cycles)
```

**CLI commands:**
```bash
python -m services.scheduler.run_schedule forecast --ticker MARUTI
python -m services.scheduler.run_schedule daily-review --ticker MARUTI
python -m services.scheduler.run_schedule feedback-status --ticker MARUTI
python -m services.scheduler.run_schedule start          # full daemon
```

---

## ContextBuilder Routing (`services/data/context/builder.py`)

Lookup: `_build_{sector}_{agent_name}` → `_build_{agent_name}` → `_build_generic`

| Method | Fetchers called |
|---|---|
| `_build_sales_demand` | `fetch_news_context(queries)` |
| `_build_fundamentals` | `get_fundamentals_context(ticker)` + `fetch_news_context()` |
| `_build_pattern_analysis` | `get_technical_context(ticker)` → RSI, MACD, BB, support/resistance |
| `_build_sentiment` | `fetch_news_context(queries)` |
| `_build_risk_macro` | `get_macro_context()` + macro_cache |
| `_build_raw_materials` | `get_raw_materials_context()` + `fetch_news_context(max_queries=1)` |
| `_build_policy_regulatory` | `fetch_tavily_context()` + `fetch_news_context()` |
| `_build_competitive_intel` | `fetch_news_context(queries)` |
| `_build_valuation_catalyst` | ⚠ not implemented → falls back to `_build_generic` |

---

## Logs & Observability

| File | Written by | Content |
|---|---|---|
| `logs/agent_calls.jsonl` | `run_logger.log_llm_call()` | per-LLM-call: tokens, cost, score, duration |
| `logs/run_summaries.jsonl` | `run_logger.log_run_summary()` | per-run: verdict, score, agent_scores, errors |
| `logs/api_usage.json` | `api_usage.record_call()` | monthly Serper/Tavily counter (auto-resets) |
| `logs/analysis_history.jsonl` | `analysis_logger.log_analysis()` | full report archive |

---

## .env Variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM inference |
| `SERPER_API_KEY` | Yes | Google search (2,500/month free) |
| `TAVILY_API_KEY` | Yes | Full-page extraction — policy agent (1,000/month free) |
| `NEWSAPI_KEY` | No | Fallback when Serper fails (100/day free) |
| `LLM_MODEL` | No | Default `qwen/qwen3-235b-a22b` |
| `AGENT_TIMEOUT_SECONDS` | No | Default 120s |
| `SERPER_MONTHLY_LIMIT` | No | Default 2500 |
| `TAVILY_MONTHLY_LIMIT` | No | Default 1000 |

---

## Known Issues

1. **Newly-listed stocks** (e.g. ATHERENERGY): yfinance `.NS` returns 404 — fundamentals and pattern_analysis fall back to LLM hallucination. No fix; add manual ticker override.
2. **RBI repo rate**: hardcoded static value in `services/data/fetchers/macro.py:get_rbi_repo_rate()` — update manually or wire RBI API.
3. **Sector mismatch**: Orchestrator always runs automobile agents regardless of ticker sector. Sector routing not implemented.
4. **valuation_catalyst context**: `_build_valuation_catalyst` missing in `services/data/context/builder.py` — falls back to generic stub.
5. **Token tracking**: `log_run_summary()` called with `total_tokens=0` hardcoded — per-agent tokens in `agent_calls.jsonl` but not summed into summary.
6. **Rubber ticker** (`^TOCOM_RUBBER`): not reliably available on yfinance — fails silently.
