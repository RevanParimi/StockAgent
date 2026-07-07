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

_SEP = "=" * 65


def _job_banner(label: str, done: bool = False) -> None:
    """Emit a visual separator so each scheduled job is easy to spot in Railway logs."""
    if done:
        logger.info("%s  DONE: %s  %s", _SEP, label, _SEP)
    else:
        logger.info(_SEP)
        logger.info("  JOB START: %s", label)
        logger.info(_SEP)


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
    except Exception as exc:
        logger.warning("[scheduler] Could not load tickers from managed_tickers.json: %s", exc, exc_info=True)

    tickers = list(settings.SCHEDULER_TICKERS)
    logger.info(
        "[scheduler] _active_tickers() fell back to SCHEDULER_TICKERS env var: %s", tickers
    )

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


from services.api.log_buffer import get_active_tickers_with_sector


def _sector_lookup() -> dict[str, str]:
    """sym -> sector from managed_tickers.json — works for ANY sector,
    including generic-graph ones (Compass Phase B). Empty dict on failure."""
    try:
        return {
            e["sym"]: e.get("sector", "automobile")
            for e in get_active_tickers_with_sector()
        }
    except Exception as exc:
        logger.warning("[scheduler] _sector_lookup failed: %s", exc)
        return {}


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

        # ── Job 8: Monthly scorecard (1st of month 2:00 am IST) ──────────────
        if getattr(settings, "SCORECARD_ENABLED", True):
            scheduler.add_job(
                func=self._scorecard_monthly_job,
                trigger=CronTrigger(
                    day=1, hour=2, minute=0, timezone="Asia/Kolkata",
                ),
                id="scorecard_monthly",
                name="Monthly RL scorecard (baseline duel)",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Monthly scorecard job: 1st of month at 2:00 am IST")
        else:
            logger.info("[Scheduler] Monthly scorecard job disabled (SCORECARD_ENABLED=false)")

        # ── Job 9: Weekly event ingestion (Saturday 10:00 am IST) ────────────
        if getattr(settings, "RL_EVENT_INGEST_ENABLED", True):
            scheduler.add_job(
                func=self._event_ingest_job,
                trigger=CronTrigger(
                    day_of_week="sat", hour=10, minute=0, timezone="Asia/Kolkata",
                ),
                id="event_ingest_weekly",
                name="Weekly dossier event ingestion",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Event ingest job: Saturdays at 10:00 am IST")
        else:
            logger.info("[Scheduler] Event ingest job disabled (RL_EVENT_INGEST_ENABLED=false)")

        # ── Job 9b: Weekly research loop (Saturday 11:00 am IST) ─────────────
        # One hour after event ingestion, so questions raised by that morning's
        # filings ingestion are immediately researchable.
        if getattr(settings, "RL_RESEARCH_LOOP_ENABLED", True):
            scheduler.add_job(
                func=self._research_loop_job,
                trigger=CronTrigger(
                    day_of_week="sat", hour=11, minute=0, timezone="Asia/Kolkata",
                ),
                id="research_loop_weekly",
                name="Weekly dossier open-question research",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Research loop job: Saturdays at 11:00 am IST")
        else:
            logger.info("[Scheduler] Research loop job disabled (RL_RESEARCH_LOOP_ENABLED=false)")

        # ── Job 10: Pre-open shock check (08:45 IST weekdays, before 09:15 open) ──
        scheduler.add_job(
            func=self._preopen_shock_check_job,
            trigger=CronTrigger(
                day_of_week="mon-fri", hour=8, minute=45, timezone="Asia/Kolkata",
            ),
            id="preopen_shock_check",
            name="Pre-open shock check (Living Envelope)",
            misfire_grace_time=900,   # 15min grace — must finish well before 09:15 open
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Pre-open shock check job: 8:45 am IST weekdays")

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

        review_date = date.today() - timedelta(days=1)
        while review_date.weekday() >= 5:
            review_date -= timedelta(days=1)

        ticker_entries = get_active_tickers_with_sector()
        _job_banner(f"RL Daily Review — {review_date.isoformat()} ({len(ticker_entries)} tickers)")
        logger.info(
            "[Scheduler] Active tickers for this run: %s",
            [e["sym"] for e in ticker_entries],
        )

        max_w = getattr(settings, "RL_SCHEDULER_MAX_WORKERS", 1)
        logger.info("[Scheduler] Running with max_workers=%d", max_w)

        def _review_one(entry: dict) -> tuple[str, str, dict | None, Exception | None]:
            t = entry["sym"]
            s = entry.get("sector", "automobile")
            try:
                result = run_daily_review(t, review_date, sector=s)
                return t, s, result, None
            except Exception as exc:
                return t, s, None, exc

        with _cf.ThreadPoolExecutor(max_workers=max_w) as executor:
            futures = {
                executor.submit(_review_one, entry): entry
                for entry in ticker_entries
            }
            for future in _cf.as_completed(futures, timeout=180 * len(ticker_entries)):
                try:
                    ticker, sector, summary, err = future.result(timeout=180)
                    if err is not None:
                        logger.error(
                            "[Scheduler] Daily review FAILED for %s: %s", ticker, err, exc_info=True
                        )
                    else:
                        logger.info(
                            "[Scheduler] %s %s sector=%s — status=%s direction=%s lessons=%s weights=v%s",
                            ticker, review_date, sector,
                            summary.get("status"),
                            summary.get("direction_correct"),
                            summary.get("lessons_added"),
                            summary.get("weight_version"),
                        )
                except _cf.TimeoutError:
                    logger.error("[Scheduler] Daily review TIMED OUT after 180s")
                except Exception as exc:
                    logger.error("[Scheduler] Unexpected error in daily review: %s", exc, exc_info=True)

        _job_banner("RL Daily Review", done=True)

    def _monthly_forecast_job(self) -> None:
        """
        Generate fresh 30-day prediction envelopes on the 1st of each month.
        Runs the full 9-agent analysis per ticker — takes ~2 min/ticker.
        """
        from core.intelligence.rl.workflows.generate_forecast import generate_forecast

        today = date.today()
        ticker_entries = get_active_tickers_with_sector()
        _job_banner(f"RL Monthly Forecast — {today.year}-{today.month:02d} ({len(ticker_entries)} tickers)")
        logger.info(
            "[Scheduler] Active tickers for this run: %s",
            [e["sym"] for e in ticker_entries],
        )
        for entry in ticker_entries:
            ticker = entry["sym"]
            sector = entry.get("sector", "automobile")
            logger.info("[Scheduler] Generating forecast for %s (sector=%s) ...", ticker, sector)
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
        _job_banner("RL Monthly Forecast", done=True)

    def _prompt_deploy_job(self) -> None:
        """
        Deploy any pending prompt file changes to GitHub once per day at midnight IST.
        Skips silently if nothing is pending or GITHUB_TOKEN/REPO are not set.
        """
        _job_banner("Prompt Daily Deploy")
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
        _job_banner("Prompt Daily Deploy", done=True)

    def _calendar_update_job(self) -> None:
        """Fetch NSE holidays for next year and hot-reload the calendar."""
        _job_banner("NSE Calendar Update (Dec 31 annual)")
        try:
            from core.intelligence.rl.calendar_updater import run_dec31_update
            run_dec31_update()
            logger.info("[Scheduler] Calendar update complete")
        except Exception as exc:
            logger.error("[Scheduler] Calendar update FAILED: %s", exc, exc_info=True)
        _job_banner("NSE Calendar Update", done=True)

    def _macro_market_news_job(self) -> None:
        """
        Macro news — market-hours run (9:00 / 12:00 / 15:00 IST weekdays).
        Queries Serper /news for real-time Nifty/market developments.
        Non-fatal: errors are logged but never crash the scheduler.
        """
        _job_banner("Macro News — Market Hours (9/12/15 IST)")
        try:
            from services.background.macro_news_fetcher import MacroNewsFetcher
            result = MacroNewsFetcher().fetch_and_review("market_hours")
            logger.info(
                "[Scheduler] Macro market-hours done — new_entries=%d iterations=%d",
                result.get("new_entries", 0), result.get("iterations", 0),
            )
        except Exception as exc:
            logger.error("[Scheduler] Macro market-hours FAILED: %s", exc, exc_info=True)
        _job_banner("Macro News — Market Hours", done=True)

    def _macro_daily_news_job(self) -> None:
        """
        Macro news — daily pre-market run (7:30 IST weekdays).
        Queries policy/RBI Serper news + NewsAPI top-headlines.
        Non-fatal: errors are logged but never crash the scheduler.
        """
        _job_banner("Macro News — Daily Policy/RBI (7:30 IST)")
        try:
            from services.background.macro_news_fetcher import MacroNewsFetcher
            result = MacroNewsFetcher().fetch_and_review("daily")
            logger.info(
                "[Scheduler] Macro daily done — new_entries=%d iterations=%d",
                result.get("new_entries", 0), result.get("iterations", 0),
            )
        except Exception as exc:
            logger.error("[Scheduler] Macro daily FAILED: %s", exc, exc_info=True)
        _job_banner("Macro News — Daily Policy/RBI", done=True)

    def _ledger_cleanup_job(self) -> None:
        """
        Downgrade stale single-ticker market-wide/sector-wide lessons weekly.
        Runs Monday at 3:30 am IST — well before any market activity.
        Non-fatal: failures per ticker are logged but never crash the scheduler.
        """
        from core.intelligence.rl.stores.ledger_propagator import (
            archive_stale_lessons,
            downgrade_stale_lessons,
        )
        from core.intelligence.rl.stores.prediction_store import PredictionStore

        sectors = _sector_lookup()

        tickers = _active_tickers()
        _job_banner(f"Weekly Ledger Cleanup — {len(tickers)} tickers")
        for ticker in tickers:
            try:
                sector = sectors.get(ticker, "automobile")
                store = PredictionStore(ticker, sector=sector)
                ticker_ledger, sector_ledger, market_ledger = store.load_all_ledgers()

                n_market = downgrade_stale_lessons(market_ledger)
                n_sector = downgrade_stale_lessons(sector_ledger)
                # Also downgrade the ticker's own ledger — its lessons have only 1
                # contributing ticker by definition, so stale ones are eligible.
                n_ticker = downgrade_stale_lessons(ticker_ledger)

                # P3-16: Sync scope downgrades back to the ticker's own ledger.
                # When a shared lesson is downgraded, the ticker's own copy of the
                # same lesson (matched by pattern) must be updated too, otherwise
                # the ticker ledger and shared ledger are out of sync.
                shared_scope: dict[str, str] = {}
                for sl in sector_ledger.lessons:
                    shared_scope[sl.pattern] = sl.scope
                for ml in market_ledger.lessons:
                    shared_scope[ml.pattern] = ml.scope  # market takes precedence
                _rank = {"stock_specific": 0, "sector_wide": 1, "market_wide": 2}
                for tl in ticker_ledger.lessons:
                    new_scope = shared_scope.get(tl.pattern)
                    if new_scope and _rank.get(new_scope, 0) < _rank.get(tl.scope, 0):
                        logger.info(
                            "[Scheduler] %s: syncing lesson %s scope %s → %s "
                            "(shared ledger downgrade)",
                            ticker, tl.lesson_id, tl.scope, new_scope,
                        )
                        tl.scope = new_scope
                        n_ticker += 1

                # RL Intelligence Phase, Component 3 — archive stale, invalidated
                # lessons from the ticker's own ledger to its cold store.
                # Non-fatal per ticker: a failure here must never block the
                # scope-downgrade saves above.
                n_archived = 0
                try:
                    n_archived = archive_stale_lessons(
                        ticker_ledger, store._archived_lessons_path()
                    )
                    if n_archived:
                        n_ticker += n_archived
                except Exception as exc:
                    logger.warning(
                        "[Scheduler] Lesson archival failed for %s (non-fatal): %s",
                        ticker, exc, exc_info=True,
                    )

                if n_market:
                    store.save_market_ledger(market_ledger)
                if n_sector:
                    store.save_sector_ledger(sector_ledger)
                if n_ticker:
                    store.save_learning_ledger(ticker_ledger)

                total_modified = n_market + n_sector + n_ticker
                if total_modified:
                    logger.info(
                        "[Scheduler] Ledger cleanup %s: %d lessons modified "
                        "(market=%d, sector=%d, ticker=%d, archived=%d)",
                        ticker, total_modified, n_market, n_sector, n_ticker, n_archived,
                    )

                # Weekly dossier distillation (knowledge layer) — same cadence as
                # stale-lesson cleanup; non-fatal per ticker.
                try:
                    from core.config import settings as _settings
                    if getattr(_settings, "RL_DOSSIER_ENABLED", True):
                        from core.intelligence.rl.agents.dossier_curator import distill_dossier
                        dossier = store.load_dossier()
                        if dossier is not None:
                            store.save_dossier(distill_dossier(dossier))
                            logger.info("[Scheduler] Distilled dossier for %s", ticker)
                except Exception as exc:
                    logger.warning("[Scheduler] Dossier distillation failed for %s: %s", ticker, exc)
            except Exception as exc:
                logger.warning("[Scheduler] Ledger cleanup failed for %s: %s", ticker, exc, exc_info=True)
        _job_banner("Weekly Ledger Cleanup", done=True)

    def _scorecard_monthly_job(self) -> None:
        """
        Build + persist the previous month's RL scorecard (agent vs control
        LLM vs naive baselines, spec 2026-06-12). Runs on the 1st of every
        month at 2:00 am IST — by then the previous month is fully closed
        out (last daily review + control-lane scoring already ran).
        Non-fatal: any failure is logged and the scheduler continues.
        """
        from core.intelligence.rl.eval.scorecard import (
            build_scorecard,
            save_scorecard,
            _previous_month,
        )

        today = date.today()
        current_month = f"{today.year}-{today.month:02d}"
        month = _previous_month(current_month)

        _job_banner(f"Monthly Scorecard — {month}")
        try:
            sc = build_scorecard(month)
            path = save_scorecard(sc)
            logger.info("[Scheduler] Scorecard for %s saved to %s", month, path)
        except Exception as exc:
            logger.warning("[Scheduler] Monthly scorecard build failed for %s: %s", month, exc, exc_info=True)
        _job_banner(f"Monthly Scorecard — {month}", done=True)

    def _event_ingest_job(self) -> None:
        """
        Weekly NSE event-driven dossier ingestion (spec 2026-06-12, section 6).
        Runs Saturdays at 10:00 am IST — after Friday's filings have settled.
        Gated on RL_EVENT_INGEST_ENABLED; non-fatal per ticker (mirrors
        `_ledger_cleanup_job`'s loop style).
        """
        from core.intelligence.rl.agents.event_ingestor import EventIngestor

        if not getattr(settings, "RL_EVENT_INGEST_ENABLED", True):
            return

        sectors = _sector_lookup()

        tickers = _active_tickers()
        _job_banner(f"Weekly Event Ingestion — {len(tickers)} tickers")
        total = 0
        for ticker in tickers:
            try:
                sector = sectors.get(ticker, "automobile")
                count = EventIngestor().run(ticker, sector)
                total += count
                logger.info(
                    "[Scheduler] Event ingest %s sector=%s — ingested=%d", ticker, sector, count,
                )
            except Exception as exc:
                logger.warning("[Scheduler] Event ingest failed for %s: %s", ticker, exc, exc_info=True)
        logger.info("[Scheduler] Weekly event ingestion complete — total ingested=%d", total)
        _job_banner("Weekly Event Ingestion", done=True)

    def _research_loop_job(self) -> None:
        """
        Weekly active research of dossier open_questions (spec 2026-06-13,
        section 5). Runs Saturdays at 11:00 am IST — one hour after event
        ingestion, so freshly-raised questions are immediately researchable.
        Gated on RL_RESEARCH_LOOP_ENABLED; non-fatal per ticker (mirrors
        `_event_ingest_job`'s loop style).
        """
        from core.intelligence.rl.agents.question_researcher import QuestionResearcher

        if not getattr(settings, "RL_RESEARCH_LOOP_ENABLED", True):
            return

        sectors = _sector_lookup()

        tickers = _active_tickers()
        _job_banner(f"Weekly Research Loop — {len(tickers)} tickers")
        answered = expired = 0
        for ticker in tickers:
            try:
                sector = sectors.get(ticker, "automobile")
                result = QuestionResearcher().run(ticker, sector)
                answered += result.get("answered", 0)
                expired += result.get("expired", 0)
                logger.info(
                    "[Scheduler] Research %s sector=%s — selected=%d answered=%d "
                    "partial=%d expired=%d", ticker, sector,
                    result.get("selected", 0), result.get("answered", 0),
                    result.get("partial", 0), result.get("expired", 0),
                )
            except Exception as exc:
                logger.warning("[Scheduler] Research loop failed for %s: %s", ticker, exc, exc_info=True)
        logger.info(
            "[Scheduler] Weekly research loop complete — answered=%d expired=%d",
            answered, expired)
        _job_banner("Weekly Research Loop", done=True)

    def _preopen_shock_check_job(self) -> None:
        """
        Pre-open sanity check (Living Envelope, RL Phase 2.5, Component 3).
        Runs weekdays at 08:45 IST — before the 09:15 am NSE open.

        Market-level: one Serper search + one FAST-tier LLM call total
        (NOT per ticker). Gated internally by RL_PREOPEN_CHECK_ENABLED;
        run_preopen_check() never raises, so this job is non-fatal by
        construction.
        """
        from core.intelligence.rl.workflows.preopen_check import run_preopen_check

        _job_banner("Pre-open Shock Check")
        try:
            result = run_preopen_check()
            if result.get("skipped"):
                logger.info("[Scheduler] Pre-open check skipped: %s", result["skipped"])
            else:
                logger.info(
                    "[Scheduler] Pre-open check — severity=%.2f direction=%s "
                    "flagged=%s reforecasts=%s",
                    result.get("severity", 0.0), result.get("direction", "neutral"),
                    result.get("flagged", []), result.get("reforecasts", []),
                )
        except Exception as exc:
            logger.error("[Scheduler] Pre-open shock check FAILED: %s", exc, exc_info=True)
        _job_banner("Pre-open Shock Check", done=True)

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
