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
    build_streak_warning_block,
    compute_final_reversion_prior,
    update_conviction_streak,
)
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.seasonal.calendar import SeasonalCalendar
from core.intelligence.regime.detector import RegimeDetector, apply_regime_multipliers
from core.intelligence.regime.state import update_sticky_regime, _read_state, _state_path
from core.schemas.feedback import RegimeSnapshot, ThesisReview
from core.intelligence.rl.agents.thesis_reviewer import ThesisReviewer, THESIS_REVIEW_THRESHOLD
from core.intelligence.rl.workflows.generate_forecast import regenerate_envelope

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


def _resolve_cycle_and_forecast(
    store: PredictionStore,
    review_date: date,
):
    """
    Pick the (cycle_id, envelope, forecast_row) to review a date against.

    Own-month cycle first. When that envelope is missing or has no row for
    the date (early-month days before that month's forecast ran, or a
    cross-month backfill), fall back to the PREVIOUS month's envelope —
    horizons span ~6 weeks, so its rows extend into the next month.
    Either envelope or forecast may come back None — callers handle both.
    """
    cycle_id = store.cycle_id_for(review_date)
    date_str = review_date.isoformat()
    envelope = store.load_envelope(cycle_id)
    forecast = envelope.get_forecast(date_str) if envelope else None

    if forecast is None:
        prev_cycle = store.cycle_id_for(review_date.replace(day=1) - timedelta(days=1))
        prev_envelope = store.load_envelope(prev_cycle)
        prev_forecast = prev_envelope.get_forecast(date_str) if prev_envelope else None
        if prev_forecast is not None:
            logger.info(
                "[daily_review] %s: %s not in own-month envelope — using previous cycle %s",
                store.ticker, date_str, prev_cycle,
            )
            return prev_cycle, prev_envelope, prev_forecast

    return cycle_id, envelope, forecast


def _fetch_actual_close(ticker: str, target_date: date) -> float | None:
    """
    Fetch the actual closing price for a specific date via yfinance.

    Uses yf.download() with a narrow window — it refreshes the crumb automatically
    and avoids the 401 'Invalid Crumb' errors seen with .history() on long-running processes.
    Falls back to get_price_history() (C++ fetcher) if download fails.

    The resulting yfinance close is then cross-checked against NSE's official
    EOD close (close_verifier.cross_check_close) — a single extra NSE call,
    no re-fetch of yfinance — guarding against symbol-cache poisoning / stale
    yfinance data on the RL scoring path.
    """
    import yfinance as yf
    from datetime import timedelta
    from core.config import settings
    from services.data.fetchers.close_verifier import cross_check_close

    suffix = ".NS"
    yf_sym = settings.YF_SYMBOL_OVERRIDES.get(ticker.upper()) or (
        ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
    )
    # Fetch 7-day window to ensure we catch the target date even with holidays
    start = (target_date - timedelta(days=7)).isoformat()
    end   = (target_date + timedelta(days=1)).isoformat()

    def _extract(df) -> float | None:
        if df is None or df.empty:
            return None
        close = df["Close"].squeeze()
        if hasattr(close, "columns"):          # multi-level columns — take first
            close = close.iloc[:, 0]
        close = close.dropna()
        target_str = target_date.isoformat()
        mask = close.index.astype(str) == target_str
        if mask.any():
            return float(close[mask].iloc[-1])
        available = close[close.index.date <= target_date]
        return float(available.iloc[-1]) if not available.empty else None

    yf_close: float | None = None

    # Attempt 1: yf.download() — handles crumb refresh automatically
    try:
        df = yf.download(yf_sym, start=start, end=end, progress=False, auto_adjust=True)
        yf_close = _extract(df)
        if yf_close is None:
            logger.debug("[daily_review] yf.download() returned empty for %s on %s", yf_sym, target_date)
    except Exception as exc:
        logger.warning("[daily_review] yf.download() failed for %s: %s", yf_sym, exc)

    # Attempt 2: BSE fallback (.BO suffix) — Yahoo sometimes serves BSE when NSE is stale
    if yf_close is None:
        bse_sym = ticker if ticker.endswith(".BO") else f"{ticker}.BO"
        try:
            df = yf.download(bse_sym, start=start, end=end, progress=False, auto_adjust=True)
            yf_close = _extract(df)
            if yf_close is not None:
                logger.debug("[daily_review] Used .BO fallback price for %s", ticker)
        except Exception as exc:
            logger.debug("[daily_review] BSE fallback failed for %s: %s", bse_sym, exc)

    # Attempt 3: get_price_history() (C++ fetcher, 1-year window, legacy path)
    if yf_close is None:
        try:
            df = get_price_history(ticker, years=1)
            yf_close = _extract(df)
        except Exception as exc:
            logger.warning("[daily_review] get_price_history() failed for %s on %s: %s", ticker, target_date, exc)

    # NSE official-close cross-check (poisoning/outage guard) — single extra
    # NSE call on top of the yfinance close already fetched above.
    close, source = cross_check_close(ticker, yf_close, target_date=target_date)
    if close is None:
        logger.warning("[daily_review] Could not fetch actual close for %s on %s (source=%s)", ticker, target_date, source)
    elif source != "agree":
        logger.info("[daily_review] Actual close for %s on %s sourced from %s: %.2f", ticker, target_date, source, close)
    return close


