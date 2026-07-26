# M0 — Multi-User Foundation: Design Spec

**Date:** 2026-07-26 · **Status:** approved design, ready for implementation planning
**Program:** Scaling ([SCALING_VISION.md](../../SCALING_VISION.md) §5 phase M0;
blueprints in [SCALING_BLUEPRINTS.md](../../SCALING_BLUEPRINTS.md);
legal gates in [LEGAL_AND_COMPLIANCE.md](../../LEGAL_AND_COMPLIANCE.md))

> **For the implementing session (read this first):** this spec is written to be executed
> by a fresh Claude session with no prior conversation context. Every referenced file
> path, symbol, and behavior below was verified against the codebase on 2026-07-26.
> Re-verify with a quick read before editing — the repo moves fast. The
> **Guardrails** section is non-negotiable; read it before writing any code.

---

## 1. Goal

Make StockAgent safe for users #2–#10 (invite-only friends & family) at ~zero added cost:

1. **Real authentication** — accounts, sessions, invite codes; `user_id` derived
   server-side from the session, never from the client.
2. **Narrator cache** — kill the per-user×holding LLM leak; narration becomes
   per-(ticker, verdict-context, date).
3. **Chat quotas** — bound the only unbounded per-user LLM cost.
4. **Ops lockdown** — `SCHEDULER_KEY` set in Railway (user action, documented here).

Everything else (Postgres, delivery worker, semantic cache, dynamic universe, telemetry
user_id) is **M1 — explicitly out of scope** (see §8 Non-goals).

## 2. Verified current state (the map)

| Fact | Where |
|---|---|
| Portfolio layer is already per-user: `PortfolioStore(user_id=...)`; data lives in `data/portfolio/<user_id>/`; `list_user_ids()` enumerates | `core/portfolio/store.py` (user_id defaulting at line ~46, `list_user_ids` at ~401) |
| Default/owner user id is `"primary"` via `settings.PORTFOLIO_DEFAULT_USER_ID` | `core/config` settings (config.yaml-backed); documented in `CODEBASE.md` §env table |
| Pipelines loop `for user_id in list_user_ids()` | `core/portfolio/pipeline.py:39-42`, `core/delivery/brief.py:270-291` |
| Only auth today: optional `X-Scheduler-Key` header gate, **dormant until env var set**; logs a warning when open | `services/api/auth.py` (`check_scheduler_key`) |
| Login/Signup UI exists but is a **non-functional prototype** (no backend calls) | `src/frontend/prototypes/auth.jsx` |
| PWA fetch wrapper already attaches `X-Scheduler-Key` to same-origin API calls | `src/frontend/prototypes/index.html:107-123` |
| Narrator: per-holding LLM call on BULK tier; prompt embeds user-specific P&L/stop; deterministic `fallback_narrative()` exists; gated by `settings.ADVISOR_NARRATE` | `core/portfolio/narrator.py` (`narrate()` at ~64, prompt at ~43-52) |
| Chat endpoints: `POST /ui/chat` (plain) and `POST /ui/chat/stream` (SSE agentic loop, 45s turn budget from AUD-101) | `services/api/routes/ui_data.py` (~2908, ~3227) |
| Chat sessions: SQLite shared across the 2 uvicorn workers | `services/data/stores/chat_session_store.py`, `data/chat_sessions.db` |
| SQLite-on-volume is the proven shared-store pattern (chat sessions, telemetry, scores) | `data/*.db`; volume survives deploys |
| Atomic file writes utility (Wave F) | `core/utils/atomic_io.py` |
| Test suite baseline: run `pytest` before starting; record the fail-set; it must be **identical** after (A/B rule) | `tests/`, see `docs/` test strategy |

**Deployment reality (do not forget):** prod is a live Railway service running a real
autopilot portfolio on a schedule. Two uvicorn workers share one volume. Deploys restart
the scheduler.

