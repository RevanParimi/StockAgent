"""
Compass Phase B — universe construction (spec §6.1 gates that are free
straight from the bhavcopy: mainboard EQ series only, no penny stocks).
"""
from __future__ import annotations

import logging

import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)


def build_universe(window: pd.DataFrame) -> list[str]:
    """Symbols whose LATEST session is series EQ with close >= min_price.

    BE/BZ (T2T) and SME series never enter; price floor kills the penny tail.
    Returns a sorted list. Empty input -> empty list (screen degrades upstream).
    """
    if window.empty:
        return []
    latest_date = window["date"].max()
    latest = window[window["date"] == latest_date]
    ok = latest[
        (latest["series"] == "EQ")
        & (latest["close"] >= settings.DISCOVERY_MIN_PRICE)
    ]
    symbols = sorted(ok["symbol"].unique().tolist())
    logger.info("[discovery.universe] %s: %d symbols (of %d listed rows)",
                latest_date, len(symbols), len(latest))
    return symbols
