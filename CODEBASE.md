# CODEBASE.md

Developer quick-reference for the StockAgent codebase. All entries verified against source files.

---

## 1. Module Map

```
StockAgent-main/
├── main.py                        # CLI entry point (wraps services/api/server.py)
├── services/                      # Runtime services layer
│   ├── api/                       # FastAPI application
│   │   ├── server.py              # App factory, lifespan, route mounting
│   │   ├── log_buffer.py          # In-memory ring buffer for /ui/logs
│   │   ├── user_profile.py        # User tier profile helpers (dormant — see CHAT_ARCHITECTURE.md)
│   │   └── routes/                # All API route files (see Section 2)
│   │                              # NB: the agentic chat loop lives in routes/ui_data.py
│   │                              #     (the old chat_graph.py LangGraph DAG was removed 2026-06-03)
│   ├── background/                # Background jobs
│   │   ├── macro_news_cache.py    # Daily macro news cache reader/writer
│   │   └── macro_news_fetcher.py  # Serper/Tavily-based macro news fetcher
│   ├── clients/                   # Shared HTTP/API clients
│   │   ├── llm_client.py          # OpenRouter LLM wrapper (AsyncOpenAI)
│   │   ├── tavily_fetcher.py      # Tavily full-page extraction client
│   │   └── alerting.py            # Alert dispatch (console/file/webhook)
│   ├── data/                      # Data persistence
│   │   ├── stores/                # Data store implementations
│   │   ├── cache/                 # Data caching utilities
│   │   ├── context/               # Context-building helpers
│   │   └── fetchers/              # Market/news data fetchers
│   └── scheduler/
│       └── python/
│           └── scheduler.py       # APScheduler jobs (RL daily review, forecast, calendar)
├── src/                           # Source packages
│   ├── backend/                   # Python backend agents
│   │   ├── sectors/               # Per-sector agent implementations
│   │   │   ├── registry.py        # Unified ticker→sector map + SectorRegistry class
│   │   │   ├── automobile/        # Automobile agents (9 agents)
│   │   │   │   ├── agents/        # Individual agent modules
│   │   │   │   ├── pipeline/
│   │   │   │   │   └── orchestrator.py   # AutomobileAgentOrchestrator
│   │   │   │   ├── prompts/       # SYSTEM_PROMPT / ANALYSIS_PROMPT per agent
│   │   │   │   ├── config/settings.py    # Automobile-specific config
│   │   │   │   └── schemas/
│   │   │   ├── banking_bfsi/      # Banking/BFSI agents (6 agents)
│   │   │   │   └── pipeline/orchestrator.py  # BankingAgentOrchestrator
│   │   │   ├── it_sector/         # IT sector agents (8 agents)
│   │   │   │   └── pipeline/orchestrator.py  # ITAgentOrchestrator
│   │   │   └── renewable_energy/  # Renewable energy agents (6 agents)
│   │   │       └── pipeline/orchestrator.py  # RenewableAgentOrchestrator
│   │   ├── intelligence/          # Backend intelligence modules
│   │   │   ├── chat/              # Agentic chat backend
│   │   │   ├── rag/               # RAG pipeline (backend path)
│   │   │   ├── rl/                # RL feedback (backend path)
│   │   │   └── technical/         # Technical indicator helpers
│   │   ├── api/
│   │   │   └── routes/            # Backend-specific route helpers
│   │   └── shared/                # Shared utilities across sectors
│   │       ├── agents/            # Base agent classes
│   │       ├── clients/           # Shared API clients
│   │       ├── config/
│   │       │   ├── settings/base.py   # Master settings file (all env vars)
│   │       │   └── rag_config.py      # RAG-specific settings
│   │       ├── data/              # Data helpers
│   │       ├── pipeline/          # Core adapter (core_adapter.py)
│   │       ├── prompts/           # Shared prompt templates
│   │       └── schemas/
│   │           └── feedback.py    # Feedback/RL schemas (src path)
│   ├── frontend/
│   │   ├── web/                   # TypeScript/React dashboard (Vite)
│   │   │   └── src/               # App.tsx, components/, features/, hooks/, pages/
│   │   └── prototypes/            # Served as static files at /app by FastAPI
│   └── prototypes/                # Legacy prototype UIs
├── core/                          # Core intelligence layer (shared across sectors)
│   ├── config/                    # Core-level config re-export
│   ├── graphs/                    # LangGraph definitions
│   ├── intelligence/
│   │   ├── rl/                    # Reinforcement learning feedback loop
│   │   │   ├── agents/            # FeedbackAgent, WeightAdapter, ThesisReviewer, DossierCurator
│   │   │   ├── algorithms/        # price_interpolator.py, lesson_emphasis.py (executable claims)
│   │   │   ├── conviction/        # tracker.py (conviction streak)
│   │   │   ├── eval/              # Read-only evaluation harness (metrics, synthetic, run_eval CLI)
│   │   │   ├── stores/            # prediction_store.py, ledger_propagator.py (archival + resurrection)
│   │   │   ├── workflows/         # generate_forecast.py, daily_review.py (Step 8.5 = dossier curator)
│   │   │   ├── nse_calendar.py    # NSE trading day calendar
│   │   │   └── calendar_updater.py
│   │   ├── regime/                # Market regime detection
│   │   │   └── detector.py
│   │   ├── rag/                   # RAG pipeline (core path)
│   │   ├── seasonal/              # Seasonal pattern calendar + validator
│   │   ├── fno/                   # F&O data helpers
│   │   └── prompt_enhancer/
│   │       └── enhancer.py        # Prompt enhancement with RL lessons
│   ├── pipeline/                  # Core pipeline abstractions
│   │   ├── base_agent.py
│   │   ├── orchestrator.py
│   │   └── signal_aggregator.py
│   ├── schemas/
│   │   ├── feedback.py            # Canonical feedback/RL schemas
│   │   └── pipeline.py
│   └── sectors/                   # Core-layer sector definitions
├── scripts/
│   ├── api_exploration/           # Ad-hoc API exploration scripts
│   └── model_bench.py             # Chat-tier model comparison harness (fabrication/latency/cost)
├── tests/                         # Test suite
│   ├── api/                       # API-level tests
│   ├── contract/                  # Contract tests (C# integration)
│   ├── fixtures/                  # Shared test fixtures
│   ├── integration/               # Integration tests
│   └── unit/                      # Unit tests
├── config/
│   └── sector_toggles.json        # Enable/disable sectors at runtime
├── data/                          # Runtime data (SQLite, prediction JSONs, caches)
├── logs/                          # Log files
├── outputs/                       # Report output files
├── docs/                          # Design documentation
├── services/csharp/
│   └── StockAgent.Scheduler/      # C# scheduler service (.NET)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

---

## 2. API Endpoints

All endpoints are served on port 8001. No global auth middleware — auth is per-endpoint where required.

### Analysis

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/analyse` | None | Run full multi-sector 9-agent pipeline for a ticker. Auto-detects sector; accepts `ticker`, `sector` (optional override), `output_format`. Returns `FinalReport` as JSON. |
| WS | `/ws/stream?ticker=<sym>` | None | WebSocket stream. Emits `agent_progress` events per agent, then a final `complete` event with the full report. |

