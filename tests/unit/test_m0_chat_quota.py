"""M0 — chat quota tests (spec §4.5, decision D9)."""
import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    return user_store


def test_member_over_quota_blocked(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 2, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    member = {"user_id": "u_ab", "role": "member"}
    assert check_chat_quota(member) is None          # turn 1
    assert check_chat_quota(member) is None          # turn 2
    blocked = check_chat_quota(member)               # turn 3 → blocked
    assert blocked is not None and blocked["error"] == "daily_quota"


def test_owner_exempt(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 1, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    owner = {"user_id": "primary", "role": "owner"}
    for _ in range(5):
        assert check_chat_quota(owner) is None


def test_zero_quota_means_unlimited(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 0, raising=False)
    from services.api.routes.ui_data import check_chat_quota
    member = {"user_id": "u_ab", "role": "member"}
    for _ in range(5):
        assert check_chat_quota(member) is None


def test_store_failure_allows_turn(store, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "CHAT_DAILY_QUOTA", 1, raising=False)
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "bump_chat_usage",
                        lambda uid: (_ for _ in ()).throw(RuntimeError("db gone")))
    from services.api.routes.ui_data import check_chat_quota
    assert check_chat_quota({"user_id": "u_ab", "role": "member"}) is None
