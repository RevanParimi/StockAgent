"""tests/unit/test_pricing_retry.py — AUD-091 one retry on close_on."""
from datetime import date

import pytest

import core.portfolio.pricing as pricing


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(pricing.time, "sleep", lambda s: None)
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)


def test_close_on_retries_once_on_transient_none(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return None if len(calls) == 1 else 123.45
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert pricing.close_on("MARUTI", date(2026, 7, 16)) == 123.45
    assert len(calls) == 2


def test_close_on_raises_after_retry_exhausted(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return None
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    with pytest.raises(pricing.PriceUnavailableError):
        pricing.close_on("MARUTI", date(2026, 7, 16))
    assert len(calls) == 2   # exactly one retry, then raise


def test_close_on_no_retry_on_first_success(monkeypatch):
    calls = []
    def fake_fetch(sym, d):
        calls.append(sym)
        return 100.0
    monkeypatch.setattr(pricing, "_fetch_actual_close", fake_fetch)
    assert pricing.close_on("MARUTI", date(2026, 7, 16)) == 100.0
    assert len(calls) == 1