### History

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/history/{ticker}?limit=30` | None | Score history from SQLite, newest first. `limit` range 1–365. |
| GET | `/history/{ticker}/latest` | None | Most recent score record; 404 if none. |

### UI Data (`/ui/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ui/bootstrap` | None | All UI data in one call: agents, tickers, market summary, trending, categories, watchlist. |
| GET | `/ui/agents?sector=automobile` | None | Agent definitions + current weights for a sector. |
| PUT | `/ui/agents/weights?sector=automobile` | None | Persist user-adjusted agent weights. Weights 0.00–0.30, sum must be 0.95–1.05. |
| GET | `/ui/agents/tasks` | None | Get persisted agent task enabled/disabled flags. |
| PUT | `/ui/agents/tasks` | None | Persist task toggle state to `data/agent_tasks.json`. |
| GET | `/ui/tickers` | None | All tickers with latest score + live yfinance price. |
| GET | `/ui/trending` | None | Tickers ranked by score delta between last two analysis runs. |
| GET | `/ui/market/summary` | None | Market pulse, driver cards, sector index changes, Nifty Auto sparkline. |
| GET | `/ui/nifty-ranges?range=1M` | None | Nifty Auto sparkline for a time range: `1W`, `1M`, `3M`, `6M`, `1Y`. |
| GET | `/ui/watchlist` | None | User watchlist with live prices. |
| PUT | `/ui/watchlist` | None | Persist watchlist to `data/watchlist.json`. |
| GET | `/ui/search?q=<term>` | None | Ticker + thesis text search (falls back to yfinance lookup). |
| GET | `/ui/categories` | None | Categories (EV, mass-market, etc.) with ticker lists. |
| PUT | `/ui/categories/{key}/tickers` | None | Add/remove tickers from a category (body: `{add: [], remove: []}`). |
| GET | `/ui/learnings` | None | RL-derived lesson cards and portfolio learning summary. |
| POST | `/ui/chat/stream` | None | **Primary chat** — agentic streaming tool-loop (SSE). Deterministic intent pre-router pre-fetches screen+news for buy/sell/momentum queries; FAST-tier model. Events: `intent`, `tool_result`, `token`, `done`. |
| POST | `/ui/chat` | None | Non-streaming twin of the chat loop (blocking JSON reply). Used as the frontend fallback. |

### Prompt Management (`/ui/prompts/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ui/prompts/catalogue` | None | List all sectors and their agent names. |
| GET | `/ui/prompts/status` | None | Pending deploy count, next midnight IST deploy time, last deploy result. |
| GET | `/ui/prompts/pending` | None | Files modified since last deploy. |
| GET | `/ui/prompts/{sector}/{agent}` | None | Read `SYSTEM_PROMPT`, `ANALYSIS_PROMPT`, `CONTEXT_SEARCH_QUERIES` for an agent. |
| PUT | `/ui/prompts/{sector}/{agent}` | None | Write prompt to disk and patch live module in-memory. Marks file as pending deploy. |
| POST | `/ui/prompts/deploy` | None | Emergency manual deploy: push pending files to GitHub immediately (requires `GITHUB_TOKEN`/`GITHUB_REPO`). |

### Scheduler (`/scheduler/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/scheduler/forecast?ticker=<sym>` | `X-Scheduler-Key` header | Generate 30-day prediction envelopes (full 9-agent pipeline). Returns 202, runs in background. |
| POST | `/scheduler/daily-review?ticker=<sym>&review_date=<ISO>` | `X-Scheduler-Key` header | Run RL daily feedback loop for one date. Returns 202, runs in background. |
| POST | `/scheduler/backfill?ticker=<sym>` | `X-Scheduler-Key` header | Backfill all past trading days this month. Returns 202, runs in background. |
| GET | `/scheduler/status` | `X-Scheduler-Key` header | Full RL state for all configured tickers: envelope, feedback log, weight memory. |

### Analytics (`/analytics/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/analytics/rl-export?format=json\|csv` | None | Full RL performance rows: one row per reviewed trading day per ticker. |
| GET | `/analytics/agent-accuracy` | None | Per-agent direction hit rate and avg price error, aggregated across tickers. |
| GET | `/analytics/weight-drift` | None | Agent weight history time-series (WeightMemory snapshots) per ticker. |
| GET | `/analytics/miss-breakdown` | None | Miss type counts per ticker and aggregated; includes chart colors. |
| GET | `/analytics/conviction-outcomes` | None | Conviction streak bucketed accuracy + scatter points. |
| GET | `/analytics/sector-comparison` | None | Cross-sector verdict distribution, avg score, best/worst ticker per sector. |
| GET | `/analytics/powerbi-feed` | None | OData v4 JSON feed for Power BI Web connector. |
| GET | `/analytics/powerbi-feed/$metadata` | None | EDMX XML schema for Power BI OData connector. |

### Meta / Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Returns `{status: "ok", service, timestamp}`. |
| GET | `/tickers` | None | Returns the `SCHEDULER_TICKERS` list from settings. |
| GET | `/docs` | None | Swagger UI (FastAPI auto-generated). |
| GET | `/redoc` | None | ReDoc (FastAPI auto-generated). |
| GET | `/` | None | Redirects to `/app/index.html`. |

**Scheduler auth note:** `SCHEDULER_KEY` is read from env. If not set, requests are allowed but a warning is logged.

---

## 3. Sector Registry

Source: `src/backend/sectors/registry.py`. Toggle state loaded from `config/sector_toggles.json`.

### Enabled sectors (tier=backend)

| Ticker | Sector |
|--------|--------|
| MARUTI, TATAMOTORS, M&M, HEROMOTOCO, BAJAJ-AUTO, EICHERMOT, TVSMOTORS, ASHOKLEY, ESCORTS, APOLLOTYRE, MRF, BALKRISIND, MOTHERSON, BOSCHLTD, SUNDRMFAST, ENDURANCE | automobile |
| HDFCBANK, ICICIBANK, SBIN, KOTAKBANK, AXISBANK, INDUSINDBK, BANKBARODA, PNB, CANARABANK, FEDERALBNK, IDFCFIRSTB, BANDHANBNK, RBLBANK, YESBANK, HDFCAMC, BAJAJFINSV, BAJFINANCE, MUTHOOTFIN, CHOLAFIN, MANAPPURAM | banking_bfsi |
| TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, COFORGE, MPHASIS, PERSISTENT, LTTS, KPITTECH, TATAELXSI, NIIT, MASTEK, HEXAWARE, HAPPSTMNDS | it_sector |
| ADANIGREEN, TATAPOWER, TORNTPOWER, CESC, SJVN, NHPC, NTPC, POWERGRID, ADANIPOWER, JSWENERGY, INOXGREEN, INOXWIND, WAAREEENER, SUZLON, PREMIERENE, RPOWER | renewable_energy |

### Disabled sectors (mapped but degrade to automobile)

| Sector | Example Tickers |
|--------|----------------|
| pharma | SUNPHARMA, DRREDDY, CIPLA, DIVISLAB, LUPIN, MANKIND, BIOCON, ZYDUSLIFE |
| fmcg | HINDUNILVR, ITC, NESTLEIND, BRITANNIA, DABUR, MARICO, TATACONSUM |
| metals | TATASTEEL, JSWSTEEL, HINDALCO, SAIL, VEDL, COALINDIA |
| oilgas | RELIANCE, ONGC, BPCL, IOC, GAIL, HINDPETRO |
| capgoods | LT, ABB, SIEMENS, BEL, HAL, BHEL, THERMAX |
| chemicals | PIDILITIND, DEEPAKNITRI, FINEORG, NAVINFLUOR |
| defence | COCHINSHIP, GRSE, MTAR, IDEAFORGE |
| infra | ULTRACEMCO, SHREECEM, DLF, LODHA |
| insurance | SBILIFE, HDFCLIFE, ICICIGI, STARHEALTH |
| logistics | DELHIVERY, BLUEDART, CONCOR |
| media | ZEEL, SUNTV, PVR, NAZARA |
| realestate | GODREJPROP, PRESTIGE, OBEROIRLTY |
| retail | DMART, TRENT, NYKAA, ZOMATO |
| agrochem | UPL, PIIND, COROMANDEL |
| hospitality | INDHOTEL, EIHOTEL, LEMONTREE |
| tech | DIXON, AMBER, KAYNES |
| telecom | BHARTIARTL, IDEA, INDUSTOWER, RAILTEL |

---

## 4. Environment Variables

### LLM / OpenRouter (`src/backend/shared/config/settings/base.py`)

Models are tiered (chosen from the 2026-06-03 benchmark, `scripts/model_bench.py`). `qwen3-235b` is
retired — it broke `json_object` output and was a weak function-caller.

| Name | Default | Description |
|------|---------|-------------|
| `OPENROUTER_API_KEY` | `""` (required) | OpenRouter API key |
| `LLM_MODEL_FAST` | `qwen/qwen3.6-flash` | **FAST tier** — the agentic chat tool-loop |
| `LLM_MODEL_REASONING` | `qwen/qwen3.7-max` | **REASONING tier** — SignalAggregator verdict, RL FeedbackAgent / ThesisReviewer (JSON-validated) |
| `LLM_MODEL_BULK` | `qwen/qwen-2.5-72b-instruct` | **BULK tier** — the 9 sector agents (proven `json_object` model) |
| `LLM_MODEL` | `= LLM_MODEL_BULK` | Back-compat catch-all for any call-site not on a named tier |
| `LLM_TEMPERATURE` | `0.2` | LLM sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Max output tokens per LLM call |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call LLM timeout |
| `LLM_INPUT_COST_PER_M` | `0.065` | Cost tracking: USD per 1M input tokens |
| `LLM_OUTPUT_COST_PER_M` | `0.26` | Cost tracking: USD per 1M output tokens |

### Data / Search APIs

| Name | Default | Description |
|------|---------|-------------|
| `SERPER_API_KEY` | `""` | Serper (Google search) — used by automobile + renewable sectors |
| `SERPER_API_KEY_2` | `""` | Serper — used by banking_bfsi + it_sector |
| `TAVILY_API_KEY` | `""` | Tavily full-page extraction (Policy agent) |
| `ALPHA_VANTAGE_API_KEY` | `""` | Alpha Vantage (optional financials) |
| `NEWSAPI_KEY` | `""` | NewsAPI (optional) |
| `FINNHUB_API_KEY` | `""` | Finnhub news/financials |
| `TWITTER_BEARER_TOKEN` | `""` | Twitter/X bearer token (optional sentiment) |

### Agent Execution

| Name | Default | Description |
|------|---------|-------------|
| `AGENT_TIMEOUT_SECONDS` | `120` | Per-agent execution timeout |
| `MAX_RETRIES` | `3` | LLM/API retry count |
| `RETRY_DELAY_SECONDS` | `2.0` | Delay between retries |

### Logging / Output

| Name | Default | Description |
|------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOG_FILE` | `logs/automobile_agent.log` | Log file path |
| `OUTPUT_DIR` | `outputs` | Report output directory |
| `REPORT_FORMAT` | `json` | Output format: `json` or `markdown` |

