"""
services/data/context/fetch_result.py
=====================================
SA-002: the typed result a bundle section producer returns.

Why this exists (audit F07, 2026-09-10; spec 2026-08-24 §15.1): a returned
string is not proof of usable source data. Two TATAMOTORS runs against a
symbol whose price source answered HTTP 404 were recorded `health=ok`,
`live=10`, `dims 9/9`. Every producer had wrapped its failure in a sentence —
"Technical data unavailable for TATAMOTORS: ...", "[No results for: ...]" —
and any nonempty sentence classified as `ok`. Matching those sentences would
only move the problem. The producer is the one place that knows whether its
data came back, so it says so here: a status, the source, the as-of date of
the newest datum, and a reason whenever the answer is not a plain `ok`.

`text` is exactly what the prompt receives; `status` is what the health record
receives. They are independent on purpose: a producer may keep an informative
"unavailable" sentence in the prompt and still report `empty`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section outcomes. The first five predate SA-002 (B2); the rest are its.
# ---------------------------------------------------------------------------
STATUS_OK = "ok"                    # verified, fresh data from the named source
STATUS_CACHE_HIT = "cache_hit"      # a cache whose recorded result was usable
STATUS_EMPTY = "empty"              # ran and had nothing — a provider no-data answer included
STATUS_NOT_APPLICABLE = "n/a"       # deliberately not fetched
STATUS_FAILED_PREFIX = "failed:"    # rendered as failed:<ExceptionType>
STATUS_STALE = "stale"              # usable data whose as-of is older than the freshness bound
STATUS_FALLBACK = "fallback"        # a core datum is missing; substitute or partial content instead
STATUS_UNVERIFIED = "unverified"    # text without a typed result — provenance unknown

# What counts as evidence that data arrived. Everything else is a defect of
# the run except `n/a`, which is a decision.
LIVE_STATUSES = frozenset({STATUS_OK, STATUS_CACHE_HIT})


@dataclass(frozen=True)
class FetchResult:
    """One section producer's answer: the prompt text and what it is worth."""

    text: str
    status: str
    source: str
    as_of: str | None = None      # ISO date (or datetime) of the newest underlying datum
    reason: str | None = None     # why the status is not a plain `ok`, or what is partial
    symbol: str | None = None     # SA-008: the provider symbol the data was fetched for

    def provenance(self) -> dict[str, str | None]:
        prov = {"source": self.source, "as_of": self.as_of, "reason": self.reason}
        if self.symbol:
            prov["symbol"] = self.symbol
        return prov


def failed_status(exc: BaseException) -> str:
    return f"{STATUS_FAILED_PREFIX}{type(exc).__name__}"


def join_reasons(reasons: Iterable[str | None]) -> str | None:
    parts = [r for r in reasons if r]
    return "; ".join(parts) if parts else None


def _as_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def is_stale(as_of: str | date | datetime | None, max_age_days: int,
             today: date | None = None) -> bool:
    """True when `as_of` is more than `max_age_days` calendar days old.

    An unknown or unparseable as-of is not called stale: staleness is a claim
    about a date, and there is none to make it about.
    """
    d = _as_date(as_of)
    if d is None:
        return False
    return ((today or date.today()) - d).days > max_age_days


def _cfg_int(key: str, fallback: int) -> int:
    try:
        from backend.shared.config.settings.loader import cfg
        return int(cfg(key, fallback=fallback))
    except Exception as exc:
        logger.debug("[fetch_result] %s unreadable, using %d: %s", key, fallback, exc)
        return fallback


def price_max_age_days() -> int:
    """Freshness bound for a daily price series (calendar days since the last bar)."""
    return _cfg_int("observability.data_health_price_max_age_days", 7)


def fundamentals_max_age_days() -> int:
    """Freshness bound for the newest reported quarter (calendar days since quarter end)."""
    return _cfg_int("observability.data_health_fundamentals_max_age_days", 200)
