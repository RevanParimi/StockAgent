"""FIX-001 — a one-bar price download is a close, not a failure.

On a stock's listing day a 7-day download holds exactly one bar. Before
FIX-001, `df["Close"].squeeze()` turned that one-bar column into a scalar,
`.dropna()` raised, and the session's own close was discarded; the audit's
IPO lane then logged the row as unpriceable (30 Sep 2026: SWASTIKAIN and
ADROITIND, "audit_nightly completed 25/27").

Expected closes and dates are the fixture's own bars, written by hand. The
frames use yfinance's download shape: (price, ticker) column levels.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

import core.intelligence.rl.workflows.daily_review as dr
import core.portfolio.pricing as pricing
from services.data.fetchers import close_verifier

FRI = date(2026, 9, 25)            # a trading day (see test_session_close_sa003)
THU = FRI - timedelta(days=1)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    close_verifier._NSE_CLOSE_CACHE.clear()
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_ENABLED", True, raising=False)
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_TOLERANCE_PCT", 1.0, raising=False)
    yield
    close_verifier._NSE_CLOSE_CACHE.clear()


def _yf_frame(bars: dict[date, float], symbol: str = "TICK.NS") -> pd.DataFrame:
    """What yf.download returns: columns (Price, Ticker)."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in bars])
    cols = pd.MultiIndex.from_tuples([("Close", symbol), ("Open", symbol)], names=["Price", "Ticker"])
    return pd.DataFrame([[v, v] for v in bars.values()], index=idx, columns=cols)


def _flat_frame(bars: dict[date, float]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in bars])
    return pd.DataFrame({"Close": list(bars.values())}, index=idx)


def _fetch(download, nse=(None, None)):
    """download: a frame, or a function of the requested symbol."""
    kw = {"side_effect": download} if callable(download) else {"return_value": download}
    with patch("yfinance.download", **kw) as dl, \
         patch.object(dr, "get_price_history", return_value=pd.DataFrame()), \
         patch.object(close_verifier, "_fetch_nse_session", return_value=nse):
        return dr._fetch_session_close("TICK", FRI), dl


# ---------------------------------------------------------------------------
# daily_review._fetch_session_close (the review's and the audit's close)
# ---------------------------------------------------------------------------

def test_a_listing_day_bar_is_the_sessions_close():
    q, _ = _fetch(_yf_frame({FRI: 101.5}))
    assert q == dr.SessionClose(101.5, FRI, "yfinance")
    assert q.fresh_for(FRI)


def test_a_listing_day_bar_is_cross_checked_like_any_other():
    q, _ = _fetch(_yf_frame({FRI: 101.5}), nse=(101.6, FRI))
    assert q == dr.SessionClose(101.5, FRI, "agree")


def test_a_one_bar_flat_frame_too():
    q, _ = _fetch(_flat_frame({FRI: 101.5}))
    assert q == dr.SessionClose(101.5, FRI, "yfinance")


def test_a_lone_earlier_bar_is_carried_forward_visibly():
    """One bar, from Thursday, for a Friday request: the same rule as for a
    longer frame. The close is Thursday's and says so."""
    q, _ = _fetch(_yf_frame({THU: 99.0}))
    assert q == dr.SessionClose(99.0, THU, "yfinance")
    assert not q.fresh_for(FRI)


def test_a_lone_nan_bar_is_no_close():
    q, _ = _fetch(_yf_frame({FRI: float("nan")}))
    assert q == dr.SessionClose(None, None, "none")


def test_the_bse_fallback_reads_a_one_bar_frame():
    def download(sym, **kw):
        return _yf_frame({FRI: 88.0}, "TICK.BO") if sym == "TICK.BO" else pd.DataFrame()

    q, dl = _fetch(download)
    assert [c.args[0] for c in dl.call_args_list] == ["TICK.NS", "TICK.BO"]
    assert q == dr.SessionClose(88.0, FRI, "yfinance")


def test_more_bars_still_pick_the_sessions_own():
    q, _ = _fetch(_yf_frame({THU: 99.0, FRI: 100.0}))
    assert q == dr.SessionClose(100.0, FRI, "yfinance")


# ---------------------------------------------------------------------------
# core.portfolio.pricing.close_on (the audit's price_fn; holdings)
# ---------------------------------------------------------------------------

def test_close_on_prices_a_listing_day_without_a_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr(pricing.time, "sleep", sleeps.append)
    with patch("yfinance.download", return_value=_yf_frame({FRI: 101.5})), \
         patch.object(dr, "get_price_history", return_value=pd.DataFrame()), \
         patch.object(close_verifier, "_fetch_nse_session", return_value=(None, None)):
        assert pricing.close_on("TICK", FRI) == 101.5
    assert sleeps == []


# ---------------------------------------------------------------------------
# close_verifier._fetch_yfinance_close (the latest close)
# ---------------------------------------------------------------------------

def test_the_latest_close_from_a_one_bar_history():
    with patch("core.intelligence.algorithms.indicators.fetcher.get_price_history",
               return_value=_yf_frame({FRI: 101.5})):
        assert close_verifier._fetch_yfinance_close("TICK") == 101.5


def test_a_nan_last_row_is_still_a_failure_not_the_previous_close():
    """Unchanged: the newest row is NaN, so there is no latest close. The
    previous day's 99.0 is not passed off as today's."""
    with patch("core.intelligence.algorithms.indicators.fetcher.get_price_history",
               return_value=_yf_frame({THU: 99.0, FRI: float("nan")})):
        assert close_verifier._fetch_yfinance_close("TICK") is None