### Data Fetching Tuning

| Name | Default | Description |
|------|---------|-------------|
| `NEWS_ARTICLES_PER_QUERY` | `5` | Number of news articles per Serper/NewsAPI query |
| `SERPER_MAX_QUERIES` | `3` | Max Serper queries per agent run |
| `FINANCIALS_LOOKBACK_QUARTERS` | `4` | Historical quarters to fetch |
| `MICRO_CYCLES_PER_DAY` | `6` | Macro news background fetch cycles/day (every 4h) |
| `MICRO_QUERIES_PER_RUN` | `2` | Serper queries per macro news background run |
| `MACRO_CACHE_TTL_HOURS` | `4` (derived) | Macro cache TTL = 24 / MICRO_CYCLES_PER_DAY |

### Scheduler

| Name | Default | Description |
|------|---------|-------------|
| `SCHEDULER_ENABLED` | `false` | Master toggle for periodic scheduled runs |
| `SCHEDULER_CRON` | `30 8 * * 1-5` | Cron for scheduled analysis runs (8:30am IST weekdays) |
| `SCHEDULER_TICKERS` | `MARUTI,TATAMOTORS,M&M,HEROMOTOCO,BAJAJ-AUTO` | Tickers processed by scheduler |
| `SCORE_DB_PATH` | `data/scores.db` | SQLite database path |
| `SCHEDULER_KEY` | `""` | API key for scheduler endpoints (header `X-Scheduler-Key`) |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Cron for daily RL feedback review (4:30pm IST weekdays) |
| `AUTO_TICKERS` | `MARUTI,...,ASHOKLEY` | Automobile sector ticker list override |

