"""M0.1 — require_owner dependency (SCHEDULER_KEY becomes server-side only).

Owner-session OR valid X-Scheduler-Key passes; members 403; anonymous 401
when AUTH_REQUIRED=true, owner-passthrough when false (local dev unchanged).
"""
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


def _mk_owner(store):
    return store.create_user("o@x.com", "hunter2longer", "O",
                             role="owner", user_id="primary")


def _mk_member(store):
    return store.create_user("m@x.com", "hunter2longer", "M")


def test_owner_session_passes(deps):
    auth, store = deps
    u = _mk_owner(store)
    tok = store.create_session(u["user_id"], True)
    got = asyncio.run(auth.require_owner(
        authorization=f"Bearer {tok}", x_scheduler_key=None))
    assert got["role"] == "owner"


def test_member_session_403(deps):
    auth, store = deps
    u = _mk_member(store)
    tok = store.create_session(u["user_id"], True)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.require_owner(
            authorization=f"Bearer {tok}", x_scheduler_key=None))
    assert ei.value.status_code == 403


def test_valid_scheduler_key_passes_without_session(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.setenv("SCHEDULER_KEY", "sekrit")
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    got = asyncio.run(auth.require_owner(
        authorization=None, x_scheduler_key="sekrit"))
    assert got["role"] == "owner"          # machine acts as owner


def test_wrong_scheduler_key_ignored_anonymous_401(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.setenv("SCHEDULER_KEY", "sekrit")
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.require_owner(
            authorization=None, x_scheduler_key="wrong"))
    assert ei.value.status_code == 401


def test_anonymous_passthrough_when_auth_not_required(deps, monkeypatch):
    # Local dev: no auth, no key → owner-passthrough, everything works.
    auth, _ = deps
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    got = asyncio.run(auth.require_owner(authorization=None, x_scheduler_key=None))
    assert got["role"] == "owner"


def test_anonymous_401_when_auth_required_no_key_set(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.require_owner(authorization=None, x_scheduler_key=None))
    assert ei.value.status_code == 401


# ---------------------------------------------------------------------------
# get_current_user_or_machine — the READ-side counterpart. require_owner is
# wrong for per-user read endpoints because it 403s members out of their OWN
# data; get_current_user alone is wrong because server-to-server reads have no
# session. This dependency is "any valid session OR the machine key".
# ---------------------------------------------------------------------------

def test_machine_key_reads_as_owner_without_a_session(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.setenv("SCHEDULER_KEY", "sekrit")
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    got = asyncio.run(auth.get_current_user_or_machine(
        authorization=None, x_scheduler_key="sekrit"))
    assert got["role"] == "owner"


def test_member_session_still_reads_its_own_data(deps, monkeypatch):
    """The whole reason this is not require_owner: a member must keep seeing
    their own report rather than being 403'd out of it."""
    auth, store = deps
    monkeypatch.setenv("SCHEDULER_KEY", "sekrit")
    u = _mk_member(store)
    tok = store.create_session(u["user_id"], True)
    got = asyncio.run(auth.get_current_user_or_machine(
        authorization=f"Bearer {tok}", x_scheduler_key=None))
    assert got["user_id"] == u["user_id"]
    assert got["role"] != "owner"


def test_wrong_key_falls_through_to_the_session_check(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.setenv("SCHEDULER_KEY", "sekrit")
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.get_current_user_or_machine(
            authorization=None, x_scheduler_key="wrong"))
    assert ei.value.status_code == 401


def test_anonymous_401_when_auth_required_and_no_key(deps, monkeypatch):
    auth, _ = deps
    monkeypatch.delenv("SCHEDULER_KEY", raising=False)
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.get_current_user_or_machine(
            authorization=None, x_scheduler_key=None))
    assert ei.value.status_code == 401
