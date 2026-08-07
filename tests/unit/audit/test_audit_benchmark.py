from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from core.audit.benchmark import (
    BenchmarkSeries,
    BenchmarkUnavailableError,
    _fetch_index_close,
)
from core.intelligence.rl.nse_calendar import trading_days_after


def test_trading_days_after_skips_weekend():
    # 2026-08-07 is a Friday; +1 trading day is Monday 2026-08-10.
    assert trading_days_after(date(2026, 8, 7), 1) == date(2026, 8, 10)


def test_trading_days_after_zero_returns_reference():
    assert trading_days_after(date(2026, 8, 7), 0) == date(2026, 8, 7)


def test_trading_days_after_is_inverse_of_ago():
    from core.intelligence.rl.nse_calendar import trading_days_ago
    start = date(2026, 8, 7)
    assert trading_days_ago(trading_days_after(start, 10), 10) == start


def test_benchmark_close_memoised_within_instance():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", return_value=24810.2) as m:
        assert series.close_on(date(2026, 8, 7)) == 24810.2
        assert series.close_on(date(2026, 8, 7)) == 24810.2
    assert m.call_count == 1        # second read came from the memo


def test_benchmark_pct_change():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", side_effect=[100.0, 110.0]):
        assert series.pct_change(date(2026, 7, 1), date(2026, 8, 1)) == 10.0


def test_benchmark_raises_when_unavailable():
    series = BenchmarkSeries()
    with patch("core.audit.benchmark._fetch_index_close", return_value=None):
        with pytest.raises(BenchmarkUnavailableError):
            series.close_on(date(2026, 8, 7))


# ---------------------------------------------------------------------------
# _fetch_index_close itself. Every test above patches it out, which is exactly
# how it shipped broken: the one function that talks to the network was never
# exercised. A 1-day yfinance window returns an EMPTY frame for ^NSEI, so the
# 2026-08-07 prod backfill graded 0 of 119 matured rows. These tests pin the
# window width and the row actually selected.
# ---------------------------------------------------------------------------

def _yf_frame(closes: dict[str, float], ticker: str = "^NSEI") -> pd.DataFrame:
    """A frame shaped the way yfinance really returns one: DatetimeIndex plus
    MultiIndex (field, ticker) columns."""
    return pd.DataFrame(
        {("Close", ticker): list(closes.values())},
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in closes]),
    )


def test_index_fetch_requests_a_window_wide_enough_to_survive_holidays():
    """The root-cause guard: a 1-day window comes back empty from yfinance."""
    seen: dict = {}

    def _capture(ticker, **kw):
        seen.update(kw)
        return _yf_frame({"2026-08-06": 24636.0})

    with patch("yfinance.download", side_effect=_capture):
        _fetch_index_close("^NSEI", date(2026, 8, 6))

    span = date.fromisoformat(seen["end"]) - date.fromisoformat(seen["start"])
    assert span.days >= 7, f"window is only {span.days} day(s) wide"


def test_index_fetch_returns_the_target_date_not_the_first_row_of_the_window():
    frame = _yf_frame({"2026-08-03": 24774.3, "2026-08-05": 24700.0,
                       "2026-08-06": 24636.0})
    with patch("yfinance.download", return_value=frame):
        assert _fetch_index_close("^NSEI", date(2026, 8, 6)) == 24636.0


def test_index_fetch_walks_back_to_the_last_close_before_an_absent_target():
    """Unscheduled holiday: the target has no row, so the most recent close
    at/before it stands in — matching daily_review._fetch_actual_close."""
    frame = _yf_frame({"2026-08-03": 24774.3, "2026-08-04": 24700.0})
    with patch("yfinance.download", return_value=frame):
        assert _fetch_index_close("^NSEI", date(2026, 8, 6)) == 24700.0


def test_index_fetch_never_returns_a_close_from_after_the_target():
    """Lookahead bias would silently corrupt every excess-return figure."""
    frame = _yf_frame({"2026-08-07": 24800.0})
    with patch("yfinance.download", return_value=frame):
        assert _fetch_index_close("^NSEI", date(2026, 8, 6)) is None


def test_index_fetch_returns_none_on_an_empty_frame():
    with patch("yfinance.download", return_value=pd.DataFrame()):
        assert _fetch_index_close("^NSEI", date(2026, 8, 6)) is None
