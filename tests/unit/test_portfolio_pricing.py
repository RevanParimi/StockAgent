"""Compass Phase A — entry pricing: real NSE close on trading days only."""
from datetime import date

import pytest

import core.portfolio.pricing as pricing
from core.portfolio.pricing import PriceUnavailableError, close_on


def test_close_on_trading_day(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_actual_close", lambda sym, d: 12345.0)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    assert close_on("MARUTI", date(2026, 7, 3)) == 12345.0


def test_close_on_holiday_walks_back(monkeypatch):
    calls = []

    def fake_fetch(sym, d):
        calls.append(d)
        return 100.0

    # Sunday 2026-07-05 -> walks back to Friday 2026-07-03
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert close_on("MARUTI", date(2026, 7, 5)) == 100.0
    assert calls[0] == date(2026, 7, 3)


def test_close_on_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(pricing, "_fetch_actual_close", lambda sym, d: None)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    with pytest.raises(PriceUnavailableError):
        close_on("NOSUCH", date(2026, 7, 3))
