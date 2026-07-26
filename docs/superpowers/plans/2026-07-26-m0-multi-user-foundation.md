# M0 Multi-User Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real auth (accounts/sessions/invites, server-side `user_id`), narrator LLM cache, and chat quotas — making users #2–#10 safe at ~zero added cost, with a behavior-no-op deploy until `AUTH_REQUIRED=true` is set.

**Architecture:** New SQLite identity store (`data/users.db`) following the existing volume-SQLite pattern; a FastAPI bearer-token dependency that replaces client-supplied `user_id` query params on user-scoped routes (the IDOR fix); narrator narration split into cached ticker-level LLM text + deterministic per-user suffix; chat quota counters enforced at the two chat endpoints. Spec: `docs/superpowers/specs/2026-07-26-m0-multi-user-foundation-design.md` — **read it fully first**, especially §9 Guardrails.

**Tech Stack:** Python 3.11+ stdlib only (`sqlite3`, `hashlib.scrypt`, `secrets`, `hmac`, `zoneinfo`), FastAPI, existing `core.utils.atomic_io`. **No new dependencies.**

## Global Constraints

- **Prod is live** (real scheduled autopilot). Never push to main 16:25–17:15 IST on NSE trading days; weekends fine.
- **Public repo:** no secrets, no prod endpoint URLs, no portfolio cash figures in any committed file.
- **A/B rule:** capture the full `pytest` fail-set before Task 1; it must be identical at the end (plus new tests green). If baseline is unexpectedly red, stop and report.
- `AUTH_REQUIRED` defaults **false** → merge deploy is a behavioral no-op. Do not default it true.
- Do not modify anything under `core/intelligence/` or `services/scheduler/`. Do not touch `data/rl/verdict_shadow.jsonl` (live experiment).
- House style: functions on hot paths never raise (log + degrade); atomic file writes via `core/utils/atomic_io.py`; module docstring headers like the surrounding files.
- Work on branch `m0-foundation`; conventional commits; suite green before merge.
- All Python new-code imports of settings go through `from core.config import settings` (the shim over `src/backend/shared/config/settings/base.py`) — match `core/portfolio/narrator.py`.
- **No hardcoded business tunables (user rule, 2026-07-26):** every value business might re-tune — quotas, caps, TTLs, thresholds, tier limits — goes through `cfg("section.key", env=..., fallback=...)` in settings, never as a literal in code. (This plan complies: `CHAT_DAILY_QUOTA`, `AUTH_REQUIRED`; session TTLs 30d/24h and password min-length 10 are acceptable as module constants only because they are security parameters, not business knobs — if in doubt, make it a setting.)

---

### Task 0: Baseline

**Files:** none (verification only)

- [ ] **Step 1: Create branch and capture baseline**

```bash
git checkout -b m0-foundation
python -m pytest -q 2>&1 | tail -20
```

Record the exact pass/fail/skip counts and any failing test ids into a scratch note. This is the A/B baseline. (Recent baseline shape: ~285 passed / 7 skipped — if you see *new* unexplained failures, stop and report before proceeding.)

---

### Task 1: Settings + identity store (`user_store.py`)

**Files:**
- Modify: `src/backend/shared/config/settings/base.py` (append after the ADVISOR block, ~line 799)
- Create: `services/data/stores/user_store.py`
- Test: `tests/unit/test_m0_user_store.py`

