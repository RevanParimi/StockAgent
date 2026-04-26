# Codebase Reference

> Ground-truth map of every module, its real path, and its public API.
> Updated: 2026-04-21 · reflects post-restructure state (commit eaf52ab) + gap fixes + TypeScript gateway.

---

## Directory Layout

```
automobile_agent/
├── main.py                        # CLI entry point
├── config/
│   ├── settings/base.py           # ALL settings/constants (LLM, weights, API keys, limits)
│   ├── settings/__init__.py       # re-exports base.py so `from config import settings` works
│   ├── rag_config.py              # shim → intelligence/rag/config.py
│   ├── prompts/
│   │   ├── automobile/            # 9 prompt files (one per agent)
│   │   └── shared/                # orchestrator.py, signal_aggregator.py, feedback_agent.py
│   └── weights/                   # (stub — future learned weights)
│
├── core/
│   ├── pipeline/
│   │   ├── base_agent.py          # BaseAgent ABC — run(), run_async(), _gather_context()
│   │   ├── orchestrator.py        # AutomobileAgentOrchestrator — runs 9 agents in parallel
│   │   └── signal_aggregator.py   # SignalAggregator — weighted score → FinalReport
│   ├── schemas/
│   │   └── pipeline.py            # ALL Pydantic models (StockQuery, AgentOutput subtypes, FinalReport)
│   ├── sectors/
│   │   ├── automobile/            # 9 agent classes (the real implementations)
│   │   ├── banking/               # stub agents (agents.py, graph.py)
│   │   ├── it/                    # stub agents
│   │   └── renewable/             # stub agents
│   └── graphs/                    # LangGraph nodes/rails/state (graph-based execution path)
│
├── intelligence/
│   ├── algorithms/indicators/fetcher.py  # get_technical_context(), compute_rsi/macd/bb
│   ├── rag/config.py              # RAG settings (RAG_ENABLED=false by default)
│   └── rl/                        # RL feedback loop (feedback_agent, weight_adapter, stores)
│
├── services/
│   ├── api/                       # FastAPI — port 8001 INTERNAL (not browser-accessible)
│   │   ├── server.py              # app + CORS (only allows :3000) + health endpoint
│   │   └── routes/
│   │       ├── analyse.py         # POST /analyse
│   │       ├── stream.py          # WS /ws/stream?ticker=X
│   │       └── history.py         # GET /history/{ticker}[/latest]
│   ├── gateway/                   # TypeScript gateway — port 3000 (public-facing)
│   │   ├── package.json           # Bun project: hono, zod, node-cron, ws
│   │   ├── tsconfig.json
│   │   ├── .env.example
│   │   └── src/
│   │       ├── index.ts           # Hono app + Bun.serve
│   │       ├── types/             # Zod schemas (report, stream, history, scheduler)
│   │       ├── client/python.ts   # Typed HTTP client → :8001
│   │       ├── routes/            # analyse, history, health, scheduler
│   │       ├── ws/stream.ts       # Bidirectional WS proxy → :8001/ws/stream
│   │       ├── jobs/analysis-cron.ts  # node-cron 8:30am IST → POST each ticker
│   │       └── middleware/logger.ts
│   ├── clients/
│   │   ├── llm_client.py          # get_llm_client(), get_async_llm_client() → OpenRouter
│   │   └── tavily_fetcher.py      # search_tavily(), fetch_tavily_context()
│   ├── data/
│   │   ├── cache/macro_cache.py   # set/get/clear_macro_cache(sector) — in-memory cache
│   │   ├── context/builder.py     # ContextBuilder.build(agent_name, query) → str
│   │   ├── fetchers/
│   │   │   ├── fundamentals.py    # get_financials(), get_fundamentals_context()
│   │   │   ├── macro.py           # get_macro_context(), get_raw_materials_context(), _fetch_latest()
│   │   │   └── news.py            # search_serper(), fetch_news_context()
│   │   └── stores/
│   │       ├── analysis_logger.py # log_analysis() → logs/analysis_history.jsonl
│   │       ├── api_usage.py       # record_call(), get_usage(), log_usage_summary()
│   │       ├── run_logger.py      # log_llm_call(), log_run_summary() → logs/agent_calls.jsonl
│   │       └── score_store.py     # persist/retrieve scores for RL loop
│   └── scheduler/python/scheduler.py  # APScheduler — RL daily review ONLY (Job 1 moved to gateway)
│
├── frontend/                      # React 19 + Vite — port 5173
│   └── vite.config.ts             # /api → :3000, /ws → :3000 (both via TS gateway)
│
├── agents/          ← COMPATIBILITY SHIMS ONLY (re-export from core/sectors/automobile/)
├── models/          ← COMPATIBILITY SHIMS ONLY (re-export from core/schemas/pipeline.py)
├── prompts/         ← COMPATIBILITY SHIMS ONLY (re-export from config/prompts/)
└── tools/           ← COMPATIBILITY SHIMS ONLY (re-export from services/)
```

