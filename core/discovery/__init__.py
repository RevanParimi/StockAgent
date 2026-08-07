"""
Compass Phase B — Discovery Engine (spec §6): weekly funnel orchestration.

run_discovery_cycle() is the single entry point used by BOTH the Saturday
scheduler job and POST /discovery/run. Every stage is individually
non-fatal: a dark data feed degrades the screen, it never kills the cycle.
"""
from __future__ import annotations

import logging
from datetime import date

# Re-exported collaborators — tests and callers patch these names HERE.
from core.discovery.deep_dive import run_deep_dives
from core.discovery.paper_lane import run_paper_reviews
from core.discovery.screen import load_latest_screen, run_screen
from core.discovery.shelf import ShelfStore
from services.data.fetchers.bhavcopy import sync_recent
from services.data.fetchers.bulk_block import refresh_bulk_block
from core.config import settings
from core.discovery.ipo_tracker import build_ipo_candidates, upcoming_lockin_alerts
from services.data.fetchers.ipo import refresh_ipo_cache

logger = logging.getLogger(__name__)

__all__ = [
    "run_discovery_cycle", "run_deep_dives", "run_paper_reviews",
    "run_screen", "load_latest_screen", "ShelfStore",
    "sync_recent", "refresh_bulk_block",
    "refresh_ipo_cache", "build_ipo_candidates", "upcoming_lockin_alerts",
    "settings",
]


def run_discovery_cycle(on: date | None = None) -> dict:
    """sync EOD -> refresh bulk/block -> ipo tracker -> screen -> deep-dives -> shelf ->
    weekly paper reviews. Returns a stage-by-stage summary; never raises."""
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

    screen = run_screen(on=on)          # never raises by contract

    try:
        dives = run_deep_dives(ipo_cands + screen.candidates, on=on)
    except Exception as exc:
        logger.warning("[discovery] deep dives failed (non-fatal): %s", exc)
        errors.append(f"deep_dives failed: {exc}")
        dives = []

    shelf_store = ShelfStore()
    try:
        shelf_summary = shelf_store.apply_deep_dives(dives, on=on)
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
        "deep_dives": len(dives),
        "shelf": shelf_summary,
        "rotated_stale": rotated,
        "paper": paper,
        "errors": errors,
    }
    logger.info("[discovery] weekly cycle complete: %s", result)
    return result
