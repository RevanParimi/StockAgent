"""Atlas A2 — chat history is scoped (user_id, session_id): one user can
never read or extend another user's conversation, even with a stolen/guessed
session_id. Legacy rows default to 'primary' so the owner keeps history."""
import pytest

import services.data.stores.chat_session_store as css


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH",
                        str(tmp_path / "chat.db"), raising=False)
    css._reset_for_tests()
    yield
    css._reset_for_tests()


def test_same_session_id_isolated_between_users():
    css.append_turns("s1", "owner-question", "owner-answer", 12, user_id="primary")
    css.append_turns("s1", "member-question", "member-answer", 12, user_id="u_mem")
    owner = [m["content"] for m in css.get_history("s1", 12, user_id="primary")]
    member = [m["content"] for m in css.get_history("s1", 12, user_id="u_mem")]
    assert owner == ["owner-question", "owner-answer"]
    assert member == ["member-question", "member-answer"]


def test_default_user_is_primary_for_legacy_callers():
    css.append_turns("s2", "q", "a", 12)                       # no user_id arg
    assert [m["content"] for m in css.get_history("s2", 12)] == ["q", "a"]
    assert css.get_history("s2", 12, user_id="u_other") == []


def test_migration_adds_column_to_existing_db(tmp_path, monkeypatch):
    # Simulate a pre-Atlas DB: create the OLD schema, then reopen via the store.
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE chat_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, ts TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL);
    """)
    conn.execute("INSERT INTO chat_turns (session_id, ts, role, content)"
                 " VALUES ('legacy', '2026-01-01T00:00:00+00:00', 'user', 'old-q')")
    conn.commit(); conn.close()
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH", str(db), raising=False)
    css._reset_for_tests()
    # Old rows are owned by 'primary'; new writes work with explicit users.
    assert [m["content"] for m in css.get_history("legacy", 12)] == ["old-q"]
    css.append_turns("legacy", "new-q", "new-a", 12, user_id="u_new")
    assert [m["content"] for m in css.get_history("legacy", 12, user_id="u_new")] \
        == ["new-q", "new-a"]


def test_has_session_scoped():
    css.append_turns("s3", "q", "a", 12, user_id="u_a")
    assert css.has_session("s3", user_id="u_a") is True
    assert css.has_session("s3", user_id="u_b") is False