**Interfaces:**
- Produces (used by Tasks 2/3/5):
  - `settings.AUTH_REQUIRED: bool`, `settings.CHAT_DAILY_QUOTA: int`
  - `user_store.create_user(email, password, display_name, *, role="member", user_id=None, consent=True) -> dict` (raises `ValueError` on duplicate email)
  - `user_store.verify_password(email, password) -> dict | None` (user dict or None; constant-time)
  - `user_store.create_session(user_id, remember_me: bool) -> str` (returns the raw bearer token)
  - `user_store.resolve_session(raw_token: str) -> dict | None` (user dict; bumps last_seen; None if expired/unknown)
  - `user_store.revoke_session(raw_token: str) -> None`
  - `user_store.create_invite(created_by: str) -> str`, `user_store.list_invites() -> list[dict]`, `user_store.consume_invite(code, used_by) -> bool`
  - `user_store.count_users() -> int`
  - `user_store.bump_chat_usage(user_id) -> int` (increments and returns today-IST count), `user_store.get_chat_usage(user_id) -> int`
  - `user_store.delete_user(user_id) -> None` (rows + sessions; NOT portfolio files — caller's job)
  - `user_store.sweep_expired_sessions() -> int`
  - User dict shape everywhere: `{"user_id", "email", "display_name", "role", "created_at"}`

- [ ] **Step 1: Add settings**

Append to `src/backend/shared/config/settings/base.py` after line ~799 (end of ADVISOR block):

```python
# ---------------------------------------------------------------------------
# M0 — Multi-user foundation (spec 2026-07-26)
# ---------------------------------------------------------------------------
AUTH_REQUIRED: bool = bool(cfg("auth.required", env="AUTH_REQUIRED", fallback=False))
CHAT_DAILY_QUOTA: int = int(cfg("chat.daily_quota", env="CHAT_DAILY_QUOTA", fallback=30))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_m0_user_store.py`:

```python
"""M0 — identity store unit tests (spec 2026-07-26 §4.1)."""
import time
import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    return user_store


def test_create_and_verify_user(store):
    u = store.create_user("A@x.com", "hunter2longer", "Alice")
    assert u["user_id"].startswith("u_") and u["role"] == "member"
    assert store.verify_password("a@x.com", "hunter2longer")["user_id"] == u["user_id"]
    assert store.verify_password("a@x.com", "wrong-password") is None
    assert store.verify_password("nobody@x.com", "hunter2longer") is None


def test_duplicate_email_rejected(store):
    store.create_user("a@x.com", "hunter2longer", "Alice")
    with pytest.raises(ValueError):
        store.create_user("A@X.COM", "hunter2longer", "Alice2")


def test_owner_user_id_override(store):
    u = store.create_user("me@x.com", "hunter2longer", "Owner",
                          role="owner", user_id="primary")
    assert u["user_id"] == "primary" and u["role"] == "owner"


def test_session_roundtrip_and_revoke(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], remember_me=True)
    assert store.resolve_session(tok)["user_id"] == u["user_id"]
    store.revoke_session(tok)
    assert store.resolve_session(tok) is None


def test_session_expiry(store, monkeypatch):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], remember_me=False)
    monkeypatch.setattr(store, "_now_epoch", lambda: time.time() + 25 * 3600)
    assert store.resolve_session(tok) is None      # 24h session expired
    assert store.sweep_expired_sessions() >= 1


def test_invite_single_use(store):
    owner = store.create_user("o@x.com", "hunter2longer", "O", role="owner",
                              user_id="primary")
    code = store.create_invite(owner["user_id"])
    assert store.consume_invite(code, "u_new1") is True
    assert store.consume_invite(code, "u_new2") is False   # single-use
    assert store.consume_invite("inv_nope", "u_x") is False


def test_chat_usage_counter(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    assert store.get_chat_usage(u["user_id"]) == 0
    assert store.bump_chat_usage(u["user_id"]) == 1
    assert store.bump_chat_usage(u["user_id"]) == 2
    assert store.get_chat_usage(u["user_id"]) == 2


def test_delete_user(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], True)
    store.delete_user(u["user_id"])
    assert store.verify_password("a@x.com", "hunter2longer") is None
    assert store.resolve_session(tok) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_user_store.py -q`
Expected: FAIL / errors with `ModuleNotFoundError: services.data.stores.user_store`

- [ ] **Step 4: Implement `services/data/stores/user_store.py`**

```python
"""
services/data/stores/user_store.py
==================================
M0 identity store (spec 2026-07-26 §4.1): users, sessions, invites, chat quota
counters. SQLite on the Railway volume (data/users.db) — same WAL +
process-wide-connection pattern as chat_session_store. Portable SQL only
(the M1 Postgres move is a dump/load).

Security notes: passwords are scrypt-hashed (stdlib, per-user salt); session
tokens are stored SHA-256-hashed so a DB leak does not leak live sessions;
verification uses constant-time comparison.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/users.db")
_conn_holder: dict = {"conn": None}
_lock = threading.Lock()
_IST = ZoneInfo("Asia/Kolkata")

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 16384, 8, 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id      TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  pw_hash      TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  role         TEXT NOT NULL DEFAULT 'member',
  created_at   TEXT NOT NULL,
  consent_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  created_at  REAL NOT NULL,
  expires_at  REAL NOT NULL,
  last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE TABLE IF NOT EXISTS invites (
  code        TEXT PRIMARY KEY,
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  used_by     TEXT,
  used_at     TEXT
);
CREATE TABLE IF NOT EXISTS chat_usage (
  user_id   TEXT NOT NULL,
  day       TEXT NOT NULL,
  llm_turns INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);
"""


def _now_epoch() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ist_today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _get_conn() -> sqlite3.Connection:
    conn = _conn_holder.get("conn")
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        _conn_holder["conn"] = conn
    return conn


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt$n={},r={},p={}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def _check_password(password: str, stored: str) -> bool:
    try:
        _, params, salt_b64, hash_b64 = stored.split("$")
        kv = dict(p.split("=") for p in params.split(","))
        dk = hashlib.scrypt(password.encode(),
                            salt=base64.b64decode(salt_b64),
                            n=int(kv["n"]), r=int(kv["r"]), p=int(kv["p"]),
                            dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _row_to_user(row: sqlite3.Row) -> dict:
    return {"user_id": row["user_id"], "email": row["email"],
            "display_name": row["display_name"], "role": row["role"],
            "created_at": row["created_at"]}


# -- users -------------------------------------------------------------------

def create_user(email: str, password: str, display_name: str, *,
                role: str = "member", user_id: str | None = None,
                consent: bool = True) -> dict:
    email = email.strip().lower()
    uid = user_id or ("u_" + secrets.token_hex(4))
    conn = _get_conn()
    with _lock:
        try:
            conn.execute(
                "INSERT INTO users (user_id, email, pw_hash, display_name,"
                " role, created_at, consent_at) VALUES (?,?,?,?,?,?,?)",
                (uid, email, _hash_password(password), display_name, role,
                 _now_iso(), _now_iso() if consent else ""))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"email or user_id already registered") from exc
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    return _row_to_user(row)


def verify_password(email: str, password: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=?",
                       (email.strip().lower(),)).fetchone()
    # Constant-time-ish: always run one scrypt even for unknown emails.
    stored = row["pw_hash"] if row else _hash_password("x" * 12)
    if _check_password(password, stored) and row:
        return _row_to_user(row)
    return None


def count_users() -> int:
    return _get_conn().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user(user_id: str) -> dict | None:
    row = _get_conn().execute("SELECT * FROM users WHERE user_id=?",
                              (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def delete_user(user_id: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM chat_usage WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()


# -- sessions ----------------------------------------------------------------

def create_session(user_id: str, remember_me: bool) -> str:
    raw = secrets.token_urlsafe(32)
    ttl = timedelta(days=30) if remember_me else timedelta(hours=24)
    now = _now_epoch()
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at,"
            " expires_at, last_seen) VALUES (?,?,?,?,?)",
            (_token_hash(raw), user_id, now, now + ttl.total_seconds(), now))
        conn.commit()
    return raw


def resolve_session(raw_token: str) -> dict | None:
    if not raw_token:
        return None
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE token_hash=?",
                       (_token_hash(raw_token),)).fetchone()
    if row is None or row["expires_at"] < _now_epoch():
        return None
    with _lock:
        conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?",
                     (_now_epoch(), row["token_hash"]))
        conn.commit()
    return get_user(row["user_id"])


def revoke_session(raw_token: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",
                     (_token_hash(raw_token),))
        conn.commit()


def sweep_expired_sessions() -> int:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?",
                           (_now_epoch(),))
        conn.commit()
    return cur.rowcount


# -- invites -----------------------------------------------------------------

def create_invite(created_by: str) -> str:
    code = "inv_" + secrets.token_urlsafe(8)
    conn = _get_conn()
    with _lock:
        conn.execute("INSERT INTO invites (code, created_by, created_at)"
                     " VALUES (?,?,?)", (code, created_by, _now_iso()))
        conn.commit()
    return code


def list_invites() -> list[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM invites ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def consume_invite(code: str, used_by: str) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "UPDATE invites SET used_by=?, used_at=?"
            " WHERE code=? AND used_by IS NULL", (used_by, _now_iso(), code))
        conn.commit()
    return cur.rowcount == 1


# -- chat quota --------------------------------------------------------------

def bump_chat_usage(user_id: str) -> int:
    day = _ist_today()
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO chat_usage (user_id, day, llm_turns) VALUES (?,?,1)"
            " ON CONFLICT(user_id, day) DO UPDATE SET llm_turns=llm_turns+1",
            (user_id, day))
        conn.commit()
    return get_chat_usage(user_id)


def get_chat_usage(user_id: str) -> int:
    row = _get_conn().execute(
        "SELECT llm_turns FROM chat_usage WHERE user_id=? AND day=?",
        (user_id, _ist_today())).fetchone()
    return int(row["llm_turns"]) if row else 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_m0_user_store.py -q`
Expected: all PASS

- [ ] **Step 6: Verify settings import**

Run: `python -c "from core.config import settings; print(settings.AUTH_REQUIRED, settings.CHAT_DAILY_QUOTA)"`
Expected: `False 30`

- [ ] **Step 7: Commit**

```bash
git add src/backend/shared/config/settings/base.py services/data/stores/user_store.py tests/unit/test_m0_user_store.py
git commit -m "feat(m0): identity store (users/sessions/invites/chat-usage) + AUTH_REQUIRED/CHAT_DAILY_QUOTA settings"
```

---

### Task 2: Auth dependency (`get_current_user`)

**Files:**
- Modify: `services/api/auth.py` (append; keep `check_scheduler_key` untouched)
- Test: `tests/unit/test_m0_auth_dependency.py`

**Interfaces:**
- Consumes: `user_store.resolve_session`, `settings.AUTH_REQUIRED`, `settings.PORTFOLIO_DEFAULT_USER_ID`
- Produces (used by Tasks 3/4/5):
  - `async def get_current_user(authorization: str | None) -> dict` — FastAPI dependency; 401 when no valid session **and** `AUTH_REQUIRED` is true; owner-passthrough dict when `AUTH_REQUIRED` is false and no token
  - `async def get_current_user_optional(authorization: str | None) -> dict | None`
  - Owner-passthrough user dict: `{"user_id": settings.PORTFOLIO_DEFAULT_USER_ID, "email": "", "display_name": "Owner", "role": "owner", "created_at": ""}`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_m0_auth_dependency.py`:

```python
"""M0 — bearer-session dependency tests (spec §4.3)."""
import asyncio
import pytest
from fastapi import HTTPException


@pytest.fixture()
def deps(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    from services.api import auth
    return auth, user_store


def test_valid_bearer_resolves_user(deps):
    auth, store = deps
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], True)
    got = asyncio.run(auth.get_current_user(authorization=f"Bearer {tok}"))
    assert got["user_id"] == u["user_id"]