### Alerts

| Name | Default | Description |
|------|---------|-------------|
| `ALERT_SCORE_CHANGE_THRESHOLD` | `0.10` | Minimum score delta to trigger alert |
| `ALERT_ON_VERDICT_CHANGE` | `true` | Fire alert on verdict change (BUY→NEUTRAL etc.) |
| `ALERT_CHANNELS` | `console,file` | Notification channels |
| `ALERT_WEBHOOK_URL` | `""` | Slack/Discord/custom webhook URL |
| `ALERT_LOG_FILE` | `outputs/alerts.log` | Alert log file path |
| `SCORE_HISTORY_MAX_ROWS` | `90` | Score history rows retained per ticker |

### RL / Feedback Loop

| Name | Default | Description |
|------|---------|-------------|
| `PREDICTION_DATA_DIR` | `data/predictions` | Root directory for prediction JSON files |
| `RL_SCHEDULER_MAX_WORKERS` | `1` | Concurrent ticker reviews (keep at 1 without file locking) |
| `RL_WEIGHT_DRIFT_ESCAPE_DAYS` | `14` | Consecutive correct days to unlock drift ceiling |
| `RL_WEIGHT_DRIFT_ESCAPE_MULTIPLIER` | `1.5` | Drift ceiling multiplier when escape active |
| `RL_CALIBRATION_REWARD_ENABLED` | `true` | Per-agent calibration reward (agent scored on its own lean, not just ensemble) |
| `RL_CALIBRATION_WEIGHT` | `0.5` | Blend of own-calibration vs ensemble-direction in agent hit-rate |
| `RL_FORGETTING_ENABLED` | `true` | Recency-weighted miss ranking + weighted feedback aggregation |
| `MISS_RECENCY_HALFLIFE_DAYS` | `21` | Miss-event recency decay half-life |
| `MISS_PENALIZABLE_DISCOUNT` | `0.3` | Weight of non-penalizable (external_shock) misses in ranking |
| `ARCHIVE_CONF_FLOOR` / `ARCHIVE_EFFECTIVENESS_FLOOR` / `ARCHIVE_STALE_DAYS` | `0.12` / `0.25` / `60` | Dead-lesson archival criteria (weekly, with resurrection) |
| `FEEDBACK_HALFLIFE_MONTHS` | `3` | Recency half-life for cross-cycle feedback aggregation |

