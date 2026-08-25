"""
scripts/generate_forecast.py
============================
Month-start script: run the full 5-agent analysis, then generate a 30-day
prediction envelope using learned weights if they exist.

Run manually or from a scheduler on the first trading day of each month.

Usage:
    python -m scripts.generate_forecast --ticker MARUTI
    python -m scripts.generate_forecast --ticker MARUTI TATAMOTORS M&M
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from core.config import settings
from core.intelligence.rl.workflows.sector_router import get_orchestrator, get_sector_weights
from core.schemas.feedback import (
    DailyForecast,
    LearningLedger,
    PredictionEnvelope,
    ReforecastEvent,
)
from core.schemas.pipeline import FinalReport
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.seasonal.calendar import SeasonalCalendar
from core.intelligence.prompt_enhancer.enhancer import PromptEnhancer
from core.intelligence.rl.algorithms.price_interpolator import (
    PriceInterpolator,
    ForecastProfile,
    compute_atr_pct,
    compute_historical_avg_return,
)
from services.data.fetchers.close_verifier import get_verified_close
from services.data.stores.log_store import configure_logging

# E1: one setup for every entry point. Idempotent, so importing this module
# from the API server (which has already configured) is a no-op rather than a
# second archive handler double-writing every row.
configure_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Number of trading days to forecast
HORIZON = settings.FORECAST_HORIZON_DAYS

def _trading_dates(start: date, n: int) -> list[date]:
    """Return the next n NSE trading days after start (skips weekends + NSE holidays)."""
    from core.intelligence.rl.nse_calendar import next_trading_day
    dates: list[date] = []
    current = start
    while len(dates) < n:
        current = next_trading_day(current)
        dates.append(current)
    return dates


def _fetch_actual_close(ticker: str) -> float | None:
    """Fetch the most recent closing price for day-0 baseline.

    Delegates to close_verifier.get_verified_close(), which cross-checks the
    yfinance close against NSE's official EOD close (poisoning/outage guard).
    """
    close, source = get_verified_close(ticker)
    if close is None:
        logger.warning("[generate_forecast] Could not fetch close for %s (source=%s)", ticker, source)
    elif source != "agree":
        logger.info("[generate_forecast] Base close for %s sourced from %s: %.2f", ticker, source, close)
    return close


_LESSON_CATEGORY_TO_AGENTS: dict[str, list[str]] = {
    "macro":         ["risk_macro", "policy_regulatory", "macro_policy"],
    "global_macro":  ["risk_macro", "global_macro"],
    "technical":     ["pattern_analysis", "technical"],
    "sentiment":     ["sentiment", "sentiment_policy"],
    "fundamental":   ["fundamentals"],
    # seasonal handled by SeasonalCalendar; data_availability is meta-only
}


def _apply_ledger_micro_adjustments(
    day_agent_scores: dict[str, float],
    learning_ledger: LearningLedger | None,
) -> dict[str, float]:
    """
    Apply recency-weighted lesson confidence as micro-adjustments to agent scores.

    High-confidence lessons confirmed recently → +0.01 per lesson (max ±0.05 per agent).
    This makes the forecast path aware of known patterns without overriding the LLM.
    Lessons older than 90 days or with <2 occurrences are ignored.
    """
    if not learning_ledger or not learning_ledger.lessons:
        return day_agent_scores

    from datetime import date as _date
    today = _date.today()

    agent_adj: dict[str, float] = {a: 0.0 for a in day_agent_scores}

    for lesson in learning_ledger.lessons:
        if not lesson.still_valid or lesson.occurrences < 2:
            continue
        if lesson.trigger_tags:
            # Tagged lessons fire via apply_lesson_emphasis() on matching
            # calendar/event days instead of this legacy category-based path.
            continue
        try:
            days_old = (today - _date.fromisoformat(lesson.last_seen)).days
        except Exception:
            days_old = 90
        recency = max(0.0, 1.0 - days_old / 90.0)
        eff = lesson.confidence * recency
        if eff < 0.35:
            continue

        delta = eff * 0.01  # ≤ 0.01 per lesson
        for agent in _LESSON_CATEGORY_TO_AGENTS.get(lesson.category, []):
            if agent in agent_adj:
                agent_adj[agent] += delta

    adjusted = {}
    for agent, score in day_agent_scores.items():
        adj = max(-0.05, min(0.05, agent_adj.get(agent, 0.0)))
        adjusted[agent] = round(max(0.0, min(1.0, score + adj)), 4)
    return adjusted


def _build_daily_forecasts(
    report: FinalReport,
    base_close: float,
    trading_dates: list[date],
    seasonal_calendar: SeasonalCalendar | None = None,
    learning_ledger: LearningLedger | None = None,
    forecast_profile: ForecastProfile | None = None,
    agent_predictions: dict | None = None,
    regime_label: str = "NORMAL",
) -> list[DailyForecast]:
    """
    Build per-day forecast rows from the FinalReport.

    Strategy:
    - forecast_profile (from PriceInterpolator) provides stock-specific
      monthly_return_pct, path_shape, and confidence_band.  This replaces
      the old static verdict_monthly_pct dict.
    - If forecast_profile is None (first cycle, LLM unavailable), the
      interpolator's static fallback is used — behaviour is identical to
      the old code for that case.
    - Agent scores are carried forward from the base report scores.
    - SeasonalCalendar adjustments are applied on top per day.
    """
    from core.intelligence.rl.algorithms.price_interpolator import PriceInterpolator, _STATIC_MONTHLY_PCT

    n = len(trading_dates)
    if n == 0:
        return []

    base_agent_scores = {
        name: ws.raw
        for name, ws in report.weighted_agent_scores.items()
    }
    base_confidence = min(1.0, max(0.1, report.final_score))

    # Build the LLM-calibrated price path via interpolator (Monte Carlo GBM primary)
    interpolator = PriceInterpolator()
    if forecast_profile is None:
        # Inline static fallback if caller didn't run the LLM profile step
        atr_pct = 0.0
        forecast_profile = interpolator._static_fallback(report.verdict, atr_pct)

    mc_path = interpolator.build_monte_carlo_paths(
        base_close=base_close,
        profile=forecast_profile,
        n_days=n,
        base_confidence=base_confidence,
        n_simulations=500,
        regime_label=regime_label,
    )

    forecasts: list[DailyForecast] = []

    for i, td in enumerate(trading_dates):
        day_num = i + 1
        p50, p10, p90, day_confidence = mc_path[i]
        running_close = p50
        change_pct = round((running_close - base_close) / base_close * 100, 4)

        day_agent_scores = dict(base_agent_scores)
        day_assumptions  = list(report.conviction_drivers[:3])

        # Annotate the first-day assumption with interpolator reasoning when available
        if i == 0 and forecast_profile.reasoning and forecast_profile.source == "llm":
            day_assumptions = [
                f"[Forecast calibration] {forecast_profile.reasoning[:100]}"
            ] + day_assumptions[:2]

        # Apply seasonal adjustments on top of the interpolated path
        if seasonal_calendar is not None:
            ctx = seasonal_calendar.get_context(td, learning_ledger)
            if ctx.is_seasonal_period:
                for agent, delta in ctx.agent_adjustments.items():
                    if agent in day_agent_scores:
                        adj = day_agent_scores[agent] + delta
                        day_agent_scores[agent] = round(max(0.0, min(1.0, adj)), 4)

                day_confidence = round(
                    max(0.05, min(0.99, day_confidence + ctx.confidence_modifier)), 4
                )

                if ctx.narrative and ctx.narrative not in day_assumptions:
                    day_assumptions = [f"[Seasonal] {ctx.narrative[:120]}"] + day_assumptions[:2]

                logger.debug(
                    "[generate_forecast] %s: seasonal active=%s adj=%s conf_mod=%+.3f",
                    td.isoformat(), ctx.active_pattern_ids,
                    ctx.agent_adjustments, ctx.confidence_modifier,
                )

        # Apply micro-adjustments from confirmed lessons — closes the architectural gap
        # where lessons only appear in narrative, not in actual forecast numbers.
        day_agent_scores = _apply_ledger_micro_adjustments(day_agent_scores, learning_ledger)

        # Knowledge layer: tagged-lesson emphasis on this day's calendar tags
        # (e.g. monsoon, budget_event, expiry_week). Applies ±RL_LESSON_EMPHASIS_DELTA
        # to prioritise/discount agents for still-valid lessons whose trigger_tags
        # match this row's calendar-derived tags.
        if learning_ledger is not None:
            from core.intelligence.rl.algorithms.lesson_emphasis import (
                apply_lesson_emphasis, calendar_day_tags)
            day_tags = calendar_day_tags(td)
            if day_tags:
                day_agent_scores = apply_lesson_emphasis(day_agent_scores, learning_ledger, day_tags)

        forecasts.append(DailyForecast(
            day=day_num,
            date=td.isoformat(),
            predicted_close=running_close,
            price_lower=p10,
            price_upper=p90,
            predicted_change_pct=change_pct,
            predicted_verdict=report.verdict,
            predicted_agent_scores=day_agent_scores,
            confidence=day_confidence,
            key_assumptions=day_assumptions,
            revised=False,
            revision_count=0,
            predicted_agent_catalysts=agent_predictions or {},
        ))

    return forecasts


# ---------------------------------------------------------------------------
# Shared pipeline helpers — used by both generate_forecast() (month-start)
# and regenerate_envelope() (Living Envelope mid-month re-forecast).
# ---------------------------------------------------------------------------

def _run_orchestrator_analysis(
    ticker: str,
    sector: str,
    effective_weights: dict[str, float],
) -> FinalReport:
    """
    Run the sector orchestrator fresh with the given effective weights.

    Learned weights are injected directly into SignalAggregator via the
    orchestrator's set_aggregator_weights() override, so no global config
    mutation is needed.
    """
    orchestrator = get_orchestrator(sector)
    orchestrator.set_aggregator_weights(effective_weights, ticker)
    return orchestrator.analyse(ticker)


def _compute_forecast_profile(
    ticker: str,
    sector: str,
    report: FinalReport,
    store: PredictionStore,
    as_of: date | None = None,
) -> tuple[ForecastProfile | None, str]:
    """
    Build the LLM-calibrated ForecastProfile + detect the market regime label.

    Non-fatal: returns (None, "NORMAL") if the interpolator/regime path fails,
    in which case the caller should fall back to PriceInterpolator's static
    profile (forecast_profile=None is handled by _build_daily_forecasts).

    Parameters
    ----------
    as_of : date | None
        Reference date for regime detection (default: today).
    """
    as_of = as_of or date.today()
    forecast_profile: ForecastProfile | None = None
    regime_label = "NORMAL"
    try:
        atr_pct = 0.0
        try:
            ohlcv = get_price_history(ticker, years=1)
            atr_pct = compute_atr_pct(ohlcv)
        except Exception:
            pass

        # Detect regime for the reference date (reuse RegimeDetector — cheap)
        from core.intelligence.regime.detector import RegimeDetector
        regime_label = "NORMAL"
        try:
            snap = RegimeDetector().detect(as_of, sector)
            regime_label = snap.regime_label
        except Exception:
            pass

        # Historical average return for this verdict (from prior cycles),
        # filtered to same-regime entries first (P3-13 regime-segmented returns).
        # RL Intelligence Phase, Component 3: when RL_FORGETTING_ENABLED, recent
        # cycles are weighted more heavily (compute_historical_avg_return uses a
        # weighted median over these (entry, weight) pairs).
        all_feedback_entries = store.load_recent_feedback_entries(
            n_cycles=6, recency_weighted=settings.RL_FORGETTING_ENABLED
        )
        hist_avg = compute_historical_avg_return(
            all_feedback_entries, report.verdict, regime_label=regime_label
        )

        interpolator = PriceInterpolator()
        forecast_profile = interpolator.get_profile(
            ticker=ticker,
            sector=sector,
            verdict=report.verdict,
            atr_pct=atr_pct,
            regime_label=regime_label,
            conviction_drivers=list(report.conviction_drivers or []),
            historical_avg_return_pct=hist_avg,
        )
        logger.info(
            "[generate_forecast] Forecast profile for %s (%s): "
            "monthly=%.1f%% shape=%s band=%.2f%% src=%s",
            ticker, report.verdict,
            forecast_profile.monthly_return_pct,
            forecast_profile.path_shape,
            forecast_profile.confidence_band_daily_pct,
            forecast_profile.source,
        )
    except Exception as exc:
        logger.warning(
            "[generate_forecast] PriceInterpolator failed (non-fatal, using static): %s", exc
        )

    return forecast_profile, regime_label


def _fetch_fno_snapshot(ticker: str, base_close: float, as_of: date | None = None):
    """
    G7b: Fetch F&O chain snapshot (non-fatal). Returns None on any failure.
    """
    as_of = as_of or date.today()
    try:
        from core.intelligence.fno.fetcher import FnOFetcher
        from core.intelligence.fno.analyzer import FnOAnalyzer
        fno_fetcher = FnOFetcher()
        chain_data = fno_fetcher.fetch_option_chain(ticker)
        fno_price = fno_fetcher.get_underlying_price(ticker) or base_close
        if chain_data:
            fno_snapshot = FnOAnalyzer().analyze(
                chain_data, fno_price, ticker, as_of.isoformat(),
                near_month_expiry=fno_fetcher.near_month_expiry,
            )
            logger.info(
                "[generate_forecast] F&O snapshot %s: PCR=%.2f OI=%s "
                "MaxPain=₹%.0f dev=%+.1f%%",
                ticker,
                fno_snapshot.pcr or 0,
                fno_snapshot.oi_buildup_direction,
                fno_snapshot.max_pain_price or 0,
                fno_snapshot.max_pain_deviation_pct or 0,
            )
            return fno_snapshot
    except Exception as exc:
        logger.warning(
            "[generate_forecast] F&O chain fetch failed (non-fatal): %s", exc
        )
    return None


def _extract_agent_predictions(report: FinalReport) -> dict[str, dict]:
    """Extract per-agent catalyst predictions from a FinalReport for RL learning."""
    agent_predictions: dict[str, dict] = {}
    for _name, _out in (report.agent_outputs or {}).items():
        _d = _out if isinstance(_out, dict) else (getattr(_out, '__dict__', {}) or {})
        agent_predictions[_name] = {
            "bull_case_if":    str(_d.get("bull_case_if", "")),
            "bear_case_if":    str(_d.get("bear_case_if", "")),
            "ticker_vs_peers": str(_d.get("ticker_vs_peers", "")),
            "what_changed":    str(_d.get("what_changed", "")),
            "data_confidence": float(_d.get("data_confidence", 0.5)),
        }
    return agent_predictions


def generate_forecast(
    ticker: str, sector: str = "automobile", paper: bool = False
) -> PredictionEnvelope:
    """
    Run full analysis + generate 30-day prediction envelope for one ticker.

    If a WeightMemory file exists, the orchestrator's SignalAggregator will
    use learned weights (injected via the store before calling orchestrator).

    Parameters
    ----------
    ticker : str
        NSE ticker symbol (e.g. "MARUTI").
    sector : str
        Sector graph to use (default: "automobile").
    paper : bool
        Write the envelope into the isolated paper-lane store root
        (discovery shelf ideas).
    """
    # Compass Phase B: paper-lane envelopes live under an ISOLATED store root
    # (spec §6.3) — the real RL tree never sees discovery paper artifacts.
    store = PredictionStore(
        ticker, sector=sector,
        base_dir=settings.PAPER_PREDICTION_DATA_DIR if paper else None,
    )
    cycle_id = store.current_cycle_id()

    logger.info("[generate_forecast] Starting forecast for %s | cycle=%s", ticker, cycle_id)

    # Load learned weights for this ticker (or bootstrap from config defaults)
    if paper:
        # PAPER-LANE ISOLATION: weight memory is never persisted for paper
        # ideas — get_or_init_weight_memory() would WRITE a default file into
        # the paper store (spec §6.3 check: "no *weight_memory* files under
        # the paper root"). Build the defaults in memory only.
        wm = store.load_weight_memory()
        if wm is None:
            from datetime import date as _date
            from core.schemas.feedback import WeightMemory
            base = get_sector_weights(sector)
            wm = WeightMemory(
                ticker=ticker,
                last_updated=_date.today().isoformat(),
                weight_version=0,
                current_weights=dict(base),
                base_weights=dict(base),
                adjustment_bounds={
                    "max_single_step": settings.WEIGHT_MAX_STEP,
                    "max_total_drift_from_base": settings.WEIGHT_MAX_DRIFT,
                },
            )
    else:
        wm = store.get_or_init_weight_memory(get_sector_weights(sector))
    effective_weights = wm.effective_weights()
    logger.info(
        "[generate_forecast] Using weight version v%d: %s",
        wm.weight_version,
        {k: round(v, 4) for k, v in effective_weights.items()},
    )

    # Run orchestrator — learned weights are injected directly into SignalAggregator
    # via the _aggregator.run() call inside, so no global config mutation needed.
    report = _run_orchestrator_analysis(ticker, sector, effective_weights)

    # Fetch actual baseline close — retry once on failure before raising
    base_close = _fetch_actual_close(ticker)
    if base_close is None:
        import time as _time
        logger.warning("[generate_forecast] yfinance failed for %s — retrying in 15s…", ticker)
        _time.sleep(15)
        base_close = _fetch_actual_close(ticker)
    if base_close is None:
        raise RuntimeError(
            f"[generate_forecast] Cannot fetch base_close for {ticker} after retry. "
            "yfinance may be rate-limited or NSE data unavailable. "
            "Will retry on next scheduled run."
        )
    logger.info("[generate_forecast] Base close for %s: ₹%.2f", ticker, base_close)

    # Load learning ledger for seasonal RL lesson merging (best-effort; non-fatal)
    ledger = store.load_learning_ledger()

    # P4: Generate prompt enhancements from miss_counter and cache for the cycle.
    # Each agent will load these lazily at run() time via PredictionStore.
    # Non-fatal: if ledger is empty or enhancer fails, the cycle proceeds normally.
    try:
        enhancer = PromptEnhancer()
        enhancements = enhancer.enhance(ticker, ledger, sector=sector, top_n=3)
        if enhancements:
            enhancer.save_enhancements(ticker, sector, enhancements, cycle_id, ledger)
            logger.info(
                "[generate_forecast] Prompt enhancements saved for %s cycle %s (%d agents)",
                ticker, cycle_id, len(enhancements),
            )
        else:
            logger.debug(
                "[generate_forecast] No prompt enhancements for %s (miss_counter empty or first cycle)",
                ticker,
            )
    except Exception as exc:
        logger.warning(
            "[generate_forecast] PromptEnhancer failed (non-fatal): %s", exc
        )

    # SeasonalCalendar injects pre-seeded domain knowledge per trading day.
    seasonal_calendar = SeasonalCalendar(sector=sector)

    # ------------------------------------------------------------------ #
    # LLM-calibrated forecast profile: replaces the static verdict→pct map.
    # Provides stock-specific monthly_return_pct, path_shape, confidence band.
    # Non-fatal: falls back to static values if LLM call fails.
    # ------------------------------------------------------------------ #
    forecast_profile, regime_label = _compute_forecast_profile(ticker, sector, report, store)

    # ------------------------------------------------------------------ #
    # G7b: Fetch F&O chain snapshot at month-start (non-fatal).
    # Stored in envelope; injected as market context during expiry week.
    # ------------------------------------------------------------------ #
    fno_snapshot = _fetch_fno_snapshot(ticker, base_close)

    # Extract per-agent catalyst predictions for RL learning
    _agent_predictions = _extract_agent_predictions(report)

    trading_dates = _trading_dates(date.today(), HORIZON)
    forecasts = _build_daily_forecasts(
        report, base_close, trading_dates,
        seasonal_calendar=seasonal_calendar,
        learning_ledger=ledger,
        forecast_profile=forecast_profile,
        agent_predictions=_agent_predictions,
        regime_label=regime_label,
    )

    envelope = PredictionEnvelope(
        ticker=ticker,
        sector=sector,
        cycle_id=cycle_id,
        generated_at=date.today().isoformat(),
        base_close=base_close,
        weight_version_used=wm.weight_version,
        forecast_profile_shape=forecast_profile.path_shape if forecast_profile else "linear",
        forecast_profile_monthly_pct=forecast_profile.monthly_return_pct if forecast_profile else 0.0,
        forecast_profile_source=forecast_profile.source if forecast_profile else "static",
        daily_forecasts=forecasts,
        agent_predictions=_agent_predictions,
        fno_snapshot=fno_snapshot,
    )

    store.save_envelope(envelope)
    logger.info(
        "[generate_forecast] Saved envelope for %s — %d day forecasts | verdict=%s",
        ticker, len(forecasts), report.verdict,
    )
    return envelope


# ---------------------------------------------------------------------------
# Living Envelope (RL Phase 2.5, Component 2) — mid-cycle shock re-forecast
# ---------------------------------------------------------------------------

def regenerate_envelope(
    ticker: str,
    sector: str,
    reason: str,
    trigger: str,
    review_date: date | None = None,
) -> PredictionEnvelope | None:
    """
    Fresh full-pipeline run -> new Monte Carlo paths for the REMAINING trading
    days of the CURRENT cycle only.

    Archives the superseded envelope first (via PredictionStore.archive_envelope()).
    Past days' forecasts (date <= review_date) are kept byte-identical; only
    days strictly after review_date are replaced with a fresh price path
    anchored on today's actual close.

    NEVER raises — returns None on:
      - RL_REFORECAST_ENABLED == False (no side effects)
      - no existing envelope for the current cycle
      - reforecast_count already at settings.RL_REFORECAST_MAX_PER_MONTH (no
        archive/save side effects)
      - any failure in the orchestrator/profile/MC pipeline (original
        envelope left untouched)

    Parameters
    ----------
    ticker, sector : as elsewhere
    reason  : human-readable sentence describing why this re-forecast fired
              (stored in ReforecastEvent.reason)
    trigger : short key — "external_shock" | "thesis_break" | "regime_flip"
              | "preopen_shock" | "manual" | ...
    review_date : the trading date that triggered this re-forecast (defaults
              to today). Forecast rows with date <= review_date are preserved
              unchanged; rows with date > review_date are regenerated.
    """
    if not getattr(settings, "RL_REFORECAST_ENABLED", True):
        return None

    review_date = review_date or date.today()
    review_date_str = review_date.isoformat()

    try:
        store = PredictionStore(ticker, sector=sector)
        # Cycle derived from review_date (== today in normal operation) so the
        # regenerated envelope is the one containing the shock day.
        cycle_id = store.cycle_id_for(review_date)

        envelope = store.load_envelope(cycle_id)
        if envelope is None:
            logger.info(
                "[regenerate_envelope] No envelope for %s cycle %s — skipping", ticker, cycle_id,
            )
            return None

        max_per_month = getattr(settings, "RL_REFORECAST_MAX_PER_MONTH", 2)
        if envelope.reforecast_count >= max_per_month:
            logger.warning(
                "[regenerate_envelope] %s: reforecast cap reached (%d/%d) — skipping",
                ticker, envelope.reforecast_count, max_per_month,
            )
            return None

        # Determine the remaining forecast rows (date > review_date) in the
        # CURRENT envelope. If there's nothing left to regenerate, bail out
        # without archiving/mutating anything.
        remaining_existing = [f for f in envelope.daily_forecasts if f.date > review_date_str]
        if not remaining_existing:
            logger.info(
                "[regenerate_envelope] %s: no remaining forecast days after %s — skipping",
                ticker, review_date_str,
            )
            return None

        # Archive the superseded envelope first. A None result (no envelope
        # file / write failure) is non-fatal — proceed with archived_file="".
        archived_file = store.archive_envelope(cycle_id) or ""

        # Fresh orchestrator analysis with the currently-effective weights —
        # same sector orchestrator the monthly path uses.
        wm = store.get_or_init_weight_memory(get_sector_weights(sector))
        effective_weights = wm.effective_weights()
        report = _run_orchestrator_analysis(ticker, sector, effective_weights)

        # Fresh baseline close — the new MC paths anchor on today's actual
        # close, not the month-start base_close.
        base_close = _fetch_actual_close(ticker)
        if base_close is None:
            logger.warning(
                "[regenerate_envelope] %s: could not fetch actual close — aborting "
                "(original envelope intact)", ticker,
            )
            return None

        ledger = store.load_learning_ledger()
        seasonal_calendar = SeasonalCalendar(sector=sector)

        forecast_profile, regime_label = _compute_forecast_profile(
            ticker, sector, report, store, as_of=review_date,
        )

        agent_predictions = _extract_agent_predictions(report)

        # Build new forecast rows for the remaining trading dates only — reuse
        # the exact dates from the existing envelope so the cycle's day/date
        # mapping stays consistent.
        remaining_dates = [date.fromisoformat(f.date) for f in remaining_existing]
        new_forecasts = _build_daily_forecasts(
            report, base_close, remaining_dates,
            seasonal_calendar=seasonal_calendar,
            learning_ledger=ledger,
            forecast_profile=forecast_profile,
            agent_predictions=agent_predictions,
            regime_label=regime_label,
        )

        # Re-number `day` to continue from the last preserved past day, and
        # mark these rows as already-revised (they supersede any pending
        # Step-7 revision for this run).
        past_forecasts = [f for f in envelope.daily_forecasts if f.date <= review_date_str]
        next_day = (past_forecasts[-1].day if past_forecasts else 0) + 1
        for i, fc in enumerate(new_forecasts):
            fc.day = next_day + i

        # Past days remain byte-identical; only future days are replaced.
        envelope.daily_forecasts = past_forecasts + new_forecasts
        envelope.reforecast_count += 1
        envelope.reforecast_history.append(ReforecastEvent(
            date=review_date_str,
            reason=reason,
            trigger=trigger,
            archived_file=archived_file,
        ))

        # The new forecast profile / weight version describe the regenerated
        # (future) path — refresh them so the envelope metadata matches the
        # MC paths actually used for the remaining days.
        if forecast_profile is not None:
            envelope.forecast_profile_shape = forecast_profile.path_shape
            envelope.forecast_profile_monthly_pct = forecast_profile.monthly_return_pct
            envelope.forecast_profile_source = forecast_profile.source
        envelope.weight_version_used = wm.weight_version

        store.save_envelope(envelope)
        logger.info(
            "[regenerate_envelope] %s: re-forecast complete (trigger=%s, "
            "reforecast_count=%d, %d days regenerated, archived=%s)",
            ticker, trigger, envelope.reforecast_count, len(new_forecasts),
            archived_file or "<none>",
        )
        return envelope
    except Exception as exc:
        logger.error(
            "[regenerate_envelope] %s: unhandled failure (non-fatal, original "
            "envelope intact): %s", ticker, exc,
        )
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate 30-day prediction envelope for automobile stocks."
    )
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=settings.SCHEDULER_TICKERS,
        help="One or more NSE ticker symbols (default: SCHEDULER_TICKERS from settings)",
    )
    args = parser.parse_args()

    tickers: list[str] = [t.strip().upper() for t in args.ticker]
    errors: list[str] = []

    for ticker in tickers:
        try:
            envelope = generate_forecast(ticker)
            print(
                f"[OK] {ticker} — cycle={envelope.cycle_id} | "
                f"base_close=₹{envelope.base_close:.2f} | "
                f"horizon={len(envelope.daily_forecasts)} days"
            )
        except Exception as exc:
            logger.error("[generate_forecast] Failed for %s: %s", ticker, exc)
            errors.append(ticker)
            print(f"[FAIL] {ticker} — {exc}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
