"""Tests for the permanent SQLite log/telemetry archive (log_store) and the
uvicorn multi-worker singleton lock — 2026-07-02 fixes.

Context: Railway console logs rotate per-deploy (3-week investigation could
only see one day), and `--workers 2` ran every scheduled job twice. The log
store archives history on the volume; the lock makes background work
single-owner.
"""
import logging
import socket
import sqlite3

import pytest

import services.data.stores.log_store as log_store


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Point the store at a throwaway DB and reset its cached connection."""
    db_path = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    yield db_path
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


def _rows(db_path, sql):
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(sql).fetchall()


def test_llm_call_persisted(fresh_db):
    log_store.log_llm_call("FeedbackAgent", "deepseek/deepseek-v4-flash",
                           1200, 300, 4500, True)
    log_store.log_llm_call("UnifiedAnalyst", "qwen/qwen3.7-max",
                           8000, 1500, 30000, False)
    rows = _rows(fresh_db, "SELECT caller, model, success FROM llm_calls ORDER BY id")
    assert rows == [
        ("FeedbackAgent", "deepseek/deepseek-v4-flash", 1),
        ("UnifiedAnalyst", "qwen/qwen3.7-max", 0),
    ]


def test_handler_mirrors_warnings_but_not_info(fresh_db):
    handler = log_store.SQLiteLogHandler(level=logging.WARNING)
    lg = logging.getLogger("test.macro_fetcher")
    lg.addHandler(handler)
    # Isolate from the root logger: tests that import services.api.server leave
    # a session-wide SQLiteLogHandler attached there, which would double-write
    # this record into the (redirected) fresh_db.
    lg.propagate = False
    try:
        lg.warning("ReviewAgent LLM failed: Expecting value")
        lg.info("routine info line")  # below handler level → not archived
    finally:
        lg.removeHandler(handler)
        lg.propagate = True
    rows = _rows(fresh_db, "SELECT level, logger, message FROM app_logs")
    assert rows == [("WARNING", "test.macro_fetcher",
                     "ReviewAgent LLM failed: Expecting value")]


def test_own_records_never_recurse(fresh_db):
    log_store._get_conn()  # force schema creation so the count query is valid
    handler = log_store.SQLiteLogHandler(level=logging.WARNING)
    lg = logging.getLogger(log_store.__name__)
    lg.addHandler(handler)
    try:
        lg.warning("db write failed")  # must be dropped, not archived
    finally:
        lg.removeHandler(handler)
    assert _rows(fresh_db, "SELECT COUNT(*) FROM app_logs") == [(0,)]


def test_never_raises_on_broken_path(monkeypatch):
    # A hopeless DB path must degrade silently, never break the pipeline.
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH",
                        "Z:/definitely/not/a/real/drive/t.db", raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    log_store.log_llm_call("X", "m", 1, 1, 1, True)   # no exception = pass
    log_store.log_app_record("ERROR", "x", "boom")     # no exception = pass


def test_singleton_lock_second_caller_loses(monkeypatch):
    from services.api.server import _acquire_singleton_lock
    import services.api.server as server

    # Pick a genuinely free port for this test run
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("SINGLETON_LOCK_PORT", str(port))
    monkeypatch.setattr(server, "_singleton_lock_socket", None)

    try:
        assert _acquire_singleton_lock() is True    # first worker wins
        assert _acquire_singleton_lock() is False   # second worker yields
    finally:
        if server._singleton_lock_socket is not None:
            server._singleton_lock_socket.close()
            server._singleton_lock_socket = None
