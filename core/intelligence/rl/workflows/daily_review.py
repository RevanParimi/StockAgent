"""
scripts/daily_review.py
=======================
Daily cron entry point for the RL Feedback / Adaptive Prediction Loop.

Runs every trading day after market close (4:30pm IST / 11:00 UTC weekdays).
Applies to all sectors: automobile · banking_bfsi · it_sector · renewable_energy

Full 8-step flow per ticker:
  1. Load prediction_envelope → today's predicted_close + assumptions
  2. Fetch actual closing price via yfinance
  3. Compute error metrics (price_error_pct, direction_correct)
  4. FeedbackAgent → miss_type + miss analysis + new raw lessons
  5. WeightAdapter → adjust agent weights (miss_type-aware), save weight_memory
  6. LearningLedger → merge/deduplicate lessons with scope and last_seen
  7. Revise remaining forecasts with new weights + horizon_confidence_adjustment
  8. Append complete entry (with timing + revised_context) to daily_feedback_log

Usage:
    python -m scripts.daily_review                              # all SCHEDULER_TICKERS (automobile)
    python -m scripts.daily_review --ticker MARUTI
    python -m scripts.daily_review --sector banking_bfsi --ticker HDFCBANK SBIN
    python -m scripts.daily_review --ticker MARUTI --date 2026-04-09   # backfill
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from datetime import date, timedelta

from core.config import settings
from core.intelligence.rl.agents.feedback_agent import (
    FeedbackAgent,
    classify_direction,
    is_direction_correct,
)
from core.intelligence.rl.agents.weight_adapter import WeightAdapter
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackAgentInput,
    FeedbackEntry,
    MissAnalysis,
    PredictionEnvelope,
    RevisedContext,
    TimingAccuracy,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.algorithms.indicators.fetcher import get_price_history

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_actual_close(ticker: str, target_date: date) -> float | None:
    """Fetch the actual closing price for a specific date via yfinance."""
    try:
        df = get_price_history(ticker, years=1)
        if df.empty:
            return None
        close = df["Close"].squeeze()
        target_str = target_date.isoformat()
        if target_str in close.index.astype(str).tolist():
            return float(close[close.index.astype(str) == target_str].iloc[-1])
        available = close[close.index.date <= target_date]
        if available.empty:
            return None
        return float(available.iloc[-1])
    except Exception as exc:
        logger.warning("[daily_review] Could not fetch close for %s on %s: %s", ticker, target_date, exc)
        return None


def _run_todays_agent_scores(
    ticker: str,
    sector: str = "automobile",
    learned_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Re-run all sub-agents with live data to compute today's scores.
    Used to measure agent_score_drift vs the frozen predicted scores.

    Routes to the correct orchestrator/graph based on sector.
    Falls back to empty dict on any failure (non-fatal).
    """
    try:
        if sector == "automobile":
            from core.pipeline.orchestrator import AutomobileAgentOrchestrator
            orchestrator = AutomobileAgentOrchestrator()
            if learned_weights:
                orchestrator._aggregator_weights = learned_weights
            report = orchestrator.analyse(ticker)
            return {name: ws.raw for name, ws in report.weighted_agent_scores.items()}

        # Other sectors: invoke their LangGraph graph
        # Graph module path follows the pattern: graphs.{sector}.graph
        sector_module = importlib.import_module(f"graphs.{sector}.graph")
        graph = getattr(sector_module, "graph")
        state = graph.invoke({"ticker": ticker})
        agent_outputs = state.get("agent_outputs", {})
        return {
            name: out.overall_score
            for name, out in agent_outputs.items()
            if hasattr(out, "overall_score")
        }

    except Exception as exc:
        logger.warning(
            "[daily_review] Agent re-run failed for %s (%s): %s", ticker, sector, exc
        )
        return {}


