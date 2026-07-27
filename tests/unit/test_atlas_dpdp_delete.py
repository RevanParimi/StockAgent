"""Atlas C6 — DPDP right-to-erasure: `delete_user_completely(user_id)`.

One entry point erases every trace of a user across all planes (spec §DPDP /
B4 Q3/Q5):

  1. atlas.db  — `DELETE FROM users` single-transaction cascade: the 7 PII
     tables drop to 0 (feedback_events HARD-DELETE, B4 Q5); the user-free
     instruments/ticker_verdicts survive; invites created_by/used_by SET NULL.
  2. filesystem — `data/portfolio/<uid>/` removed.
  3. chat_sessions.db — this user's chat_turns deleted.
  4. telemetry.db — this user's llm_calls ANONYMIZED (user_id→NULL, B4 Q3),
     row count preserved (cost is a shared-brain signal). The user_id column is
     added by C8; until then a missing-column error is a benign no-op.

Every step is idempotent + hot-path safe (log + continue): a second call
no-ops, one failing step never blocks the others, and the authoritative DB
erasure is committed *before* any best-effort filesystem/cross-DB cleanup.
"""
import sqlite3
import types

import pytest

import services.data.stores.atlas_store as atlas_store
import services.data.stores.chat_session_store as css
import services.data.stores.log_store as log_store


