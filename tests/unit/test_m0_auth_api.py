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
