"""NIFTY 50 close lookup for benchmark-relative grading.

Nothing else in the codebase fetches an index close for comparison — the
`^NSEI` references in regime/detector.py are momentum inputs, not benchmarks.
This is the module that closes that gap (design section 1, Gap D).

Memoised per instance: a backfill grades thousands of rows against the same
few hundred index dates, so one BenchmarkSeries per run turns N fetches into
one per distinct date.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from backend.shared.config.settings.loader import cfg
from core.intelligence.rl.nse_calendar import is_trading_day

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10        # matches core.portfolio.pricing.close_on


class BenchmarkUnavailableError(Exception):
    """No index close could be fetched for the date, even after walkback."""


def _fetch_index_close(ticker: str, d: date) -> float | None:
    """One yfinance index close. Returns None on any failure — the caller
    decides whether that is fatal. Isolated in its own function so tests can
    patch it without touching the network."""
    try:
        import yfinance as yf
        frame = yf.download(
            ticker,
            start=d.isoformat(),
            end=(d + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if frame is None or frame.empty:
            return None
        return float(frame["Close"].iloc[0])
    except Exception as exc:
        logger.debug("[audit.benchmark] fetch failed for %s on %s: %s", ticker, d, exc)
        return None


class BenchmarkSeries:
    """Index closes with holiday walkback, memoised for the life of one run."""

    def __init__(self, ticker: str | None = None) -> None:
        self.ticker = ticker or cfg("audit.benchmark_ticker", fallback="^NSEI")
        self._memo: dict[date, float] = {}

    def close_on(self, d: date) -> float:
        if d in self._memo:
            return self._memo[d]
        cursor = d
        for _ in range(_MAX_WALKBACK_DAYS):
            if is_trading_day(cursor):
                close = _fetch_index_close(self.ticker, cursor)
                if close is not None:
                    self._memo[d] = close
                    return close
                break
            cursor -= timedelta(days=1)
        raise BenchmarkUnavailableError(
            f"no {self.ticker} close available on/near {d}"
        )

    def pct_change(self, start: date, end: date) -> float:
        first = self.close_on(start)
        last = self.close_on(end)
        if first <= 0:
            raise BenchmarkUnavailableError(f"non-positive {self.ticker} close on {start}")
        return round((last / first - 1.0) * 100.0, 4)
