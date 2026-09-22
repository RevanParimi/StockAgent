"""PI Prospect — the two facts a verdict cannot carry (plan 2026-09-21 / IPO-4c).

An IPO verdict is written at T-1 and again when the book closes. Neither
moment knows what the audit lane needs to grade it: the LISTING DATE (the tape
has not started) and, for a band-priced issue, the final ISSUE PRICE. So the
verdict store keeps the reading and this module resolves the rest at grade
time, from data that already exists locally.

Two sources, in this order and for this reason:

  spine   `data/ipo/ipo_history.jsonl` — durable, canonical, and the SAME
          `issue_price` IPO-1's demand thresholds were fitted against. A
          forward hit-rate measured against a different price than the
          backtest is not comparable with it, which defeats the point.
  cache   `data/market_cache/ipo.json` — the live NSE feed, for an issue that
          has listed but has not reached the spine yet (the spine is rebuilt
          by scripts/ipo_backfill.py, which is manual).

Nothing is invented. An issue with no listing date, or no positive issue
price, resolves to None and the caller reports it as awaiting-listing rather
than as a grading failure — a not-yet-listed IPO is not a broken grade.

No network, no derived value, both inputs injectable: this file must be
runnable in a test with two temp paths and nothing else.
"""
from __future__ import annotations

import logging
from datetime import date

from pydantic import BaseModel

logger = logging.getLogger(__name__)

SOURCES: tuple[str, ...] = ("spine", "cache")


class ListingFacts(BaseModel):
    symbol: str
    listing_date: str                 # ISO, non-empty by construction
    issue_price: float                # > 0 by construction
    source: str                       # one of SOURCES — which file answered


def _iso(value: object) -> str:
    try:
        return date.fromisoformat(str(value or "")).isoformat()
    except ValueError:
        return ""


def _price(value: object) -> float | None:
    """A positive issue price, or None. Zero is not a price — it is the
    dark-signal rule, and compute_outcomes refuses a non-positive price for
    the same reason."""
    try:
        out = float(value)          # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _from_record(symbol: str, rec: object, source: str) -> ListingFacts | None:
    """One normalised record -> facts, or None when it carries only half."""
    if not isinstance(rec, dict):
        return None
    listing_date = _iso(rec.get("listing_date"))
    price = _price(rec.get("issue_price"))
    if not listing_date or price is None:
        return None
    return ListingFacts(symbol=symbol, listing_date=listing_date,
                        issue_price=price, source=source)


def _from_spine(symbol: str, history_store) -> ListingFacts | None:
    try:
        rows = [r for r in history_store.load_all() if r.symbol == symbol]
    except Exception as exc:                 # a dead spine degrades to the cache
        logger.warning("[ipo.listing] spine unreadable for %s (non-fatal): %s", symbol, exc)
        return None
    if not rows:
        return None
    # The spine is upserted, so one row per symbol is the normal case; take the
    # last defensively rather than assuming it.
    rec = rows[-1]
    return _from_record(symbol, {"listing_date": rec.listing_date,
                                 "issue_price": rec.issue_price}, "spine")


def _from_cache(symbol: str, cache_path: str | None) -> ListingFacts | None:
    from services.data.fetchers.ipo import load_ipo_cache
    try:
        cache = load_ipo_cache(cache_path=cache_path)
    except Exception as exc:                 # load_ipo_cache contains its own, but
        logger.warning("[ipo.listing] cache unreadable (non-fatal): %s", exc)
        return None
    # `past` first: a listed issue belongs there, and a row still sitting in
    # `current` can carry a tentative listing date the past feed has since
    # corrected.
    for bucket in ("past", "current", "upcoming"):
        for rec in cache.get(bucket) or []:
            if isinstance(rec, dict) and str(rec.get("symbol") or "") == symbol:
                facts = _from_record(symbol, rec, "cache")
                if facts is not None:
                    return facts
    return None


def listing_facts(symbol: str, *, history_store=None,
                  cache_path: str | None = None,
                  base_dir: str | None = None) -> ListingFacts | None:
    """(listing_date, issue_price) for `symbol`, or None when neither source
    has both. Never raises."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    if history_store is None:
        from core.ipo.history import IpoHistoryStore
        history_store = IpoHistoryStore(base_dir=base_dir)
    return (_from_spine(symbol, history_store)
            or _from_cache(symbol, cache_path))