### RL Knowledge Layer (Ticker Dossier + Executable Claims)

| Name | Default | Description |
|------|---------|-------------|
| `RL_DOSSIER_ENABLED` | `true` | Daily dossier curator (Step 8.5) + agent prompt digest injection |
| `DOSSIER_MAX_OBSERVATIONS` | `30` | Episodic observation buffer cap per dossier |
| `DOSSIER_DIGEST_MAX_CHARS` | `2500` | Full digest budget (chat tool, curator input) |
| `DOSSIER_AGENT_DIGEST_CHARS` | `1500` | Digest budget inside agent system prompts |
| `DOSSIER_MAX_NEW_OBS_PER_DAY` | `3` | Max curator observations merged per day |
| `DOSSIER_DISTILL_INPUT_MAX_CHARS` | `20000` | Weekly distillation LLM input bound |
| `RL_CLAIMS_ENABLED` | `true` | Executable claims: tagged lessons fire on matching event days |
| `RL_LESSON_EMPHASIS_DELTA` | `0.03` | Per-lesson agent-score nudge when a claim fires |
| `RL_LESSON_EMPHASIS_CAP` | `0.06` | Per-agent total emphasis cap per day |
| `RL_LESSON_MATCH_MIN_CONF` | `0.45` | Min effective confidence for a claim to fire |