## 3. Design decisions (with rationale — do not silently re-decide)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Identity store = SQLite on the volume (`data/users.db`), not Postgres** | Refines SCALING_VISION's "Postgres at M0." One service, 2 workers, ≤10 users: the chat-sessions SQLite pattern is proven here. Schema is written in portable SQL so the M1 Postgres move is a dump/load, not a rewrite. Zero new infra, zero new cost, zero new failure modes now |
| D2 | **Password hashing = stdlib `hashlib.scrypt`** (n=2^14, r=8, p=1, 16-byte per-user salt) | No new dependency; scrypt is memory-hard and in the stdlib. Store `scrypt$<params>$<salt-b64>$<hash-b64>` so params can evolve |
| D3 | **Session token = `secrets.token_urlsafe(32)`, stored SHA-256-hashed**, sent as `Authorization: Bearer <token>` | DB leak ≠ session leak (hashed at rest). Bearer header (not cookie) because the PWA already has exactly one fetch-wrapper to extend, and the service worker/TWA context makes cookie behavior less predictable |
| D4 | **Owner account maps to existing `user_id="primary"`** | All existing portfolio data, digests, and ledgers keep working with zero migration. First registered account (or env-designated email) gets `role='owner'`, `user_id='primary'` |
| D5 | **Signup requires an invite code** (owner-generated, single-use) | Friends-&-family gate per the legal doc — no open registration at M0 |
| D6 | **`user_id` comes ONLY from the session** on user-scoped routes; client-supplied user ids are ignored/rejected | This is the IDOR fix — the core security point of M0 (legal doc §5.1) |
| D7 | **Narrator: LLM narrates ticker-facts only; user numbers appended by template** | The prompt's user-specific fields (P&L, stop) are what force per-user calls today. Split: cache key = `(symbol, verdict, sorted(triggers), regime, date)`; deterministic suffix carries the user's numbers. O(users×holdings) → O(distinct verdict-contexts) |
| D8 | **Narrator cache store = `data/narrative_cache.json`**, day-keyed, written via `atomic_io`, in-process dict in front | Tiny (≤ universe size × few verdicts), rolls over daily, survives worker restarts; no DB needed |
| D9 | **Chat quota counts only real LLM turns** (L2 in blueprint terms), per user per IST day; owner exempt; `429` + friendly copy when exhausted | Quota is a cost bound, not a punishment; cached/free paths must never consume it |
| D10 | **Scheduler/internal jobs keep using `X-Scheduler-Key`**, not user sessions | Machine identity ≠ human identity; the existing dormant gate is correct for machines — it just needs the env var set |

## 4. Component designs

### 4.1 Identity store — `services/data/stores/user_store.py` (new)

SQLite at `data/users.db`, same connection/locking pattern as
`services/data/stores/chat_session_store.py` (copy its WAL + threading approach).

```sql
CREATE TABLE IF NOT EXISTS users (
  user_id     TEXT PRIMARY KEY,          -- 'primary' for owner; 'u_' + 8 hex for others
  email       TEXT NOT NULL UNIQUE,      -- stored lowercase
  pw_hash     TEXT NOT NULL,             -- 'scrypt$n=16384,r=8,p=1$<salt_b64>$<hash_b64>'
  display_name TEXT NOT NULL DEFAULT '',
  role        TEXT NOT NULL DEFAULT 'member',   -- 'owner' | 'member'
  created_at  TEXT NOT NULL,
  consent_at  TEXT NOT NULL               -- DPDP: signup consent timestamp
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY,          -- sha256 hex of the bearer token
  user_id     TEXT NOT NULL REFERENCES users(user_id),
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,             -- +30d if remember_me else +24h
  last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
  code        TEXT PRIMARY KEY,          -- 'inv_' + token_urlsafe(8)
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  used_by     TEXT,                      -- NULL until consumed (single-use)
  used_at     TEXT
);
CREATE TABLE IF NOT EXISTS chat_usage (
  user_id     TEXT NOT NULL,
  day         TEXT NOT NULL,             -- IST date 'YYYY-MM-DD'
  llm_turns   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);
```

API of the module (all functions never raise on storage failure — log and degrade,
matching house style): `create_user`, `verify_password`, `create_session`,
`resolve_session(token) -> user | None` (also bumps `last_seen`, rejects expired),
`revoke_session`, `create_invite`, `consume_invite`, `bump_chat_usage(user_id, day) -> int`,
`get_chat_usage`, `sweep_expired_sessions` (called from the existing startup sweep site in
`services/api/server.py` next to the chat-session sweep).

### 4.2 Auth routes — `services/api/routes/auth_api.py` (new)

| Route | Contract |
|---|---|
| `POST /auth/signup` | `{email, password, display_name, invite_code, remember_me, consent: true}` → validates invite (single-use, unused), password ≥ 10 chars, consent must be `true` (DPDP) → creates user + session → `{token, user: {user_id, email, display_name, role}}`. First-ever user (empty users table) needs no invite and becomes `role='owner', user_id='primary'` |
| `POST /auth/login` | `{email, password, remember_me}` → constant-time verify → `{token, user}`. Generic 401 on bad email *or* password (no user enumeration) |
| `POST /auth/logout` | Bearer token → revoke session → `{ok: true}` |
| `GET /auth/me` | Bearer token → `{user}` or 401. The PWA calls this at boot to restore Remember-me state |
| `POST /auth/invites` | **Owner only** → creates invite code → `{code}`. `GET /auth/invites` lists codes + used state |

