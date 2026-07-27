"""Atlas C5 — global-singleton resolution (design spec §5).

Two things:
  1. The watchlist becomes PER-USER when ATLAS_ENABLED (single SoT =
     Portfolio.watchlist) — two users never see each other's list; the legacy
     global watchlist.json (owner-only) is the dormant path.
  2. The agent_weights / agent_tasks / category configs stay GLOBAL and their
     writes require owner (they tune the one shared brain) — a member is 403.
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
def app_env(tmp_path, monkeypatch):
    # isolate users.db + atlas.db + portfolio dir + global watchlist file
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"),
                        raising=False)
    monkeypatch.setattr(ui_data, "_WATCHLIST_PATH", tmp_path / "watchlist.json",
                        raising=False)
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)

    from services.api.routes.auth_api import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(ui_data.router)
    c = TestClient(app, raise_server_exceptions=False)

    tok_owner = c.post("/auth/signup", json={
        "email": "o@x.com", "password": "hunter2longer", "display_name": "O",
        "invite_code": None, "remember_me": True, "consent": True}).json()["token"]
    inv = c.post("/auth/invites",
                 headers={"Authorization": f"Bearer {tok_owner}"}).json()["code"]
    tok_member = c.post("/auth/signup", json={
        "email": "m@x.com", "password": "hunter2longer", "display_name": "M",
        "invite_code": inv, "remember_me": True, "consent": True}).json()["token"]
    syms = [t["sym"] for t in ui_data._ALL_TICKERS][:2]
    yield c, tok_owner, tok_member, syms
    atlas_store._reset_for_tests()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- watchlist per-user (flag ON) ------------------------------------------

def test_watchlists_are_isolated_between_users(app_env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    c, tok_owner, tok_member, syms = app_env
    a, b = syms

    assert c.put("/ui/watchlist", json={"watchlist": [a]},
                 headers=_auth(tok_member)).status_code == 200
    assert c.put("/ui/watchlist", json={"watchlist": [b]},
                 headers=_auth(tok_owner)).status_code == 200

    member_wl = c.get("/ui/watchlist", headers=_auth(tok_member)).json()["watchlist"]
    owner_wl = c.get("/ui/watchlist", headers=_auth(tok_owner)).json()["watchlist"]
    assert member_wl == [a]
    assert owner_wl == [b]                       # no bleed between users


def test_member_can_edit_own_watchlist_when_enabled(app_env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    c, _, tok_member, syms = app_env
    # a member editing their OWN watchlist is allowed (not owner-gated anymore)
    r = c.put("/ui/watchlist", json={"watchlist": [syms[0]]}, headers=_auth(tok_member))
    assert r.status_code == 200 and r.json()["watchlist"] == [syms[0]]


# ---- owner-config PUTs stay owner-gated ------------------------------------

def test_shared_brain_configs_are_owner_only(app_env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    c, tok_owner, tok_member, _ = app_env
    cat_key = ui_data._CATEGORIES[0]["key"]
    cases = [
        ("/ui/agents/tasks", {"flags": {}}),
        (f"/ui/categories/{cat_key}/tickers", {"add": [], "remove": []}),
    ]
    for path, body in cases:
        assert c.put(path, json=body).status_code == 401                          # anonymous
        assert c.put(path, json=body, headers=_auth(tok_member)).status_code == 403  # member
        assert c.put(path, json=body, headers=_auth(tok_owner)).status_code == 200   # owner


# ---- dormant path (flag OFF) preserves owner-only global watchlist ----------

def test_disabled_watchlist_is_global_owner_only(app_env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    c, tok_owner, tok_member, syms = app_env
    a = syms[0]
    assert c.put("/ui/watchlist", json={"watchlist": [a]}).status_code == 401  # anonymous
    assert c.put("/ui/watchlist", json={"watchlist": [a]},
                 headers=_auth(tok_member)).status_code == 403                  # member blocked
    assert c.put("/ui/watchlist", json={"watchlist": [a]},
                 headers=_auth(tok_owner)).status_code == 200                   # owner writes global
    assert (ui_data._WATCHLIST_PATH).exists()                                   # global file written
