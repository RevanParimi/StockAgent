"""Atlas C1 — data/atlas.db store foundation (schema + FK-on connection).

This is the FK-linked user-plane relational core designed in
docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md §1/§2. The
store is a behavioral no-op at this task (nothing imports it); these tests pin
the three properties the whole M1 design leans on:

  (a) every connection opens with PRAGMA foreign_keys=ON (per-connection, not
      persisted — the store must re-issue it),
  (b) the foreign keys are actually enforced,
  (c) DELETE FROM users is the single-transaction DPDP cascade — the 7 PII
      tables drop to 0 while the user-free instruments/ticker_verdicts survive
      and the invites audit rows are retained with created_by/used_by NULLed.
"""
import sqlite3

import pytest

import services.data.stores.atlas_store as atlas_store


# The 7 PII-bearing tables that ON DELETE CASCADE off `users` (spec §2 / §DPDP).
_PII_TABLES = [
    "sessions", "chat_usage", "user_instruments", "user_advice",
    "push_subscriptions", "outbox", "feedback_events",
]


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    """Isolate every test on its own tmp atlas.db (same recipe as user_store)."""
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    yield
    atlas_store._reset_for_tests()


def _seed_full_user(conn, uid="u_1"):
    """Insert one user plus one row in every user-linked table + a shared
    instrument + a verdict + an invite the user created and consumed."""
    conn.execute(
        "INSERT INTO users (user_id, email, pw_hash, created_at, consent_at)"
        " VALUES (?,?,?,?,?)",
        (uid, f"{uid}@x.com", "h", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:00+00:00"))
    conn.execute(
        "INSERT INTO instruments (sym, created_at, updated_at)"
        " VALUES ('TCS','2026-01-01','2026-01-01')")
    conn.execute(
        "INSERT INTO ticker_verdicts (symbol, as_of_date) VALUES ('TCS','2026-01-01')")
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen)"
        " VALUES ('t', ?, 0, 0, 0)", (uid,))
    conn.execute(
        "INSERT INTO chat_usage (user_id, day, llm_turns) VALUES (?, '2026-01-01', 3)",
        (uid,))
    conn.execute(
        "INSERT INTO user_instruments (user_id, symbol, relationship)"
        " VALUES (?, 'TCS', 'held')", (uid,))
    conn.execute(
        "INSERT INTO user_advice (user_id, symbol, as_of_date, verdict)"
        " VALUES (?, 'TCS', '2026-01-01', 'HOLD')", (uid,))
    conn.execute(
        "INSERT INTO push_subscriptions (user_id, endpoint) VALUES (?, 'https://p/x')",
        (uid,))
    conn.execute(
        "INSERT INTO outbox (user_id, channel, kind, payload_ref, dedupe_key, created_at)"
        " VALUES (?, 'push', 'brief', 'ref', ?, '2026-01-01')", (uid, f"{uid}|brief|d"))
    conn.execute(
        "INSERT INTO feedback_events (ts, user_id, symbol, action)"
        " VALUES ('2026-01-01', ?, 'TCS', 'accepted')", (uid,))
    conn.execute(
        "INSERT INTO invites (code, created_by, created_at, used_by, used_at)"
        " VALUES ('inv1', ?, '2026-01-01', ?, '2026-01-02')", (uid, uid))
    conn.commit()


def test_schema_instantiates_with_foreign_keys_on():
    conn = atlas_store._get_conn()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # Every designed table exists.
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ["users", "sessions", "invites", "chat_usage", "instruments",
              "user_instruments", "ticker_verdicts", "user_advice",
              "push_subscriptions", "outbox", "feedback_events"]:
        assert t in names, f"missing table {t}"


def test_fk_enforced_rejects_orphan_user_instrument():
    conn = atlas_store._get_conn()
    conn.execute("INSERT INTO instruments (sym, created_at, updated_at)"
                 " VALUES ('TCS','2026-01-01','2026-01-01')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO user_instruments (user_id, symbol, relationship)"
                     " VALUES ('ghost', 'TCS', 'held')")
        conn.commit()


def test_dpdp_cascade_drops_pii_keeps_universe_and_nulls_invites():
    conn = atlas_store._get_conn()
    _seed_full_user(conn, "u_1")
    # sanity: everything present before delete
    for t in _PII_TABLES:
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 1, t

    conn.execute("DELETE FROM users WHERE user_id='u_1'")
    conn.commit()

    # (1) the 7 PII tables cascade to 0
    for t in _PII_TABLES:
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    # (2) the user-free universe survives
    assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ticker_verdicts").fetchone()[0] == 1
    # (3) the invite audit row is retained with both edges NULLed
    row = conn.execute(
        "SELECT created_by, used_by FROM invites WHERE code='inv1'").fetchone()
    assert tuple(row) == (None, None)


def test_reset_and_db_path_isolate_a_tmp_db(tmp_path, monkeypatch):
    conn = atlas_store._get_conn()
    conn.execute("INSERT INTO users (user_id, email, pw_hash, created_at, consent_at)"
                 " VALUES ('a','a@x.com','h','t','t')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    # Repoint to a *different* tmp DB — the previous data must not bleed through.
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "other.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    conn2 = atlas_store._get_conn()
    assert conn2.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