Plus `DELETE /auth/account` (self-service, DPDP): revokes sessions, deletes user row, and
removes `data/portfolio/<user_id>/` (owner cannot delete own account — safety).

### 4.3 Auth dependency — extend `services/api/auth.py`

```python
async def get_current_user(authorization: str | None = Header(None)) -> User:
    # parse "Bearer <token>" → user_store.resolve_session(sha256(token))
    # raise 401 if missing/invalid/expired
async def get_current_user_optional(...) -> User | None:
    # same, but returns None instead of raising — for mixed-mode M0 routes
```

**Rollout mode (critical for not breaking the live PWA + scheduler):** a new setting
`AUTH_REQUIRED` (default **false** at merge time). When false, `get_current_user_optional`
returns the owner (`primary`) for anonymous requests — exactly today's behavior, so the
deploy is a no-op until the owner has created their account in prod. When flipped to true
(env var, no code change — same pattern as SCHEDULER_KEY), anonymous user-scoped requests
get 401 and the PWA shows the login screen. **Wiring:** user-scoped routes (portfolio
read/write, chat, delivery-test, watchlist) take the dependency and use
`user.user_id` — **deleting every code path where a client-supplied user id or the
default was trusted** on those routes. Scheduler-internal routes keep
`check_scheduler_key` only.

### 4.4 Narrator cache — `core/portfolio/narrative_cache.py` (new) + `narrator.py` changes

- New prompt (in `narrator.py`): remove `Unrealised P&L` and `Stop level` lines — the LLM
  writes 2–3 sentences about **the ticker-level why** (verdict, close, regime, triggers,
  notes). These are exactly the fields shared by every user in the same verdict context.
- Cache key: `sha256(symbol | verdict | ",".join(sorted(triggers)) | ",".join(sorted(notes)) | regime_label | ist_date)`.
- `narrate(rec, signals)` becomes: build key → hit? return cached ticker-narrative +
  `_user_suffix(rec)` → miss? one LLM call, store, same return. Fallback path unchanged.
- `_user_suffix(rec)` (deterministic, no LLM):
  `f" Your position: {rec.unrealised_pnl_pct:+.1f}% vs a {rec.stop_pct:.1f}% stop."`
- Store: `data/narrative_cache.json` `{date: {key: narrative}}`; prune entries older than
  2 days on write; `atomic_io` for writes; module-level dict cache in front (the pipeline
  runs inside one process). Cache failures degrade to calling the LLM — never block.
- Result at M0 scale: with 2 users holding overlapping stocks, overlapping holdings cost
  1 call instead of 2. At 1,000 users: ~universe-sized calls/day instead of ~15,000.

### 4.5 Chat quotas — changes in `services/api/routes/ui_data.py`

- Settings: `CHAT_DAILY_QUOTA` (default **30**; `0` = unlimited). Owner role always
  unlimited.
- In `POST /ui/chat` and `POST /ui/chat/stream`: resolve user (auth dependency);
  before entering the LLM path, `bump_chat_usage` and compare. Over quota → plain route
  returns `429 {"error": "daily_quota", "detail": "You've used your 30 assistant
  questions for today — resets at midnight IST."}`; stream route emits one SSE `error`
  event with the same payload, then closes.
- Count **one turn = one user message that reaches the LLM loop**, not per internal
  tool-call fan-out (a 30-call agentic turn is still 1). Refunds on turn failure are not
  attempted (simplicity; failures are rare and quota is generous).
- IST day boundary must use the existing IST date helper used by chat session awareness
  (do not roll a new timezone conversion).

### 4.6 Frontend — `src/frontend/prototypes/auth.jsx` + `index.html`

- Wire the existing login/signup card to `/auth/login`, `/auth/signup` (add invite-code
  field + consent checkbox with a one-line purpose notice, per DPDP).
- Token storage: `localStorage['sa_auth_token']` (remember-me) else `sessionStorage`.
- Extend the Wave-B fetch wrapper (`index.html:107-123`) to also attach
  `Authorization: Bearer <token>` when present; on any 401 response, clear token and
  route to the auth screen.
