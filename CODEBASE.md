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
│   │   ├── context/               # Context-building helpers + bundle_builder.py
│   │   │                          # (Unified Sector Analyst — one-pass SectorDataBundle)
│   │   └── fetchers/              # Market/news data fetchers
│   └── scheduler/
│       └── python/
│           └── scheduler.py       # APScheduler jobs (RL daily review, forecast, calendar)
├── src/                           # Source packages
│   ├── backend/                   # Python backend agents
│   │   ├── sectors/               # Per-sector agent implementations
│   │   │   ├── registry.py        # Unified ticker→sector map + SectorRegistry class
│   │   │   ├── automobile/        # Automobile agents (9 dimensions)
│   │   │   │   ├── agents/        # Individual agent modules (legacy multi-agent fallback path)
│   │   │   │   ├── pipeline/
│   │   │   │   │   └── orchestrator.py   # AutomobileAgentOrchestrator (legacy 9-agent pool)
│   │   │   │   ├── prompts/       # SYSTEM_PROMPT / ANALYSIS_PROMPT per agent + unified.py (Unified Sector Analyst prompt)
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
│   │       ├── pipeline/          # Core adapter (core_adapter.py), base_orchestrator.py,
│   │       │                      # unified_analyst.py (Unified Sector Analyst — one-call dimension scoring)
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
│   ├── portfolio/                 # Compass Phase A: per-user virtual portfolio (see below)
│   │   ├── store.py               # PortfolioStore — per-user JSON holdings/ledger/digest
│   │   ├── pricing.py             # close_on() — yfinance + NSE cross-check entry pricing
│   │   ├── corp_actions.py        # Corp-action sync (splits/bonuses) into holdings
│   │   ├── promotion.py           # Auto-promotion into managed_tickers.json universe
│   │   ├── advisor.py             # Deterministic HOLD/ADD/TRIM/EXIT verdicts, ATR-scaled stops
│   │   ├── narrator.py            # BULK-tier LLM narration of advice
│   │   ├── digest.py              # EOD portfolio digest builder
│   │   └── pipeline.py            # run_post_review_pipeline() orchestration entry point
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

- `core/portfolio/` — Compass Phase A: per-user virtual portfolio (store, corp-action
  sync, auto-promotion into managed universe, deterministic HOLD/ADD/TRIM/EXIT advisor
  with ATR-scaled stops, BULK-tier narration, EOD digest). Event-triggered from
  scheduler_api._review_task after daily reviews. Spec:
  docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md

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

### Portfolio — Compass Phase A (`/portfolio/*`)

