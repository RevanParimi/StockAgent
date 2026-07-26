# Atlas M1 Data-Architecture — Research Memo (Task B1)

> **Role:** Researcher pass of the Atlas Phase-B 3-agent loop (Researcher → Designer → Reviewer).
> **Date:** 2026-07-26 · **Branch:** `atlas-b` · **HEAD:** `83989d5` (Phase A merge `e9c17fe` = `5f15b4e` A1 + `89be3a3` A2 already included).
> **Purpose:** Re-verify the 2026-07-26 store-audit findings against *current* code and give the Designer an exhaustive, file:line-cited map of every persistent store, its key, its user linkage, and the plane boundary. **No design decisions here — findings only.**

Repo layout note: backend code lives under `src/backend/...` (imported as `backend.*`) **and** top-level `core/` + `services/`. `.claude/worktrees/**` and `**/node_modules/**` are stale mirrors, excluded.

---

## Part 1 — Re-verification of the 7 audit findings

| # | Finding | Verdict |
|---|---|---|
| 1 | Push-subscribe session binding | **RESOLVED** (Phase A1) |
| 2 | chat_turns user_id + (user_id, session_id) scoping | **RESOLVED** (Phase A2) |
| 3 | No users→instruments join table | **CONFIRMED** (still true) |
| 4 | No VerdictStore; advisor imports PredictionStore directly | **CONFIRMED** |
| 5 | Global JSON singletons + duplicate watchlist concept | **CONFIRMED** |
| 6 | users.db FKs unenforced; portfolio "FK" = dir name; ghost dirs get autopilot | **CONFIRMED** |
| 7 | telemetry.db has no user attribution | **CONFIRMED** |

### #1 — Push subscribe → RESOLVED
- `services/api/routes/delivery_api.py:114-118` — handler takes only `subscription: dict` + `user: dict = Depends(get_current_user)`; client `user_id` param gone.
- `:127 count = store.add(subscription, user_id=user["user_id"])`; DELETE mirror `:136 PushStore().remove(endpoint, user_id=user["user_id"])`.
- Per-user cap `:106 _MAX_PUSH_SUBS_PER_USER = 50`, enforced `:124`.
- `PushStore` keyed per user `{user_id: [sub,...]}` (`core/delivery/channels.py:35-36`); `add`/`remove`/`list` all take `user_id` (`:61,:71,:82`).
- **Residual (by design):** each signature defaults `uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID` (`:62,:72,:83`) — the anonymous⇒owner single-user fallback. Last place a "default user" leaks into this store.

### #2 — chat_turns user binding → RESOLVED
- `chat_session_store.py:43 user_id TEXT NOT NULL DEFAULT 'primary'`; composite index `:48 (user_id, session_id, id)`.
- Online migration for legacy DBs `:69-71 ALTER TABLE chat_turns ADD COLUMN user_id ...` (legacy rows → `'primary'` = owner).
- Reads/writes scoped: `get_history` `:96-98 WHERE session_id=? AND user_id=?`; `append_turns` inserts user_id `:120-123` and **prunes scoped to (user_id, session_id)** `:130-133`; `has_session` `:142`.
- Call sites pass real session user: `ui_data.py` `chat` `:2920/:2943/:2969/:2999/:3005`, `chat_stream` `:3253/:3293/:3420`; helpers `:3098-3107`.
- **Residual:** store-layer default `user_id="primary"` remains (`:87,:106-108,:140`); TTL sweep is global `:153 DELETE ... WHERE ts < ?` (fine for TTL).