def test_anonymous_passthrough_when_auth_not_required(deps, monkeypatch):
    auth, _ = deps
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    got = asyncio.run(auth.get_current_user(authorization=None))
    assert got["user_id"] == settings.PORTFOLIO_DEFAULT_USER_ID
    assert got["role"] == "owner"


def test_anonymous_401_when_auth_required(deps, monkeypatch):
    auth, _ = deps
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.get_current_user(authorization=None))
    assert ei.value.status_code == 401


def test_bad_token_401_even_when_not_required(deps, monkeypatch):
    # A *presented* invalid token is always rejected — no silent fallback.
    auth, _ = deps
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.get_current_user(authorization="Bearer garbage"))
    assert ei.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_auth_dependency.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'get_current_user'`

- [ ] **Step 3: Implement — append to `services/api/auth.py`**

```python
# ---------------------------------------------------------------------------
# M0 (spec 2026-07-26 §4.3) — bearer-session user identity.
# AUTH_REQUIRED=false (default): anonymous requests act as the owner, so the
# merge deploy is a behavioral no-op. Flip the env var to enforce — no code
# change, same pattern as SCHEDULER_KEY above.
# ---------------------------------------------------------------------------
from fastapi import Header

from core.config import settings


def _owner_passthrough() -> dict:
    return {"user_id": settings.PORTFOLIO_DEFAULT_USER_ID, "email": "",
            "display_name": "Owner", "role": "owner", "created_at": ""}


async def get_current_user_optional(
        authorization: str | None = Header(None)) -> dict | None:
    """Resolve Bearer token → user dict. Invalid *presented* tokens raise 401;
    absent token returns owner-passthrough (AUTH_REQUIRED=false) or None."""
    if authorization and authorization.lower().startswith("bearer "):
        from services.data.stores import user_store
        user = user_store.resolve_session(authorization[7:].strip())
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session.")
        return user
    if not settings.AUTH_REQUIRED:
        return _owner_passthrough()
    return None


