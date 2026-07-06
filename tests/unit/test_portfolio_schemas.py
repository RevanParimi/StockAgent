"""Compass Phase A — portfolio schema validation and P&L math."""
from datetime import date

import pytest
from pydantic import ValidationError

from backend.shared.schemas.portfolio import (
    AdviceRecord,
    AppliedCorpAction,
    CorporateEvent,
    Holding,
    Portfolio,
    WatchlistItem,
)


def _holding(**kw) -> Holding:
    base = dict(
        symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=12000.0,
        adj_avg_price=12000.0, adj_qty=10, buy_date="2026-01-05",
    )
    base.update(kw)
    return Holding(**base)


def test_holding_defaults_virtual_true():
    h = _holding()
    assert h.virtual is True
    assert h.dividends_received == 0.0
    assert h.applied_actions == []


def test_unrealised_pnl_uses_adjusted_price_and_dividends():
    # 1:1 bonus applied: adj price halved, qty doubled; +₹50 dividends received
    h = _holding(adj_avg_price=6000.0, adj_qty=20, dividends_received=50.0)
    # close 6600: price gain (6600-6000)*20 = 12000; +50 dividends; cost 120000
    assert h.unrealised_pnl_pct(6600.0) == pytest.approx((12000 + 50) / 120000 * 100)


def test_holding_age_days():
    h = _holding(buy_date="2026-01-05")
    assert h.age_days(date(2026, 7, 6)) == 182


def test_portfolio_risk_profile_validated():
    with pytest.raises(ValidationError):
        Portfolio(user_id="primary", risk_profile="yolo")


def test_advice_record_verdict_validated():
    with pytest.raises(ValidationError):
        AdviceRecord(
            date="2026-07-06", user_id="primary", symbol="MARUTI",
            verdict="MOON", close=100.0, unrealised_pnl_pct=0.0, stop_pct=10.0,
        )


def test_watchlist_source_default_user():
    w = WatchlistItem(symbol="TCS", added="2026-07-06")
    assert w.source == "user"


def test_corporate_event_fields():
    e = CorporateEvent(symbol="INFY", date="2026-07-15", kind="results", desc="Board meeting - financial results")
    assert e.kind == "results"
