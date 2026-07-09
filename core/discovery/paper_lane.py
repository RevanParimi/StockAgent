"""
Compass Phase B — paper-lane runner (spec §6.3).

Every active shelf idea gets a PAPER envelope (virtual position, real
forecasts) under the ISOLATED store root, and a WEEKLY paper review — the
same duel machinery that scores real holdings, minus every learning write
(run_daily_review(paper=True) hard-disables those — Task 12).

Cadence rule (spec §6.3.4): weekly, driven by the Saturday discovery job.
Envelopes self-heal at month rollover: ensure_paper_envelope() regenerates
when the current cycle's envelope is missing.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from core.config import settings
from backend.shared.schemas.discovery import ShelfIdea
from core.discovery.shelf import ShelfStore
from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.workflows.daily_review import run_daily_review
from core.intelligence.rl.workflows.generate_forecast import generate_forecast

logger = logging.getLogger(__name__)


def _last_trading_day(on: date) -> date:
    d = on
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def ensure_paper_envelope(idea: ShelfIdea) -> str:
    """Generate the current cycle's paper envelope if missing. Returns the
    cycle_id. Raises on generation failure (caller treats per-idea failures
    as non-fatal)."""
    store = PredictionStore(
        idea.symbol, sector=idea.sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR,
    )
    cycle_id = store.current_cycle_id()
    if store.load_envelope(cycle_id) is None:
        logger.info("[paper_lane] generating paper envelope for %s (%s)",
                    idea.symbol, cycle_id)
        env = generate_forecast(idea.symbol, sector=idea.sector, paper=True)
        return env.cycle_id
    return cycle_id


def run_paper_reviews(on: date) -> dict:
    """Weekly paper review of every ACTIVE shelf idea for the most recent
    trading day. Non-fatal per idea."""
    store = ShelfStore()
    shelf = store.load()
    review_date = _last_trading_day(on)

    reviewed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for idea in shelf.ideas:
        if idea.status != "active":
            continue
        if idea.last_paper_review == review_date.isoformat():
            skipped.append(idea.symbol)
            continue
        try:
            idea.paper_cycle_id = ensure_paper_envelope(idea)
            summary = run_daily_review(
                idea.symbol, review_date, sector=idea.sector, paper=True,
            )
            if summary.get("status") == "completed":
                idea.last_paper_review = review_date.isoformat()
                reviewed.append(idea.symbol)
            else:
                failed.append(idea.symbol)
        except Exception as exc:
            logger.warning("[paper_lane] paper review failed for %s (non-fatal): %s",
                           idea.symbol, exc)
            failed.append(idea.symbol)

    store.save(shelf)
    result = {"reviewed": reviewed, "failed": failed, "skipped": skipped,
              "review_date": review_date.isoformat()}
    logger.info("[paper_lane] weekly paper reviews: %s", result)
    return result
