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
from services.data.verdict_store import VerdictStore  # plane boundary (Atlas C2)
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

        # Phase C context for SWITCH: active shelf ideas + sector weights.
        shelf_ideas: list = []
        try:
            from core.discovery.shelf import ShelfStore
            shelf_ideas = [i for i in ShelfStore().load().ideas if i.status == "active"]
        except Exception as exc:
            logger.debug("[portfolio_pipeline] shelf unavailable (non-fatal): %s", exc)
        sector_weights: dict[str, float] = {}
        try:
            total = sum(h.adj_qty * h.adj_avg_price for h in portfolio.holdings)
            if total > 0:
                for h in portfolio.holdings:
                    sector_weights[h.sector] = sector_weights.get(h.sector, 0.0) + (
                        h.adj_qty * h.adj_avg_price / total * 100.0
                    )
        except Exception:
            pass

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
                pred_store = VerdictStore(holding.symbol, sector=holding.sector)
                signals = build_signals(
                    holding, portfolio, review_date, pred_store, calendar, close,
                    ohlcv_df=ohlcv,
                )
                rec = decide(signals, holding, portfolio.risk_profile,
                             shelf_ideas=shelf_ideas, sector_weights=sector_weights)
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
        escalations.extend(a.symbol for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH"))

        # Step 3.5 — Compass Autopilot: execute verdicts, then snapshot equity.
        txns = []
        try:
            from core.portfolio import autopilot
            shelf_sectors = {i.symbol: i.sector for i in shelf_ideas
                             if getattr(i, "sector", "")}
            txns = autopilot.execute_advice(
                store, portfolio, advice, closes, review_date,
                sector_lookup=shelf_sectors)
            if txns:
                portfolio = store.load()          # digest sees post-trade state
                logger.info("[portfolio_pipeline] autopilot executed %d trade(s) for %s",
                            len(txns), user_id)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] autopilot failed for %s (non-fatal): %s",
                           user_id, exc)
        try:
            from core.portfolio import autopilot
            autopilot.record_value_point(store, store.load(), closes, review_date)
        except Exception as exc:
            logger.warning("[portfolio_pipeline] value point failed for %s (non-fatal): %s",
                           user_id, exc)

        # Step 3.6 — ledger ⇄ portfolio reconciliation (AUD-006, detect+alert).
        try:
            from core.portfolio.reconcile import reconcile
            rec_result = reconcile(store)
            if rec_result["status"] == "drift":
                logger.error("[portfolio_pipeline] reconciliation drift for %s: %s",
                             user_id, rec_result["issues"])
        except Exception as exc:
            logger.warning("[portfolio_pipeline] reconcile failed for %s (non-fatal): %s",
                           user_id, exc)

        # Step 4 — digest.
        try:
            store.save_digest(build_digest(user_id, review_date, advice, portfolio,
                                           closes, transactions=txns))
        except Exception as exc:
            logger.warning("[portfolio_pipeline] digest failed for %s: %s", user_id, exc)

        # Step 5 — Phase C M4: escalation alerts + digest delivery. Non-fatal.
        try:
            from core.delivery.alerts import AlertEvent, emit_alerts
            from core.delivery.channels import deliver
            events = [
                AlertEvent(
                    date=review_date.isoformat(),
                    kind=f"advisor_{a.verdict.lower()}",
                    symbol=a.symbol,
                    message=(a.narrative or a.verdict)
                    + (f" (switch → {a.switch_candidate})" if a.switch_candidate else ""),
                    severity="critical" if a.verdict in ("EXIT", "SWITCH") else "warning",
                )
                for a in advice if a.verdict in ("TRIM", "EXIT", "SWITCH")
            ]
            n_esc = len(events)
            events.extend(
                AlertEvent(
                    date=review_date.isoformat(),
                    kind="autopilot_trade",
                    symbol=t.symbol,
                    message=f"{t.side} {int(t.qty)} {t.symbol} @ ₹{t.price:,.2f}"
                            + (f" (realized ₹{t.realized_pnl:,.2f})" if t.side == "SELL" else ""),
                    severity="warning" if t.side == "SELL" else "info",
                )
                for t in txns
            )
            # SWITCH sold but the buy leg didn't land (unpriceable candidate,
            # budget < 1 share, or dedupe) — the user gets a SELL alert and
            # otherwise silence, which reads as a position vanishing into cash
            # with no explanation (spec §4).
            for a in advice:
                if a.verdict != "SWITCH" or not a.switch_candidate.strip():
                    continue
                candidate = a.switch_candidate.strip().upper()
                sold = any(t.side == "SELL" and t.symbol == a.symbol for t in txns)
                bought = any(t.side == "BUY" and t.symbol == candidate for t in txns)
                if sold and not bought:
                    events.append(AlertEvent(
                        date=review_date.isoformat(),
                        kind="switch_buy_skipped",
                        symbol=candidate,
                        message=f"SWITCH {a.symbol}→{candidate}: sold but buy leg "
                                "skipped (unpriceable or budget) — proceeds remain "
                                "in cash",
                        severity="warning",
                    ))
            if events:
                emit_alerts(events, user_id=user_id,
                            title=f"Advisor escalations — {review_date}")
            deliver(
                f"EOD digest — {review_date}",
                f"{len(advice)} holdings reviewed; {n_esc} escalation(s)"
                + (f"; {len(txns)} trade(s) executed" if txns else "")
                + ". Open the app or ask the chat for 'brief' for details.",
                url="/#/inbox/digest",
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("[portfolio_pipeline] delivery failed (non-fatal): %s", exc)

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
