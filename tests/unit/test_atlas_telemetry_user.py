"""Atlas C8 — Blueprint 4 telemetry user attribution.

`llm_calls` gains a nullable `user_id`: NULL = the shared brain (scheduled
analysis, self-heal); a value = a user-attributable call (chat / on-demand
/analyse / narrator pre-cache). The value flows via a `current_user_id`
ContextVar (set by the auth dependency when ATLAS_ENABLED) so it need not be
threaded through ~20 call sites. A nightly `cost_by_user_day` rollup buckets
the cost, keeping NULL as the shared-brain bucket.
"""
import sqlite3

import pytest

import services.data.stores.log_store as log_store
import services.data.stores.atlas_store as atlas_store
import services.api.auth as auth


@pytest.fixture(autouse=True)
def _reset_context():
    log_store.current_user_id.set(None)
    yield
    log_store.current_user_id.set(None)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH",
                        str(tmp_path / "telemetry.db"), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    yield tmp_path / "telemetry.db"
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


def _rows(path, sql):
    with sqlite3.connect(str(path)) as c:
        return c.execute(sql).fetchall()


# --- user_id column + ContextVar attribution --------------------------------

def test_llm_call_attributes_context_user(db):
    log_store.current_user_id.set("u_1")
    log_store.log_llm_call("chat", "m", 10, 5, 100, True)
    log_store.current_user_id.set(None)
    log_store.log_llm_call("scheduled_review", "m", 10, 5, 100, True)   # shared brain
    rows = _rows(db, "SELECT caller, user_id FROM llm_calls ORDER BY id")
    assert rows == [("chat", "u_1"), ("scheduled_review", None)]


def test_explicit_user_id_arg_overrides_context(db):
    log_store.current_user_id.set("u_ctx")
    log_store.log_llm_call("narrator", "m", 1, 1, 1, True, user_id="u_arg")
    assert _rows(db, "SELECT user_id FROM llm_calls") == [("u_arg",)]


def test_migration_adds_user_id_to_existing_db(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts TEXT NOT NULL, caller TEXT NOT NULL, model TEXT NOT NULL,"
        " input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,"
        " latency_ms INTEGER DEFAULT 0, success INTEGER DEFAULT 1);")
    conn.execute("INSERT INTO llm_calls (ts, caller, model) VALUES "
                 "('2026-01-01T00:00:00+00:00','legacy','m')")
    conn.commit(); conn.close()
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    log_store.log_llm_call("new", "m", 1, 1, 1, True, user_id="u_new")
    rows = _rows(db, "SELECT caller, user_id FROM llm_calls ORDER BY id")
    assert rows == [("legacy", None), ("new", "u_new")]
    log_store._conn.close(); log_store._conn = None


# --- cost_by_user_day rollup ------------------------------------------------

def test_rollup_buckets_by_user_and_keeps_null_shared(db):
    for uid in ("u_1", "u_1", None, "u_2"):
        log_store.current_user_id.set(uid)
        log_store.log_llm_call("c", "m", 100, 50, 10, True)
    day = _rows(db, "SELECT substr(ts,1,10) FROM llm_calls LIMIT 1")[0][0]
    result = log_store.rollup_cost_by_user_day(day)
    assert result["buckets"] == 3
    got = dict((u, calls) for u, calls in _rows(
        db, "SELECT user_id, calls FROM cost_by_user_day"))
    assert got == {"u_1": 2, "u_2": 1, None: 1}     # None = shared brain
    # idempotent: a second rollup for the same day does not double-count
    log_store.rollup_cost_by_user_day(day)
    got2 = dict((u, calls) for u, calls in _rows(
        db, "SELECT user_id, calls FROM cost_by_user_day"))
    assert got2 == got


# --- auth binds the request user (flag-gated) -------------------------------

def test_auth_attributes_only_when_enabled(monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    auth._attribute_telemetry("u_off")
    assert log_store.current_user_id.get() is None      # dormant: not attributed
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    auth._attribute_telemetry("u_on")
    assert log_store.current_user_id.get() == "u_on"