### #3 — No user_instruments join → CONFIRMED
- Holdings live only inside each user's `portfolio.json` (`core/portfolio/store.py:66`; `Portfolio.holdings` at `src/backend/shared/schemas/portfolio.py:86`).
- Only user-enumeration primitive is a directory scan: `core/portfolio/store.py:400-404 list_user_ids()` → dirs containing `portfolio.json`.
- "Which users hold TCS" = load **every** `data/portfolio/<uid>/portfolio.json` and scan holdings. `grep user_instruments` → 0 hits.
- `data/managed_tickers.json` (3 rows) **already carries** `origin`, `cadence`, `enabled`, `promoted_at` (populated only for promoted tickers) but **none** of Blueprint-1's demand fields (`holders`, `watchers`, `chat_hits_7d`, `last_analyzed`).

### #4 — No VerdictStore; advisor→PredictionStore direct → CONFIRMED
- `grep VerdictStore` → 0 matches.
- `core/portfolio/advisor.py:21 from core.intelligence.rl.stores.prediction_store import PredictionStore` — user-plane advisor reaches straight into the intelligence plane. Second reach-in `:176 from core.intelligence.rl.nse_calendar import is_trading_day` (lazy).
- **Exact surface the advisor consumes** (`build_signals`, `advisor.py:100-187`) against `core/intelligence/rl/stores/prediction_store.py`:

  | Advisor call (line) | Store signature (line) | Returns |
  |---|---|---|
  | `store.cycle_id_for(review_date)` (`:136,:157`) | `cycle_id_for(target: date) -> str` (`:129`) | `"{TICKER}_{YYYY-MM}"` |
  | `store.load_envelope(cid)` (`:136`) | `load_envelope(cycle_id=None) -> PredictionEnvelope\|None` (`:193`) | envelope or None |
  | `store.load_feedback_log(cid)` (`:157`) | `load_feedback_log(cycle_id=None) -> DailyFeedbackLog` (`:266`) | log (empty if missing) |

  Envelope attrs read (`advisor.py:137-151`): `daily_forecasts[].date/.predicted_close/.confidence`; `conviction_streak.reversion_prior`; `reforecast_history[-1].reason`.
  Feedback-log attrs read (`advisor.py:158-167`): `entries[].regime_label/.direction_correct/.thesis_review.thesis_intact`.
- Pipeline reaches in too: `pipeline.py:15-17` (get_price_history, is_trading_day, PredictionStore).

### #5 — Global singletons + duplicate watchlist → CONFIRMED
- Global JSON singletons under `data/`, read/written by `ui_data.py` with **no user scoping**:
  - `data/watchlist.json` — `ui_data.py:49`; reader `_load_watchlist` `:380`, also `:922/:1031/:1044`; writer PUT `:1048-1056` (owner-gated `require_owner` `:1050`, but the file is one global list).
  - `data/agent_weights.json` — `:45`; `_load_custom_weights` `:427`, `_save_custom_weights` `:446`, PUT `:657`.
  - `data/agent_tasks.json` — `:47`; `_load_agent_task_flags` `:392`, PUT `:1012`.
  - `data/category_tickers.json` — `:51`; reader `:1065`, writer PUT `:1097` (same class).
- **Duplicate watchlist — CONFIRMED.** Two unrelated "watchlists":
  1. Global `data/watchlist.json` = bare `list[str]` (`ui_data.py:230 _WATCHLIST_DEFAULT`, persist `:1056`).
  2. Per-user `Portfolio.watchlist` = `list[WatchlistItem]` (`src/backend/shared/schemas/portfolio.py:87`, `:76-81`); managed by `PortfolioStore.add_watchlist`/`remove_watchlist` (`core/portfolio/store.py:193-210`).
  They never reconcile: UI uses the global file; portfolio/advisor plane uses the per-user field. Same word, two stores, different shapes and tenancy.

