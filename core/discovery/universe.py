"""
Compass Phase B — universe construction (spec §6.1 gates that are free
straight from the bhavcopy: mainboard EQ series only, no penny stocks), and
the instrument rule: only companies are screened or dived. ETFs, index and
liquid funds trade in the EQ series too, so the series alone cannot tell; the
ISIN in NSE's listing does (services/data/fetchers/bhavcopy.py).
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


# -- Only companies (PR-004) ------------------------------------------------------

COMPANY, FUND, TRUST, OTHER, UNKNOWN = "company", "fund", "trust", "other", "unknown"
_TRUST_SERIES = ("RR", "IV")          # REIT units trade as RR, InvIT units as IV


def instrument_kind(symbol: str, listing: dict | None) -> str:
    """What NSE lists `symbol` as, from its ISIN and series, never its name.

      company  shares of a company: ISIN "INE…", not a REIT/InvIT series
      fund     units of a mutual-fund scheme: ISIN "INF…" (every ETF, index
               fund and liquid fund, LIQUID1 among them)
      trust    REIT or InvIT units (series RR / IV)
      other    any other ISIN (government securities, gold bonds, …)
      unknown  no listing, or the symbol is not in it
    """
    row = (listing or {}).get(symbol.strip().upper())
    if not isinstance(row, dict):
        return UNKNOWN
    isin = str(row.get("isin") or "").upper()
    if str(row.get("series") or "").upper() in _TRUST_SERIES:
        return TRUST
    if isin.startswith("INF"):
        return FUND
    if isin.startswith("INE"):
        return COMPANY
    return OTHER if isin else UNKNOWN


def companies_only(symbols: list[str], listing: dict | None) -> tuple[list[str], dict[str, str]]:
    """(the symbols NSE lists as companies, {excluded symbol: kind}), order
    kept. A symbol the listing does not know is excluded as "unknown"."""
    kept: list[str] = []
    excluded: dict[str, str] = {}
    for sym in symbols:
        kind = instrument_kind(sym, listing)
        if kind == COMPANY:
            kept.append(sym)
        else:
            excluded[sym] = kind
    return kept, excluded