### RL Phase 1 — Monthly Scorecard + Baseline Duel

| Name | Default | Description |
|------|---------|-------------|
| `RL_CONTROL_LANE_ENABLED` | `true` | Daily control-lane prediction + scoring (daily review Step 10) |
| `CONTROL_LANE_MODEL` | `""` | Control model; empty → `LLM_MODEL_REASONING` |
| `SCORECARD_ENABLED` | `true` | Monthly scorecard scheduler job (1st, 02:00 IST) |
| `SCORECARD_DIR` | `data/eval/scorecards` | Persisted monthly scorecard time series |

### Macro News Feed

| Name | Default | Description |
|------|---------|-------------|
| `MACRO_NEWS_ENABLED` | `true` | Enable macro news APScheduler jobs |
| `MACRO_NEWS_RETAIN_DAYS` | `90` | Days to keep daily feed JSON files |
| `MACRO_NEWS_CONTEXT_MAX_ITEMS` | `3` | Max HIGH-severity items injected into chat context |
| `MACRO_NEWS_REVIEWER_MAX_ITEMS` | `5` | Max HIGH-severity items passed to reviewer |

### C# Scheduler Integration

| Name | Default | Description |
|------|---------|-------------|
| `CSHARP_SCHEDULER_ENABLED` | `false` | Route score saves through C# API |
| `CSHARP_API_URL` | `http://localhost:5000` | C# scheduler service base URL |

