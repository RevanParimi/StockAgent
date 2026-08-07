from datetime import date
from unittest.mock import patch

import pytest

from core.audit.benchmark import BenchmarkSeries, BenchmarkUnavailableError
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
