"""
tools/macro_cache.py
====================
In-memory macro news cache with TTL.

Pattern mirrors StockAI graph.py _macro_cache.

Populated by:  micro_search_loop() in main.py  (runs on a schedule)
Consumed by:   ContextBuilder._build_risk_macro()

When the cache is fresh (< MACRO_CACHE_TTL_HOURS old), risk_macro skips
its 3 Serper calls for sector-level queries (INR/USD, commodities, RBI
repo rate) and uses the cached text instead. yfinance macro data
(get_macro_context) is always fetched fresh — it is free.

Budget impact:
  Cache MISS  →  12 Serper calls per full analysis (cold start)
  Cache HIT   →   9 Serper calls per full analysis (steady-state)
  Saved:           3 calls × N stocks × 30 days = N×90 credits/month
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process store  {sector: {text, fetched_at}}
# ---------------------------------------------------------------------------
_macro_cache: dict[str, dict] = {}


def set_macro_cache(sector: str, text: str) -> None:
    """Store macro news text for *sector*. Called by micro_search_loop()."""
    _macro_cache[sector] = {"text": text, "fetched_at": datetime.utcnow()}
    logger.info(
        "[macro_cache] Updated for sector=%s  (%d chars)",
        sector, len(text),
    )


def get_macro_cache(sector: str) -> Optional[str]:
    """
    Return cached text if younger than MACRO_CACHE_TTL_HOURS, else None.

    Parameters
    ----------
    sector : str
        Cache key — use "automobile" for this repo.
    """
    ttl = timedelta(hours=settings.MACRO_CACHE_TTL_HOURS)
    entry = _macro_cache.get(sector)
    if entry and datetime.utcnow() - entry["fetched_at"] < ttl:
        age_min = int((datetime.utcnow() - entry["fetched_at"]).total_seconds() // 60)
        logger.debug(
            "[macro_cache] HIT  sector=%s  age=%dm  ttl=%dh",
            sector, age_min, settings.MACRO_CACHE_TTL_HOURS,
        )
        return entry["text"]
    logger.debug("[macro_cache] MISS  sector=%s", sector)
    return None


def clear_macro_cache(sector: str | None = None) -> None:
    """Remove one sector (or all) from cache. Useful in tests."""
    if sector is None:
        _macro_cache.clear()
    else:
        _macro_cache.pop(sector, None)