### Prompt Deploy (GitHub)

| Name | Default | Description |
|------|---------|-------------|
| `GITHUB_TOKEN` | `""` | PAT with repo write scope (for prompt deploy) |
| `GITHUB_REPO` | `""` | Repo in `owner/repo` format |
| `GITHUB_BRANCH` | `main` | Branch to push prompt changes to |

### RAG (`core/intelligence/rag/config.py`)

| Name | Default | Description |
|------|---------|-------------|
| `RAG_ENABLED` | `false` | Enable RAG retrieval |
| `EMBEDDING_PROVIDER` | `groq` | Embedding provider |
| `EMBEDDING_MODEL` | `nomic-embed-text-v1.5` | Embedding model name |
| `EMBEDDING_DIMENSION` | `768` | Embedding vector size |
| `VECTOR_STORE_PROVIDER` | `chromadb` | Vector store: `chromadb`, `pinecone`, or `qdrant` |
| `CHROMA_PERSIST_DIR` | `data/chroma_db` | ChromaDB persistence directory |
| `CHROMA_COLLECTION_NAME` | `automobile_agent_kb` | ChromaDB collection name |
| `PINECONE_API_KEY` | `""` | Pinecone API key (if using Pinecone) |
| `PINECONE_ENVIRONMENT` | `""` | Pinecone environment |
| `PINECONE_INDEX_NAME` | `automobile-agent` | Pinecone index name |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant URL |
| `QDRANT_COLLECTION` | `automobile_agent` | Qdrant collection name |
| `RAG_TOP_K` | `5` | Top-K results to retrieve |
| `RAG_SIMILARITY_THRESHOLD` | `0.75` | Minimum similarity score |
| `RAG_CHUNK_SIZE` | `512` | Tokens per chunk |
| `RAG_CHUNK_OVERLAP` | `64` | Token overlap between chunks |
| `RERANKER_ENABLED` | `false` | Enable cross-encoder reranker |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |

---

## 5. Key File Locations

All paths verified to exist. Paths are relative to project root.

