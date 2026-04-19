"""
tools/scheduler.py
==================
Periodic trigger for the Automobile Agent using APScheduler.

Runs the full pipeline for every ticker in SCHEDULER_TICKERS on the
configured cron schedule, saves scores to SQLite, and fires alerts.

Public API
----------
AutomobileScheduler().start()          → blocks (runs until Ctrl+C)
AutomobileScheduler().run_now()        → run all tickers immediately once
AutomobileScheduler().run_ticker(t)   → run a single ticker now

Requirements
------------
pip install apscheduler>=3.10.0
(already in requirements.txt for Phase 4)
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime

from config import settings
from services.data.stores.score_store import ScoreStore
from services.clients.alerting import AlertManager

logger = logging.getLogger(__name__)


def _run_single_ticker(ticker: str, store: ScoreStore, alerter: AlertManager) -> None:
    """
    Execute the full pipeline for one ticker, persist the result, and alert.
    Called by the scheduler job and by run_now().
    """
    from core.pipeline.orchestrator import AutomobileAgentOrchestrator

    logger.info("[Scheduler] Starting run for %s", ticker)
    try:
        report = AutomobileAgentOrchestrator().analyse(ticker)
        store.save(report)
        alerts = alerter.check_and_alert(report, store)
        logger.info(
            "[Scheduler] %s done — score=%.3f verdict=%s alerts=%d",
            ticker, report.final_score, report.verdict, len(alerts),
        )
    except Exception as exc:
        logger.error("[Scheduler] Run failed for %s: %s", ticker, exc, exc_info=True)


class AutomobileScheduler:
    """
    Wraps APScheduler to run the automobile agent pipeline on a cron schedule.

    Configuration is read from config/settings.py:
      SCHEDULER_CRON      — cron expression (default weekdays 8:30am)
      SCHEDULER_TICKERS   — list of NSE tickers to analyse each run
      ALERT_CHANNELS      — where to send change notifications
    """

    def __init__(self) -> None:
        self._store = ScoreStore()
        self._alerter = AlertManager()
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

        # Parse the cron string into APScheduler fields
        # Format: "minute hour dom month dow"
        parts = settings.SCHEDULER_CRON.split()
        if len(parts) != 5:
            raise ValueError(
                f"SCHEDULER_CRON must have 5 fields (got: '{settings.SCHEDULER_CRON}')"
            )
        minute, hour, day, month, day_of_week = parts

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone="Asia/Kolkata",
        )

        scheduler.add_job(
            func=self._scheduled_job,
            trigger=trigger,
            id="automobile_agent_run",
            name="Automobile Agent — full ticker sweep",
            misfire_grace_time=300,   # 5 min grace if system was asleep
            coalesce=True,            # skip missed runs, don't pile up
        )

        logger.info(
            "[Scheduler] Analysis job scheduled: cron='%s' tickers=%s",
            settings.SCHEDULER_CRON,
            settings.SCHEDULER_TICKERS,
        )

        # ── Phase 5: Daily RL feedback review job ────────────────────────
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

    def _scheduled_job(self) -> None:
        """Called automatically by APScheduler on each analysis trigger."""
        logger.info(
            "[Scheduler] === Scheduled analysis run started at %s ===",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        )
        for ticker in settings.SCHEDULER_TICKERS:
            _run_single_ticker(ticker, self._store, self._alerter)
        logger.info("[Scheduler] === Scheduled analysis run complete ===")

    def _daily_review_job(self) -> None:
        """
        Called automatically by APScheduler after market close each weekday.
        Runs the RL feedback review for all configured tickers.
        """
        from datetime import date, timedelta
        from intelligence.rl.workflows.daily_review import run_daily_review

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

        def _shutdown(sig, frame):
            logger.info("[Scheduler] Shutdown signal received.")
            self._scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        self._scheduler.start()   # blocks here

    def run_now(self, tickers: list[str] | None = None) -> None:
        """
        Run the pipeline immediately for all (or specified) tickers.
        Does NOT require SCHEDULER_ENABLED=true.
        """
        targets = tickers or settings.SCHEDULER_TICKERS
        logger.info("[Scheduler] Manual run triggered for: %s", targets)
        for ticker in targets:
            _run_single_ticker(ticker, self._store, self._alerter)
        logger.info("[Scheduler] Manual run complete.")

    def run_ticker(self, ticker: str) -> None:
        """Run the pipeline immediately for a single ticker."""
        _run_single_ticker(ticker, self._store, self._alerter)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def next_run_time(self) -> str | None:
        """Return the next scheduled run time as an ISO string."""
        jobs = self._scheduler.get_jobs()
        if not jobs:
            return None
        nrt = jobs[0].next_run_time
        return nrt.isoformat() if nrt else None

    def status(self) -> dict:
        """Return scheduler status summary."""
        return {
            "enabled":          settings.SCHEDULER_ENABLED,
            "cron":             settings.SCHEDULER_CRON,
            "tickers":          settings.SCHEDULER_TICKERS,
            "next_run":         self.next_run_time(),
            "db_total_runs":    self._store.total_runs(),
            "db_ticker_count":  self._store.ticker_count(),
        }
