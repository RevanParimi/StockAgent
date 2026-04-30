"""
tools/scheduler.py
==================
APScheduler host for the RL daily-review job ONLY.

The analysis cron job (automobile_agent_run) has been moved to the
TypeScript gateway (services/gateway/src/jobs/analysis-cron.ts).
This Python process only runs the RL feedback daily review, which
must stay Python because it imports intelligence.rl modules directly.

Public API
----------
AutomobileScheduler().start()   → blocks (runs until Ctrl+C)

Requirements
------------
pip install apscheduler>=3.10.0
"""

from __future__ import annotations

import logging

from core.config import settings

logger = logging.getLogger(__name__)


class AutomobileScheduler:
    """
    Wraps APScheduler to run ONLY the RL daily feedback review.

    The analysis cron (automobile_agent_run) is now handled by the
    TypeScript gateway (services/gateway/src/jobs/analysis-cron.ts).

    Configuration is read from config/settings.py:
      FEEDBACK_CRON   — cron expression for the RL review (default 4:30pm IST weekdays)
      SCHEDULER_TICKERS — list of NSE tickers
    """

    def __init__(self) -> None:
        self._scheduler = self._build_scheduler()

    def _build_scheduler(self):
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            raise ImportError(
                "APScheduler not installed. Run: pip install apscheduler>=3.10.0"
            )

        scheduler = BlockingScheduler(timezone="Asia/Kolkata")

        # ── RL daily feedback review job ─────────────────────────────────
        # Runs after market close (4:30pm IST = 11:00 UTC) on weekdays
        feedback_parts = settings.FEEDBACK_CRON.split()
        if len(feedback_parts) == 5:
            fb_minute, fb_hour, fb_day, fb_month, fb_dow = feedback_parts
            fb_trigger = CronTrigger(
                minute=fb_minute,
                hour=fb_hour,
                day=fb_day,
                month=fb_month,
                day_of_week=fb_dow,
                timezone="Asia/Kolkata",
            )
            scheduler.add_job(
                func=self._daily_review_job,
                trigger=fb_trigger,
                id="rl_feedback_daily_review",
                name="Automobile Agent — RL daily review",
                misfire_grace_time=3600,   # 1h grace (market may close late)
                coalesce=True,
            )
            logger.info(
                "[Scheduler] RL feedback job scheduled: cron='%s'",
                settings.FEEDBACK_CRON,
            )
        else:
            logger.warning(
                "[Scheduler] Invalid FEEDBACK_CRON '%s' — daily review job not registered",
                settings.FEEDBACK_CRON,
            )

        return scheduler

    def _daily_review_job(self) -> None:
        """
        Called automatically by APScheduler after market close each weekday.
        Runs the RL feedback review for all configured tickers.
        """
        from datetime import date, timedelta
        from core.intelligence.rl.workflows.daily_review import run_daily_review

        # Review yesterday's trading session (today's close is now available)
        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

        logger.info(
            "[Scheduler] === RL daily review started — reviewing %s ===",
            review_date.isoformat(),
        )
        for ticker in settings.SCHEDULER_TICKERS:
            try:
                summary = run_daily_review(ticker, review_date)
                logger.info(
                    "[Scheduler] RL review %s %s — status=%s direction_correct=%s",
                    ticker, review_date,
                    summary.get("status"),
                    summary.get("direction_correct"),
                )
            except Exception as exc:
                logger.error(
                    "[Scheduler] RL review failed for %s: %s", ticker, exc, exc_info=True
                )
        logger.info("[Scheduler] === RL daily review complete ===")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def run_now(self, tickers: list[str] | None = None) -> None:
        """
        Manually trigger an immediate analysis run for the given tickers
        (defaults to SCHEDULER_TICKERS).  Useful for ops testing and
        one-off analysis outside the scheduled cron window.
        """
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        tickers_to_run = tickers or settings.SCHEDULER_TICKERS
        orch = AutomobileAgentOrchestrator()
        for ticker in tickers_to_run:
            try:
                report = orch.analyse(ticker)
                logger.info(
                    "[Scheduler] run_now %s – verdict=%s score=%.3f",
                    ticker, report.verdict, report.final_score,
                )
            except Exception as exc:
                logger.error("[Scheduler] run_now failed for %s: %s", ticker, exc)

    def status(self) -> dict:
        """
        Return a health/status snapshot for monitoring and the C# scheduler contract.
        """
        from services.data.stores.score_store import ScoreStore
        store = ScoreStore()
        jobs = self._scheduler.get_jobs()
        return {
            "enabled":         settings.SCHEDULER_ENABLED,
            "cron":            settings.FEEDBACK_CRON,
            "tickers":         settings.SCHEDULER_TICKERS,
            "db_total_runs":   store.total_runs(),
            "db_ticker_count": store.ticker_count(),
            "jobs": [{"id": j.id, "name": j.name} for j in jobs],
        }

    def start(self) -> None:
        """
        Start the scheduler. Blocks until Ctrl+C or SIGTERM.
        """
        if not settings.SCHEDULER_ENABLED:
            logger.warning(
                "[Scheduler] SCHEDULER_ENABLED=false — set it to true in .env to activate."
            )
            return

        logger.info("[Scheduler] Starting... Press Ctrl+C to stop.")

        try:
            self._scheduler.start()  # blocks here; raises KeyboardInterrupt on Ctrl+C
        except (KeyboardInterrupt, SystemExit):
            logger.info("[Scheduler] Shutdown signal received.")
            self._scheduler.shutdown(wait=False)  # don't block on running jobs
            logger.info("[Scheduler] Scheduler stopped cleanly.")
