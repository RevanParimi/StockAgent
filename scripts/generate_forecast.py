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

from config import settings
from agents.orchestrator import AutomobileAgentOrchestrator
from models.feedback_schemas import DailyForecast, PredictionEnvelope
from models.schemas import FinalReport
from tools.prediction_store import PredictionStore
from tools.yfinance_fetcher import get_price_history

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# Number of trading days to forecast
HORIZON = settings.FORECAST_HORIZON_DAYS

# Approximate trading day offsets (skip weekends simply with +1/+2 logic)
def _trading_dates(start: date, n: int) -> list[date]:
    """
    Return the next `n` weekday dates after `start` (Mon–Fri only).
    Does not account for Indian market holidays — a future enhancement.
    """
    dates: list[date] = []
    current = start
    while len(dates) < n:
        current += timedelta(days=1)
        if current.weekday() < 5:    # Mon=0, Fri=4
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
) -> list[DailyForecast]:
    """
    Build per-day forecast rows from the FinalReport.

    Strategy:
    - The final_score drives directional conviction.
    - We interpolate a linear price path based on the verdict's implied
      monthly return assumption (coarse — the LLM revises this daily).
    - Agent scores are carried forward as the starting assumption for each day.
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

    agent_scores = {
        name: ws.raw
        for name, ws in report.weighted_agent_scores.items()
    }
    confidence = min(1.0, max(0.1, report.final_score))

    forecasts: list[DailyForecast] = []
    running_close = base_close

    for i, td in enumerate(trading_dates):
        day_num = i + 1
        running_close = round(running_close * (1 + daily_pct / 100), 2)
        change_pct    = round((running_close - base_close) / base_close * 100, 4)

        # Confidence decays slightly further out (uncertainty grows)
        day_confidence = round(confidence * (1 - 0.005 * i), 4)
        day_confidence = max(0.1, day_confidence)

        forecasts.append(DailyForecast(
            day=day_num,
            date=td.isoformat(),
            predicted_close=running_close,
            predicted_change_pct=change_pct,
            predicted_verdict=report.verdict,
            predicted_agent_scores=agent_scores,
            confidence=day_confidence,
            key_assumptions=report.conviction_drivers[:3],
            revised=False,
            revision_count=0,
        ))

    return forecasts


def generate_forecast(ticker: str) -> PredictionEnvelope:
    """
    Run full analysis + generate 30-day prediction envelope for one ticker.

    If a WeightMemory file exists, the orchestrator's SignalAggregator will
    use learned weights (injected via the store before calling orchestrator).
    """
    store = PredictionStore(ticker)
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

    trading_dates = _trading_dates(date.today(), HORIZON)
    forecasts = _build_daily_forecasts(report, base_close, trading_dates)

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
