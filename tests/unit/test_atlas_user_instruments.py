"""Atlas C3 — user_instruments write-through + active_user_ids() (flag-gated).

The reverse index BP1 needs (finding #3): every held/watched relationship is
projected into atlas.db user_instruments on the portfolio write path, and
scheduler fan-out switches from a directory scan (list_user_ids) to a
users-table query (active_user_ids) so ghost dirs no longer trade (finding #6).

Everything is gated on cfg("atlas.enabled", env="ATLAS_ENABLED"): flag OFF is a
byte-for-byte no-op (today's dir-scan path), flag ON is the atlas path.
"""
from __future__ import annotations

import pytest

import core.portfolio.store as pstore
import services.data.stores.atlas_store as atlas_store
from core.config import settings
from backend.shared.schemas.portfolio import Holding, WatchlistItem


def _holding(sym="TCS", qty=10.0):
    return Holding(symbol=sym, sector="it", qty=qty, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=qty, buy_date="2026-01-01")


def _watch(sym="INFY"):
    return WatchlistItem(symbol=sym, sector="it", added="2026-01-01")


def _mk_user(uid):
    conn = atlas_store._get_conn()
    conn.execute("INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
                 " consent_at) VALUES (?,?,?,?,?)",
                 (uid, f"{uid}@x.com", "h", "t", "t"))
    conn.commit()


def _rows(uid, relationship):
    return [r[0] for r in atlas_store._get_conn().execute(
        "SELECT symbol FROM user_instruments WHERE user_id=? AND relationship=?",
        (uid, relationship)).fetchall()]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"),
                        raising=False)
    yield tmp_path
    atlas_store._reset_for_tests()


# ---- flag ON: write-through ------------------------------------------------

def test_add_holding_projects_held_and_ensures_instrument(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _mk_user("primary")
    store = pstore.PortfolioStore(user_id="primary")
    store.add_holding(_holding("tcs"))
    assert _rows("primary", "held") == ["TCS"]
    inst = atlas_store._get_conn().execute(
        "SELECT origin, cadence FROM instruments WHERE sym='TCS'").fetchone()
    assert tuple(inst) == ("held", "daily")


def test_remove_holding_deletes_held_row(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _mk_user("primary")
    store = pstore.PortfolioStore(user_id="primary")
    store.add_holding(_holding("tcs"))
    store.remove_holding("TCS")
    assert _rows("primary", "held") == []


def test_reduce_holding_full_exit_removes_held_row(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _mk_user("primary")
    store = pstore.PortfolioStore(user_id="primary")
    store.add_holding(_holding("tcs", qty=10.0))
    store.reduce_holding("TCS", 4.0, 110.0)         # partial — still held
    assert _rows("primary", "held") == ["TCS"]
    store.reduce_holding("TCS", 6.0, 120.0)         # full exit — no longer held
    assert _rows("primary", "held") == []


def test_watchlist_add_remove_mirror(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    _mk_user("primary")
    store = pstore.PortfolioStore(user_id="primary")
    store.add_watchlist(_watch("infy"))
    assert _rows("primary", "watch") == ["INFY"]
    inst = atlas_store._get_conn().execute(
        "SELECT origin, cadence FROM instruments WHERE sym='INFY'").fetchone()
    assert tuple(inst) == ("watched", "weekly")
    store.remove_watchlist("INFY")
    assert _rows("primary", "watch") == []


def test_write_through_hotpath_safe_without_users_row(env, monkeypatch):
    # No users row for this uid → FK would reject the user_instruments insert.
    # The portfolio write must still succeed (log + continue), never raise.
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    store = pstore.PortfolioStore(user_id="u_missing")
    p = store.add_holding(_holding("tcs"))          # must not raise
    assert p.holdings[0].symbol == "TCS"            # portfolio write succeeded
    assert _rows("u_missing", "held") == []         # index just wasn't recorded


# ---- flag ON: active_user_ids ----------------------------------------------

def test_active_user_ids_returns_atlas_users_excluding_ghosts(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    _mk_user("u_real")
    ghost = env / "portfolio" / "u_ghost"           # dir with no users row
    ghost.mkdir(parents=True)
    (ghost / "portfolio.json").write_text('{"user_id":"u_ghost"}', encoding="utf-8")
    assert pstore.active_user_ids() == ["u_real"]   # ghost excluded


def test_active_user_ids_owner_fallback_when_empty_and_auth_off(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    assert pstore.active_user_ids() == [settings.PORTFOLIO_DEFAULT_USER_ID]


# ---- flag OFF: pure no-op (dormant path) -----------------------------------

def test_disabled_is_a_noop_and_active_equals_list(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    store = pstore.PortfolioStore(user_id="primary")
    store.add_holding(_holding("tcs"))
    store.add_watchlist(_watch("infy"))
    assert atlas_store._get_conn().execute(
        "SELECT COUNT(*) FROM user_instruments").fetchone()[0] == 0
    assert pstore.active_user_ids() == pstore.list_user_ids()
    assert pstore.active_user_ids() == ["primary"]
