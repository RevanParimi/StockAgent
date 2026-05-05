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
from core.pipeline.orchestrator import AutomobileAgentOrchestrator
from core.schemas.feedback import DailyForecast, LearningLedger, PredictionEnvelope
from core.schemas.pipeline import FinalReport
from core.intelligence.rl.stores.prediction_store import PredictionStore
from core.intelligence.algorithms.indicators.fetcher import get_price_history
from core.intelligence.seasonal.calendar import SeasonalCalendar
from core.intelligence.prompt_enhancer.enhancer import PromptEnhancer

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


def _build_daily_forecasts(
    report: FinalReport,
    base_close: float,
    trading_dates: list[date],
    seasonal_calendar: SeasonalCalendar | None = None,
    learning_ledger: LearningLedger | None = None,
) -> list[DailyForecast]:
    """
    Build per-day forecast rows from the FinalReport.

    Strategy:
    - The final_score drives directional conviction.
    - We interpolate a linear price path based on the verdict's implied
      monthly return assumption (coarse — the LLM revises this daily).
    - Agent scores are carried forward as the starting assumption for each day.
    - If a SeasonalCalendar is provided, per-day seasonal adjustments are
      applied to agent scores and confidence before saving each row.
    """
    verdict_monthly_pct = {
        "STRONG BUY":  8.0,
        "BUY":         4.0,
        "NEUTRAL":     0.5,
        "SELL":       -3.0,
        "STRONG SELL":-7.0,
    }
    monthly_pct = verdict_monthly_pct.get(report.verdict, 0.5)
    daily_pct   = monthly_pct / len(trading_dates)   # linear spread

    base_agent_scores = {
        name: ws.raw
        for name, ws in report.weighted_agent_scores.items()
    }
    base_confidence = min(1.0, max(0.1, report.final_score))

    forecasts: list[DailyForecast] = []
    running_close = base_close

    for i, td in enumerate(trading_dates):
        day_num = i + 1
        running_close = round(running_close * (1 + daily_pct / 100), 2)
        change_pct    = round((running_close - base_close) / base_close * 100, 4)

        # Confidence decays slightly further out (uncertainty grows)
        day_confidence = round(base_confidence * (1 - 0.005 * i), 4)
        day_confidence = max(0.1, day_confidence)

        # Per-day agent scores start from the base report scores
        day_agent_scores = dict(base_agent_scores)
        day_assumptions  = list(report.conviction_drivers[:3])

        # Apply seasonal adjustments if calendar is available
        if seasonal_calendar is not None:
            ctx = seasonal_calendar.get_context(td, learning_ledger)
            if ctx.is_seasonal_period:
                for agent, delta in ctx.agent_adjustments.items():
                    if agent in day_agent_scores:
                        adjusted = day_agent_scores[agent] + delta
                        day_agent_scores[agent] = round(max(0.0, min(1.0, adjusted)), 4)

                # Apply confidence modifier from seasonal context
                day_confidence = round(
                    max(0.05, min(0.99, day_confidence + ctx.confidence_modifier)), 4
                )

                # Prepend seasonal narrative to key_assumptions (one entry, no duplicates)
                if ctx.narrative and ctx.narrative not in day_assumptions:
                    day_assumptions = [f"[Seasonal] {ctx.narrative[:120]}"] + day_assumptions[:2]

                logger.debug(
                    "[generate_forecast] %s: seasonal patterns active=%s adj=%s conf_mod=%+.3f",
                    td.isoformat(), ctx.active_pattern_ids,
                    ctx.agent_adjustments, ctx.confidence_modifier,
                )

        forecasts.append(DailyForecast(
            day=day_num,
            date=td.isoformat(),
            predicted_close=running_close,
            predicted_change_pct=change_pct,
            predicted_verdict=report.verdict,
            predicted_agent_scores=day_agent_scores,
            confidence=day_confidence,
            key_assumptions=day_assumptions,
            revised=False,
            revision_count=0,
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
    wm = store.get_or_init_weight_memory(settings.AGENT_WEIGHTS)
    effective_weights = wm.effective_weights()
    logger.info(
        "[generate_forecast] Using weight version v%d: %s",
        wm.weight_version,
        {k: round(v, 4) for k, v in effective_weights.items()},
    )

    # Run orchestrator — learned weights are injected directly into SignalAggregator
    # via the _aggregator.run() call inside, so no global config mutation needed.
    # We pass them through a subclass override in the orchestrator.
    orchestrator = AutomobileAgentOrchestrator()
    orchestrator._aggregator_weights = effective_weights   # picked up in _run_aggregator
    report = orchestrator.analyse(ticker)

    # Fetch actual baseline close
    base_close = _fetch_actual_close(ticker) or report.final_score * 10000  # crude fallback
    logger.info("[generate_forecast] Base close for %s: ₹%.2f", ticker, base_close)

    # Load learning ledger for seasonal RL lesson merging (best-effort; non-fatal)
    ledger = store.load_learning_ledger()

    # P4: Generate prompt enhancements from miss_counter and cache for the cycle.
    # Each agent will load these lazily at run() time via PredictionStore.
    # Non-fatal: if ledger is empty or enhancer fails, the cycle proceeds normally.
    try:
        enhancer = PromptEnhancer()
        enhancements = enhancer.enhance(ticker, ledger, top_n=3)
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
    # Currently only automobile is fully seeded; other sectors load what's available.
    seasonal_calendar = SeasonalCalendar(sector=sector)

    trading_dates = _trading_dates(date.today(), HORIZON)
    forecasts = _build_daily_forecasts(
        report, base_close, trading_dates,
        seasonal_calendar=seasonal_calendar,
        learning_ledger=ledger,
    )

    envelope = PredictionEnvelope(
        ticker=ticker,
        cycle_id=cycle_id,
        generated_at=date.today().isoformat(),
        base_close=base_close,
        weight_version_used=wm.weight_version,
        daily_forecasts=forecasts,
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
