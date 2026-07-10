"""
Compass Phase C — NSE IPO / new-listing feed (spec §6.2).

Wraps the nse pkg's listCurrentIPO / listUpcomingIPO / listPastIPO. Field
names vary across NSE report vintages, so every field is resolved through
candidate-key tuples (same defensive pattern as bulk_block.py). Subscription
breakdown (QIB / retail ×) is OPTIONAL — records without it carry None and
downstream scoring renormalizes (dark-signal pattern, spec §8).

Degraded mode: on any fetch failure the previous cache is kept and flagged
degraded — no feed is a single point of failure.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
import tempfile
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/ipo.json"
_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")
_PAST_WINDOW_DAYS = 120          # fetch a little beyond the 90d tracker window

_SYMBOL_KEYS = ("symbol", "sym", "SYMBOL")
_COMPANY_KEYS = ("companyName", "company", "issuerCompany", "COMPANY_NAME")
_SERIES_KEYS = ("series", "SERIES")
_LISTING_DATE_KEYS = ("listingDate", "listing_date", "dateOfListing", "listingDt")
_ISSUE_PRICE_KEYS = ("issuePrice", "issue_price", "finalIssuePrice", "priceBand", "issuePriceBand")
_QIB_KEYS = ("qibSubscriptionTimes", "qibTimes", "qib")
_RETAIL_KEYS = ("retailSubscriptionTimes", "riiTimes", "retail")
_TOTAL_SUB_KEYS = ("noOfTimesSubscribed", "totalSubscriptionTimes", "subscriptionTimes")
_SME_SERIES = {"SM", "ST", "SME"}


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _first(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_date(raw: str) -> str:
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _parse_price(raw: str) -> float | None:
    """'315' -> 315.0; '300 to 315' / '₹300-315' -> 315.0 (upper band)."""
    nums = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    return float(nums[-1]) if nums else None


def _parse_x(raw: str) -> float | None:
    nums = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    return float(nums[0]) if nums else None


def _normalise(rows: list, status: str) -> list[dict]:
    from core.config import settings
    out: list[dict] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        symbol = _first(item, _SYMBOL_KEYS).upper()
        if not symbol:
            continue
        series = _first(item, _SERIES_KEYS).upper()
        if series in _SME_SERIES and not settings.DISCOVERY_INCLUDE_SME:
            continue                                     # spec §6.2: SME excluded
        out.append({
            "symbol": symbol,
            "company": _first(item, _COMPANY_KEYS),
            "series": series,
            "listing_date": _parse_date(_first(item, _LISTING_DATE_KEYS)),
            "issue_price": _parse_price(_first(item, _ISSUE_PRICE_KEYS)),
            "qib_x": _parse_x(_first(item, _QIB_KEYS)),
            "retail_x": _parse_x(_first(item, _RETAIL_KEYS)),
            "total_x": _parse_x(_first(item, _TOTAL_SUB_KEYS)),
            "status": status,
        })
    return out


def load_ipo_cache(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": True,
                "current": [], "upcoming": [], "past": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[ipo] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": True,
                "current": [], "upcoming": [], "past": []}


def refresh_ipo_cache(cache_path: str | None = None) -> dict:
    """Fetch current + upcoming + past-120d IPO lists. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_ipo_cache(cache_path=str(path))

    degraded = False
    current: list[dict] = []
    upcoming: list[dict] = []
    past: list[dict] = []
    try:
        nse = _make_nse_client()
        try:
            todate = datetime.now()
            fromdate = todate - timedelta(days=_PAST_WINDOW_DAYS)
            past = _normalise(nse.listPastIPO(fromdate, todate), "past")
            current = _normalise(nse.listCurrentIPO(), "current")
            upcoming = _normalise(nse.listUpcomingIPO(), "upcoming")
        finally:
            try:
                nse.exit()
            except Exception:
                pass
    except Exception as exc:
        logger.warning("[ipo] fetch failed — keeping stale cache: %s", exc)
        degraded = True
        current = list(previous.get("current", []))
        upcoming = list(previous.get("upcoming", []))
        past = list(previous.get("past", []))

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "current": current, "upcoming": upcoming, "past": past,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[ipo] cache write failed %s: %s", path, exc)
    return result