### #6 — users.db FKs unenforced; dir-as-FK; ghost autopilot → CONFIRMED
- `services/data/stores/user_store.py` sets only `:87 PRAGMA journal_mode=WAL` — **no `PRAGMA foreign_keys`**, and schema `:36-67` has **no FK constraints**: `users.user_id` PK `:38`; `sessions.user_id` `:48`, `chat_usage.user_id` `:62`, `invites.created_by/used_by` `:56-59` all bare TEXT. Every cross-table user link is an unenforced string.
- `delete_user` `:169-175` hand-deletes sessions + chat_usage + users only. Does **not** touch portfolio dirs, chat_sessions.db rows, or push_subscriptions.json → single-transaction DPDP delete not met.
- Portfolio "FK" is a directory name: `core/portfolio/store.py:49 self._dir = ... / self.user_id`; only validation is regex `:35 ^[A-Za-z0-9_-]{1,64}$` (`:47`). No check that user_id exists in users.db.
- **Ghost-dir autopilot:** `core/portfolio/pipeline.py:39 users = list_user_ids()` → `:42 for user_id in users:` runs full advise→autopilot→deliver (`:97-99 rec.user_id`, `:201 emit_alerts(user_id=...)`, `:203-210 deliver(user_id=...)`). `list_user_ids()` never joins users.db → a deleted/never-registered dir still trades + delivers.

### #7 — telemetry.db no user attribution → CONFIRMED
- `services/data/stores/log_store.py`, DB `data/telemetry.db` (`:86`).
- `llm_calls` schema `:55-64` = `id, ts, caller, model, input_tokens, output_tokens, latency_ms, success` — **no user_id** (verified live: `PRAGMA table_info(llm_calls)` matches). `app_logs` `:68-74` = `id, ts, level, logger, message` — no user_id. Writer `log_llm_call` `:104-127` has no user param. Exactly Blueprint 4's gap.

---

## Part 2 — Store inventory

User linkage: **none / dir / column / file-key**.

