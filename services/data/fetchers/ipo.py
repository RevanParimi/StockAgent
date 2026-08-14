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
from datetime import date as _date
from datetime import datetime, timedelta, timezone

from services.data.fetchers.ipo_bids import fetch_bid_ladder

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/ipo.json"
_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")
_PAST_WINDOW_DAYS = 120          # fetch a little beyond the 90d tracker window

_SYMBOL_KEYS = ("symbol", "sym", "SYMBOL")
_COMPANY_KEYS = ("companyName", "company", "issuerCompany", "COMPANY_NAME")
# listPastIPO has no `series` key at all — it carries `securityType`
# (verified live 2026-08-12). Without this the SME guard below never fires
# on the past feed, and 287 SME rows leak into a mainboard-only universe.
_SERIES_KEYS = ("series", "SERIES", "securityType")
_LISTING_DATE_KEYS = ("listingDate", "listing_date", "dateOfListing", "listingDt")
# The current/upcoming feeds carry the BIDDING window, not a listing date
# (verified live 2026-08-11, spec section 11.1). listPastIPO does carry
# listingDate, which is why _LISTING_DATE_KEYS stays.
_ISSUE_START_KEYS = ("issueStartDate", "issue_start_date", "biddingStartDate")
_ISSUE_END_KEYS = ("issueEndDate", "issue_end_date", "biddingEndDate")
_ISSUE_PRICE_KEYS = ("issuePrice", "issue_price", "finalIssuePrice", "priceBand", "issuePriceBand")
_QIB_KEYS = ("qibSubscriptionTimes", "qibTimes", "qib")
_RETAIL_KEYS = ("retailSubscriptionTimes", "riiTimes", "retail")
# `noOfTime` is what /api/ipo-current-issue actually ships (verified live
# 2026-08-11, spec section 11.1) and MUST stay first: _first() takes the
# earliest key present. The other three are unobserved legacy guesses, kept
# only because NSE field names drift across report vintages.
_TOTAL_SUB_KEYS = ("noOfTime", "noOfTimesSubscribed", "totalSubscriptionTimes",
                   "subscriptionTimes")
