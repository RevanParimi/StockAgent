"""
Compass Phase A — real-price lookups for the virtual portfolio.

Entry price = actual NSE close on the entry date; mark-to-market happens on
trading days only (spec §4.1). Reuses daily_review's NSE-cross-checked close
fetcher so the portfolio and the RL loop can never disagree about a close.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.workflows.daily_review import (
    SessionClose,
    _fetch_actual_close,
    _fetch_session_close,
)

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10
_RETRY_SLEEP_S = 2.0


class PriceUnavailableError(Exception):
    """No close could be fetched for the symbol/date."""


def close_on(symbol: str, on: date) -> float:
    """Actual NSE close for `symbol` on `on`, walking back to the most recent
    trading day when `on` is a weekend/holiday. One short retry on a fetch
    miss (AUD-091 — this is the money path; a single transient blip at 16:30
    must not leave a holding unadvised). Raises PriceUnavailableError when no
    close can be fetched within the walkback window."""
    d = on
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(d):
            close = _fetch_actual_close(symbol.upper(), d)
            if close is None:                     # AUD-091: one retry
                time.sleep(_RETRY_SLEEP_S)
                close = _fetch_actual_close(symbol.upper(), d)
            if close is not None:
                return float(close)
            break   # trading day but no data after retry -> genuine failure
        d -= timedelta(days=1)
    raise PriceUnavailableError(f"No NSE close available for {symbol} on/near {on}")


def session_close(symbol: str, on: date) -> tuple[SessionClose, date]:
    """
    SA-003: the same close as `close_on` (same walk back over non-trading
    days, same one retry), plus the session it was fetched for. Returns
    (quote, session); `quote.fresh_for(session)` is True only when the bar is
    that session, not an earlier one carried forward. Raises
    PriceUnavailableError exactly when `close_on` would.
    """
    d = on
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(d):
            quote = _fetch_session_close(symbol.upper(), d)
            if quote.close is None:               # AUD-091: one retry
                time.sleep(_RETRY_SLEEP_S)
                quote = _fetch_session_close(symbol.upper(), d)
            if quote.close is not None:
                return SessionClose(float(quote.close), quote.bar_date, quote.source), d
            break
        d -= timedelta(days=1)
    raise PriceUnavailableError(f"No NSE close available for {symbol} on/near {on}")
