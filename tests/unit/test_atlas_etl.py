"""Atlas C10 — one-shot ETL from the legacy JSON/JSONL/users.db sources into
`atlas.db`, plus ghost-dir reconciliation (design spec §6).

The ETL is idempotent + additive (deletes nothing): running it twice yields the
same row counts and no duplicates, and every source file survives untouched
(the flag-flip rollback keeps working). Ghost portfolio dirs with no `users`
row are quarantined, never silently traded; the owner's `primary` dir is always
adopted. It writes atlas.db DIRECTLY (not through the flag-gated portfolio
write-through), so it works while ATLAS_ENABLED is still false at cutover.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import core.portfolio.store as pstore
import services.data.stores.atlas_store as atlas_store
from core.config import settings

from scripts import atlas_etl


# --- users.db (source) exact legacy schema ---------------------------------
_USERS_DDL = """
CREATE TABLE users (user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
  pw_hash TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'member', created_at TEXT NOT NULL,
  consent_at TEXT NOT NULL);
CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
  created_at REAL NOT NULL, expires_at REAL NOT NULL, last_seen REAL NOT NULL);
CREATE TABLE invites (code TEXT PRIMARY KEY, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, used_by TEXT, used_at TEXT);
CREATE TABLE chat_usage (user_id TEXT NOT NULL, day TEXT NOT NULL,
  llm_turns INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, day));
"""


def _make_users_db(path, user_ids):
    conn = sqlite3.connect(str(path))
    conn.executescript(_USERS_DDL)
    for uid in user_ids:
        conn.execute("INSERT INTO users (user_id, email, pw_hash, created_at,"
                     " consent_at) VALUES (?,?,?,?,?)",
                     (uid, f"{uid}@x.com", "scrypt$x$y$z", "2026-01-01T00:00:00+00:00",
                      "2026-01-01T00:00:00+00:00"))
    if user_ids:
        owner = user_ids[0]
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                     ("tok1", owner, 1.0, 9_999_999_999.0, 1.0))
        conn.execute("INSERT INTO invites VALUES (?,?,?,?,?)",
                     ("inv1", owner, "2026-01-01T00:00:00+00:00", None, None))
        conn.execute("INSERT INTO chat_usage VALUES (?,?,?)", (owner, "2026-07-27", 3))
    conn.commit()
    conn.close()
    return path


def _managed(path):
    path.write_text(json.dumps([
        {"sym": "MARUTI", "name": "Maruti", "sector": "automobile", "enabled": False},
        {"sym": "TCS", "name": "TCS", "sector": "it_sector", "enabled": False,
         "origin": "held", "cadence": "daily", "promoted_at": "2026-07-10"},
        {"sym": "HDFCBANK", "name": "HDFC", "sector": "banking_bfsi", "enabled": False},
    ]), encoding="utf-8")


def _portfolio(root, uid, holdings=(), watchlist=(), advice=()):
    d = root / uid
    d.mkdir(parents=True, exist_ok=True)
    (d / "portfolio.json").write_text(json.dumps({
        "user_id": uid,
        "holdings": [{"symbol": s, "sector": "x", "qty": 10.0, "avg_buy_price": 100.0,
                      "adj_avg_price": 100.0, "adj_qty": 10.0, "buy_date": "2026-07-03"}
                     for s in holdings],
        "watchlist": [{"symbol": s, "sector": "x", "added": "2026-07-03"} for s in watchlist],
    }), encoding="utf-8")
    if advice:
        with open(d / "advice_ledger.jsonl", "w", encoding="utf-8") as fh:
            for sym in advice:
                fh.write(json.dumps({
                    "date": "2026-07-03", "user_id": uid, "symbol": sym, "verdict": "HOLD",
                    "close": 100.0, "unrealised_pnl_pct": 0.0, "stop_pct": 12.0,
                    "triggers": [], "confidence": 0.6, "rationale_hash": "abc",
                    "outcome_10td": None, "outcome_30td": None, "outcome_60td": None,
                }) + "\n")
    return d


def _sub(endpoint):
    return {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """A synthetic data/ tree + an isolated atlas.db. Returns the kwargs dict
    the ETL is called with, so tests can tweak individual sources."""
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"),
                        raising=False)

    pf = tmp_path / "portfolio"
    users_db = _make_users_db(tmp_path / "users.db", ["primary", "u_a"])
    _managed(tmp_path / "managed_tickers.json")
    _portfolio(pf, "primary", holdings=["MARUTI"], advice=["MARUTI"])
    _portfolio(pf, "u_a", holdings=["TCS"], watchlist=["INFY"], advice=["TCS"])
    (tmp_path / "push.json").write_text(json.dumps({
        "primary": [_sub("https://push/x1")], "u_a": [_sub("https://push/x2")]}),
        encoding="utf-8")
    (tmp_path / "watchlist.json").write_text(json.dumps(["MARUTI"]), encoding="utf-8")

    tel = tmp_path / "telemetry.db"
    tc = sqlite3.connect(str(tel))
    tc.execute("CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, ts TEXT, cost_usd REAL)")
    tc.commit(); tc.close()

    kwargs = dict(users_db=users_db, push_json=tmp_path / "push.json",
                  managed_tickers=tmp_path / "managed_tickers.json", portfolio_dir=pf,
                  watchlist_json=tmp_path / "watchlist.json", telemetry_db=tel,
                  default_user_id="primary")
    yield tmp_path, kwargs
    atlas_store._reset_for_tests()


def _count(table):
    return atlas_store._get_conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- row counts -------------------------------------------------------------

def test_full_etl_populates_every_table(tree):
    _, kwargs = tree
    summary = atlas_etl.run_etl(**kwargs)
    assert _count("users") == 2
    assert _count("sessions") == 1
    assert _count("invites") == 1
    assert _count("chat_usage") == 1
    # MARUTI, TCS, HDFCBANK (managed) + INFY (from u_a's watch) = 4
    assert _count("instruments") == 4
    # primary held MARUTI, u_a held TCS, u_a watch INFY, primary watch MARUTI (global list)
    assert _count("user_instruments") == 4
    assert _count("user_advice") == 2
    assert _count("push_subscriptions") == 2
    assert summary["quarantined"] == []


def test_advice_ledger_maps_with_verdict_ref(tree):
    _, kwargs = tree
    atlas_etl.run_etl(**kwargs)
    row = atlas_store._get_conn().execute(
        "SELECT verdict, verdict_ref, close FROM user_advice"
        " WHERE user_id='primary' AND symbol='MARUTI'").fetchone()
    assert row["verdict"] == "HOLD"
    assert row["verdict_ref"] == "MARUTI|2026-07-03"
    assert row["close"] == 100.0


# --- idempotency ------------------------------------------------------------

def test_second_run_is_a_noop_no_duplicates(tree):
    _, kwargs = tree
    atlas_etl.run_etl(**kwargs)
    before = {t: _count(t) for t in ("users", "instruments", "user_instruments",
                                     "user_advice", "push_subscriptions")}
    atlas_etl.run_etl(**kwargs)
    after = {t: _count(t) for t in before}
    assert after == before


# --- ghost-dir reconciliation ----------------------------------------------

def test_ghost_dir_without_users_row_is_quarantined(tree):
    tmp_path, kwargs = tree
    _portfolio(kwargs["portfolio_dir"], "u_ghost", holdings=["SBIN"])
    summary = atlas_etl.run_etl(**kwargs)
    assert "u_ghost" in summary["quarantined"]
    assert (kwargs["portfolio_dir"] / "_quarantine" / "u_ghost").is_dir()
    assert not (kwargs["portfolio_dir"] / "u_ghost").exists()
    # the stranger's symbol never entered the universe or the join
    assert atlas_store._get_conn().execute(
        "SELECT COUNT(*) FROM user_instruments WHERE user_id='u_ghost'").fetchone()[0] == 0
    assert atlas_store._get_conn().execute(
        "SELECT COUNT(*) FROM instruments WHERE sym='SBIN'").fetchone()[0] == 0


def test_primary_dir_is_adopted_to_owner(tree):
    _, kwargs = tree
    summary = atlas_etl.run_etl(**kwargs)
    assert "primary" in summary["adopted"]
    assert (kwargs["portfolio_dir"] / "primary").is_dir()          # never quarantined
    assert not (kwargs["portfolio_dir"] / "_quarantine" / "primary").exists()
    assert atlas_store._get_conn().execute(
        "SELECT COUNT(*) FROM user_instruments WHERE user_id='primary'"
        " AND symbol='MARUTI' AND relationship='held'").fetchone()[0] == 1


def test_primary_never_quarantined_even_without_users_row(tree):
    """Degenerate anonymous-owner case: no registered users at all. The owner's
    dir must still be adopted (fan-out survives via the AUTH_REQUIRED fallback),
    never quarantined — losing it would erase the owner's portfolio at cutover."""
    tmp_path, kwargs = tree
    kwargs["users_db"] = _make_users_db(tmp_path / "empty_users.db", [])
    summary = atlas_etl.run_etl(**kwargs)
    assert "primary" in summary["adopted"]
    assert (kwargs["portfolio_dir"] / "primary").is_dir()
    assert not (kwargs["portfolio_dir"] / "_quarantine" / "primary").exists()


