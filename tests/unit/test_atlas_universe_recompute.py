"""Atlas C4 — nightly Universe recompute (design spec §4).

User/data-plane job: reads atlas.db user_instruments (user_id-bearing) and
writes only AGGREGATE counts + cadence + status back to instruments. The
intelligence plane reads `instruments WHERE enabled=1` and never sees a user_id
(R1; counts are a universe-ranking feature, permitted by R2). Dormant behind
ATLAS_ENABLED.
"""
from __future__ import annotations

import pytest

import core.portfolio.universe as universe
import services.data.stores.atlas_store as atlas_store
from core.config import settings


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path / "predictions"),
                        raising=False)
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    yield tmp_path
    atlas_store._reset_for_tests()


def _user(uid):
    atlas_store._get_conn().execute(
        "INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at, consent_at)"
        " VALUES (?,?,?,?,?)", (uid, f"{uid}@x.com", "h", "t", "t"))


def _instrument(sym, *, origin="seed", cadence="on_demand", enabled=0,
                status="active", updated_at="2026-01-01T00:00:00+00:00"):
    atlas_store._get_conn().execute(
        "INSERT OR IGNORE INTO instruments (sym, origin, cadence, enabled, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (sym, origin, cadence, enabled, status, "2026-01-01", updated_at))


def _membership(uid, sym, relationship):
    atlas_store._get_conn().execute(
        "INSERT OR IGNORE INTO user_instruments (user_id, symbol, relationship, added_at)"
        " VALUES (?,?,?,?)", (uid, sym, relationship, "2026-01-01"))


def _row(sym):
    return atlas_store._get_conn().execute(
        "SELECT holders, watchers, chat_hits_7d, demand_score, cadence, enabled, status"
        " FROM instruments WHERE sym=?", (sym,)).fetchone()


def _commit():
    atlas_store._get_conn().commit()


def test_counts_and_tiers(env):
    _user("u1"); _user("u2")
    _instrument("TCS"); _instrument("INFY"); _instrument("WIPRO")
    _membership("u1", "TCS", "held"); _membership("u2", "TCS", "held")   # 2 holders
    _membership("u1", "INFY", "watch")                                    # 1 watcher
    # WIPRO: no membership → refcount 0
    _commit()

    universe.recompute_universe()

    tcs = _row("TCS")
    assert (tcs["holders"], tcs["watchers"]) == (2, 0)
    assert tcs["cadence"] == "daily" and tcs["enabled"] == 1          # held → daily
    assert tcs["demand_score"] == pytest.approx(6.0)                  # 3*2 holders
    infy = _row("INFY")
    assert (infy["holders"], infy["watchers"]) == (0, 1)
    assert infy["cadence"] == "weekly" and infy["enabled"] == 1       # watch-only → weekly
    wipro = _row("WIPRO")
    assert wipro["cadence"] == "on_demand" and wipro["enabled"] == 0  # refcount 0 → demoted


def test_demote_not_delete_and_history_preserved(env):
    _instrument("TCS", origin="held", cadence="daily", enabled=1)
    _commit()
    universe.recompute_universe()                                     # no members → refcount 0
    row = _row("TCS")
    assert row["cadence"] == "on_demand" and row["enabled"] == 0
    assert row["status"] == "active"                                  # demoted, NOT archived
    # the instruments row itself still exists (never hard-deleted)
    assert _row("TCS") is not None


def test_never_archive_when_intelligence_history_exists(env, tmp_path):
    # refcount 0, archivable origin, LONG past updated_at — but history exists.
    _instrument("TCS", origin="discovery", status="active",
                updated_at="2020-01-01T00:00:00+00:00")
    hist = tmp_path / "predictions" / "automobile" / "TCS"
    hist.mkdir(parents=True)
    _commit()
    universe.recompute_universe()
    assert _row("TCS")["status"] == "active"                          # protected by history


def test_archive_when_no_history_and_grace_elapsed(env):
    _instrument("OLDCO", origin="discovery", status="active",
                updated_at="2020-01-01T00:00:00+00:00")               # far past grace
    _commit()
    universe.recompute_universe()
    assert _row("OLDCO")["status"] == "archived"


def test_budget_alert_fires_at_threshold(env, monkeypatch):
    monkeypatch.setenv("UNIVERSE_MAX_DAILY_ANALYSES", "2")            # tiny budget
    calls = []
    monkeypatch.setattr(universe, "_emit_ops_alert", lambda msg: calls.append(msg))
    _user("u1")
    _instrument("TCS"); _instrument("INFY")
    _membership("u1", "TCS", "held"); _membership("u1", "INFY", "held")  # 2 daily
    _commit()
    universe.recompute_universe()
    assert calls, "budget governor should alert at >=80% of a 2-slot daily budget"


def test_instruments_table_carries_no_user_identity(env):
    # R1 structural guarantee — the aggregate output table has no user column.
    cols = [r[1] for r in atlas_store._get_conn().execute(
        "PRAGMA table_info(instruments)").fetchall()]
    assert "user_id" not in cols


def test_disabled_is_noop(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    _instrument("TCS", cadence="daily", enabled=1)
    _commit()
    assert universe.recompute_universe() == {"status": "disabled"}
    assert _row("TCS")["cadence"] == "daily"                          # untouched
