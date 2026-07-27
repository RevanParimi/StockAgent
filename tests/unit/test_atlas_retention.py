"""Atlas C9 — nightly retention/prune (spec §7).

All caps via cfg(); a None cap means keep-all. Each prune is independently
hot-path safe so one failure never aborts the nightly lane. Dormant unless
ATLAS_ENABLED.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import core.portfolio.retention as retention
import services.data.stores.atlas_store as atlas_store
from core.config import settings
from services.data.stores import user_store


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"),
                        raising=False)
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    yield tmp_path
    atlas_store._reset_for_tests()


def _iso_days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat(timespec="seconds")


def _seed_instrument_and_user(conn):
    conn.execute("INSERT OR IGNORE INTO instruments (sym, created_at, updated_at)"
                 " VALUES ('TCS','2020-01-01','2020-01-01')")
    conn.execute("INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
                 " consent_at) VALUES ('u_1','u_1@x.com','h','t','t')")
    conn.commit()


# --- ticker_verdicts --------------------------------------------------------

def test_prune_ticker_verdicts_respects_cap(env):
    conn = atlas_store._get_conn()
    _seed_instrument_and_user(conn)
    old = (date.today() - timedelta(days=500)).isoformat()
    conn.execute("INSERT INTO ticker_verdicts (symbol, as_of_date) VALUES ('TCS', ?)", (old,))
    conn.execute("INSERT INTO ticker_verdicts (symbol, as_of_date) VALUES ('TCS', ?)",
                 (date.today().isoformat(),))
    conn.commit()
    retention._prune_ticker_verdicts()          # default cap 400 days
    kept = [r[0] for r in conn.execute("SELECT as_of_date FROM ticker_verdicts").fetchall()]
    assert kept == [date.today().isoformat()]


def test_none_cap_keeps_all(env, monkeypatch):
    conn = atlas_store._get_conn()
    _seed_instrument_and_user(conn)
    old = (date.today() - timedelta(days=9999)).isoformat()
    conn.execute("INSERT INTO ticker_verdicts (symbol, as_of_date) VALUES ('TCS', ?)", (old,))
    conn.commit()
    monkeypatch.setattr(retention, "_verdicts_cap_days", lambda: None)
    retention._prune_ticker_verdicts()
    assert conn.execute("SELECT COUNT(*) FROM ticker_verdicts").fetchone()[0] == 1


# --- outbox -----------------------------------------------------------------

def test_prune_outbox_removes_only_old_terminal_rows(env):
    conn = atlas_store._get_conn()
    _seed_instrument_and_user(conn)
    rows = [("delivered", _iso_days_ago(60), "d1"),   # old + terminal -> pruned
            ("dead", _iso_days_ago(60), "d2"),        # old + terminal -> pruned
            ("queued", _iso_days_ago(60), "d3"),      # old but not terminal -> kept
            ("delivered", _iso_days_ago(1), "d4")]    # terminal but recent -> kept
    for status, created, dk in rows:
        conn.execute("INSERT INTO outbox (user_id, channel, kind, payload_ref,"
                     " dedupe_key, status, created_at) VALUES"
                     " ('u_1','push','brief','{}', ?, ?, ?)", (dk, status, created))
    conn.commit()
    retention._prune_outbox()                   # default 30 days
    kept = sorted(r[0] for r in conn.execute("SELECT dedupe_key FROM outbox").fetchall())
    assert kept == ["d3", "d4"]


# --- value_history ----------------------------------------------------------

def test_prune_value_history_caps_lines(env, monkeypatch):
    monkeypatch.setattr(retention, "_value_history_cap", lambda: 5)
    d = env / "portfolio" / "primary"
    d.mkdir(parents=True)
    vh = d / "value_history.jsonl"
    vh.write_text("".join(f'{{"n": {i}}}\n' for i in range(10)), encoding="utf-8")
    retention._prune_value_history()
    lines = vh.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    assert lines[0] == '{"n": 5}' and lines[-1] == '{"n": 9}'


# --- lane orchestration -----------------------------------------------------

def test_run_retention_dormant_when_disabled(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    conn = atlas_store._get_conn()
    _seed_instrument_and_user(conn)
    conn.execute("INSERT INTO ticker_verdicts (symbol, as_of_date) VALUES ('TCS','2000-01-01')")
    conn.commit()
    result = retention.run_retention()
    assert result == {"skipped": "atlas_disabled"}
    assert conn.execute("SELECT COUNT(*) FROM ticker_verdicts").fetchone()[0] == 1


def test_one_prune_failure_does_not_crash_lane(env, monkeypatch):
    monkeypatch.setattr(retention, "_prune_outbox",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    result = retention.run_retention()          # must not raise
    assert result["outbox"] == "error"
    assert "ticker_verdicts" in result          # other prunes still ran
