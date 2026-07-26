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
    # PushStore() with no path arg reads settings.DELIVERY_DATA_DIR (channels.py
    # __init__), so isolate the store by repointing that dir at tmp_path.
    monkeypatch.setattr(channels.settings, "DELIVERY_DATA_DIR",
                        str(tmp_path), raising=False)
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