All endpoints take an optional `user_id` query param (default `portfolio.default_user_id`, i.e. `"primary"`); `user_id` is validated against `[A-Za-z0-9_-]{1,64}`. Auth mirrors the scheduler pattern (optional `X-Scheduler-Key`; lockdown deferred while the portfolio is virtual — user decision 2026-07-06).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/portfolio` | optional key | Holdings + watchlist marked to market at latest NSE close (per-holding `last_close`, `pnl_pct`). |
| POST | `/portfolio/holdings` | optional key | Add virtual holding `{symbol, sector, qty, buy_date, price?}` — `price` omitted → real NSE close on `buy_date`. 422 on unsupported sector / bad date / no price. Auto-promotes (origin=held, daily cadence). |
| DELETE | `/portfolio/holdings/{symbol}` | optional key | Remove holding; demotes from managed universe unless watchlisted. 404 if absent. |
| POST | `/portfolio/watchlist` | optional key | Add watchlist symbol `{symbol, sector, reason?}` — promotes with weekly cadence. |
| DELETE | `/portfolio/watchlist/{symbol}` | optional key | Remove watchlist symbol; demotes unless held. |
| POST | `/portfolio/import-csv` | optional key | Raw CSV body `symbol,sector,qty,avg_buy_price,buy_date`; blank price → real close on buy date; per-row errors reported. |
| GET | `/portfolio/advice?limit=<1-500>` | optional key | Advice-ledger tail (append-only JSONL of every verdict). |
| GET | `/portfolio/digest/latest` | optional key | Latest EOD digest (404 until the advisor has run). |
| POST | `/portfolio/run-advisor?review_date=<ISO>` | optional key | Manually trigger the post-review pipeline (corp-action sync → events → advisor → ledger → digest). 202, background. |

The pipeline also runs automatically: `scheduler_api._review_task` event-triggers `core.portfolio.pipeline.run_post_review_pipeline` after every daily-review job completes (never clock-scheduled).

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

## 4. Configuration

Tunable configuration (model tiers, thresholds, RL parameters, crons, feature flags)
lives in repo-root **`config.yaml`**, resolved by
`src/backend/shared/config/settings/loader.py` with precedence
**environment variable > config.yaml > hardcoded fallback in `base.py`**.
Secrets (API keys, webhook URLs) stay in `.env` only. Structural constants
(data-source URLs, ticker symbols, indicator periods, file paths) remain in
`base.py`. All 40+ consumers keep reading `settings.<NAME>` — the YAML layer is
invisible to them. `CONFIG_FILE` env var points at an alternate YAML.

### LLM / OpenRouter (`config.yaml` → `llm.*`)

Models are tiered (2026-06-03 benchmark, `scripts/model_bench.py`; bulk re-benchmarked
2026-07-02). Retired: `qwen3-235b` (broke `json_object`), `qwen-2.5-72b` (2-4× cost of deepseek).

| Name | Default | Description |
|------|---------|-------------|
| `OPENROUTER_API_KEY` | `""` (required) | OpenRouter API key (.env only) |
| `LLM_MODEL_FAST` | `qwen/qwen3.6-flash` | **FAST tier** — the agentic chat tool-loop |
| `LLM_MODEL_REASONING` | `z-ai/glm-5.2` | **REASONING tier** — SignalAggregator verdict, RL FeedbackAgent / ThesisReviewer, and the Unified Sector Analyst for all four sectors (JSON-validated). Switched from qwen3.7-max 2026-07-06 (~45% cheaper, higher AA index, `scripts/reasoning_bench.py` + live analyst runs) |
| `LLM_MODEL_BULK` | `deepseek/deepseek-v4-flash` | **BULK tier** — high-volume `json_object` scoring; $0.09/$0.18 per M, reasoning disabled via `JSON_MODE_EXTRA_BODY` |
| `LLM_MODEL` | `= LLM_MODEL_BULK` | Back-compat catch-all for any call-site not on a named tier |
| `LLM_TEMPERATURE` | `0.2` | LLM sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Max output tokens per LLM call |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call LLM timeout |
| `LLM_INPUT_COST_PER_M` | `0.09` | Cost tracking: USD per 1M input tokens (bulk tier) |
| `LLM_OUTPUT_COST_PER_M` | `0.18` | Cost tracking: USD per 1M output tokens (bulk tier) |

### Data / Search APIs

| Name | Default | Description |
|------|---------|-------------|
| `SERPER_API_KEY` | `""` | Serper (Google search) — since 2026-06-13 a single paid 50k-credit key serves all sectors via `get_serper_key(sector)` (credits are one-time purchases valid 6 months, no monthly reset) |
| `TAVILY_API_KEY` | `""` | Tavily full-page extraction (Policy agent) |
| `NEWSAPI_KEY` | `""` | NewsAPI (optional) |

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
| `MACRO_CACHE_TTL_HOURS` | `4` | Macro cache TTL (hours); cache populated on-miss by bundle_builder/ContextBuilder |

### Unified Sector Analyst (2026-06-12 redesign)

| Name | Default | Description |
|------|---------|-------------|
| `UNIFIED_ANALYST_SECTORS` | `automobile,banking_bfsi,it_sector,renewable_energy` | CSV of sector names on the one-bundle/one-call path (all four by default); `""` disables it everywhere (legacy multi-agent path byte-identical) |
| `UNIFIED_ANALYST_FALLBACK_LEGACY` | `true` | On total Unified Analyst failure, fall back to the legacy multi-agent worker pool |
| `UNIFIED_ANALYST_MAX_TOKENS` | `6000` | Max output tokens for the single Unified Analyst LLM call |
| `UNIFIED_SECTION_MAX_CHARS` | `2500` | Per-section cap in `SectorDataBundle` |
| `UNIFIED_BUNDLE_MAX_CHARS` | `18000` | Total cap on the rendered bundle text passed to the analyst prompt |

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

### Portfolio + Position Advisor — Compass Phase A (`config.yaml` → `portfolio.*` / `advisor.*`)

| Name | Default | Description |
|------|---------|-------------|
| `PORTFOLIO_DATA_DIR` | `data/portfolio` | Per-user roots: `data/portfolio/<user_id>/` (volume-persisted) |
| `PORTFOLIO_DEFAULT_USER_ID` | `primary` | Single-user launch default; per-user layout from day one |
| `PORTFOLIO_MAX_MANAGED_TICKERS` | `40` | Auto-promotion cap — guards LLM spend; oldest watchlist-origin entry rotates out at cap |
| `PORTFOLIO_WEEKLY_REVIEW_WEEKDAY` | `4` | Friday — watchlist-cadence names review this weekday only (held names review daily) |
| `ADVISOR_ENABLED` | `true` | Master switch for the post-review advisor pipeline |
| `ADVISOR_NARRATE` | `true` | BULK-tier LLM narration of verdicts (deterministic fallback text on any failure) |
| `ADVISOR_ATR_PERIOD` / `ADVISOR_STOP_ATR_MULT` | `20` / `3.0` | Stop = clamp(mult × ATR(period)%, bucket floor, bucket cap) |
| `ADVISOR_STOP_BUCKETS` | large `[8,12]` · mid `[12,18]` · small `[15,22]` | Stop floor/cap % per market-cap bucket; `conservative` profile tightens one notch |
| `ADVISOR_LARGE_CAP_FLOOR_CR` / `ADVISOR_MID_CAP_FLOOR_CR` | `65000` / `20000` | ₹ crore mcap thresholds for bucket resolution (unknown → mid) |
| `ADVISOR_TRIM_PROFIT_PCT` | `25.0` | Profit threshold before TRIM rules are considered |
| `ADVISOR_REVERSION_PRIOR_ELEVATED` | `0.20` | Conviction-streak reversion prior considered "elevated" (TRIM trigger) |
| `ADVISOR_CONFIDENCE_DECLINE_THRESHOLD` | `0.05` | Remaining-envelope confidence drop that counts as declining (TRIM trigger) |
| `ADVISOR_ENVELOPE_FLAT_BAND_PCT` | `1.0` | Remaining-forecast drift within ±this% = FLAT (neither ADD nor EXIT signal) |
| `ADVISOR_ADD_MIN_DIRECTION_ACCURACY` | `0.60` | Last-7-reviews hit rate required for ADD |
| `ADVISOR_MAX_POSITION_PCT` | `10.0` | Position weight cap gating ADD |
| `ADVISOR_SECTOR_CONCENTRATION_WARN_PCT` | `30.0` | Weight threshold for the `SECTOR_CONCENTRATION_HIGH` note |
| `ADVISOR_LTCG_WAIT_MIN_MONTHS` | `10` | TRIM at age 10–12 months with intact thesis → `WAIT_FOR_LTCG` note (never softens EXIT) |
| `ADVISOR_EARNINGS_GAP_DAYS` | `3` | Profitable + results within N trading days → `EARNINGS_GAP_PROTECTION` note |

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

### RL Phase 3 — Event-Driven Dossier Ingestion

| Name | Default | Description |
|------|---------|-------------|
| `RL_EVENT_INGEST_ENABLED` | `true` | Weekly NSE-event scan → dossier digestion (Sat 10:00 IST + CLI) |
| `EVENT_INGEST_LOOKBACK_DAYS` | `8` | Scan window |
| `EVENT_INGEST_MAX_EVENTS_PER_SCAN` | `3` | LLM/Tavily call cap per ticker per scan |
| `EVENT_INGEST_TEXT_MAX_CHARS` | `6000` | Per-event text bundle truncation |

### Living Envelope (RL Phase 2.5)

| Name | Default | Description |
|------|---------|-------------|
| `RL_REFORECAST_ENABLED` | `true` | Shock-triggered mid-month re-forecast (`regenerate_envelope`) on/off |
| `RL_REFORECAST_MAX_PER_MONTH` | `2` | Hard cap on re-forecasts per ticker per calendar month |
| `RL_REFORECAST_THESIS_MULT_THRESHOLD` | `0.5` | `thesis_break` trigger fires when `horizon_confidence_multiplier` drops to/below this |
| `RL_REGIME_STICKY_ENABLED` | `true` | Sticky market-wide regime hysteresis on/off |
| `RL_REGIME_CALM_DAYS` | `3` | Consecutive milder detections before exiting a severe sticky regime |
| `RL_PREOPEN_CHECK_ENABLED` | `true` | Pre-open overnight shock check (08:45 IST job + CLI) on/off |
| `RL_PREOPEN_SHOCK_SEVERITY` | `0.7` | Severity threshold above which contradicted tickers trigger a re-forecast |

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
| `services/api/routes/scheduler_api.py` | POST/GET /scheduler/* — RL trigger and status endpoints; event-triggers the portfolio advisor pipeline after daily reviews |
| `services/api/routes/portfolio_api.py` | /portfolio/* — Compass Phase A: holdings, watchlist, CSV import, advice ledger, EOD digest |
| `core/portfolio/pipeline.py` | `run_post_review_pipeline()` — corp-action sync → events refresh → advisor → ledger → digest, per user |
| `core/portfolio/advisor.py` | Deterministic HOLD/ADD/TRIM/EXIT engine (EXIT>TRIM>ADD>HOLD), ATR-scaled stops, LTCG/earnings-gap notes |
| `services/data/fetchers/corporate_events.py` | NSE corp-actions feed + forward board-meetings calendar (degraded-mode safe) |
| `data/portfolio/<user>/` | Per-user volume state: `portfolio.json`, `advice_ledger.jsonl`, `digests/` |
| `services/api/routes/prompts.py` | /ui/prompts/* — live prompt editing and GitHub deploy |
| `services/api/routes/analytics.py` | /analytics/* — RL performance exports and Power BI feed |
| `services/api/log_buffer.py` | In-memory ring buffer for real-time log streaming |
| `services/scheduler/python/scheduler.py` | APScheduler: daily RL review (4:30pm IST), monthly forecast (1st, 9am IST), calendar update (Dec 31), pre-open shock check (`preopen_shock_check`, Mon-Fri 08:45 IST, Living Envelope §27.3) |
| `services/data/stores/score_store.py` | SQLite score history (read/write/delta/range queries) |
| `services/background/macro_news_cache.py` | Daily macro news cache read/write |
| `services/clients/llm_client.py` | Async OpenRouter LLM client |
| `src/backend/sectors/registry.py` | `TICKER_SECTOR` dict + `SectorRegistry` singleton (resolve, get_handler, is_enabled) |
| `src/backend/shared/config/settings/base.py` | All environment variable definitions with defaults |
| `src/backend/shared/config/rag_config.py` | RAG-specific env vars (mirrors `core/intelligence/rag/config.py`) |
| `src/backend/shared/pipeline/base_orchestrator.py` | `BaseSectorOrchestrator` — ticker resolution (managed-ticker short-circuit, no LLM for exact `TICKERS` matches), RL weights, NSE prefetch, `_run_agents`/`_run_unified`/`_unified_enabled` dispatch, SignalAggregator |
| `services/data/context/bundle_builder.py` | `build_sector_bundle()` — one-pass `SectorDataBundle` (10 labeled, char-capped sections), sector-aware via `_SECTOR_BUNDLE_CFG` (per-sector queries, deep-dive Tavily target, commodities applicability, peer lists) |
| `src/backend/shared/pipeline/unified_analyst.py` | `UnifiedAnalyst` — one reasoning-model call → all dimension `AgentOutput`s for a sector (9/6/8/6 per `SECTOR_SPECS`); never raises, falls back to legacy on total failure |
| `src/backend/sectors/automobile/prompts/unified.py` | Unified Sector Analyst prompt for automobile (9 dimensions in one prompt) |
| `src/backend/sectors/banking_bfsi/prompts/unified.py` | Unified Sector Analyst prompt for BFSI (6 dimensions) |
| `src/backend/sectors/it_sector/prompts/unified.py` | Unified Sector Analyst prompt for IT (8 dimensions) |
| `src/backend/sectors/renewable_energy/prompts/unified.py` | Unified Sector Analyst prompt for renewable energy (6 dimensions) |
| `src/backend/sectors/automobile/pipeline/orchestrator.py` | AutomobileAgentOrchestrator — defines the 9 legacy per-dimension agents, used as the multi-agent fallback path when the unified analyst is off or fails |
| `src/backend/sectors/banking_bfsi/pipeline/orchestrator.py` | BankingAgentOrchestrator |
| `src/backend/sectors/it_sector/pipeline/orchestrator.py` | ITAgentOrchestrator |
| `src/backend/sectors/renewable_energy/pipeline/orchestrator.py` | RenewableAgentOrchestrator |
| `core/intelligence/rl/workflows/generate_forecast.py` | Generate 30-day PredictionEnvelope (runs full pipeline); `regenerate_envelope()` re-runs the pipeline mid-cycle for the remaining days only (Living Envelope, RL_DESIGN §27.2) |
| `core/intelligence/rl/workflows/daily_review.py` | Daily RL feedback: compare actual vs predicted, update weights; Step 8.5 dossier curator; post-Step-6 trigger block (external_shock/thesis_break/regime_flip) calls `regenerate_envelope()` and skips Step 7 on success (§27.2) |
| `core/intelligence/rl/workflows/preopen_check.py` | Pre-open overnight shock check (1 Serper + 1 fast LLM, market-wide); contradicted tickers trigger `regenerate_envelope(trigger="preopen_shock")` (§27.3) |
| `core/intelligence/regime/state.py` | Sticky market-wide regime hysteresis (`update_sticky_regime`, `data/predictions/_regime_state.json`) (§27.1) |
| `core/intelligence/rl/stores/prediction_store.py` | JSON R/W for envelopes, feedback logs, weight memory, ledgers, ticker dossier; `archive_envelope()` copies the superseded envelope to `{ticker_dir}/archived_envelopes/{YYYY-MM}_v{n}.json` before a re-forecast overwrite (§27.2) |
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
| `core/intelligence/rl/agents/event_ingestor.py` | Event ingestion: NSE filings → dossier guidance/business (weekly + CLI `ingest-events`) |
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
