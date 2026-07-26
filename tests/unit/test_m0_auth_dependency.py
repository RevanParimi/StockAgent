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