| # | Store | Path | Engine | Keyed by | User link | Readers | Writers |
|---|---|---|---|---|---|---|---|
| 1 | Users/identity | `data/users.db` | SQLite WAL | `users.user_id` PK; `sessions.token_hash`; `chat_usage(user_id,day)`; `invites.code` | column (unenforced TEXT) | `user_store.py` (get_user `:163`, resolve_session `:194`, count_users `:159`); `services/api/auth.py` | create_user `:128`, create_session `:180`, consume_invite `:244`, bump_chat_usage `:256`, delete_user `:169` |
| 2 | Chat sessions | `data/chat_sessions.db` | SQLite WAL | `chat_turns.id`; queried `(user_id,session_id,id)` | column `user_id` (dflt `'primary'`) | `get_history` `:87`; `ui_data.py:3099` | `append_turns` `:106`; `sweep_expired` `:145`; `ui_data.py:3105` |
| 3 | Telemetry/logs | `data/telemetry.db` | SQLite WAL | `llm_calls.id`, `app_logs.id` | **none** | `log_store.py`; scheduler status | `log_llm_call` `:104`, `log_app_record` `:130`, `SQLiteLogHandler` `:146` |
| 4 | Score history | `data/scores.db` | SQLite | `score_history` (ticker+run) | **none** | `ScoreStore` (ui_data `:271`) | pipeline/aggregator |
| 5 | Push subs | `data/delivery/push_subscriptions.json` | JSON | `{user_id: [sub,...]}` | file-key user_id (dflt owner) | `PushStore.list/user_ids` `:82,:86`; `send_push` `:149` | `add` `:61`, `remove` `:71`; delivery_api `:127,:136` |
| 6 | Portfolio | `data/portfolio/<uid>/portfolio.json` | JSON (atomic+FileLock) | file per uid; `Portfolio.user_id` | dir = uid (no FK) | `PortfolioStore.load` `:103`; delivery_api; pipeline `:50` | `save` `:146`, add/remove_holding, add/remove_watchlist |
| 7 | Advice ledger | `data/portfolio/<uid>/advice_ledger.jsonl` | JSONL append | append; `AdviceRecord.user_id` | dir + record | `load_advice` `:219` | `append_advice` `:215`; pipeline `:102` |
| 8 | Transactions | `data/portfolio/<uid>/transactions.jsonl` | JSONL append | append; `TransactionRecord.user_id` | dir + record | `load_transactions` `:241` | `append_transaction` `:237`; autopilot |
| 9 | Value history | `data/portfolio/<uid>/value_history.jsonl` | JSONL append | append (points) | dir | `load_value_history` `:263` | `append_value_point` `:259` |
| 10 | Digests/briefs/weekly | `data/portfolio/<uid>/{digests,briefs,weekly}/<date>.json` | JSON | date filename | dir | `load_latest_*` `:301,:340,:348` | `save_*` `:296,:335,:343` |
| 11 | Managed tickers (universe) | `data/managed_tickers.json` | JSON list | `sym` | **none** (global) | `log_buffer.load_managed_tickers` `:148`; scheduler `:60`; ui_data `:3448,:1395` | `save_managed_tickers` `:153`; ui_data PUT/POST/DELETE/toggle `:3474,:3530,:3639,:3667` |
| 12 | Watchlist (global) | `data/watchlist.json` | JSON `list[str]` | single list | **none** | `_load_watchlist` `:380,:922,:1031` | PUT `:1048-1056` |
| 13 | Agent weights | `data/agent_weights.json` | JSON sector→{k:float} | sector | **none** | `_load_custom_weights` `:427` | `_save_custom_weights` `:446`; PUT `:657` |
| 14 | Agent tasks | `data/agent_tasks.json` | JSON | agent_key→{task:bool} | **none** | `_load_agent_task_flags` `:392` | PUT `:1012` |
| 15 | Category tickers | `data/category_tickers.json` | JSON | category | **none** | `_load_category_overrides` `:1065` | PUT `:1097` |
| 16 | RL PredictionStore | `data/predictions/<sector>/<ticker>/*.json` | JSON atomic | ticker + cycle_id `{TICKER}_{YYYY-MM}` | **none** (user-free) | `prediction_store.py` load_envelope `:193`, load_feedback_log `:266`; advisor `:136,:157` | save_envelope `:188`, save_feedback_log `:258`, archive_envelope `:208` |
| 17 | Monthly scorecard | `data/eval/scorecards/<YYYY-MM>_scorecard.json` | JSON | month | **none** | scorecard reporting (`schemas/scorecard.py:73,96`) | scorecard builder |
| 18 | Verdict shadow lane | `data/rl/verdict_shadow.jsonl` | JSONL append | append | **none** | `learning_evidence.py:394-397` | `verdict_shadow.py:47 log_verdict_shadow` (signal_aggregator `:195`) |
| 19 | Scheduler job outcomes | `data/scheduler_job_outcomes.json` | JSON | job key | **none** | `job_outcomes.py`; scheduler status | job_outcomes writer |
| 20 | Ops alerts state | `data/ops_alerts_state.json` | JSON | key | **none** | ops alert dedupe | ops alert emitter |
| 21 | Misc caches | `data/market_cache/`, `tavily_cache/`, `macro_news/`, `nse/`, `eod_store`, `yf_symbol_cache.json`, `self_heal_checkpoint_*.json`, `prompt_deploy_status.json` | JSON/dir | various | **none** | fetchers/eod_store/fallback_events/analysis_logger/api_usage | same |

**Do NOT exist today (0 hits):** `VerdictStore`, outbox table/store (BP2), `feedback_events` store (BP5), `cost_by_user_day` roll-up (BP4), `user_instruments` join.

---

## Part 3 — Fan-out & boundary specifics

### `list_user_ids()` call sites (def `core/portfolio/store.py:400`)
1. `core/portfolio/pipeline.py:39` — daily advise/autopilot/digest/delivery loop (`:42`). **No owner fallback** (empty when no dirs).
2. `core/delivery/brief.py:270` — `list_user_ids() or [PORTFOLIO_DEFAULT_USER_ID]` (morning brief).
3. `core/delivery/weekly.py:240` — same fallback (weekly review).
4. `core/delivery/index_watch.py:35` — same fallback (index-move alerts).

