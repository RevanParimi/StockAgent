"""M0 — identity store unit tests (spec 2026-07-26 §4.1)."""
import time
import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    return user_store


def test_create_and_verify_user(store):
    u = store.create_user("A@x.com", "hunter2longer", "Alice")
    assert u["user_id"].startswith("u_") and u["role"] == "member"
    assert store.verify_password("a@x.com", "hunter2longer")["user_id"] == u["user_id"]
    assert store.verify_password("a@x.com", "wrong-password") is None
    assert store.verify_password("nobody@x.com", "hunter2longer") is None


def test_duplicate_email_rejected(store):
    store.create_user("a@x.com", "hunter2longer", "Alice")
    with pytest.raises(ValueError):
        store.create_user("A@X.COM", "hunter2longer", "Alice2")


def test_owner_user_id_override(store):
    u = store.create_user("me@x.com", "hunter2longer", "Owner",
                          role="owner", user_id="primary")
    assert u["user_id"] == "primary" and u["role"] == "owner"


def test_session_roundtrip_and_revoke(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], remember_me=True)
    assert store.resolve_session(tok)["user_id"] == u["user_id"]
    store.revoke_session(tok)
    assert store.resolve_session(tok) is None


def test_session_expiry(store, monkeypatch):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], remember_me=False)
    monkeypatch.setattr(store, "_now_epoch", lambda: time.time() + 25 * 3600)
    assert store.resolve_session(tok) is None      # 24h session expired
    assert store.sweep_expired_sessions() >= 1


def test_invite_single_use(store):
    owner = store.create_user("o@x.com", "hunter2longer", "O", role="owner",
                              user_id="primary")
    code = store.create_invite(owner["user_id"])
    assert store.consume_invite(code, "u_new1") is True
    assert store.consume_invite(code, "u_new2") is False   # single-use
    assert store.consume_invite("inv_nope", "u_x") is False


def test_chat_usage_counter(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    assert store.get_chat_usage(u["user_id"]) == 0
    assert store.bump_chat_usage(u["user_id"]) == 1
    assert store.bump_chat_usage(u["user_id"]) == 2
    assert store.get_chat_usage(u["user_id"]) == 2


def test_delete_user(store):
    u = store.create_user("a@x.com", "hunter2longer", "A")
    tok = store.create_session(u["user_id"], True)
    store.delete_user(u["user_id"])
    assert store.verify_password("a@x.com", "hunter2longer") is None
    assert store.resolve_session(tok) is None
