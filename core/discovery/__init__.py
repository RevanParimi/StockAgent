"""
Compass Phase B — Discovery Engine (spec §6): weekly funnel orchestration.

run_discovery_cycle() is the single entry point used by BOTH the Saturday
scheduler job and POST /discovery/run. Every stage is individually
non-fatal: a dark data feed degrades the screen, it never kills the cycle.

PR-004: the week's analyst budget (DISCOVERY_DEEP_DIVE_COUNT calls) goes
first to re-dives of shelf ideas that are unverified or older than
DISCOVERY_REDIVE_AFTER_DAYS, leaving the IPO slots free, then to IPO
candidates, then to the screen's ranks.
"""
from __future__ import annotations

import logging
from datetime import date

# Re-exported collaborators — tests and callers patch these names HERE.
from backend.shared.schemas.discovery import DiscoveryCandidate
from core.discovery.deep_dive import run_deep_dives
from core.discovery.paper_lane import run_paper_reviews
from core.discovery.screen import load_latest_screen, run_screen
from core.discovery.shelf import ShelfStore
from services.data.fetchers.bhavcopy import load_listing, refresh_listing, sync_recent
from services.data.fetchers.bulk_block import refresh_bulk_block
from services.data.fetchers.surveillance import market_classification
from core.discovery.insider import refresh_insider_trades
from core.config import settings
from core.discovery.ipo_tracker import build_ipo_candidates, upcoming_lockin_alerts
from services.data.fetchers.ipo import refresh_ipo_cache

logger = logging.getLogger(__name__)

__all__ = [
    "run_discovery_cycle", "run_deep_dives", "run_paper_reviews",
    "run_screen", "load_latest_screen", "ShelfStore",
    "sync_recent", "refresh_bulk_block", "refresh_listing", "load_listing",
    "market_classification", "refresh_insider_trades",
    "refresh_ipo_cache", "build_ipo_candidates", "upcoming_lockin_alerts",
    "settings",
]


