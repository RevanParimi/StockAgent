# Atlas — User-Data ↔ Central-Intelligence Program Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This is a multi-session program** — check the ✅ marks and the memory file `project_user_data_program.md` to see where the previous session stopped. Never leave a task half-done: a task is either not started, or completed through its commit step.

**Goal:** Close the two user-data privacy bugs that must land before user #2 exists (Phase A), then design and build the real relational mapping between the user plane and the central intelligence plane — proper PK/FK schema, `user_instruments` join, Verdict Store interface, migration path (Phases B/C).

**Architecture:** Phase A is two surgical fixes in the existing SQLite/JSON stores (session-bound push subscriptions; user-bound chat sessions). Phase B is a design program (3-agent loop: Researcher → Designer → Reviewer, per the user's standing preference) producing the M1 data-architecture spec — ERD, DDL, migration plan, plane-boundary API. Phase C implements that approved design in waves. Analysis that motivated this program: session 2026-07-26 audit of every persistent store (summarized in §Background below).

**Tech Stack:** Python 3.11+ stdlib (`sqlite3`), FastAPI, existing `services/api/auth.py` dependencies (`get_current_user`, `require_owner`), pytest. Phase C stack (Postgres vs volume-SQLite) is a Phase B design decision — do not presume.

## Global Constraints

- **Prod is live** (real scheduled autopilot). Never push to main 16:25–17:15 IST on NSE trading days; weekends fine.
- **Public repo:** no secrets, no prod endpoint URLs, no portfolio cash figures in committed files.
- **A/B rule:** capture the full `pytest -q` fail-set before each phase's first change; identical after (plus new tests green). Known pre-existing red baseline: 10 FAILED + 10 ERROR in `test_phase0_llm_migration.py` / `test_orchestrator.py` / `test_phase2_api.py` / `test_event_ingestor.py` (network-flaky area; one transient extra failure has been observed there — re-run before concluding a new failure is real).
- Do not modify `core/intelligence/` internals or `services/scheduler/`; do not touch `data/rl/verdict_shadow.jsonl` (live experiment). **The intelligence plane must never gain user references** (Learning Constitution R1, `docs/SCALING_BLUEPRINTS.md` Blueprint 5).
- All business tunables via `cfg("section.key", env=..., fallback=...)` in `src/backend/shared/config/settings/base.py` — never hardcoded literals.
- House style: hot paths never raise (log + degrade); atomic writes via `core/utils/atomic_io.py`; module docstring headers.
- Auth posture (M0/M0.1, already shipped): identity ONLY from bearer session via `get_current_user` / `require_owner` (`services/api/auth.py`); `AUTH_REQUIRED=false` ⇒ anonymous = owner passthrough (single-user/local compat); browsers never carry `SCHEDULER_KEY`. Tests: `tests/conftest.py` autouse `_auth_defaults` pins `AUTH_REQUIRED=False` and unsets `SCHEDULER_KEY` — enforcement tests set them explicitly.
- One branch per phase (`atlas-a`, `atlas-b`, …); conventional commits; merge only with suite green; deploy verification by curl status-code probes (never dump user data).

## Background (why — from the 2026-07-26 store audit)

| Finding | Where |
|---|---|
| `POST /delivery/push/subscribe` is keyless AND takes client `user_id` → anyone can attach a device to any user's pushes; `PushStore.add` defaults to `primary` → user #2's phone would receive the owner's brief | `services/api/routes/delivery_api.py` (~line 113), `core/delivery/channels.py:61` |
| `chat_sessions.db` has no `user_id` — chat memory is session-keyed only; any user (or the quota of one user) can continue another's conversation by session_id | `services/data/stores/chat_session_store.py` (schema line ~39), `services/api/routes/ui_data.py:3098-3105` |
| No `user_instruments` join — "which users hold TCS" requires opening every `data/portfolio/<uid>/portfolio.json`; nothing refcounts universe demotion | `core/portfolio/store.py`, `data/managed_tickers.json` |
| Verdict Store (plane boundary keyed `(ticker, date)`) designed in `docs/SCALING_VISION.md` §4 but does not exist; advisor imports `PredictionStore` directly | `core/portfolio/advisor.py:21` |
| Global singletons shared by all users: `data/watchlist.json`, `agent_weights.json`, `agent_tasks.json` (duplicate/conflicting with per-user `portfolio.json watchlist[]`) | `services/api/routes/ui_data.py` |
| `users.db` FKs are unenforced strings; portfolio "FK" is a directory name; ghost dirs still get autopilot via `list_user_ids()` | `services/data/stores/user_store.py`, `core/portfolio/pipeline.py:40` |
| `telemetry.db` has no user attribution (designed: Blueprint 4) | `docs/SCALING_BLUEPRINTS.md` |

---

# PHASE A — Pre-user-#2 privacy fixes (branch `atlas-a`)

> ✅ **PHASE A COMPLETE — 2026-07-26.** Shipped as merge `e9c17fe` (A1 `5f15b4e`,
> A2 `89be3a3`). Full-suite A/B: post-change fail-set IDENTICAL to the A0
> baseline known-red set (10 FAILED + 10 ERROR in the network-flaky
> orchestrator/phase2_api/event_ingestor area), zero Atlas failures, all 8 new
> Atlas tests green. Deployed: Railway deployment `d8217787` = SUCCESS on
> `e9c17fe`, service Online. Prod probes (AUTH_REQUIRED=true): `POST
> /delivery/push/subscribe` (no auth) → 401, `GET /auth/me` (no auth) → 401.
> Deploy-safety verified: the owner account's user_id IS `primary` and the PWA
> fetch-wrapper auto-attaches the bearer token, so push-subscribe is a
> behavioral no-op for the owner and only isolates a future user #2.
> Implementation note: A2's DB migration runs `ALTER TABLE` *before*
> `executescript(_SCHEMA)` (plan had it after) so the new user_id index does not
> reference a not-yet-existing column on a legacy index-less DB.

### Task A0: Baseline

**Files:** none (verification only)

- [x] **Step 1: Branch + baseline**

```bash
git checkout main && git pull --ff-only
git checkout -b atlas-a
python -m pytest -q 2>&1 | tail -5
```

Record pass/fail/skip counts and the FAILED/ERROR ids to a scratch note. Expected shape: ~2124 passed / 12 skipped / 10 failed + 10 errors (the known-red set in Global Constraints). New unexplained failures ⇒ stop and report.

---

### Task A1: Push subscriptions bind to the session user

**Files:**
- Modify: `services/api/routes/delivery_api.py` (push_subscribe ~113, push_unsubscribe ~130)
- Test: `tests/unit/test_atlas_push_binding.py`

**Interfaces:**
- Consumes: `get_current_user` (`services/api/auth.py`), `PushStore` (`core/delivery/channels.py` — `add(subscription, user_id)`, `remove(endpoint, user_id)`, `list(user_id)`)
- Produces: `POST /delivery/push/subscribe` and `DELETE /delivery/push/subscribe` that ignore any client-supplied user identity and use the session's `user["user_id"]`. Anonymous behavior follows `AUTH_REQUIRED` (false ⇒ owner-passthrough, preserving today's single-user flow; true ⇒ 401).

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_atlas_push_binding.py`:

```python
"""Atlas A1 — push subscriptions bind to the session user (not client input).

Pre-fix, /delivery/push/subscribe was keyless and took ?user_id= from the
client; every un-attributed device landed under 'primary' → user #2's phone
would receive the owner's briefs.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


SUB = {"endpoint": "https://push.example.com/x1", "keys": {"p256dh": "k", "auth": "a"}}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    import core.delivery.channels as channels
    monkeypatch.setattr(channels.PushStore, "PATH",
                        tmp_path / "push_subscriptions.json", raising=False)
    # If PushStore's path is an instance/module attr with a different name,
    # read core/delivery/channels.py:35-60 and patch the actual attribute.
    from services.api.routes.auth_api import router as auth_router
    from services.api.routes.delivery_api import router as delivery_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(delivery_router)
    c = TestClient(app)
    tok_owner = c.post("/auth/signup", json={
        "email": "o@x.com", "password": "hunter2longer", "display_name": "O",
        "invite_code": None, "remember_me": True, "consent": True}).json()["token"]
    inv = c.post("/auth/invites",
                 headers={"Authorization": f"Bearer {tok_owner}"}).json()["code"]
    tok_member = c.post("/auth/signup", json={
        "email": "m@x.com", "password": "hunter2longer", "display_name": "M",
        "invite_code": inv, "remember_me": True, "consent": True}).json()["token"]
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {tok_member}"}).json()
    return c, tok_member, me["user"]["user_id"], channels


def test_member_sub_lands_under_member_id(env):
    c, tok, member_id, channels = env
    r = c.post("/delivery/push/subscribe", json=SUB,
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    store = channels.PushStore()
    assert [s["endpoint"] for s in store.list(user_id=member_id)] == [SUB["endpoint"]]
    assert store.list(user_id="primary") == []          # NOT under the owner


def test_client_user_id_param_is_ignored(env):
    c, tok, member_id, channels = env
    r = c.post("/delivery/push/subscribe?user_id=primary", json=SUB,
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert channels.PushStore().list(user_id="primary") == []


def test_anonymous_401_when_auth_required(env, monkeypatch):
    c, _, _, _ = env
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    assert c.post("/delivery/push/subscribe", json=SUB).status_code == 401


def test_unsubscribe_scoped_to_session_user(env):
    c, tok, member_id, channels = env
    c.post("/delivery/push/subscribe", json=SUB,
           headers={"Authorization": f"Bearer {tok}"})
    r = c.request("DELETE",
                  f"/delivery/push/subscribe?endpoint={SUB['endpoint']}",
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["removed"] is True
    assert channels.PushStore().list(user_id=member_id) == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_atlas_push_binding.py -q`
Expected: `test_member_sub_lands_under_member_id` and `test_client_user_id_param_is_ignored` FAIL (subs land under `primary`); 401 test FAILS (route is open).
(If the fixture's `PushStore` path-patch errors, first read `core/delivery/channels.py:35-60` for the real path attribute and fix the fixture — then confirm the *behavioral* failures above.)

- [x] **Step 3: Fix the routes**

In `services/api/routes/delivery_api.py`, replace both handlers:

```python
# Session-bound (Atlas A1): the device belongs to whoever is logged in.
# AUTH_REQUIRED=false keeps the single-user flow (anonymous ⇒ owner).
@router.post("/push/subscribe", summary="Store a web-push subscription")
async def push_subscribe(
    subscription: dict,
    user: dict = Depends(get_current_user),
) -> dict:
    endpoint = subscription.get("endpoint")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://")):
        raise HTTPException(status_code=422,
                            detail="subscription.endpoint must be an https:// URL")
    store = PushStore()
    if len(store.list(user_id=user["user_id"])) >= _MAX_PUSH_SUBS_PER_USER:
        raise HTTPException(status_code=429,
                            detail="Subscription limit reached for this user.")
    count = store.add(subscription, user_id=user["user_id"])
    return {"status": "subscribed", "subscriptions": count}


@router.delete("/push/subscribe", summary="Remove a web-push subscription")
async def push_unsubscribe(
    endpoint: str = Query(...),
    user: dict = Depends(get_current_user),
) -> dict:
    removed = PushStore().remove(endpoint, user_id=user["user_id"])
    return {"removed": removed}
```

Also update the comment above them (the "keyless BY DESIGN" note is now wrong):
`# Session-bound (Atlas A1). Public-key GET below stays open — it's a public key.`

- [x] **Step 4: Run the new tests + existing delivery tests**

Run: `python -m pytest tests/unit/test_atlas_push_binding.py tests/unit/test_delivery_api.py -q`
Expected: all PASS. If an existing delivery test posted subscriptions anonymously with `?user_id=`, update it to the session pattern and note it in the commit message.

- [x] **Step 5: Commit**

```bash
git add services/api/routes/delivery_api.py tests/unit/test_atlas_push_binding.py tests/unit/test_delivery_api.py
git commit -m "fix(atlas-a1): push subscriptions bind to session user — client user_id removed (privacy)"
```

---

### Task A2: Chat sessions bind to the user

**Files:**
- Modify: `services/data/stores/chat_session_store.py` (schema + `get_history` + `append_turns` + `has_session`)
- Modify: `services/api/routes/ui_data.py` (`_session_history_get` ~3098, `_session_history_append` ~3103, and their 5 call sites at ~2943/2969/2999/3005/3291)
- Test: `tests/unit/test_atlas_chat_user_binding.py`

**Interfaces:**
- Consumes: user dicts from `get_current_user` (both chat endpoints already resolve `user`).
- Produces: `get_history(session_id, max_messages, user_id="primary")`, `append_turns(session_id, user_text, assistant_text, max_messages, user_id="primary")`, `has_session(session_id, user_id="primary")` — history reads/writes scoped to `(user_id, session_id)`. Legacy rows (pre-migration) carry `user_id='primary'` via column default, so the owner keeps their history.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_atlas_chat_user_binding.py`:

```python
"""Atlas A2 — chat history is scoped (user_id, session_id): one user can
never read or extend another user's conversation, even with a stolen/guessed
session_id. Legacy rows default to 'primary' so the owner keeps history."""
import pytest

import services.data.stores.chat_session_store as css


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH",
                        str(tmp_path / "chat.db"), raising=False)
    css._reset_for_tests()
    yield
    css._reset_for_tests()


def test_same_session_id_isolated_between_users():
    css.append_turns("s1", "owner-question", "owner-answer", 12, user_id="primary")
    css.append_turns("s1", "member-question", "member-answer", 12, user_id="u_mem")
    owner = [m["content"] for m in css.get_history("s1", 12, user_id="primary")]
    member = [m["content"] for m in css.get_history("s1", 12, user_id="u_mem")]
    assert owner == ["owner-question", "owner-answer"]
    assert member == ["member-question", "member-answer"]


def test_default_user_is_primary_for_legacy_callers():
    css.append_turns("s2", "q", "a", 12)                       # no user_id arg
    assert [m["content"] for m in css.get_history("s2", 12)] == ["q", "a"]
    assert css.get_history("s2", 12, user_id="u_other") == []


def test_migration_adds_column_to_existing_db(tmp_path, monkeypatch):
    # Simulate a pre-Atlas DB: create the OLD schema, then reopen via the store.
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE chat_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, ts TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL);
    """)
    conn.execute("INSERT INTO chat_turns (session_id, ts, role, content)"
                 " VALUES ('legacy', '2026-01-01T00:00:00+00:00', 'user', 'old-q')")
    conn.commit(); conn.close()
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH", str(db), raising=False)
    css._reset_for_tests()
    # Old rows are owned by 'primary'; new writes work with explicit users.
    assert [m["content"] for m in css.get_history("legacy", 12)] == ["old-q"]
    css.append_turns("legacy", "new-q", "new-a", 12, user_id="u_new")
    assert [m["content"] for m in css.get_history("legacy", 12, user_id="u_new")] \
        == ["new-q", "new-a"]


