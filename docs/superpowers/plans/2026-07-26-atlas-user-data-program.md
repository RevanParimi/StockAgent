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

- [ ] Produce the design spec answering, with rationale, at minimum:
  1. **Store engine decision** — Postgres (Railway addon, +$5/mo class) vs volume-SQLite-with-enforced-FKs at ≤1k users; migration trigger criteria for whichever is deferred.
  2. **Schema (DDL included):** `users`, `instruments` (from `managed_tickers.json` — keep origin/cadence/enabled), `user_instruments` (user_id FK, symbol FK, relationship `held|watch`, qty/avg_price or reference into portfolio files — decide), `ticker_verdicts` (the Verdict Store: symbol FK, date, verdict, triggers, regime, confidence — written by the intelligence plane, read by the user plane; **no user columns**), `user_advice` (per-user application: user FK, symbol, date, verdict ref, pnl/stop at decision time), `sessions`/`invites`/`chat_usage` (fold in users.db), `chat_turns` (user FK — from A2), `push_subscriptions` (user FK — from A1), `outbox` (Blueprint 2), `feedback_events` (Blueprint 5 shape, outside intelligence).
  3. **The plane boundary:** a `VerdictStore` read API the advisor/pipeline uses instead of importing `PredictionStore` — exact function signatures; what stays direct (intelligence-internal callers).
  4. **Universe refcounting:** `user_instruments` triggers promote/demote of `instruments.enabled`/cadence (Blueprint 1 tiers) — demote policy when refcount hits 0.
  5. **Global-singleton resolution:** `watchlist.json` / `agent_weights.json` / `agent_tasks.json` — per-user vs owner-config; kill the duplicate watchlist concept.
  6. **Migration plan:** ETL from JSON/JSONL + users.db; dual-write window or freeze-cutover (justify); rollback; ghost-dir reconciliation (`data/portfolio/*` without users row).
  7. **Lifecycle/retention:** advice ledger, chat turns, verdicts, value_history caps.
  8. **What M2 explicitly defers** (sharding, event bus, replicas).

### Task B3: Reviewer loop

- [ ] Adversarial review against: Learning Constitution R1–R4, `docs/LEGAL_AND_COMPLIANCE.md` (DPDP delete = single transaction now), cost budget (≤$5/mo added at M0 scale), migration risk to the LIVE autopilot. Loop Designer↔Reviewer until Reviewer verdict is APPROVED (user preference: reviewer drives).

### Task B4: User approval gate + plan append

- [ ] Present the approved spec to the user (decisions table + cost + risk). On explicit user approval: append Phase C implementation tasks to this plan file (full TDD code per task, sized like Phase A), commit both docs, update memory. **Phase C does not start in the same session as B4.**

---

# PHASE C — Implementation (appended by Task B4 — intentionally absent until the design is approved)

---

# Ops checklist (user actions — track here, nag politely)

- [x] Railway variable typo: rename `SCHEDULAR_KEY` → `SCHEDULER_KEY` — DONE 2026-07-26 (user). Prod redeploy healthy (probes 200/200/401/401). Verified this does NOT 403 any browser route: `check_scheduler_key` has zero active call sites (M0.1 moved all config/trigger routes to `require_owner`); the rename only activates `require_owner`'s additive machine-key path (owner session still works).
- [ ] **ROTATE `SCHEDULER_KEY` now (newly recommended).** The rename flipped the screenshot-exposed value from inert (typo'd env name ⇒ `os.getenv("SCHEDULER_KEY")` was `""` ⇒ machine path dead) to a **live owner-equivalent credential** (`require_owner` accepts `X-Scheduler-Key == SCHEDULER_KEY` as owner). Generate a fresh random value in Railway → nothing in the browser needs the key (owner uses the session), so zero client impact.
- [ ] Notification deep-link phone test: after key rename, fire `POST /delivery/run-brief` (owner session or key), push arrives → tap with app fully closed → must land on Inbox → Brief tab.
- [ ] Invites for friends — only AFTER Phase A is deployed (push/chat privacy fixes).
- [ ] Backup PII: once user #2 exists, access-control the nightly backup destination (email).
