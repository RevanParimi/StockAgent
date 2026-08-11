"""Atlas C3 gap — signup mirrors the new account into atlas.db.

Design: docs/superpowers/specs/2026-08-11-atlas-signup-user-mirror-design.md

`POST /auth/signup` wrote only `users.db`. `atlas_store.user_ids()` — the
fan-out set the morning brief and autopilot iterate — reads `atlas.db`. Post
C11-cutover every new signup would authenticate fine and receive NOTHING.
The one-shot ETL covers accounts that exist at cutover time, so the gap opens
exactly when the first friend is invited.

`users.db` stays the identity SoT; `atlas.db.users` is a derived mirror whose
only jobs are being the FK target for the 7 PII tables and populating
`user_ids()`. Being derived is what makes a non-fatal write safe — provided
the drift is detected, which is the `users_mirrored` invariant.
"""
from __future__ import annotations

import sqlite3
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.data.stores.atlas_store as atlas_store
from services.data.stores import user_store


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Both identity stores on tmp paths, Atlas OFF unless a test says otherwise.

    Deliberately does NOT open the atlas connection: the load-bearing test
    asserts atlas.db is never created, so the fixture must not create it.
    """
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    yield types.SimpleNamespace(tmp=tmp_path,
                                atlas_db=tmp_path / "atlas.db",
                                users_db=tmp_path / "users.db")
    atlas_store._reset_for_tests()


def _seed_user(uid="u_1", email="u1@x.com"):
    return user_store.create_user(email, "hunter2longer", "U One", user_id=uid)


def _atlas_rows(uid="u_1") -> list[sqlite3.Row]:
    return atlas_store._get_conn().execute(
        "SELECT * FROM users WHERE user_id=?", (uid,)).fetchall()


def _source_row(users_db, uid="u_1") -> sqlite3.Row:
    conn = sqlite3.connect(str(users_db))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    finally:
        conn.close()


# --- mirror_user ------------------------------------------------------------

def test_disabled_mirror_never_creates_atlas_db(env):
    """THE load-bearing test. `_get_conn()` creates atlas.db on first touch, and
    the watchdog reads an unexplained atlas.db as a dirty pre-flight → blocked →
    Saturday's automatic ETL prep suppressed. An ungated mirror plus one
    pre-cutover signup would sabotage the very cutover this work supports.

    Asserted on the FILESYSTEM, not on the return value: the return value would
    pass even if the file were created, and the file is what blocks the cutover.
    """
    _seed_user()
    assert atlas_store.mirror_user("u_1", users_db=env.users_db) is False
    assert not env.atlas_db.exists()


def test_copies_the_row_including_pw_hash_and_consent(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _seed_user()
    assert atlas_store.mirror_user("u_1", users_db=env.users_db) is True
    src = _source_row(env.users_db)
    rows = _atlas_rows()
    assert len(rows) == 1
    got = rows[0]
    assert got["email"] == "u1@x.com"
    assert got["display_name"] == "U One"
    assert got["role"] == "member"
    # pw_hash is NOT NULL in atlas.db but _row_to_user() omits it — the mirror
    # must carry it across, which is why this is an ATTACH + INSERT…SELECT.
    assert got["pw_hash"] == src["pw_hash"] and got["pw_hash"]
    assert got["consent_at"] == src["consent_at"] and got["consent_at"]
    assert got["created_at"] == src["created_at"]


def test_mirrored_user_appears_in_the_fanout_set(env, monkeypatch):
    """user_ids() is the whole point: it is what the brief and autopilot iterate."""
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _seed_user()
    atlas_store.mirror_user("u_1", users_db=env.users_db)
    assert atlas_store.user_ids() == ["u_1"]


def test_mirror_is_idempotent(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _seed_user()
    assert atlas_store.mirror_user("u_1", users_db=env.users_db) is True
    assert atlas_store.mirror_user("u_1", users_db=env.users_db) is True
    assert len(_atlas_rows()) == 1


def test_mirror_copies_only_the_named_user(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _seed_user("u_1", "u1@x.com")
    _seed_user("u_2", "u2@x.com")
    atlas_store.mirror_user("u_2", users_db=env.users_db)
    assert atlas_store.user_ids() == ["u_2"]


def test_unknown_user_id_writes_nothing(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _seed_user()
    assert atlas_store.mirror_user("u_ghost", users_db=env.users_db) is False
    assert atlas_store.user_ids() == []


def test_missing_users_db_returns_false_without_raising(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    assert atlas_store.mirror_user("u_1", users_db=env.tmp / "nope.db") is False


def test_a_failed_mirror_leaves_the_connection_usable(env, monkeypatch):
    """DETACH runs in a finally — a stranded `src` attachment would make every
    later atlas write fail with 'database src is already in use'. The source
    here ATTACHes fine and then fails on the SELECT, so the failure lands
    between the ATTACH and the DETACH."""
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    bogus = env.tmp / "empty.db"
    sqlite3.connect(str(bogus)).close()          # a real DB with no `users` table
    assert atlas_store.mirror_user("u_1", users_db=bogus) is False
    _seed_user()
    assert atlas_store.mirror_user("u_1", users_db=env.users_db) is True


# --- signup call site -------------------------------------------------------

@pytest.fixture()
def client(env):
    from services.api.routes.auth_api import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _signup(client, email, invite=None):
    return client.post("/auth/signup", json={
        "email": email, "password": "hunter2longer", "display_name": "X",
        "invite_code": invite, "remember_me": True, "consent": True})


def test_signup_mirrors_the_owner(env, client, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    resp = _signup(client, "o@x.com")
    assert resp.status_code == 200
    assert atlas_store.user_ids() == [resp.json()["user"]["user_id"]]


def test_signup_mirrors_an_invited_member(env, client, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    owner = _signup(client, "o@x.com").json()
    code = client.post("/auth/invites", headers={
        "Authorization": f"Bearer {owner['token']}"}).json()["code"]
    member = _signup(client, "m@x.com", code).json()
    assert set(atlas_store.user_ids()) == {owner["user"]["user_id"],
                                           member["user"]["user_id"]}


def test_invalid_invite_leaves_no_atlas_row(env, client, monkeypatch):
    """The invited branch mirrors AFTER consume_invite. A bad code deletes the
    just-created users.db row and 403s — mirroring first would strand an atlas
    row pointing at a user that no longer exists."""
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    owner = _signup(client, "o@x.com").json()
    assert _signup(client, "m@x.com", "not-a-real-code").status_code == 403
    assert atlas_store.user_ids() == [owner["user"]["user_id"]]


def test_signup_survives_a_raising_mirror(env, client, monkeypatch):
    """mirror_user does not raise in normal operation, so this exercises the
    call-site try/except — without it the guard could be deleted as dead code
    and no test would go red. The Atlas plane is a derived index, not the
    account: signup must never fail because of it."""
    monkeypatch.setenv("ATLAS_ENABLED", "true")

    def boom(*a, **k):
        raise RuntimeError("atlas is on fire")

    monkeypatch.setattr(atlas_store, "mirror_user", boom)
    resp = _signup(client, "o@x.com")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "o@x.com"


def test_signup_does_not_create_atlas_db_before_the_cutover(env, client):
    """Same landmine as the unit test, proven through the real route: a signup
    while the flag is off must leave the pre-flight clean."""
    assert _signup(client, "o@x.com").status_code == 200
    assert not env.atlas_db.exists()


# --- adjacent: the same landmine on the delete path -------------------------

def test_delete_does_not_materialise_atlas_db_when_absent(env):
    """delete_user_completely is deliberately NOT flag-gated (DPDP erasure must
    run either way), but pre-cutover its `_get_conn()` would create atlas.db and
    block the cutover. A nonexistent DB holds zero rows, so skipping step 1 is
    bit-for-bit identical DPDP semantics."""
    summary = atlas_store.delete_user_completely("u_1")
    assert not env.atlas_db.exists()
    assert summary["atlas_cascade"] is False


def test_delete_still_cascades_when_atlas_db_exists(env):
    conn = atlas_store._get_conn()
    conn.execute("INSERT INTO users (user_id, email, pw_hash, created_at,"
                 " consent_at) VALUES ('u_1','u1@x.com','h','t','t')")
    conn.execute("INSERT INTO chat_usage (user_id, day, llm_turns)"
                 " VALUES ('u_1','2026-01-01',3)")
    conn.commit()
    summary = atlas_store.delete_user_completely("u_1")
    assert summary["atlas_cascade"] is True
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chat_usage").fetchone()[0] == 0