def _compute_timing_accuracy(
    envelope: PredictionEnvelope,
    today_forecast,
    actual_direction: str,
) -> TimingAccuracy:
    """
    Estimate whether the predicted price move arrived on time, early, or late.

    For BUY/STRONG BUY verdicts the predicted peak is the day with the highest
    predicted_close in the full envelope. For SELL/STRONG SELL it's the lowest.
    The lag is today's day number minus that predicted peak day.
    """
    verdict = today_forecast.predicted_verdict.upper()
    bullish = verdict in {"BUY", "STRONG BUY"}
    bearish = verdict in {"SELL", "STRONG SELL"}

    if not (bullish or bearish):
        return TimingAccuracy(assessment="no_move")

    if bullish:
        peak_forecast = max(envelope.daily_forecasts, key=lambda f: f.predicted_close)
    else:
        peak_forecast = min(envelope.daily_forecasts, key=lambda f: f.predicted_close)

    predicted_peak_day  = peak_forecast.day
    actual_move_day     = today_forecast.day
    lag_days            = actual_move_day - predicted_peak_day

    # If direction doesn't match verdict at all, mark as no_move for timing
    if (bullish and actual_direction != "UP") or (bearish and actual_direction != "DOWN"):
        return TimingAccuracy(
            predicted_peak_day=predicted_peak_day,
            actual_move_start_day=actual_move_day,
            lag_days=lag_days,
            assessment="no_move",
        )

    if abs(lag_days) <= 1:
        assessment = "on_time"
    elif lag_days < -1:
        assessment = "early"   # stock moved before we expected the peak
    else:
        assessment = "late"    # stock moved after the predicted peak day

    return TimingAccuracy(
        predicted_peak_day=predicted_peak_day,
        actual_move_start_day=actual_move_day,
        lag_days=lag_days,
        assessment=assessment,
    )


def _revise_remaining_forecasts(
    ticker: str,
    store: PredictionStore,
    reviewed_date: str,
    new_weights: dict[str, float],
    revised_context: RevisedContext,
) -> None:
    """
    Update all remaining (future) forecast rows in the envelope:
      - Mark revised=True, bump revision_count
      - Re-weight agent score composite with new weights
      - Apply horizon_confidence_adjustment from RevisedContext
      - Inject revised_context.headline as the leading assumption
    """
    envelope = store.load_envelope()
    if envelope is None:
        logger.warning("[daily_review] No envelope to revise for %s", ticker)
        return

    remaining = envelope.remaining_forecasts(reviewed_date)
    if not remaining:
        logger.info("[daily_review] No remaining forecasts to revise for %s", ticker)
        return

    confidence_adj = revised_context.horizon_confidence_adjustment
    headline       = revised_context.headline

    for forecast in remaining:
        forecast.revised        = True
        forecast.revision_count += 1

        # Inject revised headline as leading assumption (avoid duplicates)
        if headline and headline not in forecast.key_assumptions:
            forecast.key_assumptions = [headline] + forecast.key_assumptions[:2]

        # Re-weight the composite score using updated agent weights
        if forecast.predicted_agent_scores and new_weights:
            weighted_sum = sum(
                forecast.predicted_agent_scores.get(a, 0.5) * w
                for a, w in new_weights.items()
            )
            weight_total = sum(new_weights.values()) or 1.0
            new_composite = round(weighted_sum / weight_total, 4)
            # Blend old confidence with new composite (don't fully replace)
            blended = round(0.7 * forecast.confidence + 0.3 * new_composite, 4)
            # Then apply the horizon confidence adjustment from FeedbackAgent
            adjusted = round(blended + confidence_adj, 4)
            forecast.confidence = max(0.05, min(0.99, adjusted))

    store.save_envelope(envelope)
    logger.info(
        "[daily_review] Revised %d remaining forecasts for %s (confidence_adj=%+.3f)",
        len(remaining), ticker, confidence_adj,
    )


# ---------------------------------------------------------------------------
# Core review function for one ticker + one date
# ---------------------------------------------------------------------------

