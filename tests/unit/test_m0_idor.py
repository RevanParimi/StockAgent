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
