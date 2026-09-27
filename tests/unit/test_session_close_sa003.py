"""SA-003 — minimum price freshness: which session a close belongs to.

The review's and the portfolio's close fetchers fall back to the newest
earlier bar when the requested session has none. That fallback is kept (the
selection is unchanged); what is new is that the result names the bar it came
from, so a carried-forward close can be told apart from the session's own.

Expected dates are the fixture's own bar dates, written by hand.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

import core.intelligence.rl.workflows.daily_review as dr
import core.portfolio.pricing as pricing
from services.data.fetchers import close_verifier

FRI = date(2026, 9, 25)
THU = FRI - timedelta(days=1)
WED = FRI - timedelta(days=2)
SAT, SUN = FRI + timedelta(days=1), FRI + timedelta(days=2)
# Frames hold at least two bars, as a 7-day download window does. (With one
# row, `df["Close"].squeeze()` is a scalar and the unchanged selection code
# finds no close at all — pre-existing, and conservative.)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    close_verifier._NSE_CLOSE_CACHE.clear()
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_ENABLED", True, raising=False)
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_TOLERANCE_PCT", 1.0, raising=False)
    yield
    close_verifier._NSE_CLOSE_CACHE.clear()


def _frame(bars: dict[date, float]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in bars])
    return pd.DataFrame({"Close": list(bars.values())}, index=idx)


def _fetch(yf_frame, nse: tuple[float | None, date | None]):
    with patch("yfinance.download", return_value=yf_frame), \
         patch.object(dr, "get_price_history", return_value=pd.DataFrame()), \
         patch.object(close_verifier, "_fetch_nse_session", return_value=nse):
        return dr._fetch_session_close("TICK", FRI)


# ---------------------------------------------------------------------------
# daily_review._fetch_session_close
# ---------------------------------------------------------------------------

def test_the_sessions_own_bar():
    q = _fetch(_frame({THU: 99.0, FRI: 100.0}), (100.2, FRI))
    assert q == dr.SessionClose(100.0, FRI, "agree")
    assert q.fresh_for(FRI)


def test_a_missing_session_carries_the_previous_bar_forward_visibly():
    """Suspended symbol: both sources' newest bar is Thursday. The close is
    Thursday's, as before — and now it says so."""
    q = _fetch(_frame({WED: 98.0, THU: 99.0}), (99.0, THU))
    assert q == dr.SessionClose(99.0, THU, "agree")
    assert not q.fresh_for(FRI)


def test_nse_disagreeing_supplies_its_own_rows_date():
    q = _fetch(_frame({THU: 130.0, FRI: 131.0}), (13000.0, FRI))   # symbol-cache poisoning
    assert q == dr.SessionClose(13000.0, FRI, "nse")


def test_nse_alone_with_a_stale_row():
    q = _fetch(pd.DataFrame(), (13000.0, THU))
    assert q == dr.SessionClose(13000.0, THU, "nse")
    assert not q.fresh_for(FRI)


def test_yfinance_alone_keeps_its_bar_date():
    q = _fetch(_frame({THU: 99.0, FRI: 100.0}), (None, None))
    assert q == dr.SessionClose(100.0, FRI, "yfinance")


def test_no_close_at_all():
    q = _fetch(pd.DataFrame(), (None, None))
    assert q == dr.SessionClose(None, None, "none")
    assert not q.fresh_for(FRI)


def test_the_bare_number_is_unchanged():
    """_fetch_actual_close (close_on, the audit) returns the same number."""
    with patch.object(dr, "_fetch_session_close",
                      return_value=dr.SessionClose(99.0, THU, "agree")):
        assert dr._fetch_actual_close("TICK", FRI) == 99.0


# ---------------------------------------------------------------------------
# close_verifier: the NSE row's own date
# ---------------------------------------------------------------------------

def _fake_nse(rows):
    class _NSE:
        def __init__(self, download_folder=None):
            self.dir = download_folder          # close_nse removes it

        def fetch_equity_historical_data(self, ticker, from_date=None, to_date=None):
            return rows

        def exit(self):
            pass
    return type("module", (), {"NSE": _NSE})


@pytest.mark.parametrize("rows, target, expected", [
    ([{"mtimestamp": "24-Sep-2026", "chClosingPrice": 99.0},
      {"mtimestamp": "25-Sep-2026", "chClosingPrice": 100.0}], FRI, (100.0, FRI)),
    # No row for Saturday: the newest row stands in, and names Friday.
    ([{"mtimestamp": "25-Sep-2026", "chClosingPrice": 100.0}], SAT, (100.0, FRI)),
    # An unparseable date is undated — never taken as the session's close.
    ([{"mtimestamp": "Sep 25", "chClosingPrice": 100.0}], FRI, (100.0, None)),
    ([], FRI, (None, None)),
])
def test_nse_session_close_names_the_row(rows, target, expected):
    with patch.dict(sys.modules, {"nse": _fake_nse(rows)}):
        assert close_verifier.nse_session_close("TICK", target) == expected
        # the float-only accessor reads the same cached fetch
        assert close_verifier._fetch_nse_close("TICK", target) == expected[0]


# ---------------------------------------------------------------------------
# pricing.session_close: close_on's walk back, plus the session
# ---------------------------------------------------------------------------

def test_a_weekend_request_resolves_to_friday(monkeypatch):
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(pricing, "_fetch_session_close",
                        lambda sym, d: dr.SessionClose(100.0, d, "agree"))
    quote, session = pricing.session_close("TICK", SUN)
    assert session == FRI and quote.fresh_for(session)


def test_one_retry_then_the_quote(monkeypatch):
    calls = []
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pricing.time, "sleep", lambda s: None)
    monkeypatch.setattr(pricing, "_fetch_session_close", lambda sym, d: (
        calls.append(d) or (dr.SessionClose(None, None, "none") if len(calls) == 1
                            else dr.SessionClose(99.0, THU, "agree"))))
    quote, session = pricing.session_close("TICK", FRI)
    assert len(calls) == 2
    assert quote.close == 99.0 and not quote.fresh_for(session)   # carried forward


def test_no_close_raises_like_close_on(monkeypatch):
    monkeypatch.setattr(pricing, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pricing.time, "sleep", lambda s: None)
    monkeypatch.setattr(pricing, "_fetch_session_close",
                        lambda sym, d: dr.SessionClose(None, None, "none"))
    with pytest.raises(pricing.PriceUnavailableError):
        pricing.session_close("TICK", FRI)