def run_daily_review(
    ticker: str,
    review_date: date,
    sector: str = "automobile",
) -> dict:
    """
    Execute the full 8-step feedback loop for one ticker on one date.

    Parameters
    ----------
    ticker : str
        NSE ticker symbol (e.g. "MARUTI", "HDFCBANK", "TCS")
    review_date : date
        The trading date being reviewed (typically yesterday)
    sector : str
        Sector graph to use: automobile | banking_bfsi | it_sector | renewable_energy
    """
    store    = PredictionStore(ticker)
    cycle_id = store.current_cycle_id()
    date_str = review_date.isoformat()

    logger.info(
        "[daily_review] === %s | sector=%s | %s | cycle=%s ===",
        ticker, sector, date_str, cycle_id,
    )

    # ------------------------------------------------------------------ #
    # Step 1: Load envelope + find today's prediction row
    # ------------------------------------------------------------------ #
    envelope = store.load_envelope(cycle_id)
    if envelope is None:
        logger.error(
            "[daily_review] No prediction envelope for %s cycle %s. "
            "Run generate_forecast.py first.",
            ticker, cycle_id,
        )
        return {"status": "no_envelope", "ticker": ticker, "date": date_str}

    today_forecast = envelope.get_forecast(date_str)
    if today_forecast is None:
        logger.warning(
            "[daily_review] No forecast row for %s on %s (holiday or non-trading day?)",
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
    # Step 3: Compute error metrics + timing
    # ------------------------------------------------------------------ #
    predicted_close = today_forecast.predicted_close
    price_error_pct = (
        round((actual_close - predicted_close) / predicted_close * 100, 4)
        if predicted_close != 0 else 0.0
    )

    actual_direction = classify_direction(actual_close, predicted_close)
    direction_correct = is_direction_correct(today_forecast.predicted_verdict, actual_direction)

    timing = _compute_timing_accuracy(envelope, today_forecast, actual_direction)

    logger.info(
        "[daily_review] %s | predicted=%.2f actual=%.2f error=%+.2f%% "
        "direction=%s correct=%s timing=%s",
        ticker, predicted_close, actual_close,
        price_error_pct, actual_direction, direction_correct, timing.assessment,
    )

    # ------------------------------------------------------------------ #
    # Step 4: FeedbackAgent — miss_type + miss analysis + raw lessons
    # ------------------------------------------------------------------ #
    wm_for_scores   = store.load_weight_memory()
    todays_scores   = _run_todays_agent_scores(
        ticker,
        sector=sector,
        learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
    )
    ledger = store.load_learning_ledger()

    market_context = ""
    try:
        from services.data.fetchers.news import get_news_context
        market_context = get_news_context(ticker, max_articles=3)
    except Exception as exc:
        logger.debug("[daily_review] News context unavailable: %s", exc)

    fb_input = FeedbackAgentInput(
        ticker=ticker,
        sector=sector,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        direction_correct=direction_correct,
        predicted_agent_scores=today_forecast.predicted_agent_scores,
        todays_agent_scores=todays_scores,
        market_context_today=market_context or "Market context unavailable.",
        key_assumptions_made=today_forecast.key_assumptions,
        active_lessons_summary=ledger.active_lessons_summary(),
    )

    fb_agent  = FeedbackAgent()
    fb_output = fb_agent.run(fb_input, ledger)

    # ------------------------------------------------------------------ #
    # Step 5: WeightAdapter — adjust weights (miss_type-aware), save
    # ------------------------------------------------------------------ #
    wm           = store.get_or_init_weight_memory(settings.AGENT_WEIGHTS)
    feedback_log = store.load_feedback_log(cycle_id)

    miss_analysis = None
    if not direction_correct or abs(price_error_pct) > 1.0:
        miss_analysis = MissAnalysis(
            primary_miss_agent=fb_output.primary_miss_agent,
            miss_type=fb_output.miss_type,
            missed_factors=fb_output.missed_factors,
            over_weighted_factors=fb_output.over_weighted_factors,
            agent_score_drift=fb_output.agent_score_drift,
        )

    # Provisional entry so WeightAdapter can see today's miss in its window
    provisional = FeedbackEntry(
        day=today_forecast.day,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        miss_analysis=miss_analysis,
        timing=timing,
    )
    feedback_log.entries = [e for e in feedback_log.entries if e.date != date_str]
    feedback_log.entries.append(provisional)
    feedback_log.entries.sort(key=lambda e: e.date)

    adapter    = WeightAdapter()
    updated_wm = adapter.update(
        weight_memory=wm,
        feedback_log=feedback_log,
        todays_primary_miss_agent=fb_output.primary_miss_agent,
        todays_miss_type=fb_output.miss_type,
    )
    store.save_weight_memory(updated_wm)
    new_weight_version = f"v{updated_wm.weight_version}"

    # ------------------------------------------------------------------ #
    # Step 6: LearningLedger — merge lessons (with scope + last_seen)
    # ------------------------------------------------------------------ #
    updated_ledger, lesson_ids = fb_agent.merge_lessons_into_ledger(fb_output, ledger)
    store.save_learning_ledger(updated_ledger)

    # ------------------------------------------------------------------ #
    # Step 7: Revise remaining forecasts with new weights + confidence adj
    # ------------------------------------------------------------------ #
    _revise_remaining_forecasts(
        ticker=ticker,
        store=store,
        reviewed_date=date_str,
        new_weights=updated_wm.effective_weights(),
        revised_context=fb_output.revised_context,
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
        timing=timing,
        revised_context=fb_output.revised_context,
        lessons_generated=lesson_ids,
        weight_adjustment_applied=new_weight_version,
        remaining_forecasts_revised=True,
    )
    store.append_feedback_entry(final_entry, cycle_id)

    summary = {
        "status":              "completed",
        "ticker":              ticker,
        "sector":              sector,
        "date":                date_str,
        "predicted_close":     predicted_close,
        "actual_close":        actual_close,
        "price_error_pct":     price_error_pct,
        "direction_correct":   direction_correct,
        "timing_assessment":   timing.assessment,
        "miss_type":           fb_output.miss_type,
        "primary_miss_agent":  fb_output.primary_miss_agent,
        "lessons_added":       lesson_ids,
        "weight_version":      new_weight_version,
        "weights":             updated_wm.effective_weights(),
        "confidence_adj":      fb_output.revised_context.horizon_confidence_adjustment,
    }

    logger.info(
        "[daily_review] Complete — %s | correct=%s | miss_type=%s | timing=%s | "
        "lessons=%s | weights=%s | conf_adj=%+.3f",
        ticker, direction_correct, fb_output.miss_type, timing.assessment,
        lesson_ids, new_weight_version,
        fb_output.revised_context.horizon_confidence_adjustment,
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run daily RL feedback review for any sector's stock predictions."
    )
    parser.add_argument(
        "--sector",
        default="automobile",
        choices=["automobile", "banking_bfsi", "it_sector", "renewable_energy"],
        help="Sector graph to use (default: automobile)",
    )
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=settings.SCHEDULER_TICKERS,
        help="One or more NSE tickers (default: SCHEDULER_TICKERS from .env)",
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
        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

    tickers: list[str] = [t.strip().upper() for t in args.ticker]
    errors:  list[str] = []

    for ticker in tickers:
        try:
            summary = run_daily_review(ticker, review_date, sector=args.sector)
            status  = summary.get("status", "unknown")
            if status == "completed":
                print(
                    f"[OK] {ticker} {review_date} | sector={args.sector} | "
                    f"error={summary['price_error_pct']:+.2f}% | "
                    f"direction={'CORRECT' if summary['direction_correct'] else 'WRONG'} | "
                    f"miss_type={summary['miss_type']} | "
                    f"timing={summary['timing_assessment']} | "
                    f"lessons={summary['lessons_added']} | "
                    f"weights={summary['weight_version']} | "
                    f"conf_adj={summary['confidence_adj']:+.3f}"
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
