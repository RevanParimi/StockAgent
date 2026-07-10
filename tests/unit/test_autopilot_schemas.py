"""Compass Autopilot — schema unit tests (spec §3)."""
import pytest

from backend.shared.schemas.portfolio import (
    Holding, Portfolio, TransactionRecord, WatchlistItem,
)


def _holding(qty=10.0, price=100.0, dividends=0.0):
    return Holding(
        symbol="MARUTI", sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-07-11",
        dividends_received=dividends,
    )


def test_transaction_record_roundtrip():
    t = TransactionRecord(
        txn_id="abc123", date="2026-07-11", ts="2026-07-11T12:00:00+00:00",
        user_id="primary", symbol="MARUTI", side="BUY", qty=5, price=100.0,
        value=500.0, cash_before=1000.0, cash_after=500.0,
        holding_qty_after=5, source="seed",
    )
    assert TransactionRecord(**t.model_dump()) == t
    assert t.realized_pnl == 0.0 and t.verdict == "" and t.triggers == []


def test_portfolio_new_fields_default_off():
    p = Portfolio(user_id="u")
    assert p.capital_in == 0.0
    assert p.autopilot is False
    assert p.last_autopilot_run == ""
    assert p.cash_deployable is None          # legacy default untouched


def test_watchlist_source_accepts_autopilot():
    w = WatchlistItem(symbol="X", added="2026-07-11", source="autopilot")
    assert w.source == "autopilot"


def test_holding_sell_partial_realizes_pro_rata_dividends():
    h = _holding(qty=10, price=100.0, dividends=50.0)
    realized = h.sell(5, 120.0)
    # (120-100)*5 + 50*0.5 = 125
    assert realized == pytest.approx(125.0)
    assert h.adj_qty == pytest.approx(5.0)
    assert h.dividends_received == pytest.approx(25.0)
    assert h.qty == 10.0                      # raw stays "as entered"


def test_holding_sell_full_and_overdraw_rejected():
    h = _holding(qty=10, price=100.0)
    assert h.sell(10, 90.0) == pytest.approx(-100.0)
    assert h.adj_qty == pytest.approx(0.0)
    h2 = _holding(qty=2, price=100.0)
    with pytest.raises(ValueError):
        h2.sell(3, 100.0)
    with pytest.raises(ValueError):
        h2.sell(0, 100.0)
