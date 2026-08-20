# CODEBASE.md

Developer quick-reference for the StockAgent codebase. All entries verified against source files.
Last full verification: **2026-07-18** (post audit Waves A–H — the Wave E deletion pass removed
~570 dead files, so trees you may remember from older commits are intentionally absent).
For the system-level map (the three loops, all 16 scheduled jobs, data layout), start with
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Module Map

```
StockAgent-main/
├── main.py                        # CLI entry point (wraps services/api/server.py)
├── services/                      # Runtime services layer
│   ├── api/                       # FastAPI application
│   │   ├── server.py              # App factory, lifespan, route mounting, RL self-heal
│   │   ├── auth.py                # M0 identity: get_current_user / require_owner (bearer session,
│   │   │                          #  owner-passthrough when AUTH_REQUIRED=false) + check_scheduler_key
│   │   │                          #  machine gate; Atlas C8 binds the request user to LLM-cost
│   │   │                          #  telemetry (_attribute_telemetry → log_store.current_user_id)
│   │   ├── log_buffer.py          # In-memory ring buffer for /ui/logs
│   │   └── routes/                # All API route files (see Section 2)
│   │                              # NB: the agentic chat loop lives in routes/ui_data.py
│   │                              #     (the old chat_graph.py LangGraph DAG was removed 2026-06-03)
│   │                              # rl_monitor.py — real /ui/rl/* adapters over PredictionStore
│   ├── background/                # Background jobs
│   │   ├── macro_news_cache.py    # Daily macro news cache reader/writer
│   │   └── macro_news_fetcher.py  # Serper/Tavily-based macro news fetcher
│   ├── clients/                   # Shared HTTP/API clients
│   │   ├── llm_client.py          # OpenRouter LLM wrapper (single factory; per-call telemetry,
│   │   │                          #  JSON_MODE_EXTRA_BODY, retry/deadline helpers)
│   │   └── tavily_fetcher.py      # Tavily full-page extraction client
│   ├── data/                      # Data persistence
│   │   ├── backup.py              # Nightly volume backup: zip + 7-copy rotation + email off-site
│   │   ├── verdict_store.py       # Atlas C2 — VerdictStore facade (the ONLY user-plane importer
│   │   │                          #  of the intelligence plane; delegates PredictionStore reads +
│   │   │                          #  publishes ticker_verdicts projections — plane boundary, R1)
│   │   ├── stores/                # eod_store.py (per-day parquet EOD cache) · telemetry stores
│   │   │                          #  (run_logger, api_usage, analysis_logger, score_store,
│   │   │                          #   log_store — BP4: llm_calls.user_id + cost_by_user_day) ·
│   │   │                          #   user_store.py (M0 auth: users/sessions/invites/quota) ·
│   │   │                          #   atlas_store.py (Atlas M1: FK-linked data/atlas.db user-plane
│   │   │                          #    core — user_instruments, ticker_verdicts, outbox,
│   │   │                          #    feedback_events; DPDP delete_user_completely) ·
│   │   │                          #   job_outcomes.py (last-run per scheduled job
│   │   │                          #   → /scheduler/status "last_runs")
│   │   ├── cache/                 # Data caching utilities
│   │   ├── context/               # Context-building helpers + bundle_builder.py
│   │   │                          # (Unified Sector Analyst — one-pass SectorDataBundle)
│   │   └── fetchers/              # Market/news data fetchers (+ bhavcopy.py, bulk_block.py,
│   │                              #  surveillance.py — discovery guard data; ipo.py — IPO lists;
│   │                              #  close_verifier.py — yfinance×NSE close cross-check +
│   │                              #  poisoning detector + non-finite sanitizer, the RL loop's
│   │                              #  price-integrity gate)
│   └── scheduler/
│       └── python/
│           └── scheduler.py       # APScheduler BackgroundScheduler — all 18 jobs (Jobs 16-18 =
│                                  #  Atlas universe/cost-rollup/retention, dormant until ATLAS_ENABLED)
│                                  # (see docs/ARCHITECTURE.md §3 for the full schedule table)
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
│   │   │   ├── renewable_energy/  # Renewable energy agents (6 agents)
│   │   │   │   └── pipeline/orchestrator.py  # RenewableAgentOrchestrator
│   │   │   └── generic/           # Compass Phase B — sector-agnostic unified graph for
│   │   │       │                  #  auto-promoted tickers outside the 4 native sectors
│   │   │       ├── pipeline/orchestrator.py  # GenericSectorOrchestrator (8 dimensions)
│   │   │       ├── prompts/       # unified.py (one-call prompt) + dimensions.py (fallback pool)
│   │   │       └── config/settings.py        # AGENT_WEIGHTS ← settings.GENERIC_AGENT_WEIGHTS; TICKERS=[]
│   │   └── (dead intelligence/, api/ subtrees deleted — audit Wave E 2026-07-17)
│   │
│   │   # src/backend/shared/ — shared machinery across sectors:
│   │   ├── shared/
│   │       ├── agents/            # Base agent classes
│   │       ├── clients/           # Shared API clients
│   │       ├── config/
│   │       │   ├── settings/base.py   # Master settings file (all env vars)
│   │       │   └── rag_config.py      # RAG-specific settings
│   │       ├── data/              # Data helpers
│   │       ├── pipeline/          # THE analysis engine:
│   │       │   ├── base_orchestrator.py   # resolve → bundle → analyse → aggregate
│   │       │   ├── unified_analyst.py     # Unified Sector Analyst — one-call dimension scoring
│   │       │   ├── signal_aggregator.py   # learned weights + conflict detection + LLM verdict
│   │       │   ├── verdict_shadow.py      # observe-only threshold(composite) lane
│   │       │   │                          #  → data/rl/verdict_shadow.jsonl (audit Wave G)
│   │       │   ├── base_agent.py          # legacy per-dimension agent base (fallback pool)
│   │       │   └── graphs/                # nodes.py/rails.py/state.py — legacy fallback
│   │       │                              #  dispatch machinery (UNIFIED_ANALYST_FALLBACK_LEGACY)
│   │       ├── prompts/           # Shared prompt templates
│   │       └── schemas/
│   │           └── feedback.py    # Feedback/RL schemas (src path)
│   └── frontend/
│       └── prototypes/            # THE real frontend — vanilla-React JSX (Babel standalone),
│                                  #  served statically at /app; PWA (sw.js + VAPID push).
│                                  #  (The old TypeScript/Vite src/frontend/web scaffold was
│                                  #   deleted in audit Wave E — it was never the deployed UI.)
├── core/                          # Core intelligence layer (shared across sectors)
│   ├── config/                    # Settings (config.yaml is the tunables source of truth)
│   ├── utils/
│   │   └── atomic_io.py           # mkstemp + os.replace atomic JSON/text writes (audit AUD-057)
│   ├── intelligence/
│   │   ├── rl/                    # Reinforcement learning feedback loop
│   │   │   ├── agents/            # feedback_agent (direction scoring: NEUTRAL correct only on
│   │   │   │                      #  FLAT moves — Wave G), weight_adapter, thesis_reviewer,
│   │   │   │                      #  dossier_curator, event_ingestor, question_researcher,
│   │   │   │                      #  control_lane
│   │   │   ├── algorithms/        # price_interpolator.py, lesson_emphasis.py (executable claims)
│   │   │   ├── conviction/        # tracker.py (conviction streak)
│   │   │   ├── eval/              # Read-only evaluation harness (metrics, synthetic, run_eval CLI)
│   │   │   ├── stores/            # prediction_store.py, ledger_propagator.py (archival +
│   │   │   │                      #  resurrection), offmarket_fetcher.py (bulk/block off-market)
│   │   │   ├── workflows/         # generate_forecast.py, daily_review.py (Step 8.5 = dossier
│   │   │   │                      #  curator), preopen_check.py, month_end_validation.py,
│   │   │   │                      #  sector_router.py
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
│   │   │                          #  + explain_triggers() (codes -> plain English, shared by
│   │   │                          #  brief/weekly/alerts); SWITCH never targets a held symbol
│   │   ├── narrator.py            # BULK-tier LLM narration of advice
│   │   ├── digest.py              # EOD portfolio digest builder (carries switch_candidate
│   │   │                          #  so the brief can name the destination)
│   │   ├── pipeline.py            # run_post_review_pipeline() orchestration entry point
│   │   ├── autopilot.py           # Compass Autopilot: deterministic verdict executor (see below)
│   │   ├── universe.py            # Atlas C4 — nightly Universe recompute (Job 16): user_instruments
│   │   │                          #  refcounts → instruments demand tiers/cadence (no user_id, R1)
│   │   └── retention.py           # Atlas C9 — nightly prune (Job 18): bounds ticker_verdicts /
│   │                              #  outbox / value_history / sessions; all caps via cfg()
│   ├── discovery/                 # Compass Phase B: weekly discovery funnel (see below)
│   │   ├── __init__.py            # run_discovery_cycle() — single orchestration entry point
│   │   ├── universe.py            # EQ-series + price-floor universe from the EOD window
│   │   ├── guards.py              # Threshold gates (liquidity, T2T, circuits, ASM/GSM, float)
│   │   ├── signals.py             # 5 live + 2 dark quant signals (pure pandas, zero LLM)
│   │   ├── screen.py              # Weighted percentile-rank composite → ScreenResult persistence
│   │   ├── deep_dive.py           # Stage-3 LLM one-call dives + sector inference
│   │   ├── shelf.py               # Discovery Shelf (cap/displace, stale rotation, promote)
│   │   ├── paper_lane.py          # Paper envelopes + weekly paper reviews (ISOLATED lane)
│   │   └── ipo_tracker.py         # Stage-2 IPO/new-listing scoring + lock-in calendar
│   ├── delivery/                  # Compass Phase C: M4 proactive delivery (see below)
│   │   ├── channels.py            # web-push (pywebpush+VAPID) + SMTP email; PushStore;
│   │   │                          #  send-then-record delivered flag; stale-sub pruning
│   │   ├── alerts.py              # AlertEvent + delivered-aware deduped emit (alerts_sent.jsonl)
│   │   │                          #  + emit_alerts_broadcast (fan-out to all subscribed users)
│   │   │                          #  + optional title/headline/status/next_step/docs (Inbox card)
│   │   │                          #  and render_alerts_html for the email body
│   │   ├── ops_alerts.py          # Job crashed / zero-output / partial-output / reconcile-drift
│   │   │                          #  operational alerts (audit AUD-039/084/090)
│   │   ├── brief.py               # Morning brief builder (08:50 IST job)
│   │   ├── weekly.py              # Weekly review builder (Sun 18:00 IST job); switch
│   │   │                          #  suggestions carry why-leave + the destination's thesis
│   │   ├── index_watch.py         # Index constituent diff -> inclusion/exclusion alerts
│   │   └── outbox.py              # Atlas C7 (BP2) — durable delivery outbox: deliver() enqueues
│   │                              #  per-channel rows when ATLAS_ENABLED; singleton-owner drainer
│   │                              #  claims each atomically (queued→sending CAS) → send + backoff
│   ├── pipeline/                  # Live shim for the automobile path via sector_router
│   │   ├── base_agent.py
│   │   ├── orchestrator.py
│   │   └── signal_aggregator.py
│   └── schemas/
│       ├── feedback.py            # Canonical feedback/RL schemas
│       └── pipeline.py
├── scripts/
│   ├── model_bench.py             # Chat-tier model comparison harness (fabrication/latency/cost)
│   ├── reasoning_bench.py         # Reasoning-tier model benchmark
│   ├── gen_vapid_keys.py          # One-time VAPID keypair generation (web-push)
│   ├── clean_ledger_errors.py     # One-off ledger repair utility
│   └── seed_autopilot.py          # One-time Autopilot seed: equal-weight holdings + autopilot=True
├── tests/                         # Test suite
│   ├── api/                       # API-level tests
│   ├── contract/                  # Cross-module contract tests (LLM migration, scheduler wiring)
│   ├── fixtures/                  # Shared test fixtures
│   ├── integration/               # Integration tests
│   └── unit/                      # Unit tests
├── config/
│   └── sector_toggles.json        # Enable/disable sectors at runtime
├── data/                          # Runtime data volume (see docs/ARCHITECTURE.md §11)
├── logs/                          # Log files
├── outputs/                       # Report output files
├── docs/                          # Design documentation (index: docs/README.md)
├── services/csharp/               # ⚠ DEAD — .NET scheduler, NOT in the Docker image (superseded
│   └── StockAgent.Scheduler/      #  by the Python APScheduler); still tracked, deletion candidate
├── Dockerfile                     # THE deploy artifact: core/ services/ src/backend→backend/
│                                  #  scripts/ main.py config.yaml prototypes → anything outside
│                                  #  its COPY set is dead in prod by construction
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

> **Deleted in audit Wave E (2026-07-17, −34.8K lines)** — if you're looking for these, they're
> gone on purpose: `core/sectors/` (22 sector skeletons, never live), `core/graphs/`,
> `src/backend/intelligence/`, `src/frontend/web/` (TS scaffold), `scripts/api_exploration/`,
> the legacy per-sector prompt trees, and the duplicate root-level test copies. History:
> [docs/audit/LEDGER.md](docs/audit/LEDGER.md) Wave E section.

- `core/portfolio/` — Compass Phase A: per-user virtual portfolio (store, corp-action
  sync, auto-promotion into managed universe, deterministic HOLD/ADD/TRIM/EXIT advisor
  with ATR-scaled stops, BULK-tier narration, EOD digest). Event-triggered from
  scheduler_api._review_task after daily reviews. Spec:
  docs/superpowers/specs/2026-07-06-portfolio-intelligence-discovery-design.md

- `core/portfolio/autopilot.py` — Compass Autopilot: deterministic executor that turns
  each review-day's advisor verdicts into paper trades (sells first, then buys; no LLM
  in the loop). Writes append-only to `transactions.jsonl` (audit trail) and
  `value_history.jsonl` (daily equity curve); executor writes stay inside
  `data/portfolio/<user>/` — never `data/rl/paper` or PredictionStore paths (isolation
  invariant, spec §8; sell + buy paths pinned by `tests/unit/test_autopilot_isolation.py`).
  One designed exception: a SWITCH buy promotes the candidate into the managed universe
  (`data/managed_tickers.json` via `core/portfolio/promotion.py`, mocked in that test).
  Seeded one-time via `scripts/seed_autopilot.py`. Spec: docs/superpowers/specs/2026-07-10-compass-autopilot-design.md

- `core/discovery/` — Compass Phase B: weekly quant discovery funnel (~2000 NSE
  mainboard stocks → composite rank → guards → ≤10 LLM deep-dives → Discovery Shelf
  with paper envelopes in an ISOLATED paper lane — `data/rl/paper/predictions` is
  never mixed into real RL metrics; `run_daily_review(paper=True)` hard-disables all
  learning writes). Driven by scheduler Job 12 (Sat 12:30 IST) + `/discovery/*` routes.
  Same spec as Phase A; plan: docs/superpowers/plans/2026-07-07-compass-phase-b.md

- `core/delivery/` — Compass Phase C: M4 proactive delivery (morning brief, weekly
  review + index watch, deduped event alerts, web-push + email channels). Jobs 13/14
  + event-triggered hooks in the advisor pipeline, pre-open check and discovery cycle.
  IPO tracker (`core/discovery/ipo_tracker.py` + `services/data/fetchers/ipo.py`)
  feeds the same Stage-3 deep-dive budget. Same spec; plan:
  docs/superpowers/plans/2026-07-09-compass-phase-c.md

- **Atlas M1 — user-data ↔ central-intelligence relational plane** (Phase C, all
  **dormant behind `cfg("atlas.enabled", env="ATLAS_ENABLED")` = false** until the
  weekend cutover; flag-off is byte-for-byte today's JSON/`users.db`/dir-scan path and
  the instant-rollback lever). One FK-linked SQLite DB `data/atlas.db` folds `users.db`
  + the global `watchlist.json` + `push_subscriptions.json` and adds the missing
  `user_instruments` join, the plane-boundary `ticker_verdicts` projection, `user_advice`,
  and the greenfield `outbox` + `feedback_events`. Modules: `services/data/stores/atlas_store.py`
  (schema + FK-on connection, `user_instruments` write-through, `active_user_ids()`, DPDP
  `delete_user_completely`, `record_feedback_event`/`feedback_aggregate`),
  `services/data/verdict_store.py` (the plane boundary — advisor/pipeline read verdicts through
  this instead of importing `PredictionStore`; the intelligence plane never gains user references,
  Learning Constitution R1, enforced by `tests/unit/test_atlas_import_boundary.py`),
  `core/delivery/outbox.py` (BP2 durable delivery), `core/portfolio/universe.py` (BP1 demand
  tiers), `core/portfolio/retention.py` (nightly prune). Telemetry `llm_calls.user_id`
  (BP4, `services/data/stores/log_store.py`) attributes cost per user (NULL = shared brain).
  Spec: docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md · plan:
  docs/superpowers/plans/2026-07-26-atlas-user-data-program.md

---

## 2. API Endpoints

All endpoints are served on port 8001. No global auth middleware — auth is per-endpoint.
Since audit Wave B (2026-07-16), **every mutation route** (all `/ui/*` writes, all
`/ui/prompts/*` routes, portfolio/discovery/delivery POST/PUT/DELETE) passes through the
shared `services/api/auth.py::check_scheduler_key` gate: requests must carry
`X-Scheduler-Key` **when `SCHEDULER_KEY` is set in the environment**; when unset the gate
logs a warning and allows (dormant enforcement — flipping it on is one env var). The only
deliberately keyless writes are the push subscribe/unsubscribe endpoints (pre-login 🔔).
Unknown paths under the API prefixes return 404 (the SPA catch-all no longer masks them).

### Auth (`/auth/*`) — M0 multi-user identity + DPDP

Bearer-session identity (`services/api/auth.py`). First signup becomes the `owner`
(`user_id='primary'`); later signups are invite-gated. `AUTH_REQUIRED=false` ⇒ anonymous
acts as owner (single-user passthrough).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/signup` · `/auth/login` · `/auth/logout` | mixed | Session lifecycle; returns `{token, user}`. |
| GET | `/auth/me` | session | Current user. |
| POST · GET | `/auth/invites` | owner | Create / list invite codes. |
| DELETE | `/auth/account` | session (not owner) | **DPDP right-to-erasure (Atlas C6)** — runs `user_store.delete_user` + `atlas_store.delete_user_completely` (single atlas.db cascade → 7 PII tables + portfolio dir + chat_turns; telemetry anonymised) + session revoke. Owner cannot self-delete. |

### Analysis

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/analyse` | session | Run full multi-sector 9-agent pipeline for a ticker. Auto-detects sector; accepts `ticker`, `sector` (optional override), `output_format`. Returns `FinalReport` as JSON. Metered per user via `analyse.daily_quota` → 429 when exhausted. |
| WS | `/ws/stream?ticker=<sym>` | session | WebSocket stream. Emits `agent_progress` events per agent, then a final `complete` event with the full report. Token rides in the `sa.bearer` subprotocol (`new WebSocket(url, ['sa.bearer', tok])`) — browsers cannot set headers on a WS handshake, and a `?token=` param would land in access logs. Same per-user quota as `/analyse`. Concurrent viewers of the **same ticker share one pipeline run** (fan-out hub in `stream.py`); the run is cancelled when the last viewer leaves. |

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
| GET | `/ui/watchlist` | None | User watchlist with live prices. When `ATLAS_ENABLED`, the session user's `Portfolio.watchlist` (per-user); else the global `data/watchlist.json` (Atlas C5). |
| PUT | `/ui/watchlist` | None → owner | Persist watchlist. When `ATLAS_ENABLED`, writes the session user's `Portfolio.watchlist`; else owner-only global `data/watchlist.json` (Atlas C5). |
| GET | `/ui/search?q=<term>` | None | Ticker + thesis text search (falls back to yfinance lookup). |
| GET | `/ui/categories` | None | Categories (EV, mass-market, etc.) with ticker lists. |
| PUT | `/ui/categories/{key}/tickers` | None | Add/remove tickers from a category (body: `{add: [], remove: []}`). |
| GET | `/ui/learnings` | None | RL-derived lesson cards and portfolio learning summary. |
| POST | `/ui/feedback` | session user | Atlas C8 (BP5) — record a user's accept/override/ignore on an advice card (`symbol`, `action`, optional `verdict_shown`/`override_direction`/`position_state`). Append-only to `feedback_events`; dormant no-op until `ATLAS_ENABLED`. |
| POST | `/ui/chat/stream` | None | **Primary chat** — agentic streaming tool-loop (SSE). Deterministic intent pre-router pre-fetches screen+news for buy/sell/momentum queries; BULK-tier default with reasoning disabled, glm-5.2 escalation on failure; **45s per-turn wall-clock budget**, ≤4 upstream attempts per logical call, one budget-free final synthesis. Server-side session memory (`session_id`). Events: `intent`, `tool_result`, `token`, `done`. |
| POST | `/ui/chat` | None | Non-streaming twin of the chat loop (blocking JSON reply; same server session memory — returns `session_id`, client-sent history is ignored). Frontend fallback. |
| GET | `/ui/logs` · `/ui/logs/stream` | None | Recent server log lines (ring buffer) + SSE tail. |

### Managed Tickers (`/ui/tickers/managed*`) — RL universe administration

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ui/tickers/managed` | None | The managed-ticker list (the RL scheduling universe). |
| PUT | `/ui/tickers/managed` | optional key | Replace the whole list (rejects empty/whitespace `sym` entries — whole-list clobber guard). |
| POST | `/ui/tickers/managed/{sym}` | optional key | Add one ticker. |
| POST | `/ui/tickers/managed/{sym}/generate-envelope` | optional key | Kick a first 30-day envelope for a newly added ticker (~2 min LLM run, background). |
| DELETE | `/ui/tickers/managed/{sym}` | optional key | Remove one ticker. |

### RL Monitor (`/ui/rl/*`) — real data behind the RL Monitor page (audit Wave C)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ui/rl/tickers` | None | Managed tickers with RL-data-present flags. |
| GET | `/ui/rl/summary/{ticker}` | None | Summary card: envelope, accuracy, weight version. |
| GET | `/ui/rl/predictions/{ticker}` | None | Per-day predicted vs actual close rows (feedback log). |
| GET | `/ui/rl/weights/{ticker}` | None | Agent weight state + drift history. |
| GET | `/ui/rl/misses/{ticker}` | None | Miss-type attribution counts. |

Ticker path params are validated against the managed list *before* any store construction
(unknown tickers 404 without creating directories).

### Prompt Management (`/ui/prompts/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ui/prompts/catalogue` | optional key | List all sectors and their agent names. |
| GET | `/ui/prompts/status` | optional key | Pending deploy count, next midnight IST deploy time, last deploy result. |
| GET | `/ui/prompts/pending` | optional key | Files modified since last deploy. |
| GET | `/ui/prompts/{sector}/{agent}` | optional key | Read `SYSTEM_PROMPT`, `ANALYSIS_PROMPT`, `CONTEXT_SEARCH_QUERIES` for an agent. |
| PUT | `/ui/prompts/{sector}/{agent}` | optional key | Write prompt to disk and patch live module in-memory (content is escaped into a safe Python string literal — no `"""`/trailing-backslash breakout). Marks file as pending deploy. |
| POST | `/ui/prompts/deploy` | optional key | Emergency manual deploy: push pending files to GitHub immediately (requires `GITHUB_TOKEN`/`GITHUB_REPO`). |

### Scheduler (`/scheduler/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/scheduler/forecast?ticker=<sym>` | `X-Scheduler-Key` header | Generate 30-day prediction envelopes (full 9-agent pipeline). Returns 202, runs in background. |
| POST | `/scheduler/daily-review?ticker=<sym>&review_date=<ISO>` | `X-Scheduler-Key` header | Run RL daily feedback loop for one date. Returns 202, runs in background. |
| POST | `/scheduler/backfill?ticker=<sym>` | `X-Scheduler-Key` header | Backfill all past trading days this month. Returns 202, runs in background. |
| GET | `/scheduler/status` | `X-Scheduler-Key` header | Full RL state for all configured tickers: envelope, feedback log, weight memory — plus `last_runs` (per-job last outcome from `data/scheduler_job_outcomes.json`: produced/expected counts, stragglers, pipeline result). |

### Portfolio — Compass Phase A (`/portfolio/*`)

All endpoints take an optional `user_id` query param (default `portfolio.default_user_id`, i.e. `"primary"`); `user_id` is validated against `[A-Za-z0-9_-]{1,64}`. Auth mirrors the scheduler pattern (optional `X-Scheduler-Key`; lockdown deferred while the portfolio is virtual — user decision 2026-07-06).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/portfolio` | optional key | Holdings + watchlist marked to market at latest NSE close (per-holding `last_close`, `pnl_pct`). |
| POST | `/portfolio/holdings` | optional key | Add virtual holding `{symbol, sector?, qty, buy_date, price?}` — `sector` omitted → resolved via `SectorRegistry`; `price` omitted → real NSE close on `buy_date`. 422 on unsupported sector / bad date / no price. Auto-promotes (origin=held, daily cadence). Wired to the prototype portfolio page's Add-holding modal (portfolio-live-wiring). |
| DELETE | `/portfolio/holdings/{symbol}` | optional key | Remove holding; demotes from managed universe unless watchlisted. 404 if absent. |
| POST | `/portfolio/watchlist` | optional key | Add watchlist symbol `{symbol, sector?, reason?}` — `sector` omitted → resolved via `SectorRegistry`; promotes with weekly cadence. |
| DELETE | `/portfolio/watchlist/{symbol}` | optional key | Remove watchlist symbol; demotes unless held. |
| POST | `/portfolio/import-csv` | optional key | Raw CSV body `symbol,sector,qty,avg_buy_price,buy_date`; blank price → real close on buy date; per-row errors reported. |
| GET | `/portfolio/advice?limit=<1-500>` | optional key | Advice-ledger tail (append-only JSONL of every verdict). |
| GET | `/portfolio/digest/latest` | optional key | Latest EOD digest (404 until the advisor has run). |
| POST | `/portfolio/run-advisor?review_date=<ISO>` | optional key | Manually trigger the post-review pipeline (corp-action sync → events → advisor → ledger → digest). 202, background. |
| GET | `/portfolio/transactions?limit=<1-1000>` | optional key | Transaction audit trail, newest first — every Autopilot trade (source, verdict, qty/price, realized P&L). |
| GET | `/portfolio/performance` | optional key | P&L summary + daily equity curve: cash, market value, total equity, day-change %, realized P&L, sourced from `value_history.jsonl` (falls back to a live mark when history is empty). |

The pipeline also runs automatically: `scheduler_api._review_task` event-triggers `core.portfolio.pipeline.run_post_review_pipeline` after every daily-review job completes (never clock-scheduled).

### Discovery — Compass Phase B (`/discovery/*`)

Auth mirrors the portfolio pattern (optional `X-Scheduler-Key`; lockdown deferred — user decision 2026-07-06).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/discovery/shelf` | optional key | Discovery Shelf — active/promoted/dropped ideas with conviction, entry zone, invalidation level, paper-review status. |
| GET | `/discovery/screen/latest` | optional key | Most recent weekly `ScreenResult` (candidates, rejected gates, dark signals, degraded checks). 404 until a screen has run. |
| POST | `/discovery/run` | optional key | Trigger a full discovery cycle now (sync → screen → dives → shelf → paper reviews). 202, background. |
| POST | `/discovery/shelf/{symbol}/promote` | optional key | One-command promote a shelf idea to the watchlist (`source="discovery"`, weekly cadence). 404 if not an active idea. |
| DELETE | `/discovery/shelf/{symbol}` | optional key | Drop a shelf idea (`reason="manual_api"`). 404 if not an active idea. |

The cycle also runs automatically: scheduler Job 12 (`discovery_weekly`, Sat 12:30 IST) calls `core.discovery.run_discovery_cycle()`; Job 11 (`bhavcopy_daily_sync`, Mon-Fri 19:00 IST) keeps the EOD parquet cache topped up. Both are gated on `discovery.enabled`.

### Delivery — Compass Phase C (`/delivery/*`)

Auth mirrors the portfolio pattern (optional `X-Scheduler-Key`), except the push
endpoints (`public-key` is public by design; `subscribe` carries no secrets).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/delivery/brief/latest` | optional key | Latest morning brief (404 until one is built). |
| GET | `/delivery/weekly/latest` | optional key | Latest weekly review (404 until one is built). |
| POST | `/delivery/run-brief` | optional key | Build + deliver the morning brief now. 202, background. |
| POST | `/delivery/run-weekly` | optional key | Build + deliver the weekly review now. 202, background. |
| GET | `/delivery/alerts?limit=50` | optional key | Emitted-alert tail (deduped sent-log). |
| GET | `/delivery/push/public-key` | none | VAPID application server key for the browser. |
| POST | `/delivery/push/subscribe` | none | Store a web-push subscription (body = PushSubscription JSON). |
| DELETE | `/delivery/push/subscribe?endpoint=` | none | Remove a web-push subscription. |

Jobs: 13 `morning_brief` (Mon-Fri 08:50 IST), 14 `weekly_review` (Sun 18:00 IST) —
both gated on `delivery.enabled`. Alerts also fire event-triggered from the advisor
pipeline, the 08:45 pre-open check, and the Saturday discovery cycle.

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

### Mapped sectors without a native graph (routed to the generic graph)

Compass Phase B: on the RL path, `core/intelligence/rl/workflows/sector_router.py`
routes any sector key outside the 4 native ones to `GenericSectorOrchestrator`
(sector-agnostic unified analyst + neutral `generic_graph.agent_weights`) — the old
silent degrade-to-automobile is gone. `PredictionStore` keeps the REAL sector name
for its directory layout (e.g. `data/predictions/pharma/SUNPHARMA/`). The chat-path
`CoreSectorAdapter` skeleton tier (commit e30042f, `config/sector_toggles.json`)
remains toggled off and unused.

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
(The old `LLM_MODEL` back-compat alias was **deleted** in the 2026-07-16 cost wave — every call site names an explicit tier; `config.yaml` is the sole model-selection source.)
| `LLM_TEMPERATURE` | `0.2` | LLM sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Max output tokens per LLM call |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call LLM timeout |
| `LLM_INPUT_COST_PER_M` | `0.09` | Cost tracking fallback: USD per 1M input tokens for models NOT in `llm.cost_rates` |
| `LLM_OUTPUT_COST_PER_M` | `0.18` | Cost tracking fallback: USD per 1M output tokens for models NOT in `llm.cost_rates` |
| `LLM_COST_RATES` | per-model table | Tier-correct cost rates (config.yaml `llm.cost_rates`, AUD-105) — every cost site calls `settings.llm_cost_usd(model, pt, ct)` |

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
| `SCHEDULER_KEY` | `""` | API key for scheduler endpoints (header `X-Scheduler-Key`); M0: now expected to be set in prod to enforce the Wave-B gate |
| `FEEDBACK_CRON` | `0 11 * * 1-5` | Cron for daily RL feedback review (4:30pm IST weekdays) |
| `AUTO_TICKERS` | `MARUTI,...,ASHOKLEY` | Automobile sector ticker list override |

### Portfolio + Position Advisor — Compass Phase A (`config.yaml` → `portfolio.*` / `advisor.*`)

| Name | Default | Description |
|------|---------|-------------|
| `PORTFOLIO_DATA_DIR` | `data/portfolio` | Per-user roots: `data/portfolio/<user_id>/` (volume-persisted) |
| `PORTFOLIO_DEFAULT_USER_ID` | `primary` | Single-user launch default; per-user layout from day one |
| `AUTH_REQUIRED` | `false` | M0: when true, user-scoped routes require a bearer session; false = anonymous acts as owner (single-user compatibility) |
| `CHAT_DAILY_QUOTA` | `30` | M0: member daily LLM chat turns; owner exempt; 0 = unlimited |
| `ANALYSE_DAILY_QUOTA` | `10` | Member daily on-demand pipeline runs (`POST /analyse` + `WS /ws/stream`); owner exempt; 0 = unlimited. **`config.yaml` key `analyse.daily_quota` only — no env override.** One run ≈ 8 LLM calls, hence tighter than chat |
| `watchdog.enabled` | `true` | Master gate for the `ops_watchdog` job (06:30 IST daily). **`config.yaml` only — no env override.** |
| `watchdog.prep_enabled` | `true` | Auto-run idempotent prep (e.g. the Atlas ETL) when a milestone's window is open. Set false for notify-only. |
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

### Discovery + Generic Graph — Compass Phase B (`config.yaml` → `discovery.*` / `generic_graph.*`)

| Setting | Default | Description |
|---------|---------|-------------|
| `discovery.enabled` | `true` (base.py fallback `false`) | Master gate for scheduler Jobs 11/12 and the discovery funnel |
| `discovery.history_days` | `550` | Rolling EOD window (~2.2yr; 12m momentum needs 252 sessions) |
| `discovery.bhavcopy_dir` | `data/market_cache/bhavcopy` | Per-day parquet EOD cache root |
| `discovery.data_dir` | `data/discovery` | `screens/`, `shelf.json`, `shelf_events.jsonl` |
| `discovery.paper_data_dir` | `data/rl/paper/predictions` | ISOLATED paper-lane store root (spec §6.3) |
| `discovery.liquidity_floor_cr` | `5.0` | Median daily traded value floor (₹ cr) |
| `discovery.float_mcap_floor_cr` | `500.0` | Free-float mcap floor (₹ cr) |
| `discovery.min_price` | `20.0` | No penny stocks |
| `discovery.max_promoter_pledge_pct` | `25.0` | Guard ships DARK in v1 (no free data source yet) |
| `discovery.circuit_streak_max` | `3` | > N trailing upper-circuit days = operator pattern, rejected |
| `discovery.shortlist_size` | `80` | Ranked names that get per-symbol guard checks |
| `discovery.max_candidates` | `40` | ScreenResult size after guards |
| `discovery.deep_dive_count` | `10` | Weekly unified-analyst calls (LLM cost cap) |
| `discovery.shelf_size` | `10` | Max active shelf ideas (stronger idea displaces weakest) |
| `discovery.stale_days` | `60` | Idea age without trigger → rotate out |
| `discovery.min_conviction` | `0.55` | Deep-dive final_score floor to reach the shelf |
| `discovery.include_sme` | `false` | SME platform excluded (spec §6.2) |
| `discovery.signal_weights` | momentum 0.30, delivery_surge 0.15, volume_breakout 0.15, bulk_block 0.15, high_52wk_rs 0.10, insider_buying 0.10, mf_holding 0.05 | Composite blend; **insider_buying + mf_holding are DARK in v1** — the screen renormalizes over live signals and reports dark ones in `ScreenResult.dark_signals` |
| `generic_graph.agent_weights` | business 0.14, fundamentals 0.18, valuation 0.14, technical 0.12, macro 0.12, risk 0.12, management 0.09, earnings 0.09 | Neutral 8-dimension weights for sectors without a native graph (sum 1.0) |

### Delivery + IPO Tracker — Compass Phase C (`config.yaml` → `delivery.*` / `discovery.ipo_*`)

| Setting | Default | Description |
|---------|---------|-------------|
| `delivery.enabled` | `true` (base.py fallback `false`) | Master gate: Jobs 13/14 + every channel send |
| `delivery.data_dir` | `data/delivery` | `push_subscriptions.json`, `alerts_sent.jsonl` |
| `delivery.email_enabled` | `false` | Needs `SMTP_HOST/PORT/USER/PASSWORD` + `DELIVERY_EMAIL_TO` in .env |
| `delivery.push_enabled` | `true` | Needs `VAPID_PRIVATE_KEY/PUBLIC_KEY/CLAIM_EMAIL` in .env (`scripts/gen_vapid_keys.py`) |
| `audit.shock_atr_mult` | `3.0` | Single-session move (× ATR) that classifies a switch miss as unforeseeable |
| `audit.switch_lane_enabled` | `true` | Grade the evaluated switch pairs (switch lane) |
| `audit.switch_grade_max_rows_per_run` | `2000` | Caps the first switch backfill so it cannot stall the nightly job |
| `advisor.switch_eval_enabled` | `true` | Record every (holding, shelf-candidate) pair the advisor evaluates (switch validation, design 2026-08-20) |
| `advisor.switch_eval_max_candidates` | `5` | Top-N active shelf ideas by conviction evaluated per holding per run |
| `delivery.alert_html_enabled` | `true` | HTML alert email body; `false` = plain text only (the Inbox card is unaffected) |
| `delivery.index_watch` | NIFTY 50 / NEXT 50 / MIDCAP 150 / SMALLCAP 250 | Weekly constituent diff → inclusion/exclusion alerts |
| `delivery.outbox_max_attempts` | `3` | BP2 outbox: sends before a row is dead-lettered (active only when `ATLAS_ENABLED`) |
| `delivery.outbox_backoff_minutes` | `[1, 5, 30]` | BP2 outbox: per-attempt reschedule delay |
| `delivery.outbox_poll_seconds` | `30` | BP2 outbox: drainer loop interval |
| `delivery.outbox_retention_days` | `30` | Prune delivered/dead outbox rows older than this (Atlas C9) |
| `discovery.ipo_enabled` | `true` (fallback `false`) | Stage-2 IPO tracker in the Saturday cycle |
| `discovery.ipo_listing_window_days` | `90` | Listings younger than this are candidates |
| `discovery.ipo_max_deep_dives` | `2` | Reserved Stage-3 slots (WITHIN `deep_dive_count`) |
| `discovery.ipo_lockin_warn_days` | `7` | Lock-in expiry flag window (30/90/180-day cliffs) |
| `discovery.ipo_qib_weight` | `3.0` | QIB subscription weighted 3× retail |
| `advisor.switch_conviction_gap` | `0.15` | SWITCH: shelf conviction − holding confidence floor |

### Atlas M1 — user-data plane (`config.yaml` → `atlas.*` / `universe.*`)

The whole Atlas relational plane is gated on `atlas.enabled` (env `ATLAS_ENABLED` wins).
**Default `false` = dormant** — every Atlas feature is a behavioral no-op and the app runs
today's JSON/`users.db`/dir-scan path; flipping to `true` at the weekend cutover activates
the plane and flag-off is the instant-rollback lever.

| Setting | Default | Description |
|---------|---------|-------------|
| `atlas.enabled` | `false` | Master flag for the entire Phase-C data plane (read live per call) |
| `atlas.db_path` | `data/atlas.db` | The FK-linked user-plane SQLite DB |
| `atlas.feedback.aggregation_floor_users` | `20` | `feedback_aggregate()` refuses below this many distinct users (privacy, reviewer R3) |
| `atlas.retention.ticker_verdicts_days` | `400` | Nightly prune of `ticker_verdicts` older than this (`null` = keep-all) |
| `atlas.retention.value_history_cap` | `400` | Keep the last N daily value points per user |
| `universe.demand_weights` | holders×3 / watchers×1 / chat_hits_7d×0.5 | BP1 demand score for the nightly recompute (Atlas C4) |
| `universe.max_daily_analyses` | `25` | Daily-cadence budget; governor alerts at `universe.budget_alert_pct` (`0.8`) |
| `universe.archive_grace_days` | `30` | Refcount-0 + no history + archivable origin → archive after this |

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
| `LEARNING_EVIDENCE_DIR` | `data/eval/learning_evidence` | Monthly Learning Evidence Report (self-ablation: adapted vs frozen vs uniform weights) |

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
| `CSHARP_API_URL` | `http://localhost:5000` | Legacy C# scheduler base URL (the C# service is dead — setting only read by `score_store.py`'s unused mirror path) |

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
| `services/api/routes/portfolio_api.py` | /portfolio/* — Compass Phase A: holdings, watchlist, CSV import, advice ledger, EOD digest; Autopilot: transactions audit trail, performance (P&L + equity curve) |
| `core/portfolio/pipeline.py` | `run_post_review_pipeline()` — corp-action sync → events refresh → advisor → ledger → digest, per user |
| `core/portfolio/advisor.py` | Deterministic HOLD/ADD/TRIM/EXIT engine (EXIT>TRIM>ADD>HOLD), ATR-scaled stops, LTCG/earnings-gap notes, `explain_triggers()` |
| `core/portfolio/autopilot.py` | `execute_advice()` — deterministic verdict executor (sells then buys, no LLM); `record_value_point()` — daily equity snapshot |
| `services/data/fetchers/corporate_events.py` | NSE corp-actions feed + forward board-meetings calendar (degraded-mode safe) |
| `data/portfolio/<user>/` | Per-user volume state: `portfolio.json`, `advice_ledger.jsonl`, `transactions.jsonl` (Autopilot audit trail), `value_history.jsonl` (daily equity curve), `digests/` |
| `scripts/seed_autopilot.py` | One-time Autopilot seed: equal-weight virtual holdings from managed tickers + `autopilot=True`; idempotent |
| `services/api/routes/discovery_api.py` | /discovery/* — Compass Phase B: shelf, latest screen, manual run, promote/drop |
| `core/discovery/__init__.py` | `run_discovery_cycle()` — weekly funnel orchestration (every stage non-fatal) |
| `core/discovery/screen.py` | Stage-1 quant screen: composite rank over live signals, guards, `ScreenResult` persistence |
| `core/discovery/deep_dive.py` | Stage-3 LLM dives (≤`discovery.deep_dive_count`/wk) + `infer_sector()` (registry → NSE industry → generic) |
| `core/discovery/shelf.py` | `ShelfStore` — cap/displacement, stale rotation, promote-to-watchlist, `shelf_events.jsonl` |
| `core/discovery/paper_lane.py` | Paper envelopes + weekly paper reviews via `paper=True` RL workflows |
| `services/data/fetchers/ipo.py` | NSE IPO lists (current/upcoming/past) + degraded-mode cache |
| `core/discovery/ipo_tracker.py` | IPO candidate scoring (QIB 3×, post-listing evidence) + lock-in calendar |
| `core/delivery/channels.py` | Web-push (pywebpush + VAPID) + SMTP email; `deliver()` fan-out |
| `core/delivery/alerts.py` | Deduped alert engine (`data/delivery/alerts_sent.jsonl`) |
| `core/delivery/brief.py` | Morning brief builder/renderer/runner |
| `core/delivery/weekly.py` | Weekly review builder (allocation, laggards, scoreboard) |
| `core/delivery/index_watch.py` | Index constituent snapshot diff → alerts |
| `services/api/routes/delivery_api.py` | /delivery/* — briefs, weekly, alerts, push subscriptions |
| `scripts/gen_vapid_keys.py` | One-time VAPID keypair generation for web-push |
| `services/data/stores/eod_store.py` | `EodStore` — per-day parquet EOD cache (canonical 12-column schema) |
| `services/data/fetchers/bhavcopy.py` | NSE delivery-bhavcopy fetcher + resumable `sync_recent()` |
| `services/data/fetchers/bulk_block.py` | Bulk/block deals cache (degraded-mode keeps stale deals) |
| `services/data/fetchers/surveillance.py` | Per-symbol NSE meta (ASM/GSM, suspension, industry) + yfinance float mcap |
| `src/backend/sectors/generic/pipeline/orchestrator.py` | GenericSectorOrchestrator — sector-agnostic 8-dimension graph (unified primary, UniversalAgent fallback pool) |
| `data/market_cache/bhavcopy/` | Per-day parquet EOD cache, ~550 sessions rolling |
| `data/discovery/` | `screens/`, `shelf.json`, `shelf_events.jsonl` |
| `data/rl/paper/predictions/` | ISOLATED paper-lane RL store — never mixed into real metrics |
| `services/api/routes/prompts.py` | /ui/prompts/* — live prompt editing and GitHub deploy |
| `services/api/routes/analytics.py` | /analytics/* — RL performance exports and Power BI feed |
| `services/api/log_buffer.py` | In-memory ring buffer for real-time log streaming |
| `services/scheduler/python/scheduler.py` | APScheduler: daily RL review (4:30pm IST), monthly forecast (1st, 9am IST), calendar update (Dec 31), pre-open shock check (`preopen_shock_check`, Mon-Fri 08:45 IST, Living Envelope §27.3), Job 13 morning brief (Mon-Fri 08:50 IST) + Job 14 weekly review (Sun 18:00 IST, Compass Phase C), `ops_watchdog` (06:30 IST daily) |
| `core/ops/watchdog/` | **The watchdog.** Reads `config/milestones.yaml` — the authoritative registry of dated milestones and standing invariants — runs named checks, and notifies on transitions via `ops_alerts`. `registry.py` loads/validates, `checks.py` probes state, `prep.py` auto-runs safe idempotent preparation, `engine.py` is the pure escalation ladder, `runner.py` wires it to state + delivery |
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
| `core/intelligence/rl/eval/learning_evidence.py` | Learning Evidence Report (AUD-116): counterfactual weight replay + sign test, credit-degeneracy, entropy/poverty-trap, per-lesson lift, Brier decomposition; CLI `python -m core.intelligence.rl.eval.learning_evidence` |
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
| `services/csharp/StockAgent.Scheduler/` | ⚠ DEAD C# .NET scheduler (not in the Docker image; deletion candidate) |
