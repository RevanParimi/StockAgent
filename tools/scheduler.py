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
from tools.score_store import ScoreStore
from tools.alerting import AlertManager

logger = logging.getLogger(__name__)


def _run_single_ticker(ticker: str, store: ScoreStore, alerter: AlertManager) -> None:
    """
    Execute the full pipeline for one ticker, persist the result, and alert.
    Called by the scheduler job and by run_now().
    """
    from agents.orchestrator import AutomobileAgentOrchestrator

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
            "[Scheduler] Job scheduled: cron='%s' tickers=%s",
            settings.SCHEDULER_CRON,
            settings.SCHEDULER_TICKERS,
        )
        return scheduler

    def _scheduled_job(self) -> None:
        """Called automatically by APScheduler on each trigger."""
        logger.info(
            "[Scheduler] === Scheduled run started at %s ===",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        )
        for ticker in settings.SCHEDULER_TICKERS:
            _run_single_ticker(ticker, self._store, self._alerter)
        logger.info("[Scheduler] === Scheduled run complete ===")

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
