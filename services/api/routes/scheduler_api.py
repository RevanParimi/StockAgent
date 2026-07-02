"""
services/api/routes/scheduler_api.py
=====================================
HTTP triggers and status monitor for the RL scheduler.

Endpoints
---------
POST /scheduler/forecast              Generate monthly prediction envelopes
POST /scheduler/daily-review          Run daily RL feedback review for a date
POST /scheduler/backfill              Run daily reviews for every past trading day this month
GET  /scheduler/status                Full RL state per configured ticker

Authentication
--------------
Set SCHEDULER_KEY in your environment. Pass it as header: X-Scheduler-Key: <value>
If SCHEDULER_KEY is not set, requests are allowed but a warning is logged.

Design
------
All POST endpoints return 202 immediately and run the work as a background task.
The actual work (9-agent analysis + RL loops) takes 1-2 min per ticker.
Use GET /scheduler/status to monitor progress.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

_SECTOR = "automobile"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing X-Scheduler-Key header.",
        )
    if not required:
        logger.warning(
            "[scheduler_api] SCHEDULER_KEY not set — endpoint is open. "
            "Add it to your Railway Variables to restrict access."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_trading_day() -> date:
    """Most recent weekday before today (skips weekends; not NSE-holiday-aware for simplicity)."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _trading_days_for_backfill(month: str | None = None) -> list[date]:
    """
    Trading days to backfill, capped at yesterday. NSE-holiday-aware.

    month=None      → 1st of the current month … yesterday (original behavior)
    month="2026-06" → every trading day of that month (… yesterday if current)
    """
    from core.intelligence.rl.nse_calendar import is_trading_day
    today     = date.today()
    yesterday = today - timedelta(days=1)
    if month:
        year_s, month_s = month.split("-")
        start = date(int(year_s), int(month_s), 1)
        end   = min(_last_day_of_month(start), yesterday)
    else:
        start = today.replace(day=1)
        end   = yesterday
    days = []
    d = start
    while d <= end:
        if is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def _last_day_of_month(any_day: date) -> date:
    next_month_first = (any_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month_first - timedelta(days=1)


def _resolve_tickers(ticker_param: str | None) -> list[str]:
    from core.config import settings
    return [ticker_param.strip().upper()] if ticker_param else list(settings.SCHEDULER_TICKERS)


# ---------------------------------------------------------------------------
# Background task implementations  (sync → run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _run_forecasts(tickers: list[str]) -> list[dict]:
    """Generate prediction envelopes for each ticker. Sync, heavy (9-agent pipeline)."""
    from core.intelligence.rl.workflows.generate_forecast import generate_forecast
    results = []
    for ticker in tickers:
        try:
            env = generate_forecast(ticker)
            result = {
                "ticker":           ticker,
                "status":           "ok",
                "cycle_id":         env.cycle_id,
                "horizon_days":     len(env.daily_forecasts),
                "base_close":       round(env.base_close, 2),
                "weight_version":   env.weight_version_used,
            }
            logger.info(
                "[scheduler_api] Forecast OK: %s cycle=%s horizon=%dd base=₹%.2f",
                ticker, env.cycle_id, len(env.daily_forecasts), env.base_close,
            )
        except Exception as exc:
            result = {"ticker": ticker, "status": "error", "detail": str(exc)}
            logger.error("[scheduler_api] Forecast FAILED for %s: %s", ticker, exc, exc_info=True)
        results.append(result)
    return results


def _run_reviews(tickers: list[str], dates: list[date]) -> list[dict]:
    """Run daily_review for each (ticker, date) pair. Sync."""
    from core.intelligence.rl.workflows.daily_review import run_daily_review
    results = []
    for review_date in dates:
        for ticker in tickers:
            try:
                summary = run_daily_review(ticker, review_date)
                status  = summary.get("status", "unknown")
                logger.info(
                    "[scheduler_api] Review %s %s — status=%s direction=%s lessons=%s",
                    ticker, review_date, status,
                    summary.get("direction_correct"), summary.get("lessons_added"),
                )
                results.append({"ticker": ticker, "date": review_date.isoformat(), **summary})
            except Exception as exc:
                logger.error(
                    "[scheduler_api] Review FAILED %s %s: %s", ticker, review_date, exc, exc_info=True
                )
                results.append({
                    "ticker": ticker, "date": review_date.isoformat(),
                    "status": "error", "detail": str(exc),
                })
    return results


# Async wrappers for BackgroundTasks
async def _forecast_task(tickers: list[str]) -> None:
    results = await asyncio.to_thread(_run_forecasts, tickers)
    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info("[scheduler_api] Forecast task complete: %d/%d ok", ok, len(results))


async def _review_task(tickers: list[str], dates: list[date]) -> None:
    results = await asyncio.to_thread(_run_reviews, tickers, dates)
    completed = sum(1 for r in results if r.get("status") == "completed")
    logger.info(
        "[scheduler_api] Review task complete: %d completed across %d ticker-date pairs",
        completed, len(results),
    )


# ---------------------------------------------------------------------------
# POST /scheduler/forecast
# ---------------------------------------------------------------------------

@router.post(
    "/forecast",
    status_code=202,
    summary="Generate monthly prediction envelopes (runs full 9-agent analysis per ticker)",
)
async def trigger_forecast(
    background_tasks: BackgroundTasks,
    ticker: str | None = Query(default=None, description="NSE ticker. Omit for all SCHEDULER_TICKERS."),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    """
    Kick off envelope generation in the background. Returns 202 immediately.

    What it does per ticker:
      1. Runs the full 9-agent pipeline (same as clicking Analyze in the UI)
      2. Saves a 30-day PredictionEnvelope with predicted close, agent scores, confidence per day
      3. Initialises WeightMemory if this is the first run ever

    Takes ~2 min per ticker. Monitor progress with GET /scheduler/status.
    Must run before any daily reviews can execute.
    """
    _check_auth(x_scheduler_key)
    tickers = _resolve_tickers(ticker)
    background_tasks.add_task(_forecast_task, tickers)
    return {
        "status":   "accepted",
        "message":  f"Forecast generation started for {tickers}. Takes ~2 min per ticker.",
        "tickers":  tickers,
        "monitor":  "/scheduler/status",
    }


# ---------------------------------------------------------------------------
# POST /scheduler/daily-review
# ---------------------------------------------------------------------------

@router.post(
    "/daily-review",
    status_code=202,
    summary="Run daily RL feedback review for a specific trading date",
)
async def trigger_daily_review(
    background_tasks: BackgroundTasks,
    ticker: str | None = Query(default=None, description="NSE ticker. Omit for all SCHEDULER_TICKERS."),
    review_date: str | None = Query(
        default=None,
        description="ISO date to review e.g. 2026-05-02. Default: last trading day.",
    ),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    """
    Kick off the 8-step daily RL feedback loop for one date in the background.

    What it does per ticker per date:
      1. Compares actual closing price to the predicted value in the envelope
      2. FeedbackAgent classifies the miss type and generates lessons
      3. WeightAdapter adjusts agent weights and saves WeightMemory v(N+1)
      4. Lessons are merged into the LearningLedger and propagated to sector/market ledgers
      5. Remaining forecasts in the envelope are revised with new weights

    Requires envelope to exist — run POST /scheduler/forecast first.
    Returns immediately. Monitor with GET /scheduler/status.
    """
    _check_auth(x_scheduler_key)
    tickers = _resolve_tickers(ticker)

    if review_date:
        try:
            target = date.fromisoformat(review_date)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date '{review_date}'. Use ISO format: YYYY-MM-DD.",
            )
    else:
        target = _last_trading_day()

    background_tasks.add_task(_review_task, tickers, [target])
    return {
        "status":       "accepted",
        "message":      f"Daily review started for {tickers} on {target}.",
        "tickers":      tickers,
        "review_date":  target.isoformat(),
        "monitor":      "/scheduler/status",
    }


# ---------------------------------------------------------------------------
# POST /scheduler/backfill
# ---------------------------------------------------------------------------

@router.post(
    "/backfill",
    status_code=202,
    summary="Run daily reviews for every past trading day in the current month",
)
async def trigger_backfill(
    background_tasks: BackgroundTasks,
    ticker: str | None = Query(default=None, description="NSE ticker. Omit for all SCHEDULER_TICKERS."),
    month: str | None = Query(default=None, description="YYYY-MM. Backfill that month instead of the current one (reviews run against that month's envelope)."),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    """
    Catch up the RL feedback loop from the start of this month up to yesterday.

    Run this once after POST /scheduler/forecast to give the RL system its
    first set of real feedback entries and kick off weight learning.

    Example: today is May 15. Backfill runs reviews for May 1, 2, 5, 6, 7, 8, 9, 12, 13, 14.
    Days with no envelope forecast row (NSE holidays) are silently skipped.

    Pass ?month=YYYY-MM to recover a PAST month (e.g. after a dead scheduler):
    reviews load that month's envelope and land in that month's feedback log.
    """
    _check_auth(x_scheduler_key)
    tickers = _resolve_tickers(ticker)
    try:
        trading_days = _trading_days_for_backfill(month)
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail=f"Invalid month {month!r} — expected YYYY-MM.")

    if not trading_days:
        return {
            "status":  "skipped",
            "message": "No past trading days found in the requested window.",
            "tickers": tickers,
        }

    background_tasks.add_task(_review_task, tickers, trading_days)
    return {
        "status":          "accepted",
        "message":         f"Backfill started: {len(trading_days)} trading days × {len(tickers)} tickers.",
        "tickers":         tickers,
        "trading_days":    [d.isoformat() for d in trading_days],
        "total_reviews":   len(trading_days) * len(tickers),
        "monitor":         "/scheduler/status",
    }


# ---------------------------------------------------------------------------
# GET /scheduler/status
# ---------------------------------------------------------------------------

@router.get("/status", summary="Full RL state for all configured tickers")
async def scheduler_status(
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    """
    Shows per-ticker RL state so you can verify the loop is running correctly.

    Reading the output:
      - envelope.exists = False   → run POST /scheduler/forecast first
      - feedback_log.entries = 0  → run POST /scheduler/backfill
      - weight_memory.version = 0 → RL not learned yet (needs ≥3 feedback entries)
      - weight_memory.rl_active   → True when UI analyses use learned weights
    """
    _check_auth(x_scheduler_key)
    from core.config import settings
    from core.intelligence.rl.stores.prediction_store import PredictionStore

    ticker_states = []
    for ticker in settings.SCHEDULER_TICKERS:
        try:
            store    = PredictionStore(ticker, sector=_SECTOR)
            cycle_id = store.current_cycle_id()
            env      = store.load_envelope(cycle_id)
            fb_log   = store.load_feedback_log(cycle_id)
            wm       = store.load_weight_memory()
            ledger   = store.load_learning_ledger()

            entries       = fb_log.entries if fb_log else []
            direction_hits = sum(1 for e in entries if e.direction_correct)
            accuracy_pct  = round(direction_hits / len(entries) * 100, 1) if entries else None

            # Top weight drifts vs base (to see what RL learned)
            weight_drifts: dict[str, float] = {}
            if wm and wm.current_weights and wm.base_weights:
                for agent in wm.current_weights:
                    drift = round(wm.current_weights[agent] - wm.base_weights.get(agent, 0), 4)
                    if abs(drift) >= 0.001:
                        weight_drifts[agent] = drift

            ticker_states.append({
                "ticker":   ticker,
                "cycle_id": cycle_id,
                "envelope": {
                    "exists":        env is not None,
                    "horizon_days":  len(env.daily_forecasts) if env else 0,
                    "base_close":    round(env.base_close, 2) if env else None,
                    "weight_ver":    env.weight_version_used if env else 0,
                },
                "feedback_log": {
                    "entries":           len(entries),
                    "direction_accuracy": f"{accuracy_pct}%" if accuracy_pct is not None else "n/a",
                    "last_date":         entries[-1].date if entries else None,
                },
                "weight_memory": {
                    "rl_active":     wm is not None and wm.weight_version > 0,
                    "version":       wm.weight_version if wm else 0,
                    "weight_drifts": weight_drifts,
                },
                "learning_ledger": {
                    "lessons":       len(ledger.lessons) if ledger else 0,
                    "top_misses":    dict(sorted(
                        (ledger.miss_counter or {}).items(), key=lambda x: -x[1]
                    )[:3]) if ledger else {},
                },
            })
        except Exception as exc:
            logger.warning("[scheduler_api] Status check failed for %s: %s", ticker, exc)
            ticker_states.append({"ticker": ticker, "status": "error", "detail": str(exc)})

    rl_active = sum(1 for t in ticker_states if t.get("weight_memory", {}).get("rl_active", False))
    total_feedback = sum(t.get("feedback_log", {}).get("entries", 0) for t in ticker_states)

    return {
        "scheduler_key_configured": bool(os.getenv("SCHEDULER_KEY")),
        "rl_active_tickers":        rl_active,
        "total_tickers":            len(ticker_states),
        "total_feedback_entries":   total_feedback,
        "summary":                  (
            "✓ RL active — learned weights in use" if rl_active > 0
            else "⚠ No RL yet — run POST /scheduler/forecast then POST /scheduler/backfill"
        ),
        "tickers": ticker_states,
    }
