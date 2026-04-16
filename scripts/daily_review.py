"""
scripts/daily_review.py
=======================
Daily cron entry point for the RL Feedback / Adaptive Prediction Loop.

Runs every trading day after market close (4:30pm IST / 11:00 UTC weekdays).

Full 8-step flow per ticker:
  1. Load prediction_envelope → today's predicted_close + assumptions
  2. Fetch actual closing price via yfinance
  3. Compute error metrics (price_error_pct, direction_correct)
  4. FeedbackAgent → miss analysis + new raw lessons
  5. WeightAdapter → adjust agent weights, save weight_memory
  6. LearningLedger → merge/deduplicate lessons
  7. Revise remaining forecasts in the envelope with updated weights
  8. Append entry to daily_feedback_log

Usage:
    python -m scripts.daily_review                        # all SCHEDULER_TICKERS
    python -m scripts.daily_review --ticker MARUTI
    python -m scripts.daily_review --ticker MARUTI --date 2026-04-09  # backfill
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from config import settings
from agents.feedback_agent import FeedbackAgent, classify_direction, is_direction_correct
from agents.orchestrator import AutomobileAgentOrchestrator
from agents.weight_adapter import WeightAdapter
from models.feedback_schemas import (
    FeedbackAgentInput,
    FeedbackEntry,
    MissAnalysis,
)
from tools.prediction_store import PredictionStore
from tools.yfinance_fetcher import get_price_history

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_actual_close(ticker: str, target_date: date) -> float | None:
    """
    Fetch the actual closing price for a specific date.
    Downloads recent history and picks the closest available date.
    """
    try:
        df = get_price_history(ticker, years=1)
        if df.empty:
            return None
        close = df["Close"].squeeze()
        # Try exact date first
        target_str = target_date.isoformat()
        if target_str in close.index.astype(str).tolist():
            return float(close[close.index.astype(str) == target_str].iloc[-1])
        # Fallback: nearest date on or before target
        available = close[close.index.date <= target_date]
        if available.empty:
            return None
        return float(available.iloc[-1])
    except Exception as exc:
        logger.warning("[daily_review] Could not fetch close for %s on %s: %s", ticker, target_date, exc)
        return None


def _run_todays_agent_scores(ticker: str, learned_weights: dict[str, float] | None = None) -> dict[str, float]:
    """
    Re-run all 5 agents with live data to get today's scores.
    Used to compute agent_score_drift vs the frozen predicted scores.
    Falls back to empty dict on failure (non-fatal).
    """
    try:
        orchestrator = AutomobileAgentOrchestrator()
        if learned_weights:
            orchestrator._aggregator_weights = learned_weights
        report = orchestrator.analyse(ticker)
        return {
            name: ws.raw
            for name, ws in report.weighted_agent_scores.items()
        }
    except Exception as exc:
        logger.warning("[daily_review] Agent re-run failed for %s: %s", ticker, exc)
        return {}


def _revise_remaining_forecasts(
    ticker: str,
    store: PredictionStore,
    reviewed_date: str,
    new_weights: dict[str, float],
    revised_context: str,
) -> None:
    """
    Update all remaining (future) forecast rows in the envelope:
    - Mark revised=True, bump revision_count
    - Re-apply the linear price path from the current predicted_close
      using the same verdict direction but with fresh confidence
    (Full re-analysis of each future day would be too expensive daily;
    the orchestrator is re-run monthly on month-start.)
    """
    envelope = store.load_envelope()
    if envelope is None:
        logger.warning("[daily_review] No envelope to revise for %s", ticker)
        return

    remaining = envelope.remaining_forecasts(reviewed_date)
    if not remaining:
        logger.info("[daily_review] No remaining forecasts to revise for %s", ticker)
        return

    for forecast in remaining:
        forecast.revised = True
        forecast.revision_count += 1
        # Inject revised context as the first assumption
        if revised_context and revised_context not in forecast.key_assumptions:
            forecast.key_assumptions = [revised_context] + forecast.key_assumptions[:2]
        # Update agent scores with new weights applied to existing raw scores
        # (simple re-weight; keeps raw scores, updates which agents matter more)
        if forecast.predicted_agent_scores and new_weights:
            weighted_sum = sum(
                forecast.predicted_agent_scores.get(a, 0.5) * w
                for a, w in new_weights.items()
            )
            weight_total = sum(new_weights.values()) or 1.0
            new_composite = round(weighted_sum / weight_total, 4)
            # Nudge confidence toward new composite (don't fully replace)
            forecast.confidence = round(
                0.7 * forecast.confidence + 0.3 * new_composite, 4
            )

    store.save_envelope(envelope)
    logger.info(
        "[daily_review] Revised %d remaining forecasts for %s",
        len(remaining), ticker,
    )


# ---------------------------------------------------------------------------
# Core review function for one ticker + one date
# ---------------------------------------------------------------------------

def run_daily_review(ticker: str, review_date: date) -> dict:
    """
    Execute the full 8-step feedback loop for one ticker on one date.

    Returns a summary dict with key metrics for the caller/logger.
    """
    store = PredictionStore(ticker)
    cycle_id = store.current_cycle_id()
    date_str = review_date.isoformat()

    logger.info(
        "[daily_review] === %s | %s | cycle=%s ===",
        ticker, date_str, cycle_id,
    )

    # ------------------------------------------------------------------ #
    # Step 1: Load envelope + find today's prediction
    # ------------------------------------------------------------------ #
    envelope = store.load_envelope(cycle_id)
    if envelope is None:
        logger.error(
            "[daily_review] No prediction envelope found for %s cycle %s. "
            "Run generate_forecast.py first.",
            ticker, cycle_id,
        )
        return {"status": "no_envelope", "ticker": ticker, "date": date_str}

    today_forecast = envelope.get_forecast(date_str)
    if today_forecast is None:
        logger.warning(
            "[daily_review] No forecast row for %s on %s (holiday or not a trading day?)",
            ticker, date_str,
        )
        return {"status": "no_forecast_row", "ticker": ticker, "date": date_str}

    # ------------------------------------------------------------------ #
    # Step 2: Fetch actual close
    # ------------------------------------------------------------------ #
    actual_close = _fetch_actual_close(ticker, review_date)
    if actual_close is None:
        logger.error("[daily_review] Could not fetch actual close for %s on %s", ticker, date_str)
        return {"status": "no_actual_data", "ticker": ticker, "date": date_str}

    # ------------------------------------------------------------------ #
    # Step 3: Compute error metrics
    # ------------------------------------------------------------------ #
    predicted_close = today_forecast.predicted_close
    price_error_pct = round(
        (actual_close - predicted_close) / predicted_close * 100, 4
    ) if predicted_close != 0 else 0.0

    actual_direction = classify_direction(actual_close, predicted_close)
    direction_correct = is_direction_correct(today_forecast.predicted_verdict, actual_direction)

    logger.info(
        "[daily_review] %s | predicted=₹%.2f actual=₹%.2f error=%.2f%% direction=%s correct=%s",
        ticker, predicted_close, actual_close,
        price_error_pct, actual_direction, direction_correct,
    )

    # ------------------------------------------------------------------ #
    # Step 4: FeedbackAgent — miss analysis + raw lessons
    # ------------------------------------------------------------------ #
    wm_for_scores = store.load_weight_memory()
    todays_agent_scores = _run_todays_agent_scores(
        ticker,
        learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
    )
    ledger = store.load_learning_ledger()

    # Fetch today's market context from the news fetcher (best-effort)
    market_context = ""
    try:
        from tools.news_fetcher import get_news_context
        market_context = get_news_context(ticker, max_articles=3)
    except Exception as exc:
        logger.debug("[daily_review] News context unavailable: %s", exc)

    fb_input = FeedbackAgentInput(
        ticker=ticker,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        direction_correct=direction_correct,
        predicted_agent_scores=today_forecast.predicted_agent_scores,
        todays_agent_scores=todays_agent_scores,
        market_context_today=market_context or "Market context unavailable.",
        key_assumptions_made=today_forecast.key_assumptions,
        active_lessons_summary=ledger.active_lessons_summary(),
    )

    fb_agent = FeedbackAgent()
    fb_output = fb_agent.run(fb_input, ledger)

    # ------------------------------------------------------------------ #
    # Step 5: WeightAdapter — adjust weights, save weight_memory
    # ------------------------------------------------------------------ #
    wm = store.get_or_init_weight_memory(settings.AGENT_WEIGHTS)  # ensures init if first run
    feedback_log = store.load_feedback_log(cycle_id)

    # Build a temporary FeedbackEntry for the window calculation
    # (the full entry is built at Step 8 after all fields are known)
    miss_analysis = None
    if not direction_correct or abs(price_error_pct) > 1.0:
        miss_analysis = MissAnalysis(
            primary_miss_agent=fb_output.primary_miss_agent,
            missed_factors=fb_output.missed_factors,
            over_weighted_factors=fb_output.over_weighted_factors,
            agent_score_drift=fb_output.agent_score_drift,
        )

    # Append a provisional entry so WeightAdapter can see today's miss
    provisional_entry = FeedbackEntry(
        day=today_forecast.day,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        miss_analysis=miss_analysis,
    )
    feedback_log.entries = [e for e in feedback_log.entries if e.date != date_str]
    feedback_log.entries.append(provisional_entry)
    feedback_log.entries.sort(key=lambda e: e.date)

    adapter = WeightAdapter()
    updated_wm = adapter.update(
        weight_memory=wm,
        feedback_log=feedback_log,
        todays_primary_miss_agent=fb_output.primary_miss_agent,
    )
    store.save_weight_memory(updated_wm)
    new_weight_version = f"v{updated_wm.weight_version}"

    # ------------------------------------------------------------------ #
    # Step 6: LearningLedger — merge lessons, save
    # ------------------------------------------------------------------ #
    updated_ledger, lesson_ids = fb_agent.merge_lessons_into_ledger(fb_output, ledger)
    store.save_learning_ledger(updated_ledger)

    # ------------------------------------------------------------------ #
    # Step 7: Revise remaining forecasts with new weights
    # ------------------------------------------------------------------ #
    _revise_remaining_forecasts(
        ticker=ticker,
        store=store,
        reviewed_date=date_str,
        new_weights=updated_wm.effective_weights(),
        revised_context=fb_output.revised_context_for_remaining_days,
    )

    # ------------------------------------------------------------------ #
    # Step 8: Append complete FeedbackEntry to daily_feedback_log
    # ------------------------------------------------------------------ #
    final_entry = FeedbackEntry(
        day=today_forecast.day,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        miss_analysis=miss_analysis,
        lessons_generated=lesson_ids,
        weight_adjustment_applied=new_weight_version,
        remaining_forecasts_revised=True,
    )
    store.append_feedback_entry(final_entry, cycle_id)

    summary = {
        "status": "completed",
        "ticker": ticker,
        "date": date_str,
        "predicted_close": predicted_close,
        "actual_close": actual_close,
        "price_error_pct": price_error_pct,
        "direction_correct": direction_correct,
        "primary_miss_agent": fb_output.primary_miss_agent,
        "lessons_added": lesson_ids,
        "weight_version": new_weight_version,
        "weights": updated_wm.effective_weights(),
    }

    logger.info(
        "[daily_review] Complete for %s | direction_correct=%s | lessons=%s | weights=%s",
        ticker, direction_correct, lesson_ids, new_weight_version,
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run daily RL feedback review for automobile stock predictions."
    )
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=settings.SCHEDULER_TICKERS,
        help="One or more NSE tickers (default: SCHEDULER_TICKERS)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date to review e.g. 2026-04-09 (default: yesterday)",
    )
    args = parser.parse_args()

    if args.date:
        review_date = date.fromisoformat(args.date)
    else:
        # Default: yesterday (market is closed; today's close is available)
        review_date = date.today() - timedelta(days=1)
        # Skip weekend
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

    tickers: list[str] = [t.strip().upper() for t in args.ticker]
    errors: list[str] = []

    for ticker in tickers:
        try:
            summary = run_daily_review(ticker, review_date)
            status = summary.get("status", "unknown")
            if status == "completed":
                print(
                    f"[OK] {ticker} {review_date} | "
                    f"error={summary['price_error_pct']:+.2f}% | "
                    f"direction={'CORRECT' if summary['direction_correct'] else 'WRONG'} | "
                    f"lessons={summary['lessons_added']} | "
                    f"weights={summary['weight_version']}"
                )
            else:
                print(f"[SKIP] {ticker} {review_date} — {status}")
        except Exception as exc:
            logger.error("[daily_review] Unhandled error for %s: %s", ticker, exc)
            errors.append(ticker)
            print(f"[FAIL] {ticker} — {exc}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
