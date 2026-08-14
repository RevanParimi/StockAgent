"""PI Prospect P2 — grey-market premium via a DEDICATED Serper key.

Ships dark. `ipo.gmp_enabled` is false and `SERPER_API_KEY_IPO` is unset, in
which case this module returns None and issues no request at all.

Why its own key: the shared SERPER_API_KEY runs at ~83 calls/day against a
2,500/month cap (prod counter, 2026-08-13: 924 calls on day 13 of 31,
projecting ~2,200-2,420). Real headroom is 80-300 calls/month, so IPO polling
on the shared key would compete directly with the daily pipeline. The spec's
original "~2,300 calls/mo headroom" was never measured and is wrong.

GMP is unofficial grey-market chatter scraped from search snippets, so a
single number is treated as a rumour: a reading requires agreement between at
least `ipo.gmp_min_sources` DISTINCT domains, and the spread between them must
be within `ipo.gmp_agreement_tolerance`. Callers render the result as
unofficial, always.
"""
from __future__ import annotations

import logging
import re
import statistics
from urllib.parse import urlparse

from services.data.fetchers.news import search_serper

logger = logging.getLogger(__name__)

# "Rs 120", "₹130", "Rs. 1,250" — the number is the premium per share.
_GMP_RE = re.compile(r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
# Guards against picking up a share count or a market-cap figure.
_MAX_PLAUSIBLE_GMP = 5000.0


def _numbers_by_domain(results: list[dict]) -> dict[str, float]:
    """One number per domain — the first plausible one. An aggregator echoed
    across two result pages is one source, not two."""
    out: dict[str, float] = {}
    for item in results or []:
        domain = urlparse(str(item.get("link") or "")).netloc.lower()
        if not domain or domain in out:
            continue
        match = _GMP_RE.search(str(item.get("snippet") or ""))
        if not match:
            continue
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if 0 < value <= _MAX_PLAUSIBLE_GMP:
            out[domain] = value
    return out


def fetch_gmp(company: str, issue_price: float | None = None) -> dict | None:
    """Median GMP across agreeing sources, or None. Never raises.

    None means "not collected" — never "no premium". A GMP of zero is a real
    and meaningful reading, which is exactly why absence must not render as 0.
    """
    from core.config import settings

    if not getattr(settings, "IPO_GMP_ENABLED", False):
        return None
    key = getattr(settings, "SERPER_API_KEY_IPO", "")
    if not key:
        logger.debug("[ipo_gmp] no SERPER_API_KEY_IPO — skipping, no call made")
        return None
    if not company:
        return None

    try:
        results = search_serper(f"{company} IPO GMP grey market premium today",
                                n=6, api_key=key)
    except Exception as exc:
        logger.warning("[ipo_gmp] search failed for %s (non-fatal): %s", company, exc)
        return None

    by_domain = _numbers_by_domain(results)
    min_sources = int(getattr(settings, "IPO_GMP_MIN_SOURCES", 2))
    if len(by_domain) < min_sources:
        logger.debug("[ipo_gmp] %s: %d source(s), need %d — discarding",
                     company, len(by_domain), min_sources)
        return None

    values = sorted(by_domain.values())
    tolerance = float(getattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25))
    if values[-1] > values[0] * (1.0 + tolerance):
        logger.debug("[ipo_gmp] %s: sources disagree (%s) — discarding",
                     company, values)
        return None

    gmp = float(statistics.median(values))
    pct = (gmp / issue_price * 100.0) if issue_price else None
    return {"gmp": gmp, "gmp_pct": pct, "sources": len(by_domain)}