def run_discovery_cycle(on: date | None = None) -> dict:
    """sync EOD -> refresh bulk/block -> instrument listing -> ipo tracker ->
    shelf hygiene (drop non-companies, name sectors, pick re-dives) -> screen
    -> deep-dives -> shelf -> weekly paper reviews. Returns a stage-by-stage
    summary; never raises."""
    on = on or date.today()
    errors: list[str] = []

    try:
        sync = sync_recent(days_back=7)
    except Exception as exc:
        logger.warning("[discovery] sync failed (non-fatal): %s", exc)
        errors.append(f"sync failed: {exc}")
        sync = {}

    try:
        refresh_bulk_block(weeks=4)
    except Exception as exc:
        logger.warning("[discovery] bulk/block refresh failed (non-fatal): %s", exc)
        errors.append(f"bulk_block failed: {exc}")

    # PR-011: every company's insider-trade filings for insider_buying. The
    # screen leaves the signal out, and says why, unless all were read.
    insider: dict = {}
    try:
        insider = refresh_insider_trades(on)
        if insider.get("error"):
            errors.append(f"insider trades failed: {insider['error']}"[:200])
    except Exception as exc:
        logger.warning("[discovery] insider trades refresh failed (non-fatal): %s", exc)
        errors.append(f"insider trades failed: {exc}")

    # PR-004: what NSE lists each symbol as. Without any listing no symbol can
    # be verified as a company, and the deep dives refuse to run blind.
    try:
        listing_info = refresh_listing(end=on)
    except Exception as exc:
        logger.warning("[discovery] listing refresh failed (non-fatal): %s", exc)
        listing_info = {"as_of": None, "fresh": False, "securities": 0}
    listing = load_listing()
    if listing is None:
        errors.append("instrument listing unavailable: no symbol can be verified as a "
                      "company, so no deep dive runs this week")

    ipo_cands: list = []
    if getattr(settings, "DISCOVERY_IPO_ENABLED", False):
        try:
            refresh_ipo_cache()
            ipo_cands = build_ipo_candidates(on=on)[
                : settings.DISCOVERY_IPO_MAX_DEEP_DIVES]
        except Exception as exc:
            logger.warning("[discovery] ipo stage failed (non-fatal): %s", exc)
            errors.append(f"ipo failed: {exc}")
            ipo_cands = []

    # PR-004: shelf hygiene before any new idea. Re-dives come first in the
    # budget but never take the IPO slots.
    shelf_store = ShelfStore()
    hygiene: dict = {"not_companies": {}, "classified": [], "redive": []}
    redive_cands: list[DiscoveryCandidate] = []
    try:
        hygiene["not_companies"] = shelf_store.drop_non_companies(listing)
        hygiene["classified"] = shelf_store.backfill_classification(market_classification)
        due = shelf_store.redive_due(on)
        room = max(0, settings.DISCOVERY_DEEP_DIVE_COUNT - len(ipo_cands))
        redive_cands = [DiscoveryCandidate(symbol=i.symbol, close=0.0, composite=0.0,
                                           flags=["redive"]) for i in due[:room]]
        hygiene["redive"] = [c.symbol for c in redive_cands]
        hygiene["redive_deferred"] = [i.symbol for i in due[room:]]
    except Exception as exc:
        logger.warning("[discovery] shelf hygiene failed (non-fatal): %s", exc)
        errors.append(f"shelf hygiene failed: {exc}")
    try:
        recent = shelf_store.recently_dived(on)
    except Exception as exc:
        logger.warning("[discovery] dive memo unreadable (non-fatal): %s", exc)
        recent = set()

    screen = run_screen(on=on)          # never raises by contract

    # A candidate dived within the month and not on the shelf already has its
    # answer (below the floor, abstained, or outranked in its sector).
    new_cands = list(ipo_cands) + list(screen.candidates)
    if recent:
        hygiene["recently_dived"] = sorted({c.symbol for c in new_cands} & recent)
        new_cands = [c for c in new_cands if c.symbol not in recent]
    try:
        dives = run_deep_dives(redive_cands + new_cands, on=on)
    except Exception as exc:
        logger.warning("[discovery] deep dives failed (non-fatal): %s", exc)
        errors.append(f"deep_dives failed: {exc}")
        dives = []
    try:
        shelf_store.record_dives(dives, on=on)
    except Exception as exc:
        logger.warning("[discovery] dive memo not written (non-fatal): %s", exc)

    redived: dict = {"refreshed": [], "dropped": {}, "capped": []}
    try:
        redive_symbols = {c.symbol for c in redive_cands}
        new_dives = dives
        if redive_symbols:
            redived = shelf_store.apply_redives(
                [d for d in dives if d.symbol in redive_symbols], on=on)
            new_dives = [d for d in dives if d.symbol not in redive_symbols]
        shelf_summary = shelf_store.apply_deep_dives(new_dives, on=on)
        rotated = shelf_store.rotate_stale(on=on)
    except Exception as exc:
        logger.warning("[discovery] shelf update failed (non-fatal): %s", exc)
        errors.append(f"shelf failed: {exc}")
        shelf_summary, rotated = {"added": [], "displaced": [], "skipped": []}, []

    try:
        if shelf_summary.get("added"):
            from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
            conviction = {d.symbol: d.conviction for d in dives}
            emit_alerts_broadcast(
                # "new discovery idea" read as a recommendation; a shelf add is
                # a research candidate that is paper-traded until you promote it.
                [AlertEvent(date=on.isoformat(), kind="shelf_add", symbol=sym,
                            message=f"added to the research shelf — tracking "
                                    f"only, not a buy (conviction "
                                    f"{conviction.get(sym, 0.0):.2f})", severity="info")
                 for sym in shelf_summary["added"]],
                title=f"Discovery shelf — {on}",
            )
    except Exception as exc:
        logger.warning("[discovery] shelf alert emit failed (non-fatal): %s", exc)

    try:
        paper = run_paper_reviews(on=on)
    except Exception as exc:
        logger.warning("[discovery] paper reviews failed (non-fatal): %s", exc)
        errors.append(f"paper failed: {exc}")
        paper = {"reviewed": [], "failed": [], "skipped": []}

    result = {
        "date": on.isoformat(),
        "sync": sync,
        "universe_size": screen.universe_size,
        "candidates": len(screen.candidates),
        "ipo_candidates": len(ipo_cands),
        "dark_signals": screen.dark_signals,
        "insider_trades": {k: insider.get(k) for k in (
            "listed", "read_now", "unread", "failed", "complete")},
        "listing": listing_info,
        "hygiene": hygiene,
        "deep_dives": len(dives),
        "redived": redived,
        "shelf": shelf_summary,
        "rotated_stale": rotated,
        "paper": paper,
        "errors": errors,
    }
    logger.info("[discovery] weekly cycle complete: %s", result)
    return result