> **Rule**: Never edit files in `agents/`, `models/`, `prompts/`, `tools/` directly — they are shims.
> Edit the real files under `core/`, `services/`, `config/`.

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
    │  GET  /api/scheduler/status   (reads cron state in-process)
    │  POST /api/scheduler/run-now  (fires analysis immediately)
    │  WS   /ws/stream          → WS proxy   :8001/ws/stream
    │  cron "30 8 * * 1-5" IST → POST :8001/analyse for each ticker
    ▼
Python FastAPI (internal)  :8001  — services/api/server.py
    │  POST /analyse  →  AutomobileAgentOrchestrator
    │  WS   /ws/stream
    │  GET  /history/*  →  ScoreStore (SQLite)

Python APScheduler  — services/scheduler/python/scheduler.py
    RL daily review only — "0 11 * * 1-5" IST (4:30pm IST = 11:00 UTC)
    Imports intelligence.rl directly; cannot be an HTTP call.
    Analysis job (automobile_agent_run) has been removed — now in TypeScript gateway.
```

**Start order:**
```bash
bun run services/gateway/src/index.ts           # TS gateway on :3000
uvicorn services.api.server:app --port 8001     # Python internal on :8001
python services/scheduler/python/scheduler.py   # RL review only
cd frontend && npm run dev                      # Vite on :5173
```

---

## Shim Map

| Old import (still works) | Real file |
|---|---|
| `from models.schemas import X` | `core/schemas/pipeline.py` |
| `from agents.base_agent import BaseAgent` | `core/pipeline/base_agent.py` |
| `from agents.{name} import {Name}Agent` | `core/sectors/automobile/{name}.py` |
| `from agents.signal_aggregator import SignalAggregator` | `core/pipeline/signal_aggregator.py` |
| `from tools.llm_client import get_llm_client` | `services/clients/llm_client.py` |
| `from tools.run_logger import log_llm_call` | `services/data/stores/run_logger.py` |
| `from tools.context_builder import ContextBuilder` | `services/data/context/builder.py` |
| `from tools.fundamentals_fetcher import get_fundamentals_context` | `services/data/fetchers/fundamentals.py` |
| `from tools.macro_fetcher import get_macro_context` | `services/data/fetchers/macro.py` |
| `from tools.news_fetcher import fetch_news_context` | `services/data/fetchers/news.py` |
| `from tools.macro_cache import get_macro_cache` | `services/data/cache/macro_cache.py` |
| `from tools.tavily_fetcher import fetch_tavily_context` | `services/clients/tavily_fetcher.py` |
| `from tools.yfinance_fetcher import get_technical_context` | `intelligence/algorithms/indicators/fetcher.py` |
| `from prompts.{name} import ANALYSIS_PROMPT` | `config/prompts/automobile/{name}.py` |
| `from prompts.orchestrator import ...` | `config/prompts/shared/orchestrator.py` |
| `from prompts.signal_aggregator import ...` | `config/prompts/shared/signal_aggregator.py` |
| `from config import settings` | `config/settings/base.py` (via `config/settings/__init__.py`) |
| `from config import rag_config` | `intelligence/rag/config.py` (via `config/rag_config.py`) |

---

## Key Settings (`config/settings/base.py`)

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
    "valuation_catalyst": 0.10,    # 9th agent added gap-fix 2
}

SCORE_THRESHOLDS = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}

# yfinance tickers used in macro.py
CRUDE_OIL_TICKER = "CL=F"   BRENT_TICKER = "BZ=F"
INR_USD_TICKER   = "INR=X"  STEEL_TICKER = "SLX"
ALUMINIUM_TICKER = "AA"     PLATINUM_TICKER = "PPLT"
PALLADIUM_TICKER = "PALL"   RUBBER_TICKER = "^TOCOM_RUBBER"  # may be unavailable
NIFTY_AUTO_TICKER = "^CNXAUTO"

# Monthly API budget limits (tracked in logs/api_usage.json)
SERPER_MONTHLY_LIMIT = 2500   # env var override
TAVILY_MONTHLY_LIMIT = 1000   # env var override
```

---

## Schemas (`core/schemas/pipeline.py`)

### Input
```python
StockQuery(ticker, company_name, exchange="NSE", analysis_date=today)
```

### Sub-score models
| Class | Fields |
|---|---|
| `SalesDemandSubScores` | fada_siam_dispatch, ev_segment_vahan, dealer_inventory, export_import, used_car_price_index |
| `FundamentalsSubScores` | revenue_ebitda_delta, margin_vs_peers, order_book_pipeline, attrition_headcount, promoter_fii_dii_flow |
| `PatternAnalysisSubScores` | price_cycle_position, seasonal_pattern, rsi_macd_bb, breakout_support_zone, peer_correlation |
| `SentimentSubScores` | news_nlp, management_tone, twitter_reddit_sentiment, youtube_view_spikes, dealer_consumer_feedback |
| `RiskMacroSubScores` | inr_usd_crude_exposure, commodity_prices, rbi_repo_emi_impact, emission_policy_risk, **global_geopolitical_risk** |
| `RawMaterialsSubScores` | steel_aluminium, platinum_palladium, crude_oil_polymer, power_tariff, commodities_trend |
| `PolicyRegulatorySubScores` | fame_ev_subsidy, emission_norms, union_budget_duties, pli_scheme, state_ev_incentives |
| `CompetitiveIntelSubScores` | ev_market_share, new_model_pipeline, jv_acquisitions, adas_safety_ratings, competitive_position |
| `ValuationCatalystSubScores` | pe_discount_vs_history, pe_discount_vs_peers, discount_reason_clarity, catalyst_strength, price_target_confidence |

### Agent output models (all extend `AgentOutput`)
```python
AgentOutput:
  agent, ticker, overall_score (0-1), key_positives[], key_risks[], 
  summary, data_freshness, error, raw_llm_response (excluded from serialisation)

ValuationCatalystOutput extends AgentOutput:
  + fair_value_estimate, current_discount_pct, discount_reason,
    recovery_catalysts[], price_target, recovery_timeline_quarters
```

### Final output
```python
FinalReport:
  ticker, company_name, final_score, verdict  # STRONG BUY|BUY|NEUTRAL|SELL|STRONG SELL
  weighted_agent_scores {agent: WeightedAgentScore(raw, weight, weighted)}
  conflicts_resolved[], conviction_drivers[], top_risks[], investment_thesis, report_date
  # Valuation fields (from valuation_catalyst, gap-fix 3):
  price_target, recovery_timeline_quarters, undervalued_by_pct,
  discount_reason, recovery_catalysts[]
  agent_outputs {agent_name: dict}   # full drill-down
```

---

## 9 Agents — Execution & Data Sources

| Agent | Class file | Prompt file | Context builder method | Primary data |
|---|---|---|---|---|
| sales_demand | `core/sectors/automobile/sales_demand.py` | `config/prompts/automobile/sales_demand.py` | `_build_sales_demand` | Serper news |
| raw_materials | `core/sectors/automobile/raw_materials.py` | `config/prompts/automobile/raw_materials.py` | `_build_raw_materials` | yfinance (SLX, AA, PPLT, PALL, CL=F, BZ=F) + Serper |
| fundamentals | `core/sectors/automobile/fundamentals.py` | `config/prompts/automobile/fundamentals.py` | `_build_fundamentals` | yfinance financials + Serper |
| pattern_analysis | `core/sectors/automobile/pattern_analysis.py` | `config/prompts/automobile/pattern_analysis.py` | `_build_pattern_analysis` | yfinance OHLCV → RSI/MACD/BB/support |
| sentiment | `core/sectors/automobile/sentiment.py` | `config/prompts/automobile/sentiment.py` | `_build_sentiment` | Serper news |
| policy_regulatory | `core/sectors/automobile/policy_regulatory.py` | `config/prompts/automobile/policy_regulatory.py` | `_build_policy_regulatory` | Tavily (full-page) + Serper |
| competitive_intel | `core/sectors/automobile/competitive_intel.py` | `config/prompts/automobile/competitive_intel.py` | `_build_competitive_intel` | Serper news |
| risk_macro | `core/sectors/automobile/risk_macro.py` | `config/prompts/automobile/risk_macro.py` | `_build_risk_macro` | yfinance macro + Serper + macro_cache |
| valuation_catalyst | `core/sectors/automobile/valuation_catalyst.py` | `config/prompts/automobile/valuation_catalyst.py` | `_build_valuation_catalyst` (TBD) | Serper + fundamentals |

---

## Data Flow (per run)

```
main.py → AutomobileAgentOrchestrator.analyse(ticker)
  1. _resolve_ticker()      → LLM → StockQuery(ticker, company_name, exchange)
  2. LangGraph worker pool  → 9 agents run in PARALLEL (Send fan-out, RetryPolicy, merge reducer)
       BaseAgent.run(query)
         _gather_context()
           priority: RAG (if enabled) → ContextBuilder.build() → generic stub
         ContextBuilder.build(agent_name, query)
           → fetchers (yfinance / Serper / Tavily / macro_cache)
           → formatted context string
         _build_prompt(query, context) → (system_prompt, user_prompt)
         _call_llm_with_retry()        → OpenRouter → JSON string
         _parse_output()               → AgentOutput subtype
         log_llm_call()                → logs/agent_calls.jsonl
  3. SignalAggregator.run()
       weighted_scores = agent.overall_score × weight for each agent
       composite = weighted_sum / weight_total
       LLM call → investment_thesis, verdict, conviction_drivers, top_risks
       extract valuation fields from valuation_catalyst output
       → FinalReport
  4. log_run_summary()      → logs/run_summaries.jsonl
  5. log_usage_summary()    → logs/api_usage.json (Serper/Tavily monthly counters)
```

---

## ContextBuilder Routing (`services/data/context/builder.py`)

```python
ContextBuilder.build(agent_name, query, sector="")
```

Lookup order: `_build_{sector}_{agent_name}` → `_build_{agent_name}` → `_build_generic`

| Agent | Fetchers called |
|---|---|
| `_build_sales_demand` | `fetch_news_context(CONTEXT_SEARCH_QUERIES)` |
| `_build_fundamentals` | `get_fundamentals_context(ticker)` + `fetch_news_context()` |
| `_build_pattern_analysis` | `get_technical_context(ticker)` → RSI, MACD, BB, support/resistance |
| `_build_sentiment` | `fetch_news_context(CONTEXT_SEARCH_QUERIES)` |
| `_build_risk_macro` | `get_macro_context()` + macro_cache OR `fetch_news_context()` |
| `_build_raw_materials` | `get_raw_materials_context()` + `fetch_news_context(max_queries=1)` |
| `_build_policy_regulatory` | `fetch_tavily_context()` + `fetch_news_context()` |
| `_build_competitive_intel` | `fetch_news_context(CONTEXT_SEARCH_QUERIES)` |
| `_build_valuation_catalyst` | not yet implemented → falls back to `_build_generic` |

---

## Logs & Observability

| File | Written by | Content |
|---|---|---|
| `logs/agent_calls.jsonl` | `run_logger.log_llm_call()` | per-LLM-call: tokens, cost, score, duration |
| `logs/run_summaries.jsonl` | `run_logger.log_run_summary()` | per-run: verdict, score, agent_scores, errors |
| `logs/api_usage.json` | `api_usage.record_call()` | monthly Serper/Tavily call counter (auto-resets) |
| `logs/analysis_history.jsonl` | `analysis_logger.log_analysis()` | full report archive |

---

## API Usage Tracking (`services/data/stores/api_usage.py`)

```python
record_call("serper")          # called inside search_serper() on success
record_call("tavily")          # called inside search_tavily() on success
get_usage()                    # → {month, serper:{calls,limit,remaining,pct_used}, tavily:{...}}
log_usage_summary()            # INFO log line — called by orchestrator after each run
```

Limits: `SERPER_MONTHLY_LIMIT=2500`, `TAVILY_MONTHLY_LIMIT=1000` (override via env vars).
Stored in: `logs/api_usage.json` — auto-resets when calendar month changes.

---

## Intelligence Layer

### Technical Indicators (`intelligence/algorithms/indicators/fetcher.py`)
```python
get_price_history(ticker, years=10)       → pd.DataFrame (NSE .NS suffix applied)
compute_rsi(close, period=14)             → float
compute_macd(close)                       → {macd, signal, histogram}
compute_bollinger_bands(close, period=20) → {upper, middle, lower, bandwidth, pct_b}
compute_support_resistance(close)         → {support, resistance}
compute_technicals(df)                    → dict of all indicators
get_seasonal_pattern(df)                  → {best_quarter, worst_quarter, current_q_avg}
get_peer_correlation(ticker)              → {correlation, beta, relative_strength}
get_technical_context(ticker)             → formatted str for prompt injection
```

### RAG (`intelligence/rag/`)
- `config.py`: `RAG_ENABLED=false` by default. Set `RAG_ENABLED=true` + fill vector store creds to activate.
- `core/embedder.py`: SentenceTransformer embeddings
- `core/retriever.py`: ChromaDB / Pinecone / Qdrant
- `core/vector_store.py`: Store management
- `ingestion/ingestion.py`: Ingest PDFs, earnings transcripts into vector store

### RL Feedback Loop (`intelligence/rl/`)
- `agents/feedback_agent.py`: Processes outcome signals (stock moved up/down post-report)
- `agents/weight_adapter.py`: Adjusts `AGENT_WEIGHTS` based on historical accuracy
- `stores/prediction_store.py`: Stores predictions for later comparison
- `workflows/daily_review.py`: Daily job — compare predictions vs outcomes, update weights
- `workflows/generate_forecast.py`: Pre-run weight injection into orchestrator

---

## Known Issues / Patterns

1. **Newly-listed stocks** (e.g. ATHERENERGY): yfinance `.NS` returns 404 — fundamentals and pattern_analysis fall back to LLM hallucination. No fix yet; add manual ticker override if needed.
2. **RBI repo rate**: hardcoded static value in `macro.py:get_rbi_repo_rate()` — update manually or wire RBI API.
3. **Sector mismatch**: Orchestrator always runs automobile agents regardless of sector (Suzlon = wind energy but gets automobile prompts). Sector routing not yet implemented.
4. **valuation_catalyst ContextBuilder**: `_build_valuation_catalyst` method missing in `services/data/context/builder.py` — falls back to generic stub (no real data injected).
5. **Token tracking in run_summary**: `log_run_summary()` called with `total_tokens=0` hardcoded — per-agent tokens logged individually in `agent_calls.jsonl` but not summed into the summary.
6. **Rubber ticker** (`^TOCOM_RUBBER`): Not reliably available on yfinance — fails silently and is omitted from context.
