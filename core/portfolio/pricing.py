"""
Compass Phase A — real-price lookups for the virtual portfolio.

Entry price = actual NSE close on the entry date; mark-to-market happens on
trading days only (spec §4.1). Reuses daily_review's NSE-cross-checked close
fetcher so the portfolio and the RL loop can never disagree about a close.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.workflows.daily_review import _fetch_actual_close

logger = logging.getLogger(__name__)

_MAX_WALKBACK_DAYS = 10


class PriceUnavailableError(Exception):
    """No close could be fetched for the symbol/date."""


def close_on(symbol: str, on: date) -> float:
    """Actual NSE close for `symbol` on `on`, walking back to the most recent
    trading day when `on` is a weekend/holiday. Raises PriceUnavailableError
    when no close can be fetched within the walkback window."""
    d = on
    for _ in range(_MAX_WALKBACK_DAYS):
        if is_trading_day(d):
            close = _fetch_actual_close(symbol.upper(), d)
            if close is not None:
                return float(close)
            break   # trading day but no data -> genuine fetch failure
        d -= timedelta(days=1)
    raise PriceUnavailableError(f"No NSE close available for {symbol} on/near {on}")
