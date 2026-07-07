"""
Compass Phase A — post-review portfolio pipeline (event-triggered).

Called by scheduler_api._review_task AFTER the daily reviews finish. Order is
load-bearing: corp-action sync runs FIRST so adj_avg_price is correct before
any advisor rule (spec §4.1 invariant). Every step is non-fatal per holding —
pipeline errors are telemetry, never training signal.
"""
from __future__ import annotations

import logging
from datetime import date

from core.config import settings
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.rl.nse_calendar import is_trading_day
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.portfolio.advisor import build_signals, decide
from core.portfolio.corp_actions import sync_corp_actions
from core.portfolio.digest import build_digest
from core.portfolio.narrator import narrate
from core.portfolio.pricing import close_on
from core.portfolio.store import PortfolioStore, list_user_ids
from services.data.fetchers.corporate_events import (
    load_events_calendar,
    refresh_events_calendar,
)

logger = logging.getLogger(__name__)


def run_post_review_pipeline(review_date: date) -> dict:
    if not settings.ADVISOR_ENABLED:
        return {"status": "disabled"}
    if not is_trading_day(review_date):
        logger.info("[portfolio_pipeline] %s is not a trading day — skipping", review_date)
        return {"status": "not_trading_day"}

    users = list_user_ids()
    total_advice, escalations = 0, []

    for user_id in users:
        store = PortfolioStore(user_id=user_id)
        # Step 1 — corp-action sync BEFORE any advisor rule (invariant).
        try:
            sync_corp_actions(store, review_date)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] corp-action sync failed for %s: %s",
                           user_id, exc)
        portfolio = store.load()
        if not portfolio.holdings:
            continue

        # Step 2 — refresh forward events for held symbols (degraded-mode safe).
        symbols = [h.symbol for h in portfolio.holdings]
        try:
            calendar = refresh_events_calendar(symbols)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] events refresh failed (using stale): %s", exc)
            calendar = load_events_calendar()

        # Step 3 — advise each holding.
        advice, closes = [], {}
        for holding in portfolio.holdings:
            try:
                close = close_on(holding.symbol, review_date)
                closes[holding.symbol] = close
                ohlcv = None
                try:
                    ohlcv = get_price_history(holding.symbol, years=1)
                except Exception as exc:
                    logger.debug("[portfolio_pipeline] OHLCV fetch failed for %s: %s",
                                 holding.symbol, exc)
                pred_store = PredictionStore(holding.symbol, sector=holding.sector)
                signals = build_signals(
                    holding, portfolio, review_date, pred_store, calendar, close,
                    ohlcv_df=ohlcv,
                )
                rec = decide(signals, holding, portfolio.risk_profile)
                rec.user_id = user_id
                rec.date = review_date.isoformat()
                rec.narrative = narrate(rec, signals)
                store.append_advice(rec)
                advice.append(rec)
            except Exception as exc:
                logger.warning(
                    "[portfolio_pipeline] advisor failed for %s/%s (non-fatal): %s",
                    user_id, holding.symbol, exc,
                )
        total_advice += len(advice)
        escalations.extend(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT"))

        # Step 4 — digest.
        try:
            store.save_digest(build_digest(user_id, review_date, advice, portfolio, closes))
        except Exception as exc:
            logger.warning("[portfolio_pipeline] digest failed for %s: %s", user_id, exc)

    logger.info(
        "[portfolio_pipeline] complete — users=%d advice=%d escalations=%s",
        len(users), total_advice, escalations,
    )
    return {
        "status": "completed",
        "users": len(users),
        "advice": total_advice,
        "escalations": escalations,
    }