- Boot flow: token present → `GET /auth/me` → restore session or show login. Preserve the
  existing deep-link hash (`/#/inbox/...`) across the login redirect — notification taps
  must still land on the Inbox after auth (don't regress the 2026-07-24 deep-link work).
- Show remaining chat quota in the chat UI when a 429 arrives (friendly copy, reset time).

### 4.7 Ops (user actions, not code — document in the plan's final report)

1. Set `SCHEDULER_KEY` in Railway (flips the dormant Wave-B gate to enforced; PWA
   wrapper already sends it).
2. After deploy: owner signs up first (becomes `primary`), generates invites.
3. Flip `AUTH_REQUIRED=true` in Railway once owner login is verified on the real phone.

## 5. Error handling summary

- Storage failures in `user_store` / narrative cache: log warning, degrade (auth storage
  failure → 503 on auth routes, never a silent open door; narrative cache failure → LLM
  call as today; quota-store failure → allow the turn, log loudly — availability over
  strict metering at M0).
- Auth failures: 401 with generic detail; no user enumeration; scrypt verify is
  constant-time compare (`hmac.compare_digest`).
- All new code follows house style: non-fatal, telemetry-first, `never raises` on the
  hot path.

## 6. Testing

- **New file `tests/test_m0_foundation.py`** (follow the per-phase test-file convention):
  user_store CRUD + password round-trip + session expiry + invite single-use; signup/login/
  me/logout via FastAPI TestClient; IDOR test (member A cannot read B's portfolio;
  anonymous 401 when `AUTH_REQUIRED=true`, owner-passthrough when false); narrator cache
  (second call with same context = no LLM client invocation — assert via mock; different
  P&L same context = cache hit + differing suffix); quota (31st turn → 429; owner exempt;
  L0-style non-LLM path doesn't consume — if L0 short-circuit exists at test time).
- **A/B rule:** run the full suite before first change, record pass/fail set; after
  implementation the fail-set must be **identical** plus the new file green.
- Playwright e2e (headless, existing harness from the deep-links work): signup → login →
  chat → logout happy path. Optional but preferred.

## 7. Acceptance criteria

1. With `AUTH_REQUIRED` unset/false: prod behavior byte-identical for the owner flow
   (briefs, autopilot, chat) — verified by the A/B fail-set and a manual smoke.
2. Owner can sign up (first user), gets `user_id='primary'`, sees existing portfolio.
3. Invited member can sign up only with a valid unused code; sees an **empty** portfolio,
   never `primary`'s (IDOR test green).
4. `AUTH_REQUIRED=true`: anonymous API calls to user-scoped routes → 401; PWA shows login;
   deep-links survive the login round-trip.
5. Narrator: for two users holding the same stock with the same verdict context, exactly
   one LLM call is made per day (observable in `telemetry.db` caller
   `portfolio_narrator`), and each user's digest shows their own P&L suffix.
6. Member hitting quota gets the friendly 429; owner never does; next IST day resets.
7. Suite fail-set identical; no new secrets in the repo; no prod endpoint/cash specifics
   in committed files.

## 8. Non-goals (M0 explicitly does NOT include)

Postgres migration · delivery worker/outbox · semantic chat cache · dynamic universe ·
`user_id` in telemetry.db · feedback events · billing · password reset by email (owner
re-invites at M0 scale) · rate limiting beyond chat quota · multi-user autopilot
(**autopilot stays owner-only — legal red line**, see LEGAL_AND_COMPLIANCE.md §1).

## 9. Guardrails for the implementing session (NON-NEGOTIABLE)

1. **Prod is live.** A real portfolio trades on a schedule. **Never push to main between
   16:25–17:15 IST on NSE trading days** (weekends fine). Deploys restart the scheduler.
2. **Public repo.** No secrets, ever (env vars only); no prod endpoint URLs or portfolio
   cash figures in committed files. If a secret ever lands in a commit — stop, tell the
   user, rotate the key; history removal is not sufficient.
3. **A/B test discipline.** Full-suite fail-set before any change, identical after
   (plus new tests green). If the baseline itself is red in new ways, stop and report.
4. **JSON-mode rule:** any new LLM call using JSON output must pass
   `response_format={"type": "json_object"}` **and** `extra_body=JSON_MODE_EXTRA_BODY`
   (see `services/clients/llm_client.py`) — this rule currently holds at 100% of call
   sites; keep it that way. (M0 adds no new LLM calls; the narrator keeps its existing
   pattern.)
5. **Don't touch the intelligence plane.** No changes under `core/intelligence/`,
   `services/scheduler/` beyond what this spec names. The shadow lane
   (`data/rl/verdict_shadow.jsonl`) is a live experiment ripening for a 2026-07-31
   decision — nothing may perturb it.
6. **`AUTH_REQUIRED` defaults false** so the merge deploy is a behavioral no-op. The flip
   is an ops action by the user, after phone verification. Do not default it true.
7. **House style:** non-fatal degradation, `record_llm_call` telemetry on every LLM path,
   atomic writes via `core/utils/atomic_io.py`, match existing module docstring headers.
8. Commits reference this spec; work on a branch; merge only with the suite green.