# The 7 PII-bearing tables that ON DELETE CASCADE off `users` (spec §2 / §DPDP).
_PII_TABLES = [
    "sessions", "chat_usage", "user_instruments", "user_advice",
    "push_subscriptions", "outbox", "feedback_events",
]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolate all four stores + the portfolio dir on tmp paths."""
    # atlas.db
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    # chat_sessions.db
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH",
                        str(tmp_path / "chat.db"), raising=False)
    css._reset_for_tests()
    # telemetry.db
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH",
                        str(tmp_path / "telemetry.db"), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    # portfolio dir
    from core.config import settings as core_settings
    pf_root = tmp_path / "portfolio"
    monkeypatch.setattr(core_settings, "PORTFOLIO_DATA_DIR", str(pf_root),
                        raising=False)
    ns = types.SimpleNamespace(tmp=tmp_path, pf_root=pf_root,
                               telemetry=tmp_path / "telemetry.db")
    yield ns
    atlas_store._reset_for_tests()
    css._reset_for_tests()
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


def _seed_full_user(conn, uid="u_1"):
    """One user + one row in every user-linked table + a shared instrument,
    a verdict, and an invite the user created and consumed."""
    conn.execute(
        "INSERT INTO users (user_id, email, pw_hash, created_at, consent_at)"
        " VALUES (?,?,?,?,?)",
        (uid, f"{uid}@x.com", "h", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO instruments (sym, created_at, updated_at)"
                 " VALUES ('TCS','2026-01-01','2026-01-01')")
    conn.execute("INSERT INTO ticker_verdicts (symbol, as_of_date)"
                 " VALUES ('TCS','2026-01-01')")
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at,"
                 " expires_at, last_seen) VALUES ('t', ?, 0, 0, 0)", (uid,))
    conn.execute("INSERT INTO chat_usage (user_id, day, llm_turns)"
                 " VALUES (?, '2026-01-01', 3)", (uid,))
    conn.execute("INSERT INTO user_instruments (user_id, symbol, relationship)"
                 " VALUES (?, 'TCS', 'held')", (uid,))
    conn.execute("INSERT INTO user_advice (user_id, symbol, as_of_date, verdict)"
                 " VALUES (?, 'TCS', '2026-01-01', 'HOLD')", (uid,))
    conn.execute("INSERT INTO push_subscriptions (user_id, endpoint)"
                 " VALUES (?, 'https://p/x')", (uid,))
    conn.execute("INSERT INTO outbox (user_id, channel, kind, payload_ref,"
                 " dedupe_key, created_at) VALUES (?, 'push', 'brief', 'ref', ?,"
                 " '2026-01-01')", (uid, f"{uid}|brief|d"))
    conn.execute("INSERT INTO feedback_events (ts, user_id, symbol, action)"
                 " VALUES ('2026-01-01', ?, 'TCS', 'accepted')", (uid,))
    conn.execute("INSERT INTO invites (code, created_by, created_at, used_by,"
                 " used_at) VALUES ('inv1', ?, '2026-01-01', ?, '2026-01-02')",
                 (uid, uid))
    conn.commit()


# --- (1) atlas.db cascade ---------------------------------------------------

def test_cascade_drops_pii_keeps_universe_and_nulls_invites(env):
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    atlas_store.delete_user_completely("u_1")
    for t in _PII_TABLES:
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ticker_verdicts").fetchone()[0] == 1
    row = conn.execute(
        "SELECT created_by, used_by FROM invites WHERE code='inv1'").fetchone()
    assert tuple(row) == (None, None)


# --- (2) portfolio directory ------------------------------------------------

def test_portfolio_dir_removed(env):
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    pf_dir = env.pf_root / "u_1"
    pf_dir.mkdir(parents=True)
    (pf_dir / "portfolio.json").write_text("{}", encoding="utf-8")
    atlas_store.delete_user_completely("u_1")
    assert not pf_dir.exists()


# --- (3) chat turns ---------------------------------------------------------

def test_chat_turns_removed_only_for_target_user(env):
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    css.append_turns("s1", "q", "a", 12, user_id="u_1")
    css.append_turns("s2", "q2", "a2", 12, user_id="u_other")
    atlas_store.delete_user_completely("u_1")
    assert css.get_history("s1", 12, user_id="u_1") == []
    assert [m["content"] for m in css.get_history("s2", 12, user_id="u_other")] \
        == ["q2", "a2"]


# --- (4) telemetry anonymize ------------------------------------------------

def test_telemetry_anonymized_row_count_preserved(env):
    # Simulate the post-C8 schema: llm_calls carries a user_id column.
    tconn = sqlite3.connect(str(env.telemetry))
    tconn.executescript(
        "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts TEXT NOT NULL, caller TEXT NOT NULL, model TEXT NOT NULL,"
        " input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,"
        " latency_ms INTEGER DEFAULT 0, success INTEGER DEFAULT 1, user_id TEXT);")
    for uid in ("u_1", "u_1", None, "u_other"):
        tconn.execute("INSERT INTO llm_calls (ts, caller, model, user_id)"
                      " VALUES ('t','chat','m',?)", (uid,))
    tconn.commit()
    tconn.close()

    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    result = atlas_store.delete_user_completely("u_1")

    assert result["telemetry_anonymized"] == 2
    check = sqlite3.connect(str(env.telemetry))
    assert check.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 4
    assert check.execute("SELECT COUNT(*) FROM llm_calls WHERE user_id='u_1'"
                         ).fetchone()[0] == 0
    assert check.execute("SELECT COUNT(*) FROM llm_calls WHERE user_id IS NULL"
                         ).fetchone()[0] == 3          # 2 anonymized + 1 pre-NULL
    assert check.execute("SELECT COUNT(*) FROM llm_calls WHERE user_id='u_other'"
                         ).fetchone()[0] == 1
    check.close()


def test_telemetry_missing_user_id_column_is_safe(env):
    # Pre-C8 real state: llm_calls has NO user_id column → benign no-op.
    log_store.log_llm_call("chat", "m", 1, 1, 1, True)
    log_store.log_llm_call("sched", "m", 1, 1, 1, True)
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    result = atlas_store.delete_user_completely("u_1")   # must not raise
    assert result["telemetry_anonymized"] == 0
    check = sqlite3.connect(str(env.telemetry))
    assert check.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 2
    check.close()


# --- idempotency + ordering -------------------------------------------------

def test_second_call_is_a_no_op(env):
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    atlas_store.delete_user_completely("u_1")
    # a second call must not raise and must leave the erased state unchanged
    atlas_store.delete_user_completely("u_1")
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_db_commit_precedes_filesystem(env, monkeypatch):
    # If the filesystem step blows up, the authoritative DB cascade must have
    # already committed — a stray artifact can never block the erasure.
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    pf_dir = env.pf_root / "u_1"
    pf_dir.mkdir(parents=True)
    import shutil
    monkeypatch.setattr(shutil, "rmtree",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    atlas_store.delete_user_completely("u_1")            # must not raise
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


# --- route wiring: DELETE /auth/account -------------------------------------

def test_delete_account_route_erases_and_revokes(env, monkeypatch):
    """End-to-end: the route runs user_store.delete_user +
    atlas_store.delete_user_completely + session revoke; the owner is protected."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.data.stores import user_store

    monkeypatch.setattr(user_store, "_DB_PATH", env.tmp / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    from services.api.routes.auth_api import router
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    def _signup(email, invite):
        return c.post("/auth/signup", json={
            "email": email, "password": "hunter2longer", "display_name": "X",
            "invite_code": invite, "remember_me": True, "consent": True}).json()

    owner = _signup("o@x.com", None)
    owner_h = {"Authorization": f"Bearer {owner['token']}"}
    inv = c.post("/auth/invites", headers=owner_h).json()["code"]
    member = _signup("m@x.com", inv)
    member_id = member["user"]["user_id"]
    member_h = {"Authorization": f"Bearer {member['token']}"}

    # seed the member's cross-plane state
    pf_dir = env.pf_root / member_id
    pf_dir.mkdir(parents=True)
    (pf_dir / "portfolio.json").write_text("{}", encoding="utf-8")
    css.append_turns("sess", "q", "a", 12, user_id=member_id)

    assert c.delete("/auth/account", headers=member_h).status_code == 200
    # session revoked → the token no longer resolves
    assert c.get("/auth/me", headers=member_h).status_code == 401
    # cross-plane state erased
    assert not pf_dir.exists()
    assert css.get_history("sess", 12, user_id=member_id) == []
    # the owner account cannot self-delete
    assert c.delete("/auth/account", headers=owner_h).status_code == 403
