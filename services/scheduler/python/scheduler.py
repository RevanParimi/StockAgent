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

import concurrent.futures as _cf
import logging
from datetime import date, timedelta

from core.config import settings

logger = logging.getLogger(__name__)


def _active_tickers() -> list[str]:
    """Read enabled tickers from managed_tickers.json; fall back to settings."""
    try:
        from services.api.log_buffer import get_active_tickers
        tickers = get_active_tickers()
        if tickers:
            # Filter out any non-string or blank entries before returning
            invalid = [t for t in tickers if not isinstance(t, str) or not t.strip()]
            if invalid:
                logger.warning("[scheduler] Removed invalid ticker entries: %s", invalid)
                tickers = [t for t in tickers if isinstance(t, str) and t.strip()]
            if tickers:
                return tickers
    except Exception:
        pass

    tickers = list(settings.SCHEDULER_TICKERS)

    if not tickers:
        logger.warning(
            "[scheduler] _active_tickers() resolved to empty list — "
            "no analysis will run this cycle. Check SCHEDULER_TICKERS in .env."
        )
    else:
        invalid = [t for t in tickers if not isinstance(t, str) or not t.strip()]
        if invalid:
            logger.warning("[scheduler] Removed invalid ticker entries: %s", invalid)
            tickers = [t for t in tickers if isinstance(t, str) and t.strip()]

    return tickers


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

        # ── Job 4: Prompt daily deploy (midnight IST = 18:30 UTC) ────────────
        scheduler.add_job(
            func=self._prompt_deploy_job,
            trigger=CronTrigger(hour=0, minute=0, timezone="Asia/Kolkata"),
            id="prompt_daily_deploy",
            name="Prompt daily deploy to GitHub",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Prompt deploy job: daily at midnight IST")

        # ── Jobs 5 + 6: Macro news background feed ───────────────────────────
        try:
            from backend.shared.config import settings as _macro_cfg
            macro_enabled = getattr(_macro_cfg, "MACRO_NEWS_ENABLED", True)
        except Exception:
            macro_enabled = True

        if macro_enabled:
            # Job 5: Market-hours run — 9:00, 12:00, 15:00 IST weekdays
            # Covers real-time Nifty/market news during NSE trading session.
            scheduler.add_job(
                func=self._macro_market_news_job,
                trigger=CronTrigger(
                    hour="9,12,15", minute=0,
                    day_of_week="mon-fri",
                    timezone="Asia/Kolkata",
                ),
                id="macro_market_news",
                name="Macro news — market hours (9/12/15 IST)",
                misfire_grace_time=1800,   # 30min grace — market moves wait for no one
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Macro market-hours news job: 9:00/12:00/15:00 IST weekdays")

            # Job 6: Daily policy/RBI run — 7:30 IST weekdays
            # Covers overnight policy decisions and top-headlines before market open.
            scheduler.add_job(
                func=self._macro_daily_news_job,
                trigger=CronTrigger(
                    hour=7, minute=30,
                    day_of_week="mon-fri",
                    timezone="Asia/Kolkata",
                ),
                id="macro_daily_news",
                name="Macro news — daily policy/RBI (7:30 IST)",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Macro daily news job: 7:30 IST weekdays")
        else:
            logger.info("[Scheduler] Macro news feed disabled (MACRO_NEWS_ENABLED=false)")

        # ── Job 7: Weekly ledger cleanup (Monday 3:30 am IST) ────────────────
        scheduler.add_job(
            func=self._ledger_cleanup_job,
            trigger=CronTrigger(
                day_of_week="mon",
                hour=3,
                minute=30,
                timezone="Asia/Kolkata",
            ),
            id="ledger_cleanup_weekly",
            name="Ledger stale-lesson cleanup (weekly)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Ledger cleanup job: Mondays at 3:30 am IST")

        return scheduler

    # ------------------------------------------------------------------
    # Job implementations
    # ------------------------------------------------------------------

    def _daily_review_job(self) -> None:
        """
        Review yesterday's trading session for all configured tickers.
        Steps back over weekends so Monday's job reviews Friday's session.
        Each ticker has a 3-minute timeout to prevent a stalled LLM call from
        blocking the entire review loop.
        """
        from core.intelligence.rl.workflows.daily_review import run_daily_review
        from services.api.log_buffer import get_active_tickers_with_sector

        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

        ticker_entries = get_active_tickers_with_sector()
        logger.info("[Scheduler] === RL daily review — %s (%d tickers) ===", review_date.isoformat(), len(ticker_entries))
        for entry in ticker_entries:
            ticker = entry["sym"]
            sector = entry.get("sector", "automobile")
            try:
                with _cf.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_daily_review, ticker, review_date, sector=sector)
                    summary = future.result(timeout=180)  # 3-minute per-ticker timeout
                logger.info(
                    "[Scheduler] %s %s sector=%s — status=%s direction=%s lessons=%s weights=v%s",
                    ticker, review_date, sector,
                    summary.get("status"),
                    summary.get("direction_correct"),
                    summary.get("lessons_added"),
                    summary.get("weight_version"),
                )
            except _cf.TimeoutError:
                logger.error("[Scheduler] Daily review TIMED OUT for %s after 180s", ticker)
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
        from services.api.log_buffer import get_active_tickers_with_sector

        today = date.today()
        ticker_entries = get_active_tickers_with_sector()
        logger.info(
            "[Scheduler] === RL monthly forecast — %d-%02d (%d tickers) ===", today.year, today.month, len(ticker_entries)
        )
        for entry in ticker_entries:
            ticker = entry["sym"]
            sector = entry.get("sector", "automobile")
            try:
                env = generate_forecast(ticker, sector=sector)
                logger.info(
                    "[Scheduler] Forecast OK: %s sector=%s cycle=%s horizon=%dd base=₹%.2f weights=v%d",
                    ticker, sector, env.cycle_id, len(env.daily_forecasts),
                    env.base_close, env.weight_version_used,
                )
            except Exception as exc:
                logger.error(
                    "[Scheduler] Monthly forecast FAILED for %s: %s", ticker, exc, exc_info=True
                )
        logger.info("[Scheduler] === RL monthly forecast complete ===")

    def _prompt_deploy_job(self) -> None:
        """
        Deploy any pending prompt file changes to GitHub once per day at midnight IST.
        Skips silently if nothing is pending or GITHUB_TOKEN/REPO are not set.
        """
        logger.info("[Scheduler] === Prompt daily deploy ===")
        try:
            from services.api.routes.prompts import run_scheduled_deploy
            result = run_scheduled_deploy(triggered_by="scheduler")
            if result["status"] == "nothing_to_deploy":
                logger.info("[Scheduler] Prompt deploy: no pending changes")
            elif result["status"] == "skipped":
                logger.info("[Scheduler] Prompt deploy skipped: %s", result.get("reason", ""))
            else:
                logger.info(
                    "[Scheduler] Prompt deploy complete — %d deployed, %d errors",
                    len(result.get("deployed", [])),
                    len(result.get("errors", [])),
                )
        except Exception as exc:
            logger.error("[Scheduler] Prompt deploy FAILED: %s", exc, exc_info=True)
        logger.info("[Scheduler] === Prompt daily deploy done ===")

    def _calendar_update_job(self) -> None:
        """Fetch NSE holidays for next year and hot-reload the calendar."""
        logger.info("[Scheduler] === NSE calendar update (Dec 31 annual job) ===")
        try:
            from core.intelligence.rl.calendar_updater import run_dec31_update
            run_dec31_update()
            logger.info("[Scheduler] Calendar update complete")
        except Exception as exc:
            logger.error("[Scheduler] Calendar update FAILED: %s", exc, exc_info=True)

    def _macro_market_news_job(self) -> None:
        """
        Macro news — market-hours run (9:00 / 12:00 / 15:00 IST weekdays).
        Queries Serper /news for real-time Nifty/market developments.
        Non-fatal: errors are logged but never crash the scheduler.
        """
        logger.info("[Scheduler] === Macro news — market-hours run ===")
        try:
            from services.background.macro_news_fetcher import MacroNewsFetcher
            result = MacroNewsFetcher().fetch_and_review("market_hours")
            logger.info(
                "[Scheduler] Macro market-hours done — new_entries=%d iterations=%d",
                result.get("new_entries", 0), result.get("iterations", 0),
            )
        except Exception as exc:
            logger.error("[Scheduler] Macro market-hours FAILED: %s", exc, exc_info=True)

    def _macro_daily_news_job(self) -> None:
        """
        Macro news — daily pre-market run (7:30 IST weekdays).
        Queries policy/RBI Serper news + NewsAPI top-headlines.
        Non-fatal: errors are logged but never crash the scheduler.
        """
        logger.info("[Scheduler] === Macro news — daily policy run ===")
        try:
            from services.background.macro_news_fetcher import MacroNewsFetcher
            result = MacroNewsFetcher().fetch_and_review("daily")
            logger.info(
                "[Scheduler] Macro daily done — new_entries=%d iterations=%d",
                result.get("new_entries", 0), result.get("iterations", 0),
            )
        except Exception as exc:
            logger.error("[Scheduler] Macro daily FAILED: %s", exc, exc_info=True)

    def _ledger_cleanup_job(self) -> None:
        """
        Downgrade stale single-ticker market-wide/sector-wide lessons weekly.
        Runs Monday at 3:30 am IST — well before any market activity.
        Non-fatal: failures per ticker are logged but never crash the scheduler.
        """
        from pathlib import Path
        from core.intelligence.rl.stores.ledger_propagator import downgrade_stale_lessons
        from core.intelligence.rl.stores.prediction_store import PredictionStore

        _KNOWN_SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]
        base_dir = "data/predictions"

        def _sector_for(ticker: str) -> str:
            return next(
                (s for s in _KNOWN_SECTORS if Path(f"{base_dir}/{s}/{ticker}").exists()),
                "automobile",
            )

        tickers = _active_tickers()
        logger.info("[Scheduler] === Weekly ledger cleanup — %d tickers ===", len(tickers))
        for ticker in tickers:
            try:
                sector = _sector_for(ticker)
                store = PredictionStore(ticker, sector=sector)
                _, sector_ledger, market_ledger = store.load_all_ledgers()

                n_market = downgrade_stale_lessons(market_ledger)
                n_sector = downgrade_stale_lessons(sector_ledger)

                if n_market:
                    store.save_market_ledger(market_ledger)
                if n_sector:
                    store.save_sector_ledger(sector_ledger)

                if n_market + n_sector:
                    logger.info(
                        "[Scheduler] Ledger cleanup %s: %d lessons modified",
                        ticker, n_market + n_sector,
                    )
            except Exception as exc:
                logger.warning("[Scheduler] Ledger cleanup failed for %s: %s", ticker, exc)
        logger.info("[Scheduler] === Weekly ledger cleanup complete ===")

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
        tickers_to_run = tickers or _active_tickers()
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
            "tickers":          _active_tickers(),
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