Inconsistency: pipeline has **no** owner fallback; the 3 delivery jobs do. All four fan out purely on directory presence, none join `users.db`.

### advisor → intelligence coupling (`core/portfolio/advisor.py`)
- `:21` PredictionStore (module-level); `:22 next_results_event` (data plane); `:176 is_trading_day` (lazy).
- `pipeline.py:15-17` also imports get_price_history, is_trading_day, PredictionStore.

### Intelligence plane is user-free (R1) → CONFIRMED
- `grep user_id|user` under `core/intelligence/**.py` returns **only** LLM-prompt tokens (`user_prompt` locals, `{"role":"user"}` dicts — e.g. `control_lane.py:42,58,110`; `feedback_agent.py:166,245`; `thesis_reviewer.py:181,229`). **Zero** tenant-identity references, no import of any user/portfolio/feedback store. PredictionStore keyed by ticker+cycle only (`prediction_store.py:105-119`). R1 holds.

---

## Part 4 — Constraints & counts

### Learning Constitution R1–R4 (`docs/SCALING_BLUEPRINTS.md:229-234`)
- **R1 Reward isolation** (`:231`): scorecards/duels/envelopes/regime-multipliers update from **market outcomes only**; no code path reads feedback events inside `core/intelligence/rl/`. Enforced by import-boundary test: `core/intelligence/rl/` must not import the feedback store.
- **R2 Aggregates as features, decisions by humans** (`:232`): feedback aggregates may rank universe / populate dashboards / flag rules for human review, but may **not** auto-adjust any weight/threshold/multiplier. "Aggregates land in reports, never in config."
- **R3 Aggregation floor** (`:233`): no feedback aggregate consumed until **≥20 distinct users** contribute (privacy boundary — no aggregate traceable to an individual). Floor constant in config; aggregator refuses below it.
- **R4 Standing bias audit** (`:234`): quarterly, compare override rates on losing vs winning positions; publish the number. Scheduled report, scorecard-email lane.
- Feedback Event shape (`:209-225`): append-only, tenant-scoped, physically outside RL stores — `ts, user_id, symbol, advice_id, verdict_shown, action(accepted|overridden|ignored), override_direction, position_state(winning|losing)`.

### SCALING_BLUEPRINTS.md — key blueprints
- **BP1 Dynamic Universe** (`:13-66`): analyzed universe = union of users' holdings ∪ watchlists ∪ discovery-shelf actives, recomputed nightly **in the intelligence plane** (`:45`). Extended `managed_tickers.json` adds `holders/watchers/chat_hits_7d/last_analyzed` (`:27-41`). Demand `= 3×holders + 1×watchers + 0.5×chat_hits_7d` (`:49`). Cadence tiers **daily/weekly/on_demand** (`:48-51`); `MAX_DAILY_ANALYSES` governor + 80% ops alert (`:52-54`). On-demand first-look → shared store → weekly tier (`:56-59`). Nothing deleted; `promotion.py` becomes one of three inputs (`:64-66`).
- **BP2 Delivery Outbox** (`:70-106`): fan-out → **outbox table** consumed by a separate worker. Columns `id, user_id, channel(push|email), kind(brief|digest|weekly|alert), payload_ref, dedupe_key, status, attempts, created_at, delivered_at` (`:89-91`). Idempotency `dedupe_key = user_id + kind + date` (`:92`); enqueue ~1ms/user (`:94`); retries `n≤3`, backoff `1m/5m/30m` (`:86,:91`); payloads are **references not blobs** (`:99-100`). At M1 the worker is a second Railway service sharing the DB (`:104-106`).
- **BP4 Per-User Cost Telemetry** (`:167-190`): additive `ALTER TABLE llm_calls ADD COLUMN user_id TEXT` nullable (`:175`); populate via `current_user_id: ContextVar[str|None]` set by auth middleware, read by `record_llm_call()` (avoids ~20 call sites) (`:177-180`). **Rule: `user_id = NULL` = "shared brain"** (scheduled analysis/ingestion/discovery); only chat, on-demand `/analyse`, and pre-cache narrator carry a user_id (`:181-186`). Nightly roll-up → `cost_by_user_day(date, user_id, calls, tokens, cost)` (`:187-190`) + per-user daily cost tripwire.
- **BP5 Feedback Events / user-free intelligence** (`:194-247`): market outcomes = unbiased labels; human behavior = biased → feedback is **input, never reward** (`:200-207`). Stored append-only, tenant-scoped, in the user plane, **physically outside RL stores** (`:224-225`), governed by R1–R4. Build-order (`:340`): schema ships whenever advice cards get accept/override UI.

