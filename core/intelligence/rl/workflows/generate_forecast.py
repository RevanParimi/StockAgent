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
from core.schemas.feedback import DailyForecast, LearningLedger, PredictionEnvelope
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

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
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
    """Fetch the most recent closing price for day-0 baseline."""
    try:
        df = get_price_history(ticker, years=1)
        if df.empty:
            return None
        close = df["Close"].squeeze()
        return float(close.iloc[-1])
    except Exception as exc:
        logger.warning("[generate_forecast] Could not fetch close for %s: %s", ticker, exc)
        return None


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


def generate_forecast(ticker: str, sector: str = "automobile") -> PredictionEnvelope:
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
    """
    store = PredictionStore(ticker, sector=sector)
    cycle_id = store.current_cycle_id()

    logger.info("[generate_forecast] Starting forecast for %s | cycle=%s", ticker, cycle_id)

    # Load learned weights for this ticker (or bootstrap from config defaults)
    wm = store.get_or_init_weight_memory(get_sector_weights(sector))
    effective_weights = wm.effective_weights()
    logger.info(
        "[generate_forecast] Using weight version v%d: %s",
        wm.weight_version,
        {k: round(v, 4) for k, v in effective_weights.items()},
    )

    # Run orchestrator — learned weights are injected directly into SignalAggregator
    # via the _aggregator.run() call inside, so no global config mutation needed.
    # We pass them through a subclass override in the orchestrator.
    orchestrator = get_orchestrator(sector)
    orchestrator._aggregator_weights = effective_weights
    report = orchestrator.analyse(ticker)

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
    forecast_profile = None
    regime_label = "NORMAL"   # default; overridden below when RegimeDetector succeeds
    try:
        atr_pct = 0.0
        try:
            ohlcv = get_price_history(ticker, years=1)
            atr_pct = compute_atr_pct(ohlcv)
        except Exception:
            pass

        # Detect regime for the current date (reuse RegimeDetector — cheap)
        from core.intelligence.regime.detector import RegimeDetector
        regime_label = "NORMAL"
        try:
            snap = RegimeDetector().detect(date.today(), sector)
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

    # ------------------------------------------------------------------ #
    # G7b: Fetch F&O chain snapshot at month-start (non-fatal).
    # Stored in envelope; injected as market context during expiry week.
    # ------------------------------------------------------------------ #
    fno_snapshot = None
    try:
        from core.intelligence.fno.fetcher import FnOFetcher
        from core.intelligence.fno.analyzer import FnOAnalyzer
        fno_fetcher = FnOFetcher()
        chain_data = fno_fetcher.fetch_option_chain(ticker)
        fno_price = fno_fetcher.get_underlying_price(ticker) or base_close
        if chain_data:
            fno_snapshot = FnOAnalyzer().analyze(
                chain_data, fno_price, ticker, date.today().isoformat(),
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
    except Exception as exc:
        logger.warning(
            "[generate_forecast] F&O chain fetch failed (non-fatal): %s", exc
        )

    # Extract per-agent catalyst predictions for RL learning
    _agent_predictions: dict[str, dict] = {}
    for _name, _out in (report.agent_outputs or {}).items():
        _d = _out if isinstance(_out, dict) else (getattr(_out, '__dict__', {}) or {})
        _agent_predictions[_name] = {
            "bull_case_if":    str(_d.get("bull_case_if", "")),
            "bear_case_if":    str(_d.get("bear_case_if", "")),
            "ticker_vs_peers": str(_d.get("ticker_vs_peers", "")),
            "what_changed":    str(_d.get("what_changed", "")),
            "data_confidence": float(_d.get("data_confidence", 0.5)),
        }

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
