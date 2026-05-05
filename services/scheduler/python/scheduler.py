"""
services/scheduler/python/scheduler.py
=======================================
BackgroundScheduler host for all automated RL jobs.

Runs as a background thread inside the FastAPI process — started from
server.py lifespan and stopped cleanly on shutdown.  Works on any cloud
platform (Railway, AWS, GCP, local) without a separate process or service.

Three scheduled jobs
--------------------
1. rl_daily_review       — every weekday 4:30 pm IST (11:00 UTC)
                           Runs the 8-step RL feedback loop for all tickers.
                           Requires a prediction envelope to exist (created by job 2).

2. rl_monthly_forecast   — 1st of every month 9:00 am IST (03:30 UTC)
                           Generates a fresh 30-day prediction envelope for all tickers.
                           Also the job that makes RL weights improve each month.

3. rl_calendar_update    — Dec 31 at 11:00 pm IST (17:30 UTC)
                           Fetches NSE holidays for the coming year from the official
                           NSE API (yfinance fallback, then fixed-holidays fallback).
                           Writes data/nse_holidays.json and hot-reloads the calendar.

Public API
----------
AutomobileScheduler()
    .start()    → starts the BackgroundScheduler (non-blocking)
    .stop()     → graceful shutdown (called from FastAPI lifespan on exit)
    .run_now(tickers?)    → immediate on-demand run (for testing / manual override)
    .status()   → dict with scheduler state and DB stats
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from core.config import settings

logger = logging.getLogger(__name__)


class AutomobileScheduler:
    """
    BackgroundScheduler wrapper for all RL automation jobs.
    start() is non-blocking — the scheduler runs in a daemon thread.
    """

    def __init__(self) -> None:
        self._scheduler = self._build_scheduler()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_scheduler(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            raise ImportError(
                "APScheduler not installed. Add apscheduler>=3.10.0 to requirements.txt"
            )

        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

        # ── Job 1: Daily RL review (4:30 pm IST = 11:00 UTC weekdays) ────────
        fb_parts = settings.FEEDBACK_CRON.split()
        if len(fb_parts) == 5:
            fb_minute, fb_hour, fb_day, fb_month, fb_dow = fb_parts
            scheduler.add_job(
                func=self._daily_review_job,
                trigger=CronTrigger(
                    minute=fb_minute, hour=fb_hour,
                    day=fb_day,       month=fb_month,
                    day_of_week=fb_dow, timezone="Asia/Kolkata",
                ),
                id="rl_daily_review",
                name="RL daily feedback review",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Daily review job: cron='%s'", settings.FEEDBACK_CRON)
        else:
            logger.warning(
                "[Scheduler] Invalid FEEDBACK_CRON '%s' — daily review NOT scheduled",
                settings.FEEDBACK_CRON,
            )

        # ── Job 2: Monthly forecast (1st of month 9:00 am IST = 03:30 UTC) ──
        scheduler.add_job(
            func=self._monthly_forecast_job,
            trigger=CronTrigger(
                day=1, hour=9, minute=0, timezone="Asia/Kolkata",
            ),
            id="rl_monthly_forecast",
            name="RL monthly forecast generation",
            misfire_grace_time=7200,  # 2h grace (market opens at 9:15 am)
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Monthly forecast job: 1st of month at 9:00 am IST")

        # ── Job 3: Dec 31 calendar update (11:00 pm IST = 17:30 UTC) ─────────
        scheduler.add_job(
            func=self._calendar_update_job,
            trigger=CronTrigger(
                month=12, day=31, hour=23, minute=0, timezone="Asia/Kolkata",
            ),
            id="rl_calendar_update",
            name="NSE holiday calendar update",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Calendar update job: Dec 31 at 11:00 pm IST")

        return scheduler

    # ------------------------------------------------------------------
    # Job implementations
    # ------------------------------------------------------------------

    def _daily_review_job(self) -> None:
        """
        Review yesterday's trading session for all configured tickers.
        Steps back over weekends so Monday's job reviews Friday's session.
        """
        from core.intelligence.rl.workflows.daily_review import run_daily_review

        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

        logger.info("[Scheduler] === RL daily review — %s ===", review_date.isoformat())
        for ticker in settings.SCHEDULER_TICKERS:
            try:
                summary = run_daily_review(ticker, review_date)
                logger.info(
                    "[Scheduler] %s %s — status=%s direction=%s lessons=%s weights=v%s",
                    ticker, review_date,
                    summary.get("status"),
                    summary.get("direction_correct"),
                    summary.get("lessons_added"),
                    summary.get("weight_version"),
                )
            except Exception as exc:
                logger.error(
                    "[Scheduler] Daily review FAILED for %s: %s", ticker, exc, exc_info=True
                )
        logger.info("[Scheduler] === RL daily review complete ===")

    def _monthly_forecast_job(self) -> None:
        """
        Generate fresh 30-day prediction envelopes on the 1st of each month.
        Runs the full 9-agent analysis per ticker — takes ~2 min/ticker.
        """
        from core.intelligence.rl.workflows.generate_forecast import generate_forecast

        today = date.today()
        logger.info(
            "[Scheduler] === RL monthly forecast — %d-%02d ===", today.year, today.month
        )
        for ticker in settings.SCHEDULER_TICKERS:
            try:
                env = generate_forecast(ticker)
                logger.info(
                    "[Scheduler] Forecast OK: %s cycle=%s horizon=%dd base=₹%.2f weights=v%d",
                    ticker, env.cycle_id, len(env.daily_forecasts),
                    env.base_close, env.weight_version_used,
                )
            except Exception as exc:
                logger.error(
                    "[Scheduler] Monthly forecast FAILED for %s: %s", ticker, exc, exc_info=True
                )
        logger.info("[Scheduler] === RL monthly forecast complete ===")

    def _calendar_update_job(self) -> None:
        """Fetch NSE holidays for next year and hot-reload the calendar."""
        logger.info("[Scheduler] === NSE calendar update (Dec 31 annual job) ===")
        try:
            from core.intelligence.rl.calendar_updater import run_dec31_update
            run_dec31_update()
            logger.info("[Scheduler] Calendar update complete")
        except Exception as exc:
            logger.error("[Scheduler] Calendar update FAILED: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the BackgroundScheduler daemon thread.
        Non-blocking — returns immediately; jobs fire at their scheduled times.
        """
        if not settings.SCHEDULER_ENABLED:
            logger.warning(
                "[Scheduler] SCHEDULER_ENABLED=false — set it to true to activate. "
                "Jobs will NOT run."
            )
            return
        try:
            self._scheduler.start()
            logger.info("[Scheduler] BackgroundScheduler started — %d jobs registered", len(self._scheduler.get_jobs()))
        except Exception as exc:
            logger.error("[Scheduler] Failed to start: %s", exc, exc_info=True)

    def stop(self) -> None:
        """Gracefully shut down the scheduler (called on server exit)."""
        try:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)
                logger.info("[Scheduler] Stopped cleanly")
        except Exception as exc:
            logger.warning("[Scheduler] Stop error (non-fatal): %s", exc)

    def run_now(self, tickers: list[str] | None = None) -> None:
        """Manually trigger an immediate analysis run (testing / ops override)."""
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        tickers_to_run = tickers or settings.SCHEDULER_TICKERS
        orch = AutomobileAgentOrchestrator()
        for ticker in tickers_to_run:
            try:
                report = orch.analyse(ticker)
                logger.info(
                    "[Scheduler] run_now %s — verdict=%s score=%.3f",
                    ticker, report.verdict, report.final_score,
                )
            except Exception as exc:
                logger.error("[Scheduler] run_now FAILED for %s: %s", ticker, exc)

    def status(self) -> dict:
        """Return a status dict for health checks and the /scheduler/status endpoint."""
        from services.data.stores.score_store import ScoreStore
        store = ScoreStore()
        jobs = self._scheduler.get_jobs() if self._scheduler else []
        return {
            "enabled":          settings.SCHEDULER_ENABLED,
            "running":          self._scheduler.running if self._scheduler else False,
            "feedback_cron":    settings.FEEDBACK_CRON,
            "tickers":          settings.SCHEDULER_TICKERS,
            "db_total_runs":    store.total_runs(),
            "db_ticker_count":  store.ticker_count(),
            "jobs": [
                {
                    "id":      j.id,
                    "name":    j.name,
                    "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                }
                for j in jobs
            ],
        }
