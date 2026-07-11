"""Autopilot API routes (spec §6). Reuses the test_portfolio_api fixture style."""
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.portfolio.store import PortfolioStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Same pattern as tests/unit/test_portfolio_api.py: patch the module-level
    # `settings` object papi imports from core.config, so PortfolioStore()
    # (constructed with no base_dir inside the route handlers) resolves to
    # tmp_path too.
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    # keep promotion machinery away from the real data/managed_tickers.json
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "demote_symbol", lambda *a, **k: False)
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def _seed_store(tmp_path, cash=10000.0):
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = [Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-06-01")]
    p.cash_deployable, p.capital_in, p.autopilot = cash, 11000.0, True
    s.save(p)
    s.append_transaction(TransactionRecord(
        txn_id="t1", date="2026-07-13", ts=datetime.now(timezone.utc).isoformat(),
        user_id="primary", symbol="MARUTI", side="SELL", qty=2, price=110.0,
        value=220.0, cash_before=0.0, cash_after=220.0, holding_qty_after=8,
        realized_pnl=20.0, verdict="TRIM"))
    s.append_value_point({"date": "2026-07-12", "market_value": 900.0, "cash": cash,
                          "total_equity": 900.0 + cash, "capital_in": 11000.0,
                          "day_change_pct": None})
    s.append_value_point({"date": "2026-07-13", "market_value": 1000.0, "cash": cash,
                          "total_equity": 1000.0 + cash, "capital_in": 11000.0,
                          "day_change_pct": 0.91})
    return s


def test_transactions_newest_first(client, tmp_path):
    _seed_store(tmp_path)
    r = client.get("/portfolio/transactions?limit=10")
    assert r.status_code == 200
    assert r.json()["transactions"][0]["txn_id"] == "t1"


def test_performance_from_value_history(client, tmp_path):
    _seed_store(tmp_path, cash=10000.0)
    r = client.get("/portfolio/performance")
    assert r.status_code == 200
    d = r.json()
    assert d["cash"] == 10000.0
    assert d["market_value"] == 1000.0
    assert d["total_equity"] == 11000.0
    assert d["realized_pnl"] == 20.0
    assert d["unrealized_pnl"] == pytest.approx(-20.0)   # total 0 − realized 20
    assert d["day_change_pct"] == 0.91
    assert d["autopilot"] is True
    assert len(d["history"]) == 2


def test_performance_empty_portfolio_accounting_on(client, tmp_path):
    """Cash accounting ON + no holdings + no value history yet (transient
    state right after opt-in): market value is 0.0 — known, not unknown —
    so total_equity == cash and the P&L fields compute (no nulls)."""
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.cash_deployable, p.capital_in, p.autopilot = 10000.0, 10000.0, True
    s.save(p)
    r = client.get("/portfolio/performance")
    assert r.status_code == 200
    d = r.json()
    assert d["market_value"] == 0.0
    assert d["total_equity"] == 10000.0          # == cash
    assert d["autopilot"] is True
    assert d["total_return_pct"] is not None     # capital_in > 0 — computes
    assert d["total_return_pct"] == pytest.approx(0.0)
    assert d["unrealized_pnl"] is not None


def test_manual_add_records_txn_and_capital(client, tmp_path):
    _seed_store(tmp_path)
    r = client.post("/portfolio/holdings", json={
        "symbol": "MARUTI", "sector": "automobile", "qty": 5,
        "buy_date": "2026-07-13", "price": 120.0})
    assert r.status_code == 200
    assert r.json()["transaction"]["source"] == "manual"
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    assert p.capital_in == pytest.approx(11000.0 + 600.0)
    assert p.cash_deployable == pytest.approx(10000.0)   # unchanged — fresh money


def test_manual_delete_sells_and_credits_cash(client, tmp_path, monkeypatch):
    _seed_store(tmp_path)
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 130.0)
    r = client.delete("/portfolio/holdings/MARUTI")
    assert r.status_code == 200
    t = r.json()["transaction"]
    assert t["side"] == "SELL" and t["qty"] == 10 and t["price"] == 130.0
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    assert p.holdings == []
    assert p.cash_deployable == pytest.approx(10000.0 + 1300.0)