### DPDP "delete = single transaction" (`docs/LEGAL_AND_COMPLIANCE.md` §2)
- `:69-70`: DPDP requires consent w/ purpose notice, purpose-limited use, **deletion on request**, breach notification.
- `:73-74`: a working "delete my account and data" path — per-user layout makes it easy: **one user_id scope to erase**.
- `:78`: push endpoints + email addresses are PII — **prune on logout/delete**.
- §5.2 (`:131-133`): every new table must carry and filter by user_id from day one.
- **Today NOT met:** `user_store.delete_user:169-175` clears only sessions/chat_usage/users — not portfolio dir, chat_sessions.db rows, or push_subscriptions.json. Layout enables it; no single delete transaction implements it.

### Actual data volume (live `data/`, counts only — no cash/secrets)
- **users.db:** users=0, sessions=0, invites=0 (schema exists, pre-first-signup).
- **portfolio dirs:** 1 (`primary`) — has `portfolio.json`, `advice_ledger.jsonl`, `digests/`; no transactions/value_history/briefs/weekly yet.
- **managed_tickers.json:** 3 (MARUTI, TCS, HDFCBANK), all `enabled:false`.
- **chat_sessions.db:** 24 chat_turns, 1 user_id, 2 session_ids.
- **telemetry.db:** llm_calls=1931, app_logs=14775 (~5.4MB + WAL); no user_id column.
- **predictions/:** 4 sectors populated (incl. test tickers `TESTSHOCK`/`ZZZNOPE`/`DOESNOTEXIST_TICKER_XYZ`).
- **scorecards:** 2 (`2026-05`, `2026-06`). **verdict_shadow.jsonl:** present under `data/rl/`.
- **This is a single-owner pre-user-#2 snapshot** (0 registered users, 1 `primary` dir). No multi-user backup exists (`analysis_data/` absent).

---

## Cross-cutting takeaways for the Designer

1. **The "default user" leak is now the last-mile issue, not a bug.** `PORTFOLIO_DEFAULT_USER_ID`/`'primary'` survive as single-user fallbacks in PushStore (`channels.py:62,72,83`), chat_session_store (`:87,106,140`), and delivery fan-out. M1 must decide: keep collapse-to-owner defaults, or make them hard failures once users.db is authoritative.
2. **Directory-as-PK is the structural gap.** `list_user_ids()` (dir scan) is the only user enumeration and drives all fan-out (`pipeline.py:39`, `brief.py:270`, `weekly.py:240`, `index_watch.py:35`) with no join to users.db — enabling ghost-dir autopilot and blocking single-transaction delete.
3. **Two watchlists, one name** — reconcile `data/watchlist.json` (global `list[str]`) vs `Portfolio.watchlist` (`list[WatchlistItem]`).
4. **Plane boundary is clean on the intelligence side** (user-free, R1 holds) but **breached from the user side** — advisor imports `PredictionStore` directly (`advisor.py:21`). A read-only accessor / `VerdictStore` seam restores the boundary without touching the RL plane.
5. **BP4 (telemetry user_id), BP2 (outbox), BP5 (feedback_events), and DPDP single-transaction delete are all greenfield** — zero code artifacts today.