# --- the fan-out switch this migration feeds --------------------------------

def test_active_user_ids_dry_run_equals_registered_set(tree, monkeypatch):
    tmp_path, kwargs = tree
    _portfolio(kwargs["portfolio_dir"], "u_ghost", holdings=["SBIN"])
    atlas_etl.run_etl(**kwargs)
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    assert set(pstore.active_user_ids()) == {"primary", "u_a"}      # ghost excluded


# --- global watchlist kill sequence -----------------------------------------

def test_global_watchlist_merges_into_owner(tree):
    _, kwargs = tree
    atlas_etl.run_etl(**kwargs)
    # projected into the join for the owner...
    assert atlas_store._get_conn().execute(
        "SELECT COUNT(*) FROM user_instruments WHERE user_id='primary'"
        " AND symbol='MARUTI' AND relationship='watch'").fetchone()[0] == 1
    # ...and merged into the owner's portfolio.json (the post-cutover SoT)
    pf = json.loads((kwargs["portfolio_dir"] / "primary" / "portfolio.json")
                    .read_text(encoding="utf-8"))
    assert "MARUTI" in [w["symbol"] for w in pf["watchlist"]]


# --- telemetry additive migration -------------------------------------------

def test_telemetry_user_id_column_added_idempotently(tree):
    _, kwargs = tree
    atlas_etl.run_etl(**kwargs)
    cols = [r[1] for r in sqlite3.connect(str(kwargs["telemetry_db"]))
            .execute("PRAGMA table_info(llm_calls)").fetchall()]
    assert "user_id" in cols
    atlas_etl.run_etl(**kwargs)          # second run must not raise