def _run_todays_agent_scores(
    ticker: str,
    sector: str = "automobile",
    learned_weights: dict[str, float] | None = None,
    capture: dict | None = None,
) -> dict[str, float]:
    """
    Re-run all sub-agents with live data to compute today's scores.
    Used to measure agent_score_drift vs the frozen predicted scores.

    Routes to the correct orchestrator/graph based on sector.
    Falls back to empty dict on any failure (non-fatal).

    AUD-117: when `capture` is provided, the fresh FinalReport is stored at
    capture["report"] so the caller can reuse this single re-run's verdict for
    hard-bind grading (avoids a second orchestrator pass). Left unset on failure.
    """
    try:
        from core.intelligence.rl.workflows.sector_router import get_orchestrator
        orchestrator = get_orchestrator(sector)
        if learned_weights:
            orchestrator.set_aggregator_weights(learned_weights, ticker)
        report = orchestrator.analyse(ticker)
        if capture is not None:
            capture["report"] = report
        return {name: ws.raw for name, ws in report.weighted_agent_scores.items()}
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
    ticker_ledger=None,
    today_tags: list[str] | None = None,
    cycle_id: str | None = None,
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
      - Step 7 (knowledge layer): Apply executable-claim emphasis to
        predicted_agent_scores for tagged lessons firing on today's tags
    """
    envelope = store.load_envelope(cycle_id)
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

        # Knowledge layer: tagged-lesson emphasis on today's matching tags.
        # Applied to predicted_agent_scores BEFORE the composite re-weight below
        # so the boosted/dampened scores feed into new_composite.
        if ticker_ledger is not None and today_tags:
            from core.intelligence.rl.algorithms.lesson_emphasis import apply_lesson_emphasis
            forecast.predicted_agent_scores = apply_lesson_emphasis(
                forecast.predicted_agent_scores, ticker_ledger, today_tags)

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
    paper: bool = False,
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
        (any other sector key routes via the generic graph)
    paper : bool
        PAPER-LANE mode (Compass Phase B, spec §6.3): isolated store root;
        disables WeightAdapter writes, shared-ledger propagation, sticky-regime
        writes, re-forecasts and the control lane. Per-idea local
        ledger/feedback only.
    """
    store    = PredictionStore(
        ticker, sector=sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR if paper else None,
    )
    cycle_id = store.cycle_id_for(review_date)
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
            "[daily_review] %s: RegimeDetector failed — using NORMAL regime (non-fatal): %s",
            ticker, exc,
        )

    # ------------------------------------------------------------------ #
    # Living Envelope, Component 1: sticky regime label (hysteresis).
    #
    # The raw RegimeDetector label is ephemeral — a single calm day can flip
    # MACRO_CRISIS straight back to NORMAL. update_sticky_regime() applies
    # market-wide hysteresis (enter severe regimes immediately, exit only
    # after RL_REGIME_CALM_DAYS milder detections). The STICKY label drives
    # regime weight multipliers and the cycle-log/feedback regime field
    # below. Never fatal — falls back to the raw detected label.
    # ------------------------------------------------------------------ #
    sticky_regime_label = regime_snapshot.regime_label
    prior_sticky_label: str | None = None
    if paper:
        # PAPER-LANE ISOLATION: sticky regime state is GLOBAL
        # (data/predictions/_regime_state.json) — paper reviews read the raw
        # label and never write hysteresis state.
        pass
    else:
        try:
            prior_state = _read_state(_state_path())
            prior_sticky_label = prior_state.label if prior_state else None
            new_regime_state = update_sticky_regime(regime_snapshot.regime_label, review_date.isoformat())
            sticky_regime_label = new_regime_state.label
            if sticky_regime_label != regime_snapshot.regime_label:
                logger.info(
                    "[daily_review] Sticky regime: raw=%s sticky=%s (calm_streak=%d)",
                    regime_snapshot.regime_label, sticky_regime_label, new_regime_state.calm_streak,
                )
        except Exception as exc:
            logger.warning(
                "[daily_review] %s: sticky regime update failed — using raw label (non-fatal): %s",
                ticker, exc,
            )

    # Sticky-label-driven regime multipliers: recompute from settings using the
    # STICKY label (not the raw one) so the weight adjustment reflects the
    # persisted regime state, not a single noisy day's detection.
    sticky_regime_multipliers = settings.REGIME_MULTIPLIERS.get(
        sticky_regime_label, regime_snapshot.multipliers
    )

    # ------------------------------------------------------------------ #
    # Step 1: Load envelope + find today's prediction row
    # ------------------------------------------------------------------ #
    cycle_id, envelope, today_forecast = _resolve_cycle_and_forecast(store, review_date)

    if envelope is None:
        logger.error(
            "[daily_review] No prediction envelope for %s cycle %s. "
            "Run generate_forecast.py first.",
            ticker, cycle_id,
        )
        return {"status": "no_envelope", "ticker": ticker, "date": date_str}

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
        logger.debug(
            "[daily_review] %s: Volume context unavailable (non-fatal): %s", ticker, exc,
        )

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
    # AUD-117: the verdict direction_correct is graded against. Defaults to the
    # frozen envelope verdict (skip-rerun days + flag OFF); overridden below to
    # the fresh daily verdict when the hard-bind flag is on and a re-run exists.
    graded_verdict = today_forecast.predicted_verdict

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
    _rerun_threshold = settings.RL_AGENT_RERUN_THRESHOLD_PCT
    _early_exit_used = False
    if _should_skip_agent_rerun(direction_correct, price_error_pct, _rerun_threshold):
        todays_scores = dict(today_forecast.predicted_agent_scores) if today_forecast.predicted_agent_scores else {}
        _early_exit_used = True
        logger.info(
            "[daily_review] Early-exit: direction correct + |error| %.2f%% < %.1f%% "
            "— using predicted scores, skipping orchestrator re-run",
            abs(price_error_pct),
            _rerun_threshold,
        )
    else:
        _todays_capture: dict = {}
        todays_scores = _run_todays_agent_scores(
            ticker,
            sector=sector,
            learned_weights=wm_for_scores.effective_weights() if wm_for_scores else None,
            capture=_todays_capture,
        )
        if not todays_scores and today_forecast.predicted_agent_scores:
            todays_scores = dict(today_forecast.predicted_agent_scores)
            logger.info(
                "[daily_review] Agent re-run unavailable for %s — "
                "using envelope predicted scores as fallback for drift analysis", ticker,
            )
        # AUD-117 Binding 2: grade against the FRESH daily verdict (the threshold
        # verdict under Binding 1) from this same re-run, not the frozen
        # month-start predicted_verdict. Flag OFF or no fresh report => unchanged.
        if settings.RL_HARD_BIND_VERDICT_ENABLED:
            _fresh_report = _todays_capture.get("report")
            if _fresh_report is not None:
                graded_verdict = _fresh_report.verdict
                direction_correct = is_direction_correct(graded_verdict, actual_direction)
                logger.info(
                    "[daily_review] %s hard-bind grading: %s -> %s | direction_correct=%s",
                    ticker, today_forecast.predicted_verdict, graded_verdict, direction_correct,
                )

    # P2: Load all three ledger tiers in one call.
    # ticker_ledger = stock-specific lessons for this ticker
    # sector_ledger = sector-wide shared lessons from all tickers in this sector
    # market_ledger = cross-sector market-wide lessons
    ticker_ledger, sector_ledger, market_ledger = store.load_all_ledgers()

    market_context = ""
    # F5: did the FeedbackAgent actually see company news today? Reported in the
    # summary so the scheduler can count fetched-vs-blind per run — the baseline
    # metric for the news-query fix (2026-07-30: 12 of 16 tickers ran blind, and
    # only a WARNING line recorded it).
    news_available = False
    try:
        from services.data.fetchers.news import get_news_context
        market_context = get_news_context(ticker, max_articles=3)
        if market_context and market_context != "Market context unavailable.":
            news_available = True
            logger.info(
                "[daily_review] %s: News context fetched (%d chars, preview: %.120s)",
                ticker, len(market_context), market_context.replace("\n", " "),
            )
        else:
            logger.warning("[daily_review] %s: News context unavailable — FeedbackAgent runs without market news", ticker)
    except Exception as exc:
        logger.warning("[daily_review] %s: News context fetch failed (import/runtime error): %s", ticker, exc)

    # F2 companion metric to F5's news_available, which stays False on a rescued
    # ticker (it means "company news", and the F1 blind-rate A/B depends on that).
    # This one answers the different question the miss-taxonomy validation asks:
    # did the agent have ANY real evidence today?
    macro_fallback_used = False

    # F2: blind ticker ⇒ fall back to the market-wide macro feed rather than to
    # nothing. With no context at all the agent's own rules (cite only what is
    # in market_context_today, external_shock capped at 20% of days) funnel every
    # large unexplained move into model_bias/direction_flip — a full weight
    # penalty and a permanent lesson, both written off blindness. The macro cache
    # is already fetched 4x a day, so this costs no API calls. Labelled
    # market-wide so it can never be mistaken for company-specific evidence.
    if not news_available and settings.RL_MACRO_FALLBACK_CONTEXT_ENABLED:
        try:
            from services.background.macro_news_cache import MacroNewsCache
            macro_block = MacroNewsCache().get_for_daily_review(
                max_items=settings.RL_MACRO_FALLBACK_MAX_ITEMS,
                for_date=review_date,      # backfills must not read today's feed
            )
            if macro_block:
                macro_fallback_used = True
                market_context = (
                    (market_context or "Market context unavailable.")
                    + "\n\n[MARKET-WIDE CONTEXT — company-specific news unavailable]\n"
                    + "These are market/macro events, NOT news about this stock. "
                      "Use them only if they plausibly explain today's move.\n"
                    + macro_block
                )
                logger.info(
                    "[daily_review] %s: macro fallback context injected (%d chars)",
                    ticker, len(macro_block),
                )
        except Exception as exc:
            logger.warning(
                "[daily_review] %s: macro fallback context unavailable: %s", ticker, exc
            )

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
    if existing_streak.streak_days >= settings.RL_STREAK_WARNING_THRESHOLD:
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
        enhancements = store.load_enhancements(cycle_id)
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
        logger.debug("[daily_review] %s: P4 enhancements unavailable: %s", ticker, exc)

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # G7b: Inject F&O chain context during expiry week (non-fatal).
    # PCR and max pain help FeedbackAgent understand options-driven moves.
    # ------------------------------------------------------------------ #
    try:
        from core.intelligence.rl.nse_calendar import is_fno_expiry_week
        if is_fno_expiry_week(review_date):
            fno_envelope = store.load_envelope(cycle_id)
            if fno_envelope and fno_envelope.fno_snapshot:
                fno_ctx_str = fno_envelope.fno_snapshot.to_context_string()
                if fno_ctx_str:
                    market_context = (market_context or "") + "\n\n" + fno_ctx_str
                    logger.info(
                        "[daily_review] G7b: F&O snapshot injected for %s (expiry week): "
                        "PCR=%.2f OI=%s MaxPain=₹%.0f",
                        ticker,
                        fno_envelope.fno_snapshot.pcr or 0,
                        fno_envelope.fno_snapshot.oi_buildup_direction,
                        fno_envelope.fno_snapshot.max_pain_price or 0,
                    )
    except Exception as exc:
        logger.warning("[daily_review] %s: F&O context injection failed (non-fatal): %s", ticker, exc)

    # G4: Load previous trading day's off-market signals (non-fatal).
    # Injected into market_context before FeedbackAgent so it can
    # attribute block/bulk deals and pre-open gap to yesterday's move.
    # ------------------------------------------------------------------ #
    offmarket_context_str = ""
    try:
        from core.intelligence.rl.nse_calendar import trading_days_ago
        from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher
        yesterday = trading_days_ago(review_date, 1)
        prev_signals = store.load_offmarket_signals(yesterday.isoformat())
        if prev_signals and prev_signals.summary:
            offmarket_context_str = OffMarketFetcher.build_context_string(prev_signals)
            market_context = (market_context or "") + "\n\n" + offmarket_context_str
            logger.info(
                "[daily_review] G4: Off-market signals from %s injected for %s: %s",
                yesterday.isoformat(), ticker, prev_signals.summary,
            )
    except Exception as exc:
        logger.warning("[daily_review] %s: Off-market signal load failed (non-fatal): %s", ticker, exc)

    # ------------------------------------------------------------------ #
    # G8: Inject NSE market intelligence (FII/DII + bulk deals) — non-fatal.
    # Structured exchange data helps FeedbackAgent attribute moves to
    # institutional flows rather than guessing from news snippets.
    # ------------------------------------------------------------------ #
    try:
        from services.data.fetchers.nse_market import get_nse_market_data, format_nse_market_context
        nse_mkt = get_nse_market_data()
        if not nse_mkt.get("error"):
            nse_mkt_str = format_nse_market_context(nse_mkt, focus="all", ticker=ticker)
            if nse_mkt_str:
                market_context = (market_context or "") + "\n\n" + nse_mkt_str
                logger.info(
                    "[daily_review] G8: NSE market intelligence injected for %s: "
                    "FII=%s Cr / DII=%s Cr",
                    ticker, nse_mkt.get("fii_net_cr"), nse_mkt.get("dii_net_cr"),
                )
    except Exception as exc:
        logger.warning(
            "[daily_review] %s: NSE market intelligence injection failed (non-fatal): %s",
            ticker, exc,
        )

    # ------------------------------------------------------------------ #
    # Static event tags for today — deterministic, LLM-independent. Used by
    # Step-7 claim matching and persisted on the FeedbackEntry.
    # ------------------------------------------------------------------ #
    from backend.shared.schemas.feedback import tag_events
    from core.intelligence.rl.algorithms.lesson_emphasis import calendar_day_tags
    today_tags = sorted(set(tag_events(market_context or ""))
                         | set(calendar_day_tags(review_date)))

    # ------------------------------------------------------------------ #
    # Assemble supplementary context for FeedbackAgentInput
    # ------------------------------------------------------------------ #

    # If early-exit was used, todays_scores == predicted_agent_scores (identical).
    # Inject a system note so FeedbackAgent knows not to infer zero drift from them.
    if _early_exit_used:
        market_context = (market_context or "") + (
            "\n\n[SYSTEM NOTE — FROZEN AGENT SCORES]\n"
            "The agent re-run was skipped today (direction correct + error below threshold). "
            "The 'Today\\'s re-run composite scores' shown below are IDENTICAL to the predicted "
            "scores — do NOT interpret them as evidence of zero agent drift. "
            "Focus your analysis on market_context_today and existing lessons."
        )

    # 1. Significant sub-score drift — agents where |composite drift| > 0.10
    # Suppressed on early-exit days (scores are frozen, drift would be artifically zero).
    # predicted_scores is also used below (top_drift_agents) regardless of
    # early-exit, so it must be defined unconditionally (pre-existing bug fix).
    SUBSCORE_DRIFT_THRESHOLD = 0.10
    significant_subscore_drift: dict = {}
    predicted_scores = today_forecast.predicted_agent_scores or {}
    if not _early_exit_used:
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
    except Exception as exc:
        logger.debug(
            "[daily_review] %s: Could not load previous watch signals (non-fatal): %s",
            ticker, exc,
        )

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

    # Pull catalyst predictions from the forecast envelope for this day
    _predicted_catalysts: dict = {}
    if today_forecast and hasattr(today_forecast, "predicted_agent_catalysts"):
        _predicted_catalysts = today_forecast.predicted_agent_catalysts or {}
    elif envelope and hasattr(envelope, "agent_predictions"):
        _predicted_catalysts = envelope.agent_predictions or {}

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
        predicted_catalysts_by_agent=_predicted_catalysts,
    )

    fb_agent  = FeedbackAgent()
    fb_output = fb_agent.run(fb_input, ticker_ledger)

    # Hoisted from below (Step 5) so the external_shock rate-cap block can use
    # it: at this point today's provisional entry has not been appended yet,
    # so feedback_log.entries already holds only prior-cycle entries. The same
    # object is reused (not reloaded) at the Step 5 site below.
    feedback_log = store.load_feedback_log(cycle_id)

    # ------------------------------------------------------------------ #
    # external_shock rate cap: LLMs tend to over-use external_shock to
    # avoid assigning blame, effectively disabling learning.  If more than
    # 20% of penalizable days in this cycle are already classified as
    # external_shock, override this one to direction_flip.
    # Only applies when direction was wrong — correct-direction external_shock
    # is semantically valid (e.g. sudden gap-down on correct UP prediction).
    # ------------------------------------------------------------------ #
    if fb_output.miss_type == "external_shock" and not direction_correct:
        prior_entries = feedback_log.entries  # today's provisional not yet appended
        if len(prior_entries) >= 5:
            shock_days = sum(
                1 for e in prior_entries
                if e.miss_analysis and e.miss_analysis.miss_type == "external_shock"
            )
            if shock_days / len(prior_entries) > 0.20:
                logger.warning(
                    "[daily_review] %s: external_shock rate %d/%d=%.0f%% exceeds 20%% cap "
                    "— overriding to direction_flip to enforce model accountability",
                    ticker, shock_days, len(prior_entries),
                    shock_days / len(prior_entries) * 100,
                )
                from dataclasses import replace as _replace
                fb_output = fb_output.model_copy(update={"miss_type": "direction_flip"})

    # ------------------------------------------------------------------ #
    # Absurd price-error guard: a broken INPUT is not a forecast miss.
    #
    # TATAMOTORS 2026-06-01..06-11 reviewed predicted ~5920 against actual
    # ~380 — a stale pre-split envelope ramping +0.99/day. All nine rows were
    # classified `magnitude` with direction_correct=True, so a corporate-action
    # fault trained the weights at 0.25x and polluted agent_accuracy.avg_error
    # for nine sessions before the envelope was regenerated on 06-12.
    #
    # No model predicts 15x wrong. Past the threshold, record the row as
    # `data_stale` (a NO_PENALTY miss type) and skip the weight update, so the
    # garbage never reaches the learned state. Deliberately placed after the
    # external_shock cap so the reclassification is the LAST word on miss_type.
    # ------------------------------------------------------------------ #
    absurd_error = False
    _absurd_threshold = getattr(settings, "RL_ABSURD_PRICE_ERROR_PCT", 50.0)
    if abs(price_error_pct) > _absurd_threshold:
        absurd_error = True
        logger.error(
            "[daily_review] %s: |price_error|=%.2f%% exceeds the %.1f%% absurd "
            "threshold — predicted=%.4f actual=%.4f. Treating as data_stale and "
            "SKIPPING the weight update; this is a stale envelope or a bad "
            "fetch, not a model miss.",
            ticker, abs(price_error_pct), _absurd_threshold,
            predicted_close, actual_close,
        )
        fb_output = fb_output.model_copy(update={"miss_type": "data_stale"})

    # ------------------------------------------------------------------ #
    # Step 5: WeightAdapter — adjust weights (miss_type-aware), save
    #
    # Pre-load IIMA factor regime for regime-aware penalty scaling.
    # Non-fatal: missing regime falls back to standard 1.0× scaling.
    # ------------------------------------------------------------------ #
    _factor_regime_data: dict | None = None
    try:
        from core.intelligence.rl.algorithms.factor_regime import get_factor_regime
        _factor_regime_data = get_factor_regime()
        if _factor_regime_data:
            logger.debug(
                "[daily_review] Factor regime loaded: %s %s (WML avg=%.3f%%)",
                _factor_regime_data.get("strength"), _factor_regime_data.get("regime"),
                _factor_regime_data.get("avg_wml_pct", 0),
            )
    except Exception as exc:
        logger.debug("[daily_review] %s: Factor regime unavailable (non-fatal): %s", ticker, exc)

    if paper:
        # PAPER-LANE ISOLATION: weight memory is never persisted for paper
        # ideas — get_or_init_weight_memory() would WRITE a fresh file into
        # the store on first review. Load if present, else build the config
        # default in memory only.
        wm = store.load_weight_memory()
        if wm is None:
            from core.schemas.feedback import WeightMemory
            wm = WeightMemory(
                ticker=ticker,
                last_updated=date.today().isoformat(),
                weight_version=0,
                current_weights=dict(settings.AGENT_WEIGHTS),
                base_weights=dict(settings.AGENT_WEIGHTS),
                adjustment_bounds={
                    "max_single_step": settings.WEIGHT_MAX_STEP,
                    "max_total_drift_from_base": settings.WEIGHT_MAX_DRIFT,
                },
            )
    else:
        wm = store.get_or_init_weight_memory(settings.AGENT_WEIGHTS)
    # feedback_log was loaded above (before the external_shock rate-cap block);
    # reuse the same object here rather than reloading.

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
        graded_verdict=graded_verdict,
        miss_analysis=miss_analysis,
        timing=timing,
        predicted_agent_scores=today_forecast.predicted_agent_scores,
        event_tags=today_tags,
    )
    feedback_log.entries = [e for e in feedback_log.entries if e.date != date_str]
    feedback_log.entries.append(provisional)
    feedback_log.entries.sort(key=lambda e: e.date)

    if paper or absurd_error:
        # PAPER-LANE ISOLATION: no weight training on paper ideas — junk
        # discovery names must never move learned weights (spec §6.3).
        # absurd_error: the row describes a broken input, not model behaviour —
        # training on it is what let the TATAMOTORS split corrupt nine sessions.
        updated_wm = wm
        new_weight_version = f"v{wm.weight_version}"
    else:
        adapter    = WeightAdapter()
        updated_wm = adapter.update(
            weight_memory=wm,
            feedback_log=feedback_log,
            todays_primary_miss_agent=fb_output.primary_miss_agent,
            todays_miss_type=fb_output.miss_type,
            timing_lag_days=timing.lag_days if timing and timing.lag_days is not None else 0,
            seasonal_threshold_deltas=seasonal_ctx.accuracy_threshold_delta or None,
            factor_regime=_factor_regime_data,
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
            updated_wm.effective_weights(), sticky_regime_multipliers, sector=sector
        )
        logger.info(
            "[daily_review] Regime '%s' effective weights applied for %s",
            sticky_regime_label, ticker,
        )
    except Exception as exc:
        logger.warning(
            "[daily_review] %s: Regime weight application failed (using learned weights, non-fatal): %s",
            ticker, exc,
        )
        regime_effective_weights = updated_wm.effective_weights()

    # ------------------------------------------------------------------ #
    # Step 6: LearningLedger — merge lessons + propagate to shared ledgers
    # ------------------------------------------------------------------ #
    updated_ledger, lesson_ids = fb_agent.merge_lessons_into_ledger(
        fb_output, ticker_ledger, cold_store_path=store._archived_lessons_path(),
        # F3: the same context the agent reasoned over, so each lesson records the
        # dated headlines behind it instead of only its conclusion.
        market_context=market_context,
    )
    store.save_learning_ledger(updated_ledger)

    # P2: Route sector_wide / market_wide lessons to the shared ledgers.
    # Only lesson_ids touched in this review cycle are propagated; stale
    # lessons already in the ledger from previous cycles are left alone.
    if paper:
        logger.debug("[daily_review] %s: paper lane — shared-ledger propagation skipped", ticker)
    else:
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
                "[daily_review] %s: Shared ledger propagation failed (non-fatal): %s",
                ticker, exc,
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
            logger.warning(
                "[daily_review] %s: Thesis review failed (non-fatal): %s", ticker, exc,
            )

    # ------------------------------------------------------------------ #
    # Living Envelope, Component 2: shock-triggered re-forecast.
    #
    # Checked in this order — first match wins (recorded as `trigger`):
    #   external_shock : FeedbackAgent miss_type == "external_shock" AND
    #                     direction wrong, AFTER the 20% rate-cap override
    #                     above (i.e. the classification survived the cap).
    #   thesis_break   : ThesisReviewer ran (Step 7a) and its
    #                     horizon_confidence_multiplier <=
    #                     RL_REFORECAST_THESIS_MULT_THRESHOLD.
    #   regime_flip    : sticky regime TRANSITIONED into MACRO_CRISIS today
    #                     (prior sticky label != MACRO_CRISIS, new == MACRO_CRISIS).
    #
    # On a successful regenerate_envelope(), Step 7b's confidence-only
    # revision is SKIPPED for this run — the fresh envelope already
    # supersedes it. On None (flag off / cap reached / pipeline failure),
    # Step 7b proceeds exactly as before. Wrapped so a failure here never
    # blocks the rest of the review.
    # ------------------------------------------------------------------ #
    reforecast_envelope: PredictionEnvelope | None = None
    reforecast_trigger: str | None = None
    # Re-forecasts only make sense for the live cycle: regenerate_envelope()
    # always rewrites the CURRENT month's envelope, so a shock seen while
    # replaying a historical date (cross-month backfill) must not fire it.
    _is_live_cycle = cycle_id == store.current_cycle_id()
    if getattr(settings, "RL_REFORECAST_ENABLED", True) and _is_live_cycle and not paper:
        try:
            thesis_mult_threshold = getattr(settings, "RL_REFORECAST_THESIS_MULT_THRESHOLD", 0.5)

            if fb_output.miss_type == "external_shock" and not direction_correct:
                reforecast_trigger = "external_shock"
                reforecast_reason = (
                    f"External shock on {date_str}: actual direction "
                    f"({actual_direction}) diverged from predicted verdict "
                    f"({today_forecast.predicted_verdict}); FeedbackAgent "
                    f"classified the miss as external_shock."
                )
            elif thesis_review is not None and thesis_review.horizon_confidence_multiplier <= thesis_mult_threshold:
                reforecast_trigger = "thesis_break"
                reforecast_reason = (
                    f"Thesis break on {date_str}: horizon_confidence_multiplier="
                    f"{thesis_review.horizon_confidence_multiplier:.2f} <= "
                    f"{thesis_mult_threshold:.2f}. Invalidated assumptions: "
                    f"{', '.join(thesis_review.assumptions_invalidated) or 'n/a'}."
                )
            elif (
                prior_sticky_label is not None
                and prior_sticky_label != "MACRO_CRISIS"
                and sticky_regime_label == "MACRO_CRISIS"
            ):
                reforecast_trigger = "regime_flip"
                reforecast_reason = (
                    f"Regime flip on {date_str}: sticky market regime entered "
                    f"MACRO_CRISIS (was {prior_sticky_label})."
                )

            if reforecast_trigger is not None:
                reforecast_envelope = regenerate_envelope(
                    ticker=ticker,
                    sector=sector,
                    reason=reforecast_reason,
                    trigger=reforecast_trigger,
                    review_date=review_date,
                )
                if reforecast_envelope is not None:
                    # Step 7b (skipped below) normally persists the updated
                    # conviction streak into the envelope. Carry that over
                    # onto the freshly-regenerated envelope so streak state
                    # isn't lost on a re-forecast day.
                    try:
                        reforecast_envelope.conviction_streak = updated_streak
                        store.save_envelope(reforecast_envelope)
                    except Exception as exc:
                        logger.warning(
                            "[daily_review] %s: failed to persist conviction "
                            "streak onto regenerated envelope (non-fatal): %s",
                            ticker, exc,
                        )
                    logger.info(
                        "[daily_review] %s: re-forecast triggered (%s) — "
                        "envelope regenerated (reforecast_count=%d); "
                        "Step 7 confidence revision skipped for %s",
                        ticker, reforecast_trigger,
                        reforecast_envelope.reforecast_count, date_str,
                    )
                else:
                    logger.info(
                        "[daily_review] %s: re-forecast trigger '%s' fired but "
                        "regenerate_envelope() returned None (cap/flag/failure) "
                        "— proceeding with Step 7 as usual",
                        ticker, reforecast_trigger,
                    )
        except Exception as exc:
            logger.warning(
                "[daily_review] %s: re-forecast trigger block failed (non-fatal): %s",
                ticker, exc,
            )

    # ------------------------------------------------------------------ #
    # Step 7b: Revise remaining forecasts with regime-adjusted weights
    #         + confidence adj + P3 reversion prior dampening + persist streak
    #         + thesis multiplier (when thesis broken)
    #
    # Skipped when a Living Envelope re-forecast already succeeded above —
    # the fresh envelope supersedes confidence-only nudging of the dead one.
    # ------------------------------------------------------------------ #
    if reforecast_envelope is None:
        _revise_remaining_forecasts(
            ticker=ticker,
            store=store,
            reviewed_date=date_str,
            new_weights=regime_effective_weights,
            revised_context=fb_output.revised_context,
            reversion_prior=final_reversion_prior,
            updated_streak=updated_streak,
            thesis_review=thesis_review,
            ticker_ledger=updated_ledger,
            today_tags=today_tags,
            cycle_id=cycle_id,
        )

    # ------------------------------------------------------------------ #
    # Step 8: Append complete FeedbackEntry to daily_feedback_log
    # ------------------------------------------------------------------ #
    # Knowledge layer: audit which lessons' claims fired today, using the
    # post-merge ledger (updated_ledger) consistent with Step-7 emphasis.
    # Empty list when claims are disabled or there is no ledger/tags.
    claims_fired: list[str] = []
    if getattr(settings, "RL_CLAIMS_ENABLED", True) and updated_ledger and today_tags:
        from core.intelligence.rl.algorithms.lesson_emphasis import matching_lessons
        claims_fired = [l.lesson_id for l in matching_lessons(updated_ledger, today_tags)]

    final_entry = FeedbackEntry(
        day=today_forecast.day,
        date=date_str,
        predicted_close=predicted_close,
        actual_close=actual_close,
        price_error_pct=price_error_pct,
        predicted_verdict=today_forecast.predicted_verdict,
        actual_direction=actual_direction,
        direction_correct=direction_correct,
        graded_verdict=graded_verdict,
        regime_label=sticky_regime_label,
        event_tags=today_tags,
        claims_fired=claims_fired,
        volume_vs_20d_avg=volume_vs_20d_avg,
        miss_analysis=miss_analysis,
        timing=timing,
        revised_context=fb_output.revised_context,
        thesis_review=thesis_review,
        lessons_generated=lesson_ids,
        weight_adjustment_applied=new_weight_version,
        predicted_catalysts_snapshot=_predicted_catalysts,
        offmarket_context=offmarket_context_str,
        predicted_agent_scores=today_forecast.predicted_agent_scores,
    )
    store.append_feedback_entry(final_entry, cycle_id)

    # ------------------------------------------------------------------ #
    # Step 8.5: Dossier curator — runs EVERY day (hit or miss), never fatal.
    # Extracts durable knowledge from today's review into the per-ticker
    # TickerDossier. Failure here must never block Step 9 below.
    # ------------------------------------------------------------------ #
    if getattr(settings, "RL_DOSSIER_ENABLED", True):
        try:
            from backend.shared.schemas.dossier import TickerDossier
            from core.intelligence.rl.agents.dossier_curator import DossierCurator
            dossier = store.load_dossier() or TickerDossier(
                ticker=ticker, sector=sector,
                created_at=final_entry.date, last_updated=final_entry.date)
            updated_dossier = DossierCurator().run(
                dossier, final_entry, market_context or "", fb_output)
            store.save_dossier(updated_dossier)
            logger.info(
                "[daily_review] Step 8.5 dossier updated for %s (%d observations)",
                ticker, len(updated_dossier.observations),
            )
        except Exception as exc:
            logger.warning(
                "[daily_review] %s: Step 8.5 dossier curator failed (non-fatal): %s",
                ticker, exc,
            )

    # ------------------------------------------------------------------ #
    # G4: Fetch today's off-market signals after market close (non-fatal).
    # Saves to store for injection into tomorrow's daily_review.
    # ------------------------------------------------------------------ #
    try:
        from core.intelligence.rl.stores.offmarket_fetcher import OffMarketFetcher
        today_signals = OffMarketFetcher().fetch_all(ticker, date_str)
        store.save_offmarket_signals(today_signals)
        if today_signals.summary:
            logger.info(
                "[daily_review] G4: Off-market signals saved for %s on %s: %s",
                ticker, date_str, today_signals.summary,
            )
        else:
            logger.debug(
                "[daily_review] G4: No off-market signals found for %s on %s", ticker, date_str
            )
    except Exception as exc:
        logger.warning("[daily_review] %s: Off-market signal fetch failed (non-fatal): %s", ticker, exc)

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

    # ------------------------------------------------------------------ #
    # Step 10: Control lane (the "duel") — score yesterday's prediction and
    # make tomorrow's, using a bare LLM with the same close + market_context
    # StockAgent had at this moment. Flag-gated, never fatal.
    # ------------------------------------------------------------------ #
    if not paper and getattr(settings, "RL_CONTROL_LANE_ENABLED", True):
        try:
            from core.intelligence.rl.agents.control_lane import run_control_lane_step
            run_control_lane_step(
                store, ticker, sector, review_date,
                actual_close=actual_close,
                actual_direction=final_entry.actual_direction,
                market_context=market_context or "",
            )
        except Exception as exc:
            logger.warning(
                "[daily_review] %s: Step 10 control lane failed (non-fatal): %s",
                ticker, exc,
            )

    # Switch validation (design 2026-08-20): persist news_available per
    # (symbol, date). It was only ever aggregated into one scheduler log line,
    # so "was this call made blind?" could not be answered afterwards — which
    # silently attributed every such miss to the model's reasoning. Paper-lane
    # reviews are excluded: they run on an isolated store against symbols
    # nobody holds, and mixing them in would corrupt the real index.
    if not paper:
        try:
            from core.audit.evidence import record_news_availability
            record_news_availability(ticker, review_date, news_available,
                                     macro_fallback_used)
        except Exception as exc:
            logger.debug("[daily_review] news-availability record failed "
                         "(non-fatal): %s", exc)

    summary = {
        "status":                   "completed",
        "ticker":                   ticker,
        "sector":                   sector,
        "paper":                    paper,
        "date":                     date_str,
        "predicted_close":          predicted_close,
        "actual_close":             actual_close,
        "price_error_pct":          price_error_pct,
        "direction_correct":        direction_correct,
        "timing_assessment":        timing.assessment,
        # F5: sensing telemetry — False means this review's attribution was made
        # without company news (see the news fetch block above).
        "news_available":           news_available,
        # F2: True when company news was missing but market-wide macro context
        # was injected instead — a blind review that still had real evidence.
        "macro_fallback_used":      macro_fallback_used,
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
        "regime_label":             sticky_regime_label,
        "regime_label_raw":         regime_snapshot.regime_label,
        "regime_vix":               regime_snapshot.vix_value,
        "regime_fii_proxy_pct":     regime_snapshot.fii_proxy_5d_pct,
        "regime_sector_rsi":        regime_snapshot.sector_rsi,
        "regime_effective_weights": regime_effective_weights,
        # Living Envelope, Component 2: re-forecast trigger/outcome for this run.
        "reforecast_trigger":       reforecast_trigger,
        "reforecast_fired":         reforecast_envelope is not None,
        "reforecast_count":         reforecast_envelope.reforecast_count if reforecast_envelope else None,
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
        help="Sector graph to use (native: automobile | banking_bfsi | it_sector | "
             "renewable_energy; any other sector key routes via the generic graph)",
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
            logger.error(
                "[daily_review] Unhandled error for %s: %s", ticker, exc, exc_info=True,
            )
            errors.append(ticker)
            print(f"[FAIL] {ticker} — {exc}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
