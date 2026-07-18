"""
services/data/fetchers/close_verifier.py
=========================================
NSE official close cross-check for RL scoring paths.

The RL loop's most important inputs — the daily actual close (daily_review
scoring) and the re-forecast base close (generate_forecast) — come solely
from yfinance (get_price_history), an unofficial scraper that has served the
WRONG COMPANY's price under symbol-cache poisoning (e.g. MARUTI returning a
~131 quote instead of ~13000) and has regular outage days.

get_verified_close() cross-checks the yfinance close against NSE's official
EOD close (NSE.fetch_equity_historical_data — the "Next API" historical
endpoint, which remains reliable even when NSE's quote-equity endpoint 403s).

Logic (gated by settings.CLOSE_VERIFY_ENABLED):
  1. Fetch yfinance close (via get_price_history — same helper callers use today).
  2. Fetch NSE official close (day-cached in-process, like nse_market.py).
  3. Both present, within CLOSE_VERIFY_TOLERANCE_PCT  -> (yfinance_close, "agree")
     Both present, beyond tolerance                   -> (nse_close, "nse") + WARNING
  4. yfinance missing, NSE present  -> (nse_close, "nse")
     NSE missing, yfinance present  -> (yfinance_close, "yfinance")
     both missing                   -> (None, "none")
  5. Flag off -> pure yfinance passthrough (yfinance_close, "yfinance"), NSE never called.

NEVER raises.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process daily cache for NSE closes — avoids hammering NSE for every
# ticker on every call within the same process/day.
# ---------------------------------------------------------------------------

_NSE_CLOSE_CACHE: dict[str, dict[str, float | None]] = {}  # { "YYYY-MM-DD": { ticker: close } }


def _today_key() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Individual fetchers
# ---------------------------------------------------------------------------

def _sanitize(close: float | None) -> float | None:
    """NaN/inf/non-positive closes are data failures, not prices — a NaN last
    row from yfinance (RISHABH 2026-07-18) passed the `is None` guard in
    generate_forecast and was saved into an envelope as base_close=nan."""
    if close is None or not math.isfinite(close) or close <= 0:
        return None
    return close


def _fetch_yfinance_close(ticker: str) -> float | None:
    """Most recent close via the existing yfinance/C++ fetcher. Never raises."""
    try:
        from core.intelligence.algorithms.indicators.fetcher import get_price_history
        df = get_price_history(ticker, years=1)
        if df.empty:
            return None
        close = df["Close"].squeeze()
        return _sanitize(float(close.iloc[-1]))
    except Exception as exc:
        logger.debug("[close_verifier] yfinance close fetch failed for %s: %s", ticker, exc)
        return None


def _fetch_nse_close(ticker: str, target_date: date | None = None) -> float | None:
    """Official NSE EOD close via NSE.fetch_equity_historical_data.

    With target_date=None, returns the most recent available close. With a
    target_date, returns the close for that specific trading date (falling
    back to the most recent prior trading day within the lookback window).

    Uses the "Next API" historical endpoint, which has remained reliable even
    when NSE's quote-equity endpoint returns 403. Day-cached in-process per
    (ticker, target_date). Never raises.
    """
    cache = _NSE_CLOSE_CACHE.setdefault(_today_key(), {})
    cache_key = f"{ticker}:{target_date.isoformat() if target_date else 'latest'}"
    if cache_key in cache:
        return cache[cache_key]

    close: float | None = None
    try:
        from nse import NSE
        import pathlib
        import tempfile

        dl_folder = pathlib.Path(tempfile.mkdtemp())
        nse = NSE(download_folder=dl_folder)
        try:
            anchor = target_date or date.today()
            data = nse.fetch_equity_historical_data(
                ticker, from_date=anchor - timedelta(days=10), to_date=anchor,
            )
            if data:
                if target_date is not None:
                    target_str = target_date.strftime("%d-%b-%Y")
                    match = next((d for d in data if d.get("mtimestamp") == target_str), None)
                    row = match or data[-1]
                else:
                    row = data[-1]
                close = _sanitize(float(row["chClosingPrice"]))
        finally:
            try:
                nse.exit()
            except Exception:
                pass
    except Exception as exc:
        logger.debug("[close_verifier] NSE close fetch failed for %s: %s", ticker, exc)
        close = None

    cache[cache_key] = close
    return close


# ---------------------------------------------------------------------------
# Shared comparison logic
# ---------------------------------------------------------------------------

def _compare(ticker: str, yf_close: float | None, nse_close: float | None) -> tuple[float | None, str]:
    """Apply the agree/disagree/fallback rules given two already-fetched closes."""
    if yf_close is not None and nse_close is not None:
        tolerance_pct = getattr(settings, "CLOSE_VERIFY_TOLERANCE_PCT", 1.0)
        diff_pct = abs(yf_close - nse_close) / nse_close * 100 if nse_close else 0.0
        if diff_pct <= tolerance_pct:
            return (yf_close, "agree")
        logger.warning(
            "[close_verifier] %s: yfinance close (%.2f) and NSE close (%.2f) "
            "disagree by %.2f%% (tolerance=%.2f%%) — using NSE value. "
            "Possible yfinance symbol-cache poisoning or stale data.",
            ticker, yf_close, nse_close, diff_pct, tolerance_pct,
        )
        return (nse_close, "nse")

    if yf_close is None and nse_close is not None:
        return (nse_close, "nse")

    if yf_close is not None and nse_close is None:
        return (yf_close, "yfinance")

    return (None, "none")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _safe_call(fn, *args, default=None, label: str = ""):
    """Call fn(*args), swallowing any exception and returning default. Logs at debug."""
    try:
        return fn(*args)
    except Exception as exc:
        logger.debug("[close_verifier] %s failed: %s", label or getattr(fn, "__name__", "call"), exc)
        return default


def get_verified_close(ticker: str) -> tuple[float | None, str]:
    """Authoritative MOST RECENT close for RL scoring paths.

    Used by generate_forecast for the day-0 / re-forecast base close.

    Returns (close, source) where source in {"agree", "nse", "yfinance", "none"}.
    NEVER raises.
    """
    try:
        yf_close = _safe_call(_fetch_yfinance_close, ticker, label="yfinance close fetch")

        if not getattr(settings, "CLOSE_VERIFY_ENABLED", True):
            return (yf_close, "yfinance") if yf_close is not None else (None, "none")

        nse_close = _safe_call(_fetch_nse_close, ticker, label="NSE close fetch")
        return _compare(ticker, yf_close, nse_close)
    except Exception as exc:
        logger.warning("[close_verifier] get_verified_close failed for %s: %s", ticker, exc)
        return (None, "none")


def cross_check_close(
    ticker: str,
    yf_close: float | None,
    target_date: date | None = None,
) -> tuple[float | None, str]:
    """Cross-check an ALREADY-FETCHED yfinance close against NSE's official close.

    Used by daily_review, which has its own multi-attempt yfinance fetch
    (yf.download + BSE fallback + C++ fetcher) for a specific target_date —
    this avoids a second yfinance fetch while still applying the NSE
    cross-check / poisoning detector.

    Returns (close, source) where source in {"agree", "nse", "yfinance", "none"}.
    NEVER raises.
    """
    try:
        yf_close = _sanitize(yf_close)
        if not getattr(settings, "CLOSE_VERIFY_ENABLED", True):
            return (yf_close, "yfinance") if yf_close is not None else (None, "none")

        nse_close = _safe_call(_fetch_nse_close, ticker, target_date, label="NSE close fetch")
        return _compare(ticker, yf_close, nse_close)
    except Exception as exc:
        logger.warning("[close_verifier] cross_check_close failed for %s: %s", ticker, exc)
        return (yf_close, "yfinance") if yf_close is not None else (None, "none")