async def get_current_user(
        authorization: str | None = Header(None)) -> dict:
    user = await get_current_user_optional(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_m0_auth_dependency.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/auth.py tests/unit/test_m0_auth_dependency.py
git commit -m "feat(m0): bearer-session get_current_user dependency with AUTH_REQUIRED rollout switch"
```

---

### Task 3: Auth routes + server registration

**Files:**
- Create: `services/api/routes/auth_api.py`
- Modify: `services/api/server.py` (router registration ~line 432; startup sweep ~line 358)
- Test: `tests/unit/test_m0_auth_api.py`

**Interfaces:**
- Consumes: `user_store` (Task 1), `get_current_user` (Task 2)
- Produces: routes `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/invites`, `GET /auth/invites`, `DELETE /auth/account`. Response envelope for signup/login: `{"token": str, "user": {user_id, email, display_name, role}}`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_m0_auth_api.py`:

```python
"""M0 — auth route tests (spec §4.2) via FastAPI TestClient on a bare app."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    from services.api.routes.auth_api import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _signup(client, email="me@x.com", invite=None, consent=True):
    return client.post("/auth/signup", json={
        "email": email, "password": "hunter2longer", "display_name": "Me",
        "invite_code": invite, "remember_me": True, "consent": consent})


def test_first_user_becomes_owner_primary_no_invite(client):
    r = _signup(client)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["user_id"] == "primary"
    assert body["user"]["role"] == "owner"
    assert body["token"]


def test_second_user_needs_valid_invite(client):
    tok = _signup(client).json()["token"]
    r = _signup(client, email="f@x.com", invite=None)
    assert r.status_code == 403
    inv = client.post("/auth/invites",
                      headers={"Authorization": f"Bearer {tok}"}).json()["code"]
    r2 = _signup(client, email="f@x.com", invite=inv)
    assert r2.status_code == 200
    assert r2.json()["user"]["user_id"].startswith("u_")
    # invite is single-use
    assert _signup(client, email="g@x.com", invite=inv).status_code == 403


def test_consent_required(client):
    r = _signup(client, consent=False)
    assert r.status_code == 422


def test_login_logout_me(client):
    _signup(client)
    r = client.post("/auth/login", json={
        "email": "ME@x.com", "password": "hunter2longer", "remember_me": False})
    assert r.status_code == 200
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/auth/me", headers=h).json()["user"]["user_id"] == "primary"
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_login_generic_401(client):
    _signup(client)
    for email, pw in [("me@x.com", "wrongpassword"), ("no@x.com", "hunter2longer")]:
        r = client.post("/auth/login", json={
            "email": email, "password": pw, "remember_me": False})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password."


def test_invites_owner_only(client):
    tok_owner = _signup(client).json()["token"]
    inv = client.post("/auth/invites",
                      headers={"Authorization": f"Bearer {tok_owner}"}).json()["code"]
    tok_member = _signup(client, email="f@x.com", invite=inv).json()["token"]
    r = client.post("/auth/invites",
                    headers={"Authorization": f"Bearer {tok_member}"})
    assert r.status_code == 403


def test_member_can_delete_account_owner_cannot(client, tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"),
                        raising=False)
    tok_owner = _signup(client).json()["token"]
    inv = client.post("/auth/invites",
                      headers={"Authorization": f"Bearer {tok_owner}"}).json()["code"]
    tok_member = _signup(client, email="f@x.com", invite=inv).json()["token"]
    assert client.delete("/auth/account",
                         headers={"Authorization": f"Bearer {tok_member}"}).status_code == 200
    assert client.delete("/auth/account",
                         headers={"Authorization": f"Bearer {tok_owner}"}).status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_auth_api.py -q`
Expected: FAIL with `ModuleNotFoundError: services.api.routes.auth_api`

- [ ] **Step 3: Implement `services/api/routes/auth_api.py`**

```python
"""
services/api/routes/auth_api.py
===============================
M0 auth routes (spec 2026-07-26 §4.2): signup (invite-gated after the first
user), login, logout, me, owner invite management, DPDP self-service account
deletion. Sessions are bearer tokens resolved by services.api.auth.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from services.api.auth import get_current_user
from services.data.stores import user_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

_MIN_PW = 10


class SignupBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=_MIN_PW)
    display_name: str = ""
    invite_code: str | None = None
    remember_me: bool = True
    consent: bool


class LoginBody(BaseModel):
    email: str
    password: str
    remember_me: bool = False


def _session_response(user: dict, remember_me: bool) -> dict:
    return {"token": user_store.create_session(user["user_id"], remember_me),
            "user": user}


@router.post("/signup")
def signup(body: SignupBody) -> dict:
    if not body.consent:
        raise HTTPException(status_code=422,
                            detail="Consent to the data-use notice is required.")
    first_user = user_store.count_users() == 0
    if first_user:
        try:
            user = user_store.create_user(
                body.email, body.password, body.display_name,
                role="owner", user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
        except ValueError:
            raise HTTPException(status_code=409, detail="Email already registered.")
        logger.info("[auth] owner account created")
        return _session_response(user, body.remember_me)
    if not body.invite_code:
        raise HTTPException(status_code=403, detail="An invite code is required.")
    try:
        user = user_store.create_user(body.email, body.password, body.display_name)
    except ValueError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    if not user_store.consume_invite(body.invite_code, user["user_id"]):
        user_store.delete_user(user["user_id"])
        raise HTTPException(status_code=403, detail="Invalid or used invite code.")
    return _session_response(user, body.remember_me)


@router.post("/login")
def login(body: LoginBody) -> dict:
    user = user_store.verify_password(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _session_response(user, body.remember_me)


@router.post("/logout")
def logout(user: dict = Depends(get_current_user),
           authorization: str | None = Header(None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        user_store.revoke_session(authorization[7:].strip())
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


@router.post("/invites")
def create_invite(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    return {"code": user_store.create_invite(user["user_id"])}


@router.get("/invites")
def list_invites(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    return {"invites": user_store.list_invites()}


@router.delete("/account")
def delete_account(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] == "owner":
        raise HTTPException(status_code=403,
                            detail="The owner account cannot self-delete.")
    user_store.delete_user(user["user_id"])
    pf_dir = Path(settings.PORTFOLIO_DATA_DIR) / user["user_id"]
    try:
        if pf_dir.is_dir():
            shutil.rmtree(pf_dir)
    except Exception as exc:
        logger.warning("[auth] portfolio dir cleanup failed for %s: %s",
                       user["user_id"], exc)
    logger.info("[auth] account deleted (DPDP): %s", user["user_id"])
    return {"ok": True}
```

(Note the `Header` import: add `from fastapi import Header` to the imports at the top of the file.)

- [ ] **Step 4: Register router + startup sweep in `services/api/server.py`**

Next to the other imports/registrations (~line 432):

```python
from services.api.routes.auth_api import router as auth_router
app.include_router(auth_router,      tags=["Auth"])
```

In the startup block next to the chat-session sweep (~line 358-364), add:

```python
# M0: session TTL sweep (users.db; same singleton-guard as the chat sweep above)
try:
    from services.data.stores.user_store import sweep_expired_sessions
    swept = sweep_expired_sessions()
    if swept:
        logger.info("[startup] Swept %d expired auth sessions", swept)
except Exception as exc:
    logger.warning("[startup] Auth session sweep failed (non-fatal): %s", exc)
```

Mirror exactly how the chat sweep is guarded (if it runs only on the singleton worker, this one does too — read the surrounding lines first).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_m0_auth_api.py -q`
Expected: all PASS

- [ ] **Step 6: Boot smoke**

Run: `python -c "from services.api.server import app; print('routes:', sum(1 for r in app.routes if getattr(r,'path','').startswith('/auth')))"`
Expected: `routes: 7`

- [ ] **Step 7: Commit**

```bash
git add services/api/routes/auth_api.py services/api/server.py tests/unit/test_m0_auth_api.py
git commit -m "feat(m0): /auth routes (signup/login/logout/me/invites/account) + startup session sweep"
```

---

### Task 4: IDOR fix — portfolio routes take identity from the session

**Files:**
- Modify: `services/api/routes/portfolio_api.py` (every route with `user_id: str | None = Query(default=None)`)
- Test: `tests/unit/test_m0_idor.py`

**Interfaces:**
- Consumes: `get_current_user` (Task 2)
- Produces: user-scoped portfolio routes whose store is always `PortfolioStore(user_id=user["user_id"])`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_m0_idor.py`:

```python
"""M0 — IDOR regression tests (spec §3 D6, legal doc §5.1).

A member must never be able to read another user's portfolio by naming a
user_id; anonymous access is owner-passthrough only while AUTH_REQUIRED=false.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"),
                        raising=False)
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    from services.api.routes.auth_api import router as auth_router
    from services.api.routes.portfolio_api import router as pf_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(pf_router)
    return TestClient(app)


def _mk_member(client):
    tok_owner = client.post("/auth/signup", json={
        "email": "me@x.com", "password": "hunter2longer", "display_name": "O",
        "invite_code": None, "remember_me": True, "consent": True}).json()["token"]
    inv = client.post("/auth/invites",
                      headers={"Authorization": f"Bearer {tok_owner}"}).json()["code"]
    tok_member = client.post("/auth/signup", json={
        "email": "f@x.com", "password": "hunter2longer", "display_name": "F",
        "invite_code": inv, "remember_me": True, "consent": True}).json()["token"]
    return tok_owner, tok_member


def test_member_cannot_name_another_user_id(client):
    _, tok_member = _mk_member(client)
    r = client.get("/portfolio?user_id=primary",
                   headers={"Authorization": f"Bearer {tok_member}"})
    assert r.status_code == 200
    # The query param must be IGNORED: member sees their own (empty) portfolio.
    assert r.json()["user_id"] != "primary"


def test_member_sees_own_empty_portfolio(client):
    _, tok_member = _mk_member(client)
    r = client.get("/portfolio",
                   headers={"Authorization": f"Bearer {tok_member}"})
    assert r.status_code == 200
    assert r.json()["holdings"] == []


def test_anonymous_owner_passthrough_when_not_required(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    r = client.get("/portfolio")
    assert r.status_code == 200
    assert r.json()["user_id"] == settings.PORTFOLIO_DEFAULT_USER_ID


def test_anonymous_401_when_required(client, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    assert client.get("/portfolio").status_code == 401
```

Note: the `GET /portfolio` response shape (`user_id`, `holdings` keys) comes from the existing route (~`portfolio_api.py:95`). Adjust assertions to the actual JSON keys after reading the route — the *security* assertions (which user's data, 401) are the point.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_idor.py -q`
Expected: `test_member_cannot_name_another_user_id` FAILS (query param currently honored) and `test_anonymous_401_when_required` FAILS (no auth on routes)

- [ ] **Step 3: Rewire `portfolio_api.py`**

Mechanical, repeated for **every** route in the file that has `user_id: str | None = Query(default=None)` (grep shows ~12 sites: lines ~79, 106, 181, 240, 266, 283, 305, 316, 332, 343, …):

1. Add imports at top: `from fastapi import Depends` (if absent) and `from services.api.auth import get_current_user`.
2. Replace the parameter `user_id: str | None = Query(default=None)` with `user: dict = Depends(get_current_user)`.
3. Replace every use of `user_id` in the body with `user["user_id"]` (i.e. `_store(user["user_id"])`).
4. Keep `_store()` itself unchanged.
5. Do NOT touch routes that are scheduler-internal (anything guarded by `check_scheduler_key`) — machine identity stays key-based (spec D10).

Docstring at the top of the file (line ~6) currently says "user_id query param defaults to portfolio.default_user_id" — update it to "identity comes from the bearer session (M0); AUTH_REQUIRED=false maps anonymous to the owner".

- [ ] **Step 4: Run the new tests + the existing portfolio tests**

Run: `python -m pytest tests/unit/test_m0_idor.py -q && python -m pytest tests/unit -k portfolio -q`
Expected: new tests PASS. Existing portfolio API tests may need the same mechanical change **in test setup only** (they may pass `user_id=` query params — those now get ignored, which for single-user test fixtures resolves to owner-passthrough and should still pass with `AUTH_REQUIRED=false` default). If any existing test asserts on the ignored param's effect, update the test to use a bearer session instead, and say so in the commit message.

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/portfolio_api.py tests/unit/test_m0_idor.py
git commit -m "fix(m0): portfolio routes derive user from bearer session, never from client params (IDOR)"
```

---

### Task 5: Narrator cache — one LLM call per verdict-context per day

**Files:**
- Create: `core/portfolio/narrative_cache.py`
- Modify: `core/portfolio/narrator.py`
- Test: `tests/unit/test_m0_narrator_cache.py` (extend patterns from existing `tests/unit/test_portfolio_narrator.py`)

**Interfaces:**
- Consumes: `atomic_io` utils, existing `AdviceRecord`/`AdvisorSignals`
- Produces:
  - `narrative_cache.get(key: str) -> str | None`, `narrative_cache.put(key: str, text: str) -> None`, `narrative_cache.context_key(symbol, verdict, triggers, notes, regime_label, ist_date) -> str`
  - `narrator.narrate(rec, signals)` — same signature, now cache-backed; returns `<ticker narrative> <user suffix>`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_m0_narrator_cache.py`:

```python
"""M0 — narrator cache tests (spec §4.4, decision D7/D8)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _rec(pnl=12.3):
    return SimpleNamespace(symbol="TCS", verdict="TRIM", close=4100.0,
                           unrealised_pnl_pct=pnl, stop_pct=-8.0,
                           triggers=["trim_profit_confidence_decline"],
                           notes=[])


def _signals():
    return SimpleNamespace(regime_label="RANGE_NEUTRAL")


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path, monkeypatch):
    from core.portfolio import narrative_cache
    monkeypatch.setattr(narrative_cache, "_CACHE_PATH",
                        tmp_path / "narrative_cache.json")
    narrative_cache._mem.clear()
    yield


def test_context_key_ignores_user_numbers():
    from core.portfolio.narrative_cache import context_key
    k1 = context_key("TCS", "TRIM", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    k2 = context_key("TCS", "TRIM", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    k3 = context_key("TCS", "HOLD", ["a"], [], "RANGE_NEUTRAL", "2026-07-26")
    assert k1 == k2 and k1 != k3


def test_second_call_same_context_hits_cache():
    from core.portfolio import narrator
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"narrative": "Ticker-level why."}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
    with patch.object(narrator, "get_llm_client", return_value=fake), \
         patch.object(narrator.settings, "ADVISOR_NARRATE", True):
        out1 = narrator.narrate(_rec(pnl=12.3), _signals())
        out2 = narrator.narrate(_rec(pnl=-4.0), _signals())   # different user P&L!
    assert fake.chat.completions.create.call_count == 1        # ONE call
    assert "Ticker-level why." in out1 and "Ticker-level why." in out2
    assert "+12.3%" in out1 and "-4.0%" in out2                # per-user suffixes


def test_cache_failure_degrades_to_llm(monkeypatch):
    from core.portfolio import narrator, narrative_cache
    monkeypatch.setattr(narrative_cache, "get",
                        lambda k: (_ for _ in ()).throw(RuntimeError("boom")))
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"narrative": "Fresh."}'))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    with patch.object(narrator, "get_llm_client", return_value=fake), \
         patch.object(narrator.settings, "ADVISOR_NARRATE", True):
        assert "Fresh." in narrator.narrate(_rec(), _signals())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_narrator_cache.py -q`
Expected: FAIL with `ModuleNotFoundError: core.portfolio.narrative_cache`

- [ ] **Step 3: Implement `core/portfolio/narrative_cache.py`**

```python
"""
core/portfolio/narrative_cache.py
=================================
M0 (spec 2026-07-26 §4.4): day-scoped cache of ticker-level narrator output,
keyed by verdict context — the same (symbol, verdict, triggers, notes, regime,
date) produces the same narration for every user, so the LLM runs once per
context per day instead of once per user-holding. File-backed on the volume
(atomic writes) with an in-process dict in front. Failures degrade to a miss.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.utils.atomic_io import atomic_write_json  # match actual util name

logger = logging.getLogger(__name__)

_CACHE_PATH = Path("data/narrative_cache.json")
_mem: dict[str, str] = {}
_KEEP_DAYS = 2
_IST = ZoneInfo("Asia/Kolkata")


def ist_today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def context_key(symbol: str, verdict: str, triggers: list[str],
                notes: list[str], regime_label: str, ist_date: str) -> str:
    blob = "|".join([symbol, verdict, ",".join(sorted(triggers)),
                     ",".join(sorted(notes)), regime_label, ist_date])
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _load_disk() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key: str) -> str | None:
    if key in _mem:
        return _mem[key]
    day_map = _load_disk().get(ist_today(), {})
    if key in day_map:
        _mem[key] = day_map[key]
        return day_map[key]
    return None


def put(key: str, text: str) -> None:
    _mem[key] = text
    try:
        disk = _load_disk()
        today = ist_today()
        disk.setdefault(today, {})[key] = text
        keep = sorted(disk.keys())[-_KEEP_DAYS:]
        disk = {d: v for d, v in disk.items() if d in keep}
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(_CACHE_PATH, disk)
    except Exception as exc:  # cache write failure must never block narration
        logger.warning("[narrative_cache] persist failed (non-fatal): %s", exc)
```

**Before coding:** open `core/utils/atomic_io.py` and use its actual exported function name (the plan assumes `atomic_write_json(path, obj)`; if the util exposes e.g. `atomic_write(path, text)`, adapt the one call site accordingly).

- [ ] **Step 4: Modify `core/portfolio/narrator.py`**

Three edits:

(a) Remove user-specific lines from the prompt — replace the `_PROMPT` block (lines ~43-52) with:

```python
_PROMPT = """You are the narration layer of a personal stock-research tool.
Write a 2-3 sentence research note (NOT financial advice — never use the word
"advice") explaining this deterministic verdict on the stock.

Verdict: {verdict} on {symbol} at close ₹{close}
Regime: {regime}
Rule triggers: {triggers}
Annotations: {notes}

Do not mention any specific investor's position, P&L, or stop level.
Respond with JSON: {{"narrative": "<2-3 sentences>"}}"""
```

(b) Add the user suffix helper (after `fallback_narrative`):

```python
def _user_suffix(rec: AdviceRecord) -> str:
    return f" Your position: {rec.unrealised_pnl_pct:+.1f}% vs a {rec.stop_pct:.1f}% stop."
```

(c) Rework `narrate()` — cache check before the LLM, cache store after, suffix on every return path (including cache hits), fallback path unchanged except it also gets the suffix:

```python
def narrate(rec: AdviceRecord, signals: AdvisorSignals) -> str:
    if not settings.ADVISOR_NARRATE:
        return fallback_narrative(rec) + _user_suffix(rec)
    from core.portfolio import narrative_cache
    try:
        key = narrative_cache.context_key(
            rec.symbol, rec.verdict, list(rec.triggers), list(rec.notes),
            signals.regime_label, narrative_cache.ist_today())
        cached = narrative_cache.get(key)
    except Exception as exc:
        logger.warning("[narrator] cache read failed (non-fatal): %s", exc)
        key, cached = None, None
    if cached:
        return cached + _user_suffix(rec)
    started = time.time()
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=settings.LLM_MODEL_BULK,
            messages=[{"role": "user", "content": _PROMPT.format(
                verdict=rec.verdict, symbol=rec.symbol, close=rec.close,
                regime=signals.regime_label,
                triggers=", ".join(rec.triggers) or "none",
                notes=", ".join(rec.notes) or "none",
            )}],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=300,
            response_format={"type": "json_object"},
            extra_body=JSON_MODE_EXTRA_BODY,
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = salvage_truncated_json(raw)
        if not isinstance(data, dict):
            data = {}
        narrative = str(data.get("narrative", "")).strip()
        usage = getattr(resp, "usage", None)
        record_llm_call(
            "portfolio_narrator", settings.LLM_MODEL_BULK,
            getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0),
            int((time.time() - started) * 1000), True,
        )
        if narrative and key:
            try:
                narrative_cache.put(key, narrative)
            except Exception as exc:
                logger.warning("[narrator] cache write failed (non-fatal): %s", exc)
        return (narrative or fallback_narrative(rec)) + _user_suffix(rec)
    except Exception as exc:
        logger.warning("[narrator] narration failed for %s (non-fatal): %s", rec.symbol, exc)
        try:
            record_llm_call(
                "portfolio_narrator", settings.LLM_MODEL_BULK, 0, 0,
                int((time.time() - started) * 1000), False,
            )
        except Exception:
            pass
        return fallback_narrative(rec) + _user_suffix(rec)
```

- [ ] **Step 5: Run new + existing narrator tests**

Run: `python -m pytest tests/unit/test_m0_narrator_cache.py tests/unit/test_portfolio_narrator.py -q`
Expected: new tests PASS. Existing narrator tests may assert on exact output without the suffix — update those assertions to expect the suffix (behavior change is intentional and spec'd), noting it in the commit message.

- [ ] **Step 6: Commit**

```bash
git add core/portfolio/narrative_cache.py core/portfolio/narrator.py tests/unit/test_m0_narrator_cache.py tests/unit/test_portfolio_narrator.py
git commit -m "feat(m0): narrator cache — one LLM call per (ticker,verdict-context,day); user numbers via deterministic suffix"
```

---

### Task 6: Chat quotas

**Files:**
- Modify: `services/api/routes/ui_data.py` (`POST /ui/chat` ~line 2908 and `POST /ui/chat/stream` ~line 3227)
- Test: `tests/unit/test_m0_chat_quota.py`

**Interfaces:**
- Consumes: `get_current_user` (Task 2), `user_store.bump_chat_usage/get_chat_usage` (Task 1), `settings.CHAT_DAILY_QUOTA`
- Produces: helper `check_chat_quota(user: dict) -> dict | None` in `ui_data.py` — returns the 429 payload dict when over quota, else None (after counting the turn)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_m0_chat_quota.py`:

```python
"""M0 — chat quota tests (spec §4.5, decision D9)."""
import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    return user_store


def test_member_over_quota_blocked(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 2, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    member = {"user_id": "u_ab", "role": "member"}
    assert check_chat_quota(member) is None          # turn 1
    assert check_chat_quota(member) is None          # turn 2
    blocked = check_chat_quota(member)               # turn 3 → blocked
    assert blocked is not None and blocked["error"] == "daily_quota"


def test_owner_exempt(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 1, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    owner = {"user_id": "primary", "role": "owner"}
    for _ in range(5):
        assert check_chat_quota(owner) is None


def test_zero_quota_means_unlimited(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 0, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    member = {"user_id": "u_ab", "role": "member"}
    for _ in range(5):
        assert check_chat_quota(member) is None


def test_store_failure_allows_turn(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 1, raising=False)
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "bump_chat_usage",
                        lambda uid: (_ for _ in ()).throw(RuntimeError("db gone")))
    from services.api.routes.ui_data import check_chat_quota
    assert check_chat_quota({"user_id": "u_ab", "role": "member"}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_m0_chat_quota.py -q`
Expected: FAIL with `ImportError: cannot import name 'check_chat_quota'`

- [ ] **Step 3: Implement in `services/api/routes/ui_data.py`**

Add near the chat endpoints (~line 2900), plus `from services.api.auth import get_current_user` at the imports:

```python
def check_chat_quota(user: dict) -> dict | None:
    """M0 (spec §4.5): count this LLM turn against the user's daily quota.
    Returns the 429 payload when exhausted, else None. One user message = one
    turn regardless of internal tool fan-out. Availability over strict
    metering: storage failure allows the turn (loudly)."""
    from core.config import settings as _s
    quota = int(getattr(_s, "CHAT_DAILY_QUOTA", 0) or 0)
    if quota <= 0 or user.get("role") == "owner":
        return None
    try:
        from services.data.stores import user_store
        used = user_store.bump_chat_usage(user["user_id"])
    except Exception as exc:
        logger.warning("[ui/chat] quota store failed — allowing turn: %s", exc)
        return None
    if used > quota:
        return {"error": "daily_quota",
                "detail": (f"You've used your {quota} assistant questions for "
                           "today — resets at midnight IST.")}
    return None
```

Wire into both endpoints:

- `POST /ui/chat` (~line 2908): add parameter `user: dict = Depends(get_current_user)`; first line of the handler body, **before any LLM/session work**:

```python
    quota_block = check_chat_quota(user)
    if quota_block:
        return JSONResponse(status_code=429, content=quota_block)
```

- `POST /ui/chat/stream` (~line 3227): add the same `Depends(get_current_user)` parameter; before starting the SSE generator, run the same check; when blocked, return the stream's error shape — read how the endpoint currently emits its SSE `error` event on LLM failure (~line 3373) and reuse that exact mechanism, sending `quota_block["detail"]` as the message, then close. (`JSONResponse(429)` before the stream begins is also acceptable if the frontend handles non-SSE errors — check how the PWA calls it; prefer the SSE error event for uniformity.)

Import note: `JSONResponse` may already be imported in this file; add `from fastapi.responses import JSONResponse` only if missing. Same for `Depends`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_m0_chat_quota.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/routes/ui_data.py tests/unit/test_m0_chat_quota.py
git commit -m "feat(m0): chat daily quota (member-only, owner exempt, availability-first)"
```

---

### Task 7: Frontend — wire the auth screen, token plumbing, quota copy

**Files:**
- Modify: `src/frontend/prototypes/auth.jsx` (login/signup submit, invite + consent fields)
- Modify: `src/frontend/prototypes/index.html` (fetch wrapper ~lines 107-123; boot flow)

**Interfaces:**
- Consumes: `/auth/*` routes (Task 3); 429 `daily_quota` payload (Task 6)
- Produces: token in `localStorage['sa_auth_token']` (remember-me) / `sessionStorage['sa_auth_token']`; every same-origin API call carries `Authorization: Bearer <token>`

This task is UI wiring in a hand-rolled React prototype — read the surrounding component code first and match its patterns (the file uses hooks like `useStateAuth`, styled spans, no build step).

- [ ] **Step 1: Token helpers + wrapper extension in `index.html`**

Inside the same `<script>` that defines the Wave-B fetch wrapper (~line 107), extend it:

```javascript
  function saGetToken() {
    return localStorage.getItem('sa_auth_token')
        || sessionStorage.getItem('sa_auth_token') || '';
  }
  function saSetToken(tok, remember) {
    (remember ? localStorage : sessionStorage).setItem('sa_auth_token', tok);
    (remember ? sessionStorage : localStorage).removeItem('sa_auth_token');
  }
  function saClearToken() {
    localStorage.removeItem('sa_auth_token');
    sessionStorage.removeItem('sa_auth_token');
  }
```

In the wrapper body where `X-Scheduler-Key` is attached (~line 123), also attach the bearer header and add a 401 hook on the response:

```javascript
        var tok = saGetToken();
        if (tok) {
          init.headers = Object.assign({}, init.headers || {},
                                       { 'Authorization': 'Bearer ' + tok });
        }
```

and after the underlying `fetch` resolves (wrap the returned promise):

```javascript
        return origFetch(input, init).then(function (resp) {
          if (resp.status === 401 && saGetToken()) {
            saClearToken();
            try { window.dispatchEvent(new Event('sa-auth-expired')); } catch (e) {}
          }
          return resp;
        });
```

(Adapt names to the wrapper's actual local variables — read lines 100-130 first.)

- [ ] **Step 2: Wire `auth.jsx` submit handlers**

In the submit button handler (~line 142 `{tab==='login' ? 'Log in' : 'Create account'}`), replace the prototype no-op with real calls:

```javascript
  async function submitAuth() {
    setBusy(true); setErr('');
    try {
      const path = tab === 'login' ? '/auth/login' : '/auth/signup';
      const body = tab === 'login'
        ? { email, password: pw, remember_me: remember }
        : { email, password: pw, display_name: name, invite_code: invite || null,
            remember_me: remember, consent: consent };
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) { setErr(data.detail || 'Something went wrong.'); return; }
      saSetToken(data.token, remember);
      onAuthed(data.user);          // parent callback: route to the app shell
    } catch (e) {
      setErr('Network error — try again.');
    } finally { setBusy(false); }
  }
```

Add to the signup tab: an invite-code field (text input, same `Field` component style as email/password) and a consent checkbox with the one-line notice: *"I agree that my email, portfolio and watchlist are stored to run this research service. Delete anytime in Settings."* Signup button disabled until checked. Add state hooks (`invite`, `consent`, `remember`, `busy`, `err`) following the file's existing `useStateAuth` pattern.

- [ ] **Step 3: Boot flow + logout + quota copy**

- Boot (where the app decides auth vs shell — follow how `auth.jsx` is currently mounted): if `saGetToken()` present → `GET /auth/me` → on 200 route to app shell, on 401 show auth screen. **Preserve `location.hash` across this flow** — notification deep-links (`/#/inbox/...`) must survive login (regression guard for the 2026-07-24 work).
- Listen for the `sa-auth-expired` event → route to auth screen.
- Logout menu item: `POST /auth/logout` then `saClearToken()` then show auth screen.
- Chat UI: when a chat request returns 429 / SSE error with `daily_quota`, render the `detail` string as an assistant-style info bubble (no scary error styling).

- [ ] **Step 4: Manual smoke (local)**

```bash
python main.py  # or the documented local run command — check README/CODEBASE.md
```

In a browser: signup (first user → owner) → logout → login (Remember me) → reload restores session → portfolio renders. Record what you verified in the task report.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/prototypes/auth.jsx src/frontend/prototypes/index.html
git commit -m "feat(m0): wire auth screen to /auth API; bearer token plumbing + 401 handling + quota copy"
```

---

### Task 8: A/B verification, docs, merge, ops handoff

**Files:**
- Modify: `CODEBASE.md` (env table: add `AUTH_REQUIRED`, `CHAT_DAILY_QUOTA`; note `SCHEDULER_KEY` now expected in prod)

- [ ] **Step 1: Full-suite A/B**

Run: `python -m pytest -q 2>&1 | tail -20`
Compare against the Task 0 baseline: the fail-set must be **identical**, plus all `test_m0_*` files green. Any new failure = fix before merging (see spec §9.3).

- [ ] **Step 2: Update `CODEBASE.md` env table**

Add rows next to `PORTFOLIO_DEFAULT_USER_ID` (~line 538):

```markdown
| `AUTH_REQUIRED` | `false` | M0: when true, user-scoped routes require a bearer session; false = anonymous acts as owner (single-user compatibility) |
| `CHAT_DAILY_QUOTA` | `30` | M0: member daily LLM chat turns; owner exempt; 0 = unlimited |
```

- [ ] **Step 3: Commit docs, merge to main (respect the deploy window), push**

```bash
git add CODEBASE.md
git commit -m "docs(m0): env table — AUTH_REQUIRED, CHAT_DAILY_QUOTA"
git checkout main
git merge --no-ff m0-foundation -m "merge: M0 multi-user foundation (spec 2026-07-26)"
git push origin main
```

**Deploy-window check first:** if today is an NSE trading day and current IST time is 16:00–17:20, wait.

- [ ] **Step 4: Report the ops handoff to the user (do not perform these — they are the user's calls)**

1. Set `SCHEDULER_KEY=<long random>` in Railway (flips Wave-B enforcement on; PWA wrapper already sends it).
2. After deploy: sign up in prod first (first account → owner → `primary`, sees the existing portfolio).
3. Verify owner login + a notification deep-link tap on the real phone.
4. Then set `AUTH_REQUIRED=true` in Railway.
5. Generate invites from the owner account for friends.
6. Reminder (legal doc): backups now contain user PII once user #2 exists — access-control the backup destination.

---

## Self-review notes (done at plan time)

- **Spec coverage:** §4.1→Task 1, §4.2→Task 3, §4.3→Task 2, §4.4→Task 5, §4.5→Task 6, §4.6→Task 7, §4.7→Task 8 ops, §6 tests→Tasks 1-6, §7 acceptance→Tasks 4/5/6/8. DELETE /auth/account (spec §4.2 last row) → Task 3. Startup sweep (§4.1) → Task 3 Step 4.
- **Known adaptation points (deliberate, flagged inline):** `atomic_io` exported name (Task 5 Step 3); portfolio JSON keys in IDOR tests (Task 4 Step 1); SSE error shape reuse (Task 6 Step 3); wrapper local variable names (Task 7 Step 1). Each says "read the target lines first."
- **Type consistency:** user dict shape defined once (Task 1 Interfaces) and used identically in Tasks 2/3/4/6. `check_chat_quota` name consistent between Task 6 test and implementation. `sa_auth_token` key consistent across Task 7 steps.
