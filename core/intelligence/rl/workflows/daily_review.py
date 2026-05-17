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
    ConvictionStreak,
    DailyFeedbackLog,
    FeedbackAgentInput,
    FeedbackEntry,
    MissAnalysis,
    PredictionEnvelope,
    RevisedContext,
    TimingAccuracy,
)
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.rl.stores.ledger_propagator import (
    build_tiered_lessons_summary,
    propagate_lessons,
)
from core.intelligence.rl.conviction.tracker import (
    STREAK_WARNING_THRESHOLD,
    build_streak_warning_block,
    compute_final_reversion_prior,
    update_conviction_streak,
)
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.seasonal.calendar import SeasonalCalendar
from core.intelligence.regime.detector import RegimeDetector, apply_regime_multipliers
from core.schemas.feedback import RegimeSnapshot, ThesisReview
from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer, THESIS_REVIEW_THRESHOLD

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_skip_agent_rerun(
    direction_correct: bool,
    price_error_pct: float,
    threshold: float,
) -> bool:
    """
    True when the 9-agent orchestrator re-run can be safely skipped.
    Skipping is valid when direction is correct and the error is small —
    WeightAdapter takes no meaningful action on these days anyway.
    threshold=0.0 disables the early exit.
    """
    if threshold <= 0.0:
        return False
    return direction_correct and abs(price_error_pct) < threshold


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
    reversion_prior: float = 0.0,
    updated_streak: ConvictionStreak | None = None,
    thesis_review: ThesisReview | None = None,
) -> None:
    """
    Update all remaining (future) forecast rows in the envelope:
      - Mark revised=True, bump revision_count
      - Re-weight agent score composite with new weights
      - Apply horizon_confidence_adjustment from RevisedContext
      - Inject revised_context.headline as the leading assumption
      - P3: Apply reversion_prior dampening to confidence
      - P3: Persist updated_streak to the envelope
      - Step 7: Apply thesis_review.horizon_confidence_multiplier when thesis broken
    """
    envelope = store.load_envelope()
    if envelope is None:
        logger.warning("[daily_review] No envelope to revise for %s", ticker)
        return

    remaining = envelope.remaining_forecasts(reviewed_date)
    if not remaining:
        logger.info("[daily_review] No remaining forecasts to revise for %s", ticker)
        # P3: Still persist the updated streak even when no forecasts remain.
        if updated_streak is not None:
            envelope.conviction_streak = updated_streak
            store.save_envelope(envelope)
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
            # Apply the horizon confidence adjustment from FeedbackAgent
            adjusted = round(blended + confidence_adj, 4)

            # P3: Apply mean reversion dampening when a streak is elevated.
            # Formula: adjusted × (1.0 - reversion_prior × 0.5)
            # A prior of 0.25 reduces confidence by 12.5%; 0.30 by 15%.
            if reversion_prior > 0:
                adjusted = round(adjusted * (1.0 - reversion_prior * 0.5), 4)

            # Step 7: Apply thesis multiplier when a core assumption was invalidated.
            # This is a global multiplier on ALL remaining forecasts, separate from
            # the per-day horizon_confidence_adjustment.  A broken thesis (e.g. crude
            # spike invalidated the low-input-cost assumption) deserves a deeper cut
            # than a small daily adjustment would provide.
            if thesis_review is not None and thesis_review.horizon_confidence_multiplier < 1.0:
                adjusted = round(adjusted * thesis_review.horizon_confidence_multiplier, 4)

            forecast.confidence = max(0.05, min(0.99, adjusted))

    # P3: Persist the updated conviction streak into the envelope before saving.
    if updated_streak is not None:
        envelope.conviction_streak = updated_streak

    store.save_envelope(envelope)
    logger.info(
        "[daily_review] Revised %d remaining forecasts for %s "
        "(confidence_adj=%+.3f, reversion_prior=%.3f)",
        len(remaining), ticker, confidence_adj, reversion_prior,
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
    store    = PredictionStore(ticker, sector=sector)
    cycle_id = store.current_cycle_id()
    date_str = review_date.isoformat()

    logger.info(
        "[daily_review] === %s | sector=%s | %s | cycle=%s ===",
        ticker, sector, date_str, cycle_id,
    )

    # ------------------------------------------------------------------ #
    # Step 0 (P5): Detect market regime — non-fatal, falls back to NORMAL
    # ------------------------------------------------------------------ #
    regime_snapshot: RegimeSnapshot = RegimeSnapshot()   # safe NORMAL default
    try:
        regime_snapshot = RegimeDetector().detect(review_date, sector)
        logger.info(
            "[daily_review] Regime detected: %s (VIX=%.1f, FII_proxy=%+.2f%%, RSI=%.1f)",
            regime_snapshot.regime_label,
            regime_snapshot.vix_value,
            regime_snapshot.fii_proxy_5d_pct,
            regime_snapshot.sector_rsi,
        )
    except Exception as exc:
        logger.warning(
            "[daily_review] RegimeDetector failed — using NORMAL regime (non-fatal): %s", exc
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

    # P3: Snapshot the current streak BEFORE today's update.
    # The snapshot is injected into the FeedbackAgent prompt (Step 4) and the
    # streak is then advanced using today's verdict (Step 6.5).
    existing_streak = envelope.conviction_streak

    # ------------------------------------------------------------------ #
    # Step 2: Fetch actual close + volume context
    # ------------------------------------------------------------------ #
    actual_close = _fetch_actual_close(ticker, review_date)
    if actual_close is None:
        logger.error("[daily_review] Could not fetch actual close for %s on %s", ticker, date_str)
        return {"status": "no_actual_data", "ticker": ticker, "date": date_str}

    # Volume-vs-20d-avg: tells FeedbackAgent if today's move was institutional or noise.
    volume_vs_20d_avg: float | None = None
    try:
        ohlcv = get_price_history(ticker, years=1)
        if ohlcv is not None and not ohlcv.empty and "Volume" in ohlcv.columns:
            vol_series = ohlcv["Volume"].dropna()
            today_str_for_vol = review_date.isoformat()
            today_vol_rows = vol_series[vol_series.index.astype(str) == today_str_for_vol]
            if today_vol_rows.empty:
                today_vol_rows = vol_series.iloc[-1:]
            if not today_vol_rows.empty:
                today_vol = float(today_vol_rows.iloc[-1])
                avg_20d   = float(vol_series.tail(20).mean()) if len(vol_series) >= 20 else float(vol_series.mean())
                if avg_20d > 0:
                    volume_vs_20d_avg = round(today_vol / avg_20d, 2)
    except Exception as exc:
        logger.debug("[daily_review] Volume context unavailable (non-fatal): %s", exc)

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
    wm_for_scores = store.load_weight_memory()
    _rerun_threshold = getattr(settings, "RL_AGENT_RERUN_THRESHOLD_PCT", 0.5)
    if _should_skip_agent_rerun(direction_correct, price_error_pct, _rerun_threshold):
        todays_scores = dict(today_forecast.predicted_agent_scores) if today_forecast.predicted_agent_scores else {}
        logger.info(
            "[daily_review] Early-exit: direction correct + |error| %.2f%% < %.1f%% "
            "— using predicted scores, skipping orchestrator re-run",
            abs(price_error_pct),
            _rerun_threshold,
        )
    else:
        todays_scores = _run_todays_agent_scores(
            ticker,
            sector=sector,
            learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
        )
        if not todays_scores and today_forecast.predicted_agent_scores:
            todays_scores = dict(today_forecast.predicted_agent_scores)
            logger.info(
                "[daily_review] Agent re-run unavailable for %s — "
                "using envelope predicted scores as fallback for drift analysis", ticker,
            )

    # P2: Load all three ledger tiers in one call.
    # ticker_ledger = stock-specific lessons for this ticker
    # sector_ledger = sector-wide shared lessons from all tickers in this sector
    # market_ledger = cross-sector market-wide lessons
    ticker_ledger, sector_ledger, market_ledger = store.load_all_ledgers()

    market_context = ""
    try:
        from services.data.fetchers.news import get_news_context
        market_context = get_news_context(ticker, max_articles=3)
    except Exception as exc:
        logger.debug("[daily_review] News context unavailable: %s", exc)

    # Inject seasonal context so FeedbackAgent doesn't "discover" known patterns.
    # The narrative is appended to market_context_today with a clear [SEASONAL] tag.
    seasonal_calendar = SeasonalCalendar(sector=sector)
    seasonal_ctx = seasonal_calendar.get_context(review_date, ticker_ledger)
    if seasonal_ctx.is_seasonal_period:
        seasonal_note = (
            f"\n\n[SEASONAL CONTEXT — pre-seeded domain knowledge, not from live news]\n"
            f"Active patterns: {', '.join(seasonal_ctx.active_pattern_ids)}\n"
            f"{seasonal_ctx.narrative}\n"
            f"Agent adjustments applied to this day's forecast: {seasonal_ctx.agent_adjustments}\n"
            f"Do NOT classify known seasonal patterns as new lessons — "
            f"they are already seeded and tracked separately."
        )
        market_context = (market_context or "Market context unavailable.") + seasonal_note
        logger.info(
            "[daily_review] Seasonal patterns active on %s: %s",
            date_str, seasonal_ctx.active_pattern_ids,
        )

    # P3: If the system has issued the same directional verdict for ≥ N consecutive
    # days, inject a structured warning so the FeedbackAgent explicitly checks for
    # momentum exhaustion (RSI divergence, volume dry-up, etc.).
    if existing_streak.streak_days >= STREAK_WARNING_THRESHOLD:
        streak_note = build_streak_warning_block(existing_streak)
        market_context = (market_context or "Market context unavailable.") + streak_note
        logger.info(
            "[daily_review] Conviction streak alert injected: %d days of '%s' (prior=%.2f)",
            existing_streak.streak_days,
            existing_streak.current_verdict,
            existing_streak.reversion_prior,
        )

    # P5: Inject regime narrative so FeedbackAgent is aware of current market conditions.
    if regime_snapshot.regime_label != "NORMAL":
        regime_note = (
            f"\n\n[MARKET REGIME — {regime_snapshot.regime_label}]\n"
            f"{regime_snapshot.narrative}\n"
            f"Agent weight multipliers active today: "
            + ", ".join(
                f"{k}×{v:.2f}"
                for k, v in regime_snapshot.multipliers.items()
                if v != 1.0
            )
        )
        market_context = (market_context or "Market context unavailable.") + regime_note

    # P2: Build 3-tier combined lessons summary for FeedbackAgent prompt.
    # TIER 1 (top 6): stock-specific from ticker_ledger
    # TIER 2 (top 3): sector-wide from shared sector_ledger
    # TIER 3 (top 2): market-wide from shared market_ledger
    tiered_summary = build_tiered_lessons_summary(ticker_ledger, sector_ledger, market_ledger)

    # P4: Load prompt enhancements (top missed factors from previous cycles) and
    # append them to market_context_today so FeedbackAgent is primed on recurring blindspots.
    try:
        enhancements = store.load_enhancements(store.current_cycle_id())
        if enhancements:
            lines = ["[RECURRING BLINDSPOTS — pay close attention]"]
            for agent_key, tips in enhancements.items():
                for tip in tips[:2]:     # cap at 2 per agent to stay concise
                    lines.append(f"  {agent_key}: {tip}")
            enhancement_note = "\n".join(lines)
            market_context = (market_context or "") + "\n\n" + enhancement_note
            logger.info(
                "[daily_review] P4 prompt enhancements injected (%d agents)", len(enhancements)
            )
    except Exception as exc:
        logger.debug("[daily_review] P4 enhancements unavailable: %s", exc)

    # ------------------------------------------------------------------ #
    # Assemble supplementary context for FeedbackAgentInput
    # ------------------------------------------------------------------ #

    # 1. Significant sub-score drift — agents where |composite drift| > 0.10
    SUBSCORE_DRIFT_THRESHOLD = 0.10
    significant_subscore_drift: dict = {}
    predicted_scores = today_forecast.predicted_agent_scores or {}
    for agent, today_score in todays_scores.items():
        predicted_score = predicted_scores.get(agent, today_score)
        drift = today_score - predicted_score
        if abs(drift) >= SUBSCORE_DRIFT_THRESHOLD:
            pred_sub = today_forecast.predicted_agent_subscores.get(agent, {})
            # today's sub-scores come from agent re-run (not stored separately yet — best-effort)
            if pred_sub:
                significant_subscore_drift[agent] = {
                    dim: {"predicted": val, "actual": val}  # actual sub-scores not available yet
                    for dim, val in pred_sub.items()
                }

    # 2. Weight drift summary from WeightMemory
    wm_loaded = store.load_weight_memory()
    weight_drift_str = wm_loaded.weight_drift_summary() if wm_loaded else ""

    # 3. Recent accuracy trend — 3-week rolling comparison for top agents
    def _accuracy_trend(log, agents: list[str]) -> str:
        """Build "agent: W/7 this week, X/7 last, Y/7 two weeks ago" string."""
        if not log or not log.entries:
            return ""
        lines = []
        for agent in agents[:3]:
            windows = []
            for offset in [0, 7, 14]:
                start = len(log.entries) - 7 - offset
                end   = len(log.entries) - offset
                window = log.entries[max(0, start):max(0, end)]
                if not window:
                    continue
                hits  = sum(1 for e in window if e.direction_correct)
                windows.append(f"{hits}/{len(window)}")
            if windows:
                lines.append(f"  {agent}: {' → '.join(windows)} (this week → -1wk → -2wk)")
        return "\n".join(lines)

    feedback_log_for_trend = store.load_feedback_log(cycle_id)
    # Use primary miss candidates: agents with largest drift
    top_drift_agents = sorted(
        todays_scores.keys(),
        key=lambda a: abs(todays_scores.get(a, 0) - predicted_scores.get(a, 0)),
        reverse=True,
    )[:3]
    accuracy_trend_str = _accuracy_trend(feedback_log_for_trend, top_drift_agents)

    # 4. Previous watch signals — from yesterday's FeedbackEntry
    previous_watch_signals: list[str] = []
    try:
        yesterday_entries = [
            e for e in feedback_log_for_trend.entries
            if e.date < date_str and e.revised_context
        ]
        if yesterday_entries:
            previous_watch_signals = yesterday_entries[-1].revised_context.watch_signals or []
    except Exception:
        pass

    # 5. Volume context string
    volume_context_str = ""
    if volume_vs_20d_avg is not None:
        if volume_vs_20d_avg >= 2.0:
            vol_label = "high — institutional-scale activity"
        elif volume_vs_20d_avg <= 0.5:
            vol_label = "very low — illiquid drift, not conviction"
        else:
            vol_label = "normal"
        volume_context_str = f"{volume_vs_20d_avg:.1f}× 20-day average ({vol_label})"

    # 6. Forecast profile context from envelope
    forecast_profile_str = ""
    if hasattr(envelope, "forecast_profile_shape") and envelope.forecast_profile_shape != "linear":
        forecast_profile_str = (
            f"Forecast shape: {envelope.forecast_profile_shape} "
            f"(expected monthly move: {envelope.forecast_profile_monthly_pct:+.1f}%). "
            f"{'60% of expected move anticipated in first 10 days.' if envelope.forecast_profile_shape == 'front_loaded' else ''}"
            f"{'80% of expected move anticipated in days 11-30.' if envelope.forecast_profile_shape == 'back_loaded' else ''}"
        )
    else:
        forecast_profile_str = (
            f"Linear forecast (uniform drift). "
            f"Expected monthly: {getattr(envelope, 'forecast_profile_monthly_pct', 0.0):+.1f}%."
        )

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
        active_lessons_summary=tiered_summary,
        # New context fields
        significant_subscore_drift=significant_subscore_drift,
        weight_drift_summary=weight_drift_str,
        recent_accuracy_trend=accuracy_trend_str,
        previous_watch_signals=previous_watch_signals,
        volume_context=volume_context_str,
        forecast_profile_context=forecast_profile_str,
    )

    fb_agent  = FeedbackAgent()
    fb_output = fb_agent.run(fb_input, ticker_ledger)

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
        timing_lag_days=timing.lag_days if timing and timing.lag_days is not None else 0,
        seasonal_threshold_deltas=seasonal_ctx.accuracy_threshold_delta or None,
    )
    store.save_weight_memory(updated_wm)
    new_weight_version = f"v{updated_wm.weight_version}"

    # ------------------------------------------------------------------ #
    # Step 5.5 (P5): Apply regime multipliers to effective weights.
    #
    # DESIGN DECISION — regime adjustments are intentionally ephemeral:
    #   - WeightMemory tracks LONG-TERM learned accuracy across many cycles.
    #   - Regime multipliers reflect SHORT-TERM market conditions (e.g. high VIX,
    #     FII selling pressure) that may flip within days.
    # Baking regime effects into WeightMemory would contaminate long-term weights
    # with transient noise. Instead, regime-adjusted weights are used only for
    # today's forecast revision (Step 7) and then discarded.
    # Tomorrow's daily_review loads fresh regime state and applies new multipliers.
    # ------------------------------------------------------------------ #
    try:
        regime_effective_weights = apply_regime_multipliers(
            updated_wm.effective_weights(), regime_snapshot.multipliers
        )
        logger.info(
            "[daily_review] Regime '%s' effective weights applied for %s",
            regime_snapshot.regime_label, ticker,
        )
    except Exception as exc:
        logger.warning(
            "[daily_review] Regime weight application failed (using learned weights, non-fatal): %s", exc
        )
        regime_effective_weights = updated_wm.effective_weights()

    # ------------------------------------------------------------------ #
    # Step 6: LearningLedger — merge lessons + propagate to shared ledgers
    # ------------------------------------------------------------------ #
    updated_ledger, lesson_ids = fb_agent.merge_lessons_into_ledger(fb_output, ticker_ledger)
    store.save_learning_ledger(updated_ledger)

    # P2: Route sector_wide / market_wide lessons to the shared ledgers.
    # Only lesson_ids touched in this review cycle are propagated; stale
    # lessons already in the ledger from previous cycles are left alone.
    try:
        updated_sector_ledger, updated_market_ledger = propagate_lessons(
            ticker=ticker,
            updated_ledger=updated_ledger,
            sector_ledger=sector_ledger,
            market_ledger=market_ledger,
            lesson_ids=lesson_ids,
        )
        store.save_sector_ledger(updated_sector_ledger)
        store.save_market_ledger(updated_market_ledger)
    except Exception as exc:
        logger.warning(
            "[daily_review] Shared ledger propagation failed (non-fatal): %s", exc
        )

    # ------------------------------------------------------------------ #
    # Step 6.5 (P3): Update conviction streak + compute reversion prior
    # ------------------------------------------------------------------ #
    # The streak counts consecutive days the envelope issued the same direction.
    # The reversion prior dampens remaining forecast confidence proportionally.
    # RSI divergence (pattern_analysis score contradicts verdict) amplifies 1.5×.
    updated_streak = update_conviction_streak(
        current_streak=existing_streak,
        today_verdict=today_forecast.predicted_verdict,
        today_date=date_str,
    )
    final_reversion_prior = compute_final_reversion_prior(
        streak_days=updated_streak.streak_days,
        verdict=today_forecast.predicted_verdict,
        todays_agent_scores=todays_scores,
        sector_rsi=regime_snapshot.sector_rsi,
    )
    logger.info(
        "[daily_review] Conviction streak: '%s' %d day(s) | "
        "base_prior=%.3f → final=%.3f (max_seen=%d)",
        updated_streak.current_verdict,
        updated_streak.streak_days,
        updated_streak.reversion_prior,
        final_reversion_prior,
        updated_streak.max_streak_seen,
    )

    # ------------------------------------------------------------------ #
    # Step 7a (conditional): Thesis review on significant misses.
    #
    # Fires only when the miss was large (>2%) OR the model called the
    # direction completely wrong (direction_flip / model_bias).
    #
    # Design: re-weighting alone cannot fix a broken underlying thesis.
    # If the system assumed "stable crude" but crude spiked 8%, every
    # remaining forecast is structurally wrong until re-assessed.
    # The multiplier from ThesisReviewer discounts ALL remaining forecasts
    # globally, separately from the per-day horizon_confidence_adjustment.
    # ------------------------------------------------------------------ #
    thesis_review: ThesisReview | None = None
    _reviewer = ThesisReviewer()
    if _reviewer.should_review(price_error_pct, direction_correct, fb_output.miss_type, ticker=ticker):
        try:
            thesis_review = _reviewer.review(
                ticker=ticker,
                sector=sector,
                key_assumptions=today_forecast.key_assumptions,
                fb_output=fb_output,
                market_context=market_context or "",
                price_error_pct=price_error_pct,
            )
            logger.info(
                "[daily_review] Thesis review: intact=%s multiplier=%.2f invalidated=%s",
                thesis_review.thesis_intact,
                thesis_review.horizon_confidence_multiplier,
                thesis_review.assumptions_invalidated,
            )
        except Exception as exc:
            logger.warning("[daily_review] Thesis review failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------ #
    # Step 7b: Revise remaining forecasts with regime-adjusted weights
    #         + confidence adj + P3 reversion prior dampening + persist streak
    #         + thesis multiplier (when thesis broken)
    # ------------------------------------------------------------------ #
    _revise_remaining_forecasts(
        ticker=ticker,
        store=store,
        reviewed_date=date_str,
        new_weights=regime_effective_weights,
        revised_context=fb_output.revised_context,
        reversion_prior=final_reversion_prior,
        updated_streak=updated_streak,
        thesis_review=thesis_review,
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
        regime_label=regime_snapshot.regime_label,
        volume_vs_20d_avg=volume_vs_20d_avg,
        miss_analysis=miss_analysis,
        timing=timing,
        revised_context=fb_output.revised_context,
        thesis_review=thesis_review,
        lessons_generated=lesson_ids,
        weight_adjustment_applied=new_weight_version,
    )
    store.append_feedback_entry(final_entry, cycle_id)

    # ------------------------------------------------------------------ #
    # Step 9 (P1): Seasonal validation — month-end only
    # Runs only on the last trading day of the month to avoid O(seeds×log)
    # overhead on every daily review.
    # ------------------------------------------------------------------ #
    from core.intelligence.rl.workflows.month_end_validation import (
        _is_last_trading_day_of_month,
        run_month_end_validation,
    )
    if _is_last_trading_day_of_month(review_date):
        run_month_end_validation(
            ticker=ticker,
            sector=sector,
            store=store,
            seasonal_ctx=seasonal_ctx,
            seasonal_calendar=seasonal_calendar,
            ticker_ledger=ticker_ledger,
            cycle_id=cycle_id,
            review_date=review_date,
        )

    summary = {
        "status":                   "completed",
        "ticker":                   ticker,
        "sector":                   sector,
        "date":                     date_str,
        "predicted_close":          predicted_close,
        "actual_close":             actual_close,
        "price_error_pct":          price_error_pct,
        "direction_correct":        direction_correct,
        "timing_assessment":        timing.assessment,
        "miss_type":                fb_output.miss_type,
        "primary_miss_agent":       fb_output.primary_miss_agent,
        "lessons_added":            lesson_ids,
        "weight_version":           new_weight_version,
        "weights":                  updated_wm.effective_weights(),
        "confidence_adj":           fb_output.revised_context.horizon_confidence_adjustment,
        "seasonal_patterns_active": seasonal_ctx.active_pattern_ids,
        # P3: conviction streak state
        "conviction_streak_days":   updated_streak.streak_days,
        "conviction_verdict":       updated_streak.current_verdict,
        "reversion_prior":          final_reversion_prior,
        # Step 7: thesis review state (None when miss was not significant)
        "thesis_intact":            thesis_review.thesis_intact if thesis_review else None,
        "thesis_confidence_mult":   thesis_review.horizon_confidence_multiplier if thesis_review else None,
        "thesis_invalidated":       thesis_review.assumptions_invalidated if thesis_review else [],
        # P5: regime multiplier state
        "regime_label":             regime_snapshot.regime_label,
        "regime_vix":               regime_snapshot.vix_value,
        "regime_fii_proxy_pct":     regime_snapshot.fii_proxy_5d_pct,
        "regime_sector_rsi":        regime_snapshot.sector_rsi,
        "regime_effective_weights": regime_effective_weights,
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