| File | Purpose |
|------|---------|
| `services/api/server.py` | FastAPI app factory, lifespan hooks, route mounting, startup RL self-heal |
| `services/api/routes/analyse.py` | POST /analyse — full pipeline entry point |
| `services/api/routes/stream.py` | WebSocket /ws/stream — real-time agent progress |
| `services/api/routes/history.py` | GET /history — score history from SQLite |
| `services/api/routes/ui_data.py` | All /ui/* routes (bootstrap, agents, tickers, chat, learnings, etc.) |
| `services/api/routes/scheduler_api.py` | POST/GET /scheduler/* — RL trigger and status endpoints |
| `services/api/routes/prompts.py` | /ui/prompts/* — live prompt editing and GitHub deploy |
| `services/api/routes/analytics.py` | /analytics/* — RL performance exports and Power BI feed |
| `services/api/log_buffer.py` | In-memory ring buffer for real-time log streaming |
| `services/scheduler/python/scheduler.py` | APScheduler: daily RL review (4:30pm IST), monthly forecast (1st, 9am IST), calendar update (Dec 31) |
| `services/data/stores/score_store.py` | SQLite score history (read/write/delta/range queries) |
| `services/background/macro_news_cache.py` | Daily macro news cache read/write |
| `services/clients/llm_client.py` | Async OpenRouter LLM client |
| `src/backend/sectors/registry.py` | `TICKER_SECTOR` dict + `SectorRegistry` singleton (resolve, get_handler, is_enabled) |
| `src/backend/shared/config/settings/base.py` | All environment variable definitions with defaults |
| `src/backend/shared/config/rag_config.py` | RAG-specific env vars (mirrors `core/intelligence/rag/config.py`) |
| `src/backend/sectors/automobile/pipeline/orchestrator.py` | AutomobileAgentOrchestrator (9 agents, async concurrent) |
| `src/backend/sectors/banking_bfsi/pipeline/orchestrator.py` | BankingAgentOrchestrator |
| `src/backend/sectors/it_sector/pipeline/orchestrator.py` | ITAgentOrchestrator |
| `src/backend/sectors/renewable_energy/pipeline/orchestrator.py` | RenewableAgentOrchestrator |
| `core/intelligence/rl/workflows/generate_forecast.py` | Generate 30-day PredictionEnvelope (runs full pipeline) |
| `core/intelligence/rl/workflows/daily_review.py` | Daily RL feedback: compare actual vs predicted, update weights; Step 8.5 dossier curator |
| `core/intelligence/rl/stores/prediction_store.py` | JSON R/W for envelopes, feedback logs, weight memory, ledgers, ticker dossier |
| `core/intelligence/rl/stores/ledger_propagator.py` | Propagate lessons to sector/market ledgers; stale-lesson archival + resurrection |
| `core/intelligence/rl/agents/feedback_agent.py` | LLM-based miss classification and lesson generation (lessons carry trigger_tags) |
| `core/intelligence/rl/agents/weight_adapter.py` | Agent weight adjustment with per-agent calibration reward (RL_CALIBRATION_REWARD_ENABLED) |
| `core/intelligence/rl/agents/thesis_reviewer.py` | Conditional thesis review on significant miss (Section 21) |
| `core/intelligence/rl/agents/dossier_curator.py` | Daily dossier curator (Step 8.5, runs hits AND misses) + weekly distillation |
| `core/intelligence/rl/algorithms/price_interpolator.py` | Price interpolation for RL feedback (recency-weighted median when RL_FORGETTING_ENABLED) |
| `core/intelligence/rl/algorithms/lesson_emphasis.py` | Executable claims: tagged lessons nudge agent scores on matching event days |
| `core/intelligence/rl/eval/` | Read-only eval harness: `python -m core.intelligence.rl.eval.run_eval [--synthetic] [--ablate ...]` |
| `core/intelligence/rl/eval/baselines.py` | Naive baselines (persistence, always-up/down) for the monthly duel |
| `core/intelligence/rl/eval/scorecard.py` | Monthly scorecard builder: agent vs control vs baselines + MoM deltas; CLI `run_schedule scorecard` |
| `core/intelligence/rl/agents/control_lane.py` | Bare-LLM control lane (daily review Step 10): same info, no architecture |
| `src/backend/shared/schemas/dossier.py` | TickerDossier schema + budgeted markdown digest (`to_digest`) |
| `src/backend/shared/schemas/scorecard.py` | ControlPrediction/ControlLog + MonthlyScorecard schemas |
| `core/intelligence/rl/conviction/tracker.py` | Conviction streak tracking |
| `core/intelligence/rl/nse_calendar.py` | NSE trading day calendar (holiday-aware) |
| `core/intelligence/regime/detector.py` | Market regime detection (VIX/FII/RSI-based) |
| `core/intelligence/prompt_enhancer/enhancer.py` | Injects RL lessons and regime context into agent prompts |
| `core/intelligence/seasonal/calendar.py` | Seasonal pattern calendar |
| `core/schemas/feedback.py` | Canonical RL schemas: FeedbackEntry, WeightMemory, PredictionEnvelope, LearningLedger |
| `config/sector_toggles.json` | Runtime sector enable/disable toggles |
| `data/scores.db` | SQLite: score history per ticker (created at runtime) |
| `data/predictions/` | RL prediction JSON files: `{sector}/{ticker}/{cycle_id}/` |
| `data/macro_news/` | Daily macro news feed JSON files: `{YYYY-MM-DD}_macro_feed.json` |
| `data/agent_weights.json` | Persisted user weight overrides (created at runtime) |
| `data/watchlist.json` | User watchlist (created at runtime) |
| `data/nse_holidays.json` | NSE holiday calendar (fetched on first deploy) |
| `src/frontend/web/` | TypeScript/React dashboard (Vite; `npm run dev` for local) |
| `services/csharp/StockAgent.Scheduler/` | C# .NET scheduler service |
