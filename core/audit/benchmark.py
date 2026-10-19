"""NIFTY 50 close lookup for benchmark-relative grading.

Nothing else in the codebase fetches an index close for comparison — the
`^NSEI` references in regime/detector.py are momentum inputs, not benchmarks.
This is the module that closes that gap (design section 1, Gap D).

Memoised per instance: a backfill grades thousands of rows against the same
few hundred index dates, so one BenchmarkSeries per run turns N fetches into
one per distinct date. `preload` answers a whole date range from ONE download
(the portfolio screen's Nifty line needs a close under every value point).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta

from backend.shared.config.settings.loader import cfg
from core.intelligence.rl.nse_calendar import is_trading_day

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10        # matches core.portfolio.pricing.close_on
_FETCH_WINDOW_DAYS = 7         # matches daily_review._fetch_actual_close
_RANGE_TTL_S = 3600.0          # a preloaded range is reused for an hour
_RANGE_CACHE_MAX = 16
_range_cache: dict[tuple[str, date, date], tuple[float, dict[date, float]]] = {}
_range_lock = threading.Lock()


class BenchmarkUnavailableError(Exception):
    """No index close could be fetched for the date, even after walkback."""


def _closes_from_frame(frame) -> dict[date, float]:
    """{bar date: close} from a yfinance frame, NaNs dropped."""
    if frame is None or frame.empty:
        return {}
    close = frame["Close"]
    if hasattr(close, "columns"):      # multi-level columns — take first
        close = close.iloc[:, 0]
    close = close.dropna()
    return {ts.date(): float(v) for ts, v in close.items()}


def _fetch_index_bars(ticker: str, start: date, end: date) -> dict[date, float] | None:
    """Every index close from `start` to `end` inclusive in one download;
    None on any failure."""
    try:
        import yfinance as yf
        frame = yf.download(ticker, start=start.isoformat(),
                            end=(end + timedelta(days=1)).isoformat(),
                            progress=False, auto_adjust=True)
        return _closes_from_frame(frame)
    except Exception as exc:
        logger.debug("[audit.benchmark] range fetch failed for %s %s..%s: %s",
                     ticker, start, end, exc)
        return None


def _session_for(d: date) -> date | None:
    """The trading day `close_on(d)` asks for: `d`, or the last trading day
    before it within the walkback."""
    cursor = d
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(cursor):
            return cursor
        cursor -= timedelta(days=1)
    return None


def _pick(bars: dict[date, float], session: date) -> float | None:
    """The bar `_fetch_index_close(session)` selects from the same data: the
    session's own close, else the latest one in the window before it, never
    one after it."""
    if session in bars:
        return bars[session]
    earlier = [d for d in bars if session - timedelta(days=_FETCH_WINDOW_DAYS) <= d < session]
    return bars[max(earlier)] if earlier else None


def _fetch_index_close(ticker: str, d: date) -> float | None:
    """One yfinance index close. Returns None on any failure — the caller
    decides whether that is fatal. Isolated in its own function so tests can
    patch it without touching the network.

    The request spans _FETCH_WINDOW_DAYS, not one day: yfinance answers a
    single-day window with an EMPTY frame, which is why the first prod
    backfill (2026-08-07) graded 0 of 119 matured rows. Same window and same
    row-selection rule as the equity fetcher this sits beside,
    daily_review._fetch_actual_close — entry and exit legs must not measure
    their two dates by different conventions.
    """
    try:
        import yfinance as yf
        frame = yf.download(
            ticker,
            start=(d - timedelta(days=_FETCH_WINDOW_DAYS)).isoformat(),
            end=(d + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
        # Target absent (unscheduled holiday): the most recent close before
        # it stands in. Never after — a future close would be lookahead bias
        # in the denominator of every excess-return figure.
        return _pick(_closes_from_frame(frame), d)
    except Exception as exc:
        logger.debug("[audit.benchmark] fetch failed for %s on %s: %s", ticker, d, exc)
        return None


class BenchmarkSeries:
    """Index closes with holiday walkback, memoised for the life of one run."""

    def __init__(self, ticker: str | None = None) -> None:
        self.ticker = ticker or cfg("audit.benchmark_ticker", fallback="^NSEI")
        self._memo: dict[date, float] = {}
        self._loaded: tuple[date, date] | None = None

    def preload(self, start: date, end: date) -> bool:
        """Answer every date in [start, end] from one download, by the same
        walkback and bar choice as `close_on`. Afterwards a date in the range
        never fetches: one with no close raises BenchmarkUnavailableError.
        A loaded range is shared between instances for an hour (past closes
        do not change), but only once its last session has a bar of its own:
        while the provider lags, that day stands on the close before it, and
        the next load asks again. Returns False when the download failed."""
        key = (self.ticker, start, end)
        now = time.monotonic()
        with _range_lock:
            hit = _range_cache.get(key)
        if hit is not None and now - hit[0] < _RANGE_TTL_S:
            closes = hit[1]
        else:
            first = _session_for(start) or start
            bars = _fetch_index_bars(
                self.ticker, first - timedelta(days=_FETCH_WINDOW_DAYS), end)
            if bars is None:
                self._loaded = (start, end)
                return False
            closes = {}
            d = start
            while d <= end:
                session = _session_for(d)
                value = _pick(bars, session) if session else None
                if value is not None:
                    closes[d] = value
                d += timedelta(days=1)
            last_session = _session_for(end)
            if last_session is not None and last_session in bars:
                with _range_lock:
                    if len(_range_cache) >= _RANGE_CACHE_MAX:
                        _range_cache.pop(min(_range_cache, key=lambda k: _range_cache[k][0]))
                    _range_cache[key] = (now, closes)
        self._memo.update(closes)
        self._loaded = (start, end)
        return True

    def close_on(self, d: date) -> float:
        if d in self._memo:
            return self._memo[d]
        if self._loaded and self._loaded[0] <= d <= self._loaded[1]:
            raise BenchmarkUnavailableError(f"no {self.ticker} close available on/near {d}")
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