def test_has_session_scoped():
    css.append_turns("s3", "q", "a", 12, user_id="u_a")
    assert css.has_session("s3", user_id="u_a") is True
    assert css.has_session("s3", user_id="u_b") is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_atlas_chat_user_binding.py -q`
Expected: FAIL with `TypeError: append_turns() got an unexpected keyword argument 'user_id'`

- [x] **Step 3: Implement in `chat_session_store.py`**

(a) Schema block gains the column (fresh DBs):

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id    TEXT NOT NULL DEFAULT 'primary',
    ts         TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_turns_session ON chat_turns (user_id, session_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_turns_ts ON chat_turns (ts);
"""
```

(b) In `_get_conn()`, after `conn.executescript(_SCHEMA)`, migrate existing DBs (Atlas A2 — legacy rows become the owner's):

```python
        try:                       # Atlas A2: add user_id to pre-existing DBs
            conn.execute("ALTER TABLE chat_turns ADD COLUMN"
                         " user_id TEXT NOT NULL DEFAULT 'primary'")
            conn.commit()
        except sqlite3.OperationalError:
            pass                   # column already exists
```

(c) Scope the three functions (keyword arg keeps every legacy caller working):

```python
def get_history(session_id: str, max_messages: int, user_id: str = "primary") -> list[dict]:
    """Return the last `max_messages` turns for this user's session, oldest first."""
    try:
        conn = _get_conn()
        if conn is None or not session_id:
            return []
        with _lock:
            rows = conn.execute(
                "SELECT role, content FROM chat_turns"
                " WHERE session_id = ? AND user_id = ?"
                " ORDER BY id DESC LIMIT ?",
                (session_id, user_id, int(max_messages)),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    except Exception as exc:
        logger.warning("[chat_session_store] read failed (non-fatal): %s", exc)
        return []
```

`append_turns(session_id, user_text, assistant_text, max_messages, user_id="primary")`: add `user_id` to both INSERTs (`(session_id, user_id, ts, role, content) VALUES (?, ?, ?, 'user', ?)` etc.) and add `AND user_id = ?` to the prune DELETE's outer WHERE and inner SELECT. `has_session(session_id, user_id="primary")` forwards: `return bool(get_history(session_id, 1, user_id=user_id))`.

(d) In `ui_data.py`, thread the user through the helpers and all 5 call sites:

```python
def _session_history_get(session_id: str, user_id: str = "primary") -> list[dict]:
    from services.data.stores.chat_session_store import get_history
    return get_history(session_id, _SESSION_MAX_TURNS, user_id=user_id)


def _session_history_append(session_id: str, user_text: str,
                            assistant_text: str, user_id: str = "primary") -> None:
    from services.data.stores.chat_session_store import append_turns
    append_turns(session_id, user_text, assistant_text, _SESSION_MAX_TURNS,
                 user_id=user_id)
```

Call sites (both endpoints already have `user` in scope): `_session_history_get(session_id, user["user_id"])` at ~2943 and ~3291; `_session_history_append(session_id, message, reply, user["user_id"])` at ~2969/2999/3005 (in `chat_stream`'s generator the variable is `final_text` — pass `user["user_id"]` there too, ~3382).

- [x] **Step 4: Run new + existing chat tests**

Run: `python -m pytest tests/unit/test_atlas_chat_user_binding.py tests/unit/test_chat_session_memory.py tests/unit/test_chat_turn_budget.py tests/unit/test_m0_chat_quota.py -q`
Expected: all PASS (legacy tests pass because the default arg is `'primary'` and their direct calls use the owner user).

- [x] **Step 5: Commit**

```bash
git add services/data/stores/chat_session_store.py services/api/routes/ui_data.py tests/unit/test_atlas_chat_user_binding.py
git commit -m "fix(atlas-a2): chat history scoped (user_id, session_id) — cross-user session reuse isolated"
```

---

### Task A3: Phase-A close-out — A/B, merge, deploy, prod verify

- [x] **Step 1: Full-suite A/B** — `python -m pytest -q 2>&1 | tail -5`; fail-set must equal the A0 baseline (re-run once before treating a new network-area failure as real).
- [x] **Step 2: Merge + push** (deploy-window check first: not 16:25–17:15 IST on a trading day):

```bash
git checkout main && git merge --no-ff atlas-a -m "merge: Atlas Phase A — push-sub + chat-session user binding (pre-user-#2 privacy)"
git diff --stat atlas-a HEAD   # MUST be empty
git push origin main && git branch -d atlas-a
```

- [x] **Step 3: Watch deploy** — `railway deployment list --json` until SUCCESS on the merge commit.
- [x] **Step 4: Prod probes (status codes only):**

```bash
BASE="https://stockagent-ai.up.railway.app"
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" \
  -d '{"endpoint":"https://x/y"}' "$BASE/delivery/push/subscribe"        # expect 401
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/auth/me"                  # expect 401
```

- [x] **Step 5: Update memory** — mark Phase A DONE in `project_user_data_program.md` (+ MEMORY.md hook), including deploy commit hash and probe results.

---

# PHASE B — M1 data-architecture design (3-agent loop) (branch `atlas-b`, docs only)

**Deliverable:** `docs/superpowers/specs/YYYY-MM-DD-m1-data-architecture-design.md` — approved by the user — plus Phase C tasks appended to THIS plan file (that appending is Task B4's explicit output, with full code per task, same rigor as Phase A).

### Task B1: Researcher pass

- [x] Re-verify the §Background findings against current code (repo moves fast) and produce a research memo covering, at minimum: every persistent store + its key + its user linkage; every reader/writer of `portfolio.json`, `managed_tickers.json`, global `watchlist.json`; every place `list_user_ids()` drives fan-out; advisor's exact `PredictionStore` surface (`load_envelope`, `cycle_id_for` at `core/portfolio/advisor.py:104-160`); current row/file counts from a prod backup if available. Save as `docs/superpowers/research/2026-XX-XX-atlas-data-research.md`. Commit. — **DONE 2026-07-26** → `docs/superpowers/research/2026-07-26-atlas-data-research.md`. Findings #1/#2 RESOLVED (Phase A); #3–#7 CONFIRMED still-open; full store inventory (21 stores) + `list_user_ids()` fan-out map + advisor↔PredictionStore surface + R1–R4 + BP1/2/4/5 + DPDP delete gap + live data counts (0 users, 1 `primary` dir, 3 managed tickers, telemetry no user_id).

### Task B2: Designer pass

- [x] **DONE 2026-07-26** → `docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md` (787→~830 lines). Answers all 8 questions with rationale + runnable DDL. Reviewer findings R1–R6 folded back in (see B3). Produce the design spec answering, with rationale, at minimum:
  1. **Store engine decision** — Postgres (Railway addon, +$5/mo class) vs volume-SQLite-with-enforced-FKs at ≤1k users; migration trigger criteria for whichever is deferred.
  2. **Schema (DDL included):** `users`, `instruments` (from `managed_tickers.json` — keep origin/cadence/enabled), `user_instruments` (user_id FK, symbol FK, relationship `held|watch`, qty/avg_price or reference into portfolio files — decide), `ticker_verdicts` (the Verdict Store: symbol FK, date, verdict, triggers, regime, confidence — written by the intelligence plane, read by the user plane; **no user columns**), `user_advice` (per-user application: user FK, symbol, date, verdict ref, pnl/stop at decision time), `sessions`/`invites`/`chat_usage` (fold in users.db), `chat_turns` (user FK — from A2), `push_subscriptions` (user FK — from A1), `outbox` (Blueprint 2), `feedback_events` (Blueprint 5 shape, outside intelligence).
  3. **The plane boundary:** a `VerdictStore` read API the advisor/pipeline uses instead of importing `PredictionStore` — exact function signatures; what stays direct (intelligence-internal callers).
  4. **Universe refcounting:** `user_instruments` triggers promote/demote of `instruments.enabled`/cadence (Blueprint 1 tiers) — demote policy when refcount hits 0.
  5. **Global-singleton resolution:** `watchlist.json` / `agent_weights.json` / `agent_tasks.json` — per-user vs owner-config; kill the duplicate watchlist concept.
  6. **Migration plan:** ETL from JSON/JSONL + users.db; dual-write window or freeze-cutover (justify); rollback; ghost-dir reconciliation (`data/portfolio/*` without users row).
  7. **Lifecycle/retention:** advice ledger, chat turns, verdicts, value_history caps.
  8. **What M2 explicitly defers** (sharding, event bus, replicas).

### Task B3: Reviewer loop

- [x] **DONE 2026-07-26** → `docs/superpowers/research/2026-07-26-atlas-data-review.md`. Adversarial review with a **verification log** (every load-bearing code claim re-checked against source). 6 findings, all closed in-loop this session: **R1** migration-trigger #1 was un-monitorable (`Dockerfile:47 --workers 2` ⇒ two atlas.db-writer processes exist *today*, not a future event) → reframed to measurable `SQLITE_BUSY`/latency/throughput, SQLite-still-correct rationale (users.db/chat_sessions.db already multi-worker) added; **R2** the "existing import-boundary test" does **not** exist (blueprint only *prescribes* it, `SCALING_BLUEPRINTS.md:231`) → "existing/extends" corrected in spec **and** research memo, "R1 holds by construction today", **create the guard** made a Phase-C requirement; **R3** in-process outbox drainer would double-send under `--workers 2` (app already hit "every cron job fired twice", `server.py:306-388`) → pinned to the existing singleton-lock owner + atomic claim CAS; **R4** `chat_hits_7d` had no data source → `=0` at M1, `symbol_mentions` tap deferred to M1.x; **R5** DPDP asymmetry (telemetry anonymize vs feedback hard-delete) → default stated + **routed to B4 as Q5**; **R6a** `invites.created_by` CASCADE→SET NULL (align invite-graph audit), **R6b** R2 citation added for `instruments` aggregates. Revised DDL + DPDP cascade **re-instantiated in sqlite3** (7 PII tables→0, invites retained NULLed, instruments/ticker_verdicts survive) = OK. **Verdict: APPROVED** for the B4 gate. Loop Designer↔Reviewer until Reviewer verdict is APPROVED (user preference: reviewer drives).

### Task B4: User approval gate + plan append

- [x] **DONE 2026-07-27.** Presented the approved spec (decisions table + cost + risk + 2 deviations + 5 open Qs) to the user. **User verdict: APPROVE AS-IS**, delete policy = **spec default** (telemetry anonymize / feedback hard-delete). Ratification stamped into the spec ("B4 ratification — RESOLVED 2026-07-27"). Phase C implementation tasks appended below. **Phase C NOT started this session (per rule).** Present the approved spec to the user (decisions table + cost + risk). On explicit user approval: append Phase C implementation tasks to this plan file (full TDD code per task, sized like Phase A), commit both docs, update memory. **Phase C does not start in the same session as B4.**

---

# PHASE C — Implementation (branch `atlas-c`, appended by Task B4 on user approval 2026-07-27)

> **Design source of truth:** `docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md`
> (APPROVED + B4-ratified). Every task here implements a numbered section of that spec; when in
> doubt, the spec wins. **Execution rule (unchanged):** a task is untouched or completed through its
> commit; TDD (write failing test → run red → implement → run green → commit); all tunables via
> `cfg()`; hot paths log+degrade; atomic writes; module docstring headers.
>
> **Global safety for Phase C:** everything ships **dormant behind `cfg("atlas.enabled",
> env="ATLAS_ENABLED", fallback=False)`** and is a behavioral no-op until the cutover task (C11).
> The flag is the rollback lever (`ATLAS_ENABLED=false` ⇒ today's JSON/`users.db`/dir-scan path).
> **No `atlas.db` read is wired into fan-out until C11.** Merges to main are allowed while dormant
> (never 16:25–17:15 IST on trading days); the *cutover* itself (C11) is weekend-only.
>
> **Ordering / waves (dependency-correct):**
> - **Wave α — foundation, dormant:** C0 baseline · C1 `atlas.db` store + schema · C2 VerdictStore
>   facade + import-boundary test + advisor/pipeline swap.
> - **Wave β — write model, dormant:** C3 `user_instruments` write-through + `active_user_ids()` ·
>   C4 nightly Universe recompute · C5 global-singleton resolution.
> - **Wave γ — greenfield features:** C6 DPDP `delete_user_completely` · C7 outbox worker (BP2) ·
>   C8 feedback_events + accept/override UI + telemetry BP4 · C9 retention jobs.
> - **Wave δ — cutover:** C10 ETL + ghost-dir reconciliation · C11 close-out (A/B, weekend cutover,
>   flip flag, first-run watch, decommission).

### Task C0: Baseline

- [x] **Branch + baseline.** — **DONE 2026-07-27.** Branched `atlas-c` **off `atlas-b`** (not `main`):
  `atlas-b` = `main` + 4 docs-only commits with **zero code divergence**, so the pytest baseline is
  identical either way, and branching off `atlas-b` keeps the plan + spec (the Phase-C source of
  truth) on the working branch instead of orphaning them; they land on `main` together with the
  Phase-C code at the C11 merge (no premature main push/deploy). Baseline captured to
  `scratchpad/atlas_c_baseline.md`: **12 failed, 2131 passed, 12 skipped, 10 errors**. 10F+10E = the
  documented known-red network area; the 2 extra failures (`test_autopilot_api::test_manual_add_identical_retry_dedupes`,
  `test_portfolio_locking::test_cross_process_add_holding_is_atomic`) are Windows cross-process
  file-lock flakes (`[WinError 5]` on `os.replace(portfolio.tmp→portfolio.json)`) — environmental,
  non-deterministic, zero code diff at this commit.

---

### Task C1: `atlas.db` store foundation (spec §1, §2)

**Files:** Create `services/data/stores/atlas_store.py`; Test `tests/unit/test_atlas_store.py`.

**Interfaces:**
- Produces: `_get_conn()` (process-wide connection, opens with `PRAGMA journal_mode=WAL;
  busy_timeout=5000; foreign_keys=ON`), `_SCHEMA` (the full spec §2 DDL for `atlas.db`), `_reset_for_tests()`,
  `db_path()` = `cfg("atlas.db_path", fallback="data/atlas.db")`. Mirrors the `user_store.py` recipe
  (WAL, `_lock`, `_conn_holder`) so tests can monkeypatch `_DB_PATH`/`_conn_holder` the same way.
- Consumes: `cfg()` from `src/backend/shared/config/settings/base.py`.

- [x] **Step 1 — failing tests** `tests/unit/test_atlas_store.py` (4): (a) FK-on connection +
  all designed tables present; (b) FK enforced (orphan `user_instruments` → `IntegrityError`);
  (c) DPDP cascade (7 PII tables → 0; `instruments`/`ticker_verdicts` survive; `invites`
  `created_by/used_by` NULLed) — the check was written directly from the spec §2 DDL (the Phase-B
  `scratchpad/atlas_ddl_check.py` lived in a prior session's scratchpad, now cleaned up);
  (d) `_reset_for_tests` + `_DB_PATH` monkeypatch isolate a tmp DB.
- [x] **Step 2 — run red** (ModuleNotFoundError: `services.data.stores.atlas_store`).
- [x] **Step 3 — implement** `atlas_store.py`: `user_store.py` connection skeleton; `_SCHEMA` = spec
  §2 DDL verbatim (owner-first); WAL + busy_timeout + `foreign_keys=ON` issued on every connection.
  No business functions — schema + connection only. Behavioral no-op (imported by nothing).
- [x] **Step 4 — run green** (4/4 atlas tests pass; full-suite collection clean at 2169, +4).
- [x] **Step 5 — commit** `bd76779` `feat(atlas-c1): atlas.db store foundation — schema + FK-on connection (dormant)`.

---

### Task C2: `VerdictStore` facade + import-boundary test + advisor/pipeline swap (spec §3, reviewer R2)

**Files:** Create `services/data/verdict_store.py`; Create `tests/unit/test_atlas_import_boundary.py`;
Create `tests/unit/test_verdict_store_facade.py`; Modify `core/portfolio/advisor.py` (import `:21`,
`build_signals` type hint), `core/portfolio/pipeline.py` (imports `:15-17`).

**Interfaces:**
- Produces: `VerdictStore(ticker, sector=None)` duck-typing the exact `PredictionStore` read surface —
  `cycle_id_for(target: date) -> str`, `load_envelope(cycle_id=None) -> EnvelopeView|None`,
  `load_feedback_log(cycle_id=None) -> FeedbackView`, plus `get_verdict_card(symbol, as_of) -> dict|None`
  and `publish_projection(symbol, as_of, ...)` (writes one `ticker_verdicts` row from the freshly
  written ticker-keyed envelope/feedback — user-plane projection, D2). Delegates the three read calls
  to `PredictionStore`; the facade is the **only** user-plane importer of the intelligence plane.
- **R2 guard (new, not "extended"):** `test_atlas_import_boundary.py` AST-walks every module under
  `core/intelligence/**` and asserts none imports `services.data.verdict_store`, the feedback store,
  `feedback_events`, `atlas_store`, or any `services.data.stores.user_store`/portfolio store. This is
  the guard the blueprint prescribed but never had.

- [x] **Step 1 — failing tests.** (a) `test_atlas_import_boundary.py` (7): AST-walks
  `core/intelligence/**`, asserts none imports {verdict_store, atlas_store, user_store, portfolio
  store, feedback_events}, + 5 synthetic-negative + 1 allowed-arrow check so a green walk is
  meaningful. Reads with `utf-8-sig` (one intelligence file carries a BOM). (b)
  `test_verdict_store_facade.py` (8): the 3 delegated reads return the store objects unchanged
  (monkeypatched fake PredictionStore), degrade to None on exception, + publish/get round-trip,
  idempotent upsert, and hot-path safety on a bad DB.
- [x] **Step 2 — run red** (facade `ModuleNotFoundError`; boundary guard already green — it scans
  source, doesn't import the facade).
- [x] **Step 3 — implement** `verdict_store.py` per spec §3. Chose **delegate-and-return-raw**:
  the facade returns PredictionStore's actual `PredictionEnvelope`/`DailyFeedbackLog` objects
  (byte-for-byte the advisor surface, zero drift risk) rather than re-wrapping in EnvelopeView/
  FeedbackView — the advisor duck-types, importing only `VerdictStore`, so R1 holds. Swapped
  `advisor.py:21/:104` and `pipeline.py:17/:92` PredictionStore→VerdictStore. `is_trading_day`/
  `get_price_history`/`next_results_event` left as direct imports (spec §3). Other PredictionStore
  importers (scheduler/rl_monitor/analytics/run_schedule) are the RL operational surface, stay direct.
- [x] **Step 4 — run green** (48 passed: facade+boundary+`test_portfolio_advisor`/`_switch`/
  `test_portfolio_pipeline`/`test_autopilot_pipeline`; updated the 2 `pipeline.PredictionStore`
  monkeypatch targets → `pipeline.VerdictStore`, fake already duck-types). Full-suite collection clean
  (2183, no import cycle).
- [x] **Step 5 — commit** `d91c497` `feat(atlas-c2): VerdictStore facade + R1 import-boundary test; advisor/pipeline swap`.

---

### Task C3: `user_instruments` write-through + `active_user_ids()` (spec §4, §6, reviewer none)

**Files:** Modify `core/portfolio/store.py` (add/remove holding + watchlist hooks; add `active_user_ids()`);
Modify fan-out sites `core/portfolio/pipeline.py:39`, `core/delivery/brief.py:270`, `weekly.py:240`,
`index_watch.py:35`; Create `tests/unit/test_atlas_user_instruments.py`.

**Interfaces:**
- Produces: transactional upserts into `atlas.db user_instruments` on `add_holding`(→`held`)/`remove_holding`,
  `add_watchlist`(→`watch`)/`remove_watchlist`, each ensuring an `instruments` row exists (held ⇒
  `origin='held',cadence='daily'`; watch ⇒ `origin='watched',cadence='weekly'`). All **flag-gated** —
  no-op when `ATLAS_ENABLED=false`. `active_user_ids()` per spec §6 (atlas users query; preserves
  `AUTH_REQUIRED=false ⇒ [primary]`; falls back to `list_user_ids()` when flag off).

- [x] **Step 1 — failing tests** (`test_atlas_user_instruments.py`, 8): flag-ON write-through
  (add_holding→held+instrument origin/cadence, remove_holding, reduce_holding full-exit,
  watchlist mirror, hot-path-safe with no users row), active_user_ids (atlas users, ghost excluded,
  owner fallback), flag-OFF no-op + `active_user_ids()==list_user_ids()`.
- [x] **Step 2 — run red.**
- [x] **Step 3 — implement.** `atlas_store.enabled/user_ids/upsert_user_instrument/
  remove_user_instrument` (idempotent, atomic, hot-path safe). `PortfolioStore._sync_instrument`
  hooks on add/remove holding + add/remove watchlist + **reduce_holding full-exit** (added for
  refcount accuracy — same 'held ended' event). `active_user_ids()` per spec §6; repointed all 4
  fan-out sites (pipeline bare; brief/weekly/index_watch keep `or [DEFAULT]` to preserve the dormant
  path exactly). config.yaml gains a dormant `atlas:` section.
- [x] **Step 4 — run green** (59 passed across affected areas; renamed 6 monkeypatch targets
  `list_user_ids`→`active_user_ids` in test_autopilot_pipeline/test_delivery_brief/test_delivery_weekly;
  full-suite collection clean 2191).
- [x] **Step 5 — commit** `40d6cd5` `feat(atlas-c3): user_instruments write-through + active_user_ids() (flag-gated)`.

> **Gap flagged (post-cutover, not blocking):** new signups still write only to `users.db`, not
> `atlas.db users`. The C10 ETL migrates *existing* users at cutover, but ongoing signups won't have
> an `atlas.db users` row, so their `user_instruments` write-through FK-skips (hot-path safe, just not
> indexed) and `active_user_ids()` won't fan out to them until a re-ETL. Wiring the signup path to
> also write `atlas.db` (dual-write or switch the auth SoT) is out of the current Phase-C task list —
> track for before user #2 relies on atlas fan-out.

---

### Task C4: Nightly Universe recompute (spec §4)

**Files:** Create `core/portfolio/universe.py` (`recompute_universe()`); register in the nightly
scheduler lane (same place as the backup job); Create `tests/unit/test_atlas_universe_recompute.py`.

**Interfaces:** `recompute_universe()` (user-plane) reads `user_instruments`, writes only aggregates
to `instruments`: `holders`/`watchers` counts, `chat_hits_7d=0` (reviewer R4 — deferred tap),
`demand_score = cfg("universe.demand_weights")·(h,w,c)`, cadence tiers (held→daily; top-N by demand→daily,
N=`cfg("universe.max_daily_analyses")`; watched long-tail→weekly; rest→on_demand); budget governor ops
alert at `cfg("universe.budget_alert_pct",0.8)`. Demote policy: refcount→0 ⇒ `cadence='on_demand',enabled=0`,
history preserved; archive only if no intelligence history + `origin in (watched,on_demand,discovery)` +
refcount-0 for `cfg("universe.archive_grace_days",30)`.

- [x] **Step 1 — failing tests** (`test_atlas_universe_recompute.py`, 7): counts/tiers,
  demote-not-delete, never-archive-with-history, archive-after-grace, budget alert at threshold,
  no-`user_id`-column invariant, disabled no-op.
- [x] **Step 2 — run red.** — [x] **Step 3 — implement** `core/portfolio/universe.py` per spec §4;
  all weights/N/thresholds via `cfg()` (config.yaml `universe:` section). Refinement: a watch-only
  ticker earns a daily slot only once demand ≥ one held-equivalent (holders weight) — derived from
  `demand_weights`, no new key — so a lone watcher stays weekly (cost control). `updated_at` written
  only on a real state change → it is the archive grace clock. Registered as scheduler **Job 16**
  (23:00 IST, before backup).
- [x] **Step 4 — run green** (7 atlas + 19 scheduler tests; collection 2198). — [x] **Step 5 — commit**
  `e76f198` `feat(atlas-c4): nightly Universe recompute — demand tiers + demote policy`.

---

### Task C5: Global-singleton resolution (spec §5)

**Files:** Modify `services/api/routes/ui_data.py` (watchlist read/write endpoints → per-user;
`agent_weights`/`agent_tasks`/`category_tickers` PUTs → `require_owner`); Create
`tests/unit/test_atlas_singletons.py`.

**Interfaces:** watchlist becomes per-user (single SoT = `Portfolio.watchlist`, projected into
`user_instruments(watch)`); the global `data/watchlist.json` endpoints repoint to the session user's
portfolio store; `agent_weights.json`/`agent_tasks.json`/`category_tickers.json` stay global but
their write routes require owner (they tune the one shared brain — spec §5 rationale). Per-user tuning
already exists via `Portfolio.risk_profile` (no new knob).

- [x] **Step 1 — failing tests** (`test_atlas_singletons.py`, 4): two users isolated watchlists,
  member edits own list, shared-brain configs owner-only (401/403/200), dormant global-owner-only.
- [x] **Step 2 — run red.** — [x] **Step 3 — implement.** The 3 config PUTs **already** used
  `require_owner` (M0.1 lockdown — spec §5's owner-config requirement was already met); C5 adds the
  regression guard. Watchlist GET/PUT flag-gated to the session user's `Portfolio.watchlist` when
  ATLAS_ENABLED (PUT dep require_owner→get_current_user + manual owner check in the dormant branch to
  preserve the exact legacy owner-only global-file behavior; GET gains get_current_user_optional).
- [x] **Step 4 — run green** (4 atlas + 47 auth-lockdown/m0/ui tests; collection 2202).
- [x] **Step 5 — commit** `04a5039` `feat(atlas-c5): watchlist per-user; agent/task/category configs owner-gated`.

> **WAVE β COMPLETE (C3–C5) — A/B CLEAN.** Full-suite: 10 failed, 2170 passed, 12 skipped, 10 errors
> — fail-set == the C0 known-red network area exactly (the 2 Windows file-lock flakes did not recur);
> 2170 passed = wave-α 2151 + 19 new C3/C4/C5 tests. Both design-heavy waves (α + β) now validated.
> **NEXT SESSION = wave γ from C6.**

---

### Task C6: DPDP `delete_user_completely` (spec §Learning-Constitution/DPDP, B4 Q3/Q5)

**Files:** Add `delete_user_completely(user_id)` to `services/data/stores/atlas_store.py`; wire an
authenticated route (`DELETE /auth/me` or `services/api/routes/auth_api.py`); Create
`tests/unit/test_atlas_dpdp_delete.py`.

**Interfaces:** one entry point: (1) atomic cascade `DELETE FROM users WHERE user_id=?` on `atlas.db`
(7 PII tables → 0; `invites` SET NULL; `instruments`/`ticker_verdicts` survive); (2) idempotent
follow-ups in the **same function**, DB-commit-first: `shutil.rmtree(data/portfolio/<uid>/)`,
`chat_sessions.db DELETE FROM chat_turns WHERE user_id=?`, `telemetry.db UPDATE llm_calls SET
user_id=NULL WHERE user_id=?` (**anonymize — B4 Q3**). `feedback_events` is removed by the cascade
(**hard-delete — B4 Q5**). All follow-ups retry-safe and no-op if already clean.

- [x] **Step 1 — failing tests** (`test_atlas_dpdp_delete.py`, 8): atlas cascade (reuse C1's
  assertions); portfolio dir gone; chat_turns gone for the target user only; telemetry `llm_calls`
  user's rows → `user_id IS NULL` with row count preserved (post-C8 schema simulated) **and** the
  missing-column pre-C8 state is a safe no-op; idempotent (second call no-ops); DB commit precedes
  filesystem (rmtree made to raise → cascade still committed); + a route test for `DELETE /auth/account`
  (both stores erased + session revoked, owner can't self-delete).
- [x] **Step 2 — run red** (all 8 fail: `no attribute 'delete_user_completely'`).
- [x] **Step 3 — implement** per spec (order: DB commit → fs → cross-DB; each wrapped log+continue).
  Kept each store's DB access in its owning module: `chat_session_store.delete_user_turns` +
  `log_store.anonymize_user` (defensive `no such column` skip until C8 adds `llm_calls.user_id`);
  `atlas_store.delete_user_completely` orchestrates via lazy imports. **NOT flag-gated** — DPDP erasure
  must run whether or not `ATLAS_ENABLED` (pre-cutover atlas.db holds no rows for the user → harmless
  0-row cascade). Enhanced `DELETE /auth/account` to run `user_store.delete_user` +
  `atlas_store.delete_user_completely` + `revoke_session` (portfolio rmtree moved into the cascade);
  `test_m0_auth_api.py` `client` fixture now isolates atlas/chat/telemetry on tmp paths.
- [x] **Step 4 — run green** (31 passed across new + M0-auth + log_store + chat + atlas_store).
  Full-suite A/B CLEAN: 10F+10E == C0 known-red, **2178 passed** (2170 + 8), 12 skipped, 10 errors.
- [x] **Step 5 — commit** `c83075c` `feat(atlas-c6): DPDP delete_user_completely — single cascade + idempotent follow-ups`.

---

### Task C7: Outbox worker (BP2) — in-process, singleton-lock owner, atomic claim (spec §7, §8, reviewer R3)

**Files:** Create `core/delivery/outbox.py` (`enqueue()`, `drain_once()`); wire the drainer into the
**existing singleton-lock owner** in `services/api/server.py` (reuse the localhost-socket guard at
`:306-388` — do NOT add a new lock); repoint fan-out (`brief.py`/`weekly.py`/`index_watch.py`/`pipeline.py`)
to `enqueue()` behind the flag; Create `tests/unit/test_atlas_outbox.py`.

**Interfaces:** `enqueue(user_id, channel, kind, payload_ref, dedupe_key)` (idempotent via UNIQUE
`dedupe_key`); `drain_once()` claims each row atomically —
`UPDATE outbox SET status='sending', attempts=attempts+1 WHERE id=? AND status='queued'`, acts only if
`rowcount==1` (reviewer R3: prevents double-send under `--workers 2`), sends via the existing push/email
transports, then `status='delivered'` or reschedules `next_attempt_at` with `cfg("delivery.outbox_backoff_minutes",[1,5,30])`
up to `cfg("delivery.outbox_max_attempts",3)` then `status='dead'`.

- [ ] **Step 1 — failing tests:** enqueue idempotency (duplicate `dedupe_key` → one row); atomic claim
  (two concurrent `drain_once` calls send exactly once — simulate by racing the CAS); backoff + dead-letter
  after max attempts; drainer only runs in the singleton owner (assert guarded start). Flag-gated no-op.
- [ ] **Step 2 — run red.** — [ ] **Step 3 — implement** (transports are the existing `send_push`/email;
  worker is a daemon thread started only inside the singleton-lock branch of the lifespan).
- [ ] **Step 4 — run green** (new + delivery tests — no real transport, per `conftest` isolation).
- [ ] **Step 5 — commit** `feat(atlas-c7): BP2 outbox — in-process drainer (singleton owner) + atomic claim`.

---

### Task C8: feedback_events (BP5) + accept/override UI + telemetry BP4 user_id (spec §2 telemetry, R2/R3/R4)

**Files:** Add `record_feedback_event()` to `atlas_store.py`; advice-card accept/override endpoint in
`ui_data.py` + frontend hook; telemetry BP4: `ALTER TABLE llm_calls ADD COLUMN user_id`, a
`current_user_id: ContextVar` set by auth, read by `log_llm_call`, nightly `cost_by_user_day` rollup;
Create `tests/unit/test_atlas_feedback_events.py`, `tests/unit/test_atlas_telemetry_user.py`.

**Interfaces:** `record_feedback_event(ts,user_id,symbol,advice_ref,verdict_shown,action,override_direction,position_state)`
(append-only, user-plane, **outside** `core/intelligence/` — R1). Aggregation refuses below
`cfg("atlas.feedback.aggregation_floor_users",20)` (R3). Telemetry: `user_id` nullable, **NULL = shared
brain** (BP4); only chat / on-demand `/analyse` / narrator pre-cache set it; scheduled analysis stays NULL.

- [ ] **Step 1 — failing tests:** feedback event persists + DPDP-cascades on user delete; aggregator
  returns nothing below the 20-user floor; `llm_calls.user_id` populated for a chat call, NULL for a
  scheduled call; `cost_by_user_day` rollup buckets NULL as "shared brain". Import-boundary test (C2)
  still green (feedback store not imported by intelligence).
- [ ] **Step 2 — run red.** — [ ] **Step 3 — implement** (ContextVar avoids threading user_id through
  ~20 call sites — BP4). — [ ] **Step 4 — run green.**
- [ ] **Step 5 — commit** `feat(atlas-c8): BP5 feedback_events + accept/override UI + BP4 telemetry user_id`.

---

### Task C9: Retention jobs (spec §7)

**Files:** Create `core/portfolio/retention.py` (or fold into the nightly lane); Create
`tests/unit/test_atlas_retention.py`.

**Interfaces:** nightly prune, all caps via `cfg()`: `ticker_verdicts` older than
`atlas.retention.ticker_verdicts_days`(400); `outbox` delivered/dead older than
`delivery.outbox_retention_days`(30); `value_history` points cap(400); `sessions` expiry (existing sweep);
`user_advice`/`feedback_events` keep by default (None). Hot-path-safe (log+continue).

- [ ] **Step 1 — failing tests:** each prune respects its `cfg` cap; None ⇒ keep-all; a job failure
  doesn't crash the lane. — [ ] **Step 2 — run red.** — [ ] **Step 3 — implement.** — [ ] **Step 4 — green.**
- [ ] **Step 5 — commit** `feat(atlas-c9): retention/prune jobs — all caps via cfg()`.

---

### Task C10: ETL + ghost-dir reconciliation (spec §6)

**Files:** Create `scripts/atlas_etl.py` (idempotent, additive, deletes nothing); Create
`tests/unit/test_atlas_etl.py`.

**Interfaces:** per spec §6 cutover step 3–4: `users.db`→users/sessions/invites/chat_usage (ATTACH +
INSERT…SELECT); `push_subscriptions.json`→rows; `managed_tickers.json`→instruments; each
`portfolio.json` holdings/watchlist→`user_instruments`; `advice_ledger.jsonl`→`user_advice`;
`watchlist.json`→owner's `Portfolio.watchlist`→`user_instruments(watch)`; `telemetry.db` ALTER (in
place). **Ghost-dir reconciliation:** `primary`→adopt to owner; matching users row→keep; **no users
row→quarantine** to `data/portfolio/_quarantine/<uid>/` + one ops alert (no silent adoption). Re-runnable.

- [ ] **Step 1 — failing tests** on a synthetic `data/` tree: row-count assertions post-ETL; idempotent
  (second run = same counts, no dupes); ghost dir with no users row is quarantined not adopted; `primary`
  adopted to owner; `active_user_ids()` dry-run equals the intended set.
- [ ] **Step 2 — run red.** — [ ] **Step 3 — implement** (ATTACH for the SQLite→SQLite copy; JSONL
  stream for ledgers). — [ ] **Step 4 — run green.**
- [ ] **Step 5 — commit** `feat(atlas-c10): ETL + ghost-dir reconciliation (idempotent, additive)`.

---

### Task C11: Close-out — A/B, weekend cutover, flip flag, first-run watch, decommission

- [ ] **Step 1 — Full-suite A/B** — fail-set must equal the C0 baseline (+ all new atlas tests green).
- [ ] **Step 2 — Merge dormant** (`ATLAS_ENABLED` unset/false): `git checkout main && git merge --no-ff
  atlas-c`; `git diff --stat atlas-c HEAD` empty; push (respect the deploy window); confirm Railway
  deploy SUCCESS — behavioral no-op (nothing reads `atlas.db` yet).
- [ ] **Step 3 — Weekend cutover** (Sat/Sun, scheduler idle, `/scheduler/status` idle): run
  `scripts/atlas_etl.py`; run the spec §6 step-5 validations (row counts, dry-run `active_user_ids()`,
  DDL integrity check).
- [ ] **Step 4 — Flip** `ATLAS_ENABLED=true` in Railway; redeploy. Fan-out switches to `active_user_ids()`.
- [ ] **Step 5 — First-run watch** (next trading day): 16:30 autopilot + 08:50 brief fan out to exactly
  the owner (+ any real users), **zero ghost dirs**; `/scheduler/status` clean; no `SQLITE_BUSY` in logs.
- [ ] **Step 6 — Decommission window:** keep `users.db`/`watchlist.json`/`push_subscriptions.json`/
  `managed_tickers.json` **read-only** until `cfg("atlas.retention.source_decommission_days",14)` of
  green operation, then remove. Update memory + this plan; program COMPLETE.

**Rollback at any point:** `ATLAS_ENABLED=false` + redeploy ⇒ instant revert to the JSON/dir-scan path;
`atlas.db` is rebuildable from the still-present sources (ETL deletes nothing).

---

# Ops checklist (user actions — track here, nag politely)

- [x] Railway variable typo: rename `SCHEDULAR_KEY` → `SCHEDULER_KEY` — DONE 2026-07-26 (user). Prod redeploy healthy (probes 200/200/401/401). Verified this does NOT 403 any browser route: `check_scheduler_key` has zero active call sites (M0.1 moved all config/trigger routes to `require_owner`); the rename only activates `require_owner`'s additive machine-key path (owner session still works).
- [ ] **ROTATE `SCHEDULER_KEY` now (newly recommended).** The rename flipped the screenshot-exposed value from inert (typo'd env name ⇒ `os.getenv("SCHEDULER_KEY")` was `""` ⇒ machine path dead) to a **live owner-equivalent credential** (`require_owner` accepts `X-Scheduler-Key == SCHEDULER_KEY` as owner). Generate a fresh random value in Railway → nothing in the browser needs the key (owner uses the session), so zero client impact.
- [ ] Notification deep-link phone test: after key rename, fire `POST /delivery/run-brief` (owner session or key), push arrives → tap with app fully closed → must land on Inbox → Brief tab.
- [ ] Invites for friends — only AFTER Phase A is deployed (push/chat privacy fixes).
- [ ] Backup PII: once user #2 exists, access-control the nightly backup destination (email).
