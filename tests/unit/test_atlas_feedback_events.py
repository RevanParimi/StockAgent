"""Atlas C8 — Blueprint 5 feedback_events (accept/override on advice cards).

Append-only, user-plane, OUTSIDE core/intelligence (Learning Constitution R1 —
the import-boundary guard in test_atlas_import_boundary.py keeps it that way).
A user's rows DPDP-cascade on account delete. Aggregation refuses to return
anything below a distinct-user floor (reviewer R3, privacy).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.data.stores.atlas_store as atlas_store
import services.api.routes.ui_data as ui_data
from core.config import settings
from services.data.stores import user_store


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    yield tmp_path
    atlas_store._reset_for_tests()


def _mk_user(uid):
    atlas_store._get_conn().execute(
        "INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
        " consent_at) VALUES (?,?,?,?,?)",
        (uid, f"{uid}@x.com", "h", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:00+00:00"))
    atlas_store._get_conn().commit()


def _count(uid=None):
    sql = "SELECT COUNT(*) FROM feedback_events"
    args = ()
    if uid:
        sql += " WHERE user_id=?"; args = (uid,)
    return atlas_store._get_conn().execute(sql, args).fetchone()[0]


# --- record -----------------------------------------------------------------

def test_record_persists_all_fields(env):
    _mk_user("u_1")
    rid = atlas_store.record_feedback_event(
        "u_1", "TCS", "overridden", advice_ref="a1", verdict_shown="BUY",
        override_direction="SELL", position_state="losing")
    assert rid is not None
    row = atlas_store._get_conn().execute(
        "SELECT symbol, action, verdict_shown, override_direction, position_state"
        " FROM feedback_events WHERE id=?", (rid,)).fetchone()
    assert tuple(row) == ("TCS", "overridden", "BUY", "SELL", "losing")


def test_record_is_flag_gated_noop(env, monkeypatch):
    _mk_user("u_1")
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    assert atlas_store.record_feedback_event("u_1", "TCS", "accepted") is None
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    assert _count() == 0


def test_invalid_action_is_rejected_safely(env):
    _mk_user("u_1")
    assert atlas_store.record_feedback_event("u_1", "TCS", "not_a_valid_action") is None
    assert _count() == 0


def test_feedback_cascades_on_user_delete(env, monkeypatch):
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(env / "pf"), raising=False)
    _mk_user("u_1")
    atlas_store.record_feedback_event("u_1", "TCS", "accepted")
    assert _count("u_1") == 1
    atlas_store.delete_user_completely("u_1")
    assert _count("u_1") == 0


# --- aggregation floor (privacy, reviewer R3) -------------------------------

def test_aggregate_refuses_below_floor(env, monkeypatch):
    monkeypatch.setattr(atlas_store, "_feedback_floor", lambda: 2)
    _mk_user("u_1")
    atlas_store.record_feedback_event("u_1", "TCS", "accepted")
    assert atlas_store.feedback_aggregate() is None       # 1 user < floor 2


def test_aggregate_returns_at_or_above_floor(env, monkeypatch):
    monkeypatch.setattr(atlas_store, "_feedback_floor", lambda: 2)
    for uid, action in (("u_1", "accepted"), ("u_2", "overridden")):
        _mk_user(uid)
        atlas_store.record_feedback_event(uid, "TCS", action)
    agg = atlas_store.feedback_aggregate()
    assert agg is not None
    assert agg["users"] == 2
    assert agg["by_action"]["accepted"] == 1
    assert agg["by_action"]["overridden"] == 1


# --- endpoint ---------------------------------------------------------------

def test_feedback_endpoint_records_for_session_user(env, monkeypatch):
    monkeypatch.setattr(user_store, "_DB_PATH", env / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    from services.api.routes.auth_api import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(ui_data.router)
    c = TestClient(app, raise_server_exceptions=False)
    tok = c.post("/auth/signup", json={
        "email": "o@x.com", "password": "hunter2longer", "display_name": "O",
        "invite_code": None, "remember_me": True, "consent": True}).json()["token"]
    _mk_user("primary")            # owner's atlas.db row (FK target)
    r = c.post("/ui/feedback",
               json={"symbol": "TCS", "action": "accepted", "verdict_shown": "BUY"},
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert _count("primary") == 1