_SME_SERIES = {"SM", "ST", "SME"}
# Bonds and other non-equity instruments share the IPO feed. An equity-IPO
# study must not treat an NCD as a listing.
_NON_EQUITY_TYPES = {"DEBT", "N0", "N1", "IV", "RR"}


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
        if series in _NON_EQUITY_TYPES:
            continue
        total_x = _parse_x(_first(item, _TOTAL_SUB_KEYS))
        # `noOfTime` is the NSE-only figure, and NSE serves a literal 0.00 for
        # some rows. A bare 0.0 with no category breakdown means "unknown",
        # not "nobody bid" — the dark-signal rule, same as parse_bid_ladder.
        if total_x == 0.0:
            total_x = None
        out.append({
            "symbol": symbol,
            "company": _first(item, _COMPANY_KEYS),
            "series": series,
            "listing_date": _parse_date(_first(item, _LISTING_DATE_KEYS)),
            "issue_start": _parse_date(_first(item, _ISSUE_START_KEYS)),
            "issue_end": _parse_date(_first(item, _ISSUE_END_KEYS)),
            "issue_price": _parse_price(_first(item, _ISSUE_PRICE_KEYS)),
            "qib_x": _parse_x(_first(item, _QIB_KEYS)),
            "retail_x": _parse_x(_first(item, _RETAIL_KEYS)),
            "total_x": total_x,
            # noOfTime is the NSE-only figure (the ladder's all-exchange
            # `combined` total, when available, overwrites both this value
            # and the flag in _enrich_open_issues below) — it under-reports
            # vs the all-exchange figure the market actually quotes, so a
            # consumer showing this number unqualified would show a WRONG
            # number, not an honestly absent one.
            "total_x_nse_only": total_x is not None,
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


_LADDER_FIELDS = ("bid_ladder", "cutoff_share", "qib_x", "retail_x", "total_x")


def _carry_forward(rec: dict, previous: dict | None) -> None:
    """Restore ladder-derived fields from the previous cache, in place.

    Every pass rebuilds rows from _normalise, which knows only what the LIST
    feed carries — and the list feed has no ladder. Without this, a closed
    issue's final ladder is destroyed by the next refresh, and that row is the
    completed demand picture the capture ledger exists to keep.

    Only fills fields the new row lacks: a fresh fetch always wins.
    """
    if not previous:
        return
    prior = previous.get(rec.get("symbol", ""))
    if not isinstance(prior, dict):
        return
    for field in _LADDER_FIELDS:
        if rec.get(field) is None and prior.get(field) is not None:
            rec[field] = prior[field]
            if field == "total_x":
                # The qualifier must travel WITH the value it qualifies.
                # _normalise recomputes this as `total_x is not None`, so it is
                # always a bool and the `is None` guard above can never carry it.
                # A carried NSE-only total whose flag stayed False renders as if
                # it were the all-exchange figure — a wrong number, not a partial
                # one (spec §11.4).
                rec["total_x_nse_only"] = bool(prior.get("total_x_nse_only", False))


def _enrich_open_issues(rows: list[dict], on: _date,
                        previous: dict | None = None) -> None:
    """Attach the bid ladder to issues whose window is OPEN, in place.

    Only open issues get a live fetch: an upcoming one has no bids yet and a
    closed one will never change, so either would spend an NSE call to learn
    nothing. Closed issues instead inherit their last known ladder via
    _carry_forward. Bounded by IPO_MAX_LADDER_FETCHES because this runs inside
    a scheduler job.
    """
    from core.config import settings
    from core.ipo.calendar import issue_state

    if not getattr(settings, "IPO_BID_LADDER_ENABLED", True):
        for rec in rows:
            _carry_forward(rec, previous)
        return

    budget = int(getattr(settings, "IPO_MAX_LADDER_FETCHES", 10))
    for rec in rows:
        if issue_state(rec, on) != "open" or budget <= 0:
            _carry_forward(rec, previous)
            continue
        ladder = fetch_bid_ladder(rec["symbol"])
        if ladder is None:
            # Budget is spent only on a SUCCESSFUL fetch: a run of dead-endpoint
            # failures must not exhaust the cap with zero enrichment (§9b).
            _carry_forward(rec, previous)
            continue
        budget -= 1
        combined = ladder.get("combined") or {}
        rec["bid_ladder"] = ladder
        rec["cutoff_share"] = ladder.get("cutoff_share")
        for field, key in (("qib_x", "qib"), ("retail_x", "retail")):
            if combined.get(key) is not None:
                rec[field] = combined[key]
        if combined.get("total") is not None:
            rec["total_x"] = combined["total"]
            rec["total_x_nse_only"] = False
        _carry_forward(rec, previous)


def _capture_signals(rows: list[dict], on: _date, store=None) -> int:
    """Append one capture-ledger snapshot per issue that has a ladder.

    Spends NO additional API calls: it persists what _enrich_open_issues
    already fetched and previously discarded. An issue with no ladder is
    skipped rather than written as all-None — a row in the ledger asserts a
    reading was taken, and "we looked and there were no bids yet" is not the
    same claim as "we never looked".

    Never raises: a dead ledger must not break the cache write the morning
    brief depends on.
    """
    from core.config import settings
    from core.ipo.calendar import issue_state

    if not getattr(settings, "IPO_SIGNALS_ENABLED", True):
        return 0

    written = 0
    try:
        if store is None:
            from core.ipo.signals import IpoSignalStore
            store = IpoSignalStore()
        from core.ipo.signals import IpoSignalSnapshot
        stamp = datetime.now(timezone.utc).isoformat()
        for rec in rows:
            ladder = rec.get("bid_ladder")
            if not isinstance(ladder, dict):
                continue
            snap = IpoSignalSnapshot(
                symbol=rec.get("symbol", ""),
                captured_at=stamp,
                state=issue_state(rec, on),
                issue_start=rec.get("issue_start", "") or "",
                issue_end=rec.get("issue_end", "") or "",
                combined=ladder.get("combined") or {},
                nse_only=ladder.get("nse_only") or {},
                cutoff_share=rec.get("cutoff_share"),
            )
            if store.append(snap):
                written += 1
    except Exception as exc:
        logger.warning("[ipo] signal capture failed (non-fatal): %s", exc)
        return written
    return written


def refresh_ipo_cache(cache_path: str | None = None,
                      on: _date | None = None) -> dict:
    """Fetch current + upcoming + past-120d IPO lists, then enrich OPEN issues
    with their category-wise bid ladder. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_ipo_cache(cache_path=str(path))
    on = on or _date.today()

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
            from services.data.fetchers.nse_client import close_nse
            close_nse(nse)  # exit() + rmtree(download_folder) — AUD-017
    except Exception as exc:
        logger.warning("[ipo] fetch failed — keeping stale cache: %s", exc)
        degraded = True
        current = list(previous.get("current", []))
        upcoming = list(previous.get("upcoming", []))
        past = list(previous.get("past", []))

    if not degraded:
        prior_rows: dict[str, dict] = {}
        for bucket in ("current", "upcoming", "past"):
            for row in previous.get(bucket, []) or []:
                if isinstance(row, dict) and row.get("symbol"):
                    prior_rows.setdefault(row["symbol"], row)
        _enrich_open_issues(current + upcoming, on, previous=prior_rows)

        captured = _capture_signals(current + upcoming, on)
        if captured:
            logger.info("[ipo] captured %d signal snapshot(s)", captured)

        try:
            from core.config import settings as _s
            from core.ipo.signals import IpoSignalStore
            IpoSignalStore().prune(
                older_than_days=int(getattr(_s, "IPO_SIGNAL_RETENTION_DAYS", 400)))
        except Exception as exc:
            logger.warning("[ipo] signal prune failed (non-fatal): %s", exc)

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
