"""
services/scheduler/python/scheduler.py
=======================================
BackgroundScheduler host for all automated RL jobs.

Runs as a background thread inside the FastAPI process — started from
server.py lifespan and stopped cleanly on shutdown.  Works on any cloud
platform (Railway, AWS, GCP, local) without a separate process or service.

Three scheduled jobs
--------------------
1. rl_daily_review       — Mon–Fri 4:30 pm IST (FEEDBACK_CRON, IST-native fields)
                           Runs the 8-step RL feedback loop for all tickers,
                           then event-triggers the Compass portfolio pipeline
                           (advisor → autopilot → digest, AUD-043).
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
from pathlib import Path

from backend.shared.config.settings.loader import cfg
from core.audit.outcomes import grade_due
from core.audit.report import build_report as build_audit_report
from core.audit.report import render_section as render_audit_section
from core.audit.thresholds import emit_breaches, evaluate_breaches
from core.config import settings

logger = logging.getLogger(__name__)

_SEP = "=" * 65

# Where the nightly audit run summary lands, for the watchdog to read.
# Module-level so tests can redirect it — writing to the real data/ dir from
# a test run would pollute the working tree and, worse, feed the watchdog
# fabricated numbers.
_AUDIT_SUMMARY_PATH = Path("data") / "audit_last_run.json"


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

        # AUD-084 rider: anything that still escapes a job function (the
        # harvest-TimeoutError class) must page a human, not just vanish
        # into the apscheduler error log.
        try:
            from apscheduler.events import EVENT_JOB_ERROR
            scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        except Exception as exc:
            logger.warning("[Scheduler] could not register error listener: %s", exc)

        # ── Job 1: Daily RL review (FEEDBACK_CRON — IST-native fields, named days) ──
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

        # ── Job 11: Daily bhavcopy sync (19:00 IST weekdays — EOD data settles ~18:30) ──
        if getattr(settings, "DISCOVERY_ENABLED", False):
            scheduler.add_job(
                func=self._bhavcopy_sync_job,
                trigger=CronTrigger(
                    day_of_week="mon-fri", hour=19, minute=0, timezone="Asia/Kolkata",
                ),
                id="bhavcopy_daily_sync",
                name="Daily bhavcopy EOD cache sync",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Bhavcopy sync job: weekdays at 7:00 pm IST")
        else:
            logger.info("[Scheduler] Bhavcopy sync job disabled (DISCOVERY_ENABLED=false)")

        # ── Job 12: Weekly discovery funnel (Sat 12:30 IST — after event-ingest
        # 10:00 and research-loop 11:00, so the week's filings are digested first) ──
        if getattr(settings, "DISCOVERY_ENABLED", False):
            scheduler.add_job(
                func=self._discovery_weekly_job,
                trigger=CronTrigger(
                    day_of_week="sat", hour=12, minute=30, timezone="Asia/Kolkata",
                ),
                id="discovery_weekly",
                name="Weekly discovery funnel (screen + deep-dives + shelf + paper)",
                misfire_grace_time=7200,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Discovery job: Saturdays at 12:30 pm IST")
        else:
            logger.info("[Scheduler] Discovery job disabled (DISCOVERY_ENABLED=false)")

        # ── Job 13: Morning brief (Mon-Fri 08:50 IST — right after the 08:45
        # pre-open shock check, before the 09:15 open; spec §7 M4) ───────────
        if getattr(settings, "DELIVERY_ENABLED", False):
            scheduler.add_job(
                func=self._morning_brief_job,
                trigger=CronTrigger(
                    day_of_week="mon-fri", hour=8, minute=50, timezone="Asia/Kolkata",
                ),
                id="morning_brief",
                name="Morning brief (M4 proactive delivery)",
                misfire_grace_time=1800,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Morning brief job: weekdays at 8:50 am IST")

            # ── Job 14: Weekly review + index watch (Sun 18:00 IST) ─────────
            scheduler.add_job(
                func=self._weekly_review_job,
                trigger=CronTrigger(
                    day_of_week="sun", hour=18, minute=0, timezone="Asia/Kolkata",
                ),
                id="weekly_review",
                name="Weekly portfolio review + index watch (M4)",
                misfire_grace_time=7200,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Weekly review job: Sundays at 6:00 pm IST")
        else:
            logger.info("[Scheduler] Delivery jobs disabled (DELIVERY_ENABLED=false)")

        # ── Job 15: Nightly data backup (23:30 IST daily — AUD-088) ─────────
        # Always on: the local rotation under data/backups/ is free; the
        # emailed off-site copy rides whenever the SMTP transport is configured.
        scheduler.add_job(
            func=self._backup_job,
            trigger=CronTrigger(hour=23, minute=30, timezone="Asia/Kolkata"),
            id="data_backup_nightly",
            name="Nightly data backup (zip + email off-site)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Backup job: daily at 11:30 pm IST")

        # ── Job 16: Atlas Universe recompute (23:00 IST daily — Atlas C4) ───
        # Reads atlas.db user_instruments, writes only aggregate demand/cadence
        # back to instruments. Runs before the backup so the archive captures
        # the recomputed universe. Dormant no-op until ATLAS_ENABLED is set.
        scheduler.add_job(
            func=self._universe_recompute_job,
            trigger=CronTrigger(hour=23, minute=0, timezone="Asia/Kolkata"),
            id="atlas_universe_recompute",
            name="Atlas Universe recompute (demand tiers)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Universe recompute job: daily at 11:00 pm IST")

        # ── Job 17: Atlas cost-by-user rollup (23:15 IST daily — Atlas C8 BP4) ─
        # Buckets the day's llm_calls cost by user_id (NULL = shared brain) into
        # cost_by_user_day. Dormant no-op until ATLAS_ENABLED. Runs between the
        # universe recompute (23:00) and the backup (23:30).
        scheduler.add_job(
            func=self._cost_rollup_job,
            trigger=CronTrigger(hour=23, minute=15, timezone="Asia/Kolkata"),
            id="atlas_cost_rollup",
            name="Atlas cost-by-user rollup (BP4)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Cost rollup job: daily at 11:15 pm IST")

        # ── Job 18: Atlas retention prune (23:20 IST daily — Atlas C9) ──────
        # Bounds ticker_verdicts / outbox / value_history / sessions; all caps
        # via cfg(), None = keep-all. Dormant no-op until ATLAS_ENABLED.
        scheduler.add_job(
            func=self._retention_job,
            trigger=CronTrigger(hour=23, minute=20, timezone="Asia/Kolkata"),
            id="atlas_retention",
            name="Atlas retention prune (bounded stores)",
            misfire_grace_time=3600,
            coalesce=True,
            replace_existing=True,
        )
        logger.info("[Scheduler] Retention prune job: daily at 11:20 pm IST")

        # ── Verification layer: nightly grading + breach check (23:45 IST) ──
        # After atlas_retention so the day's ledgers have settled. Read-only
        # over the learning stack — it can never contaminate a validation run.
        if cfg("audit.enabled", fallback=True):
            scheduler.add_job(
                func=self._audit_nightly_job,
                trigger=CronTrigger(hour=23, minute=45, timezone="Asia/Kolkata"),
                id="audit_nightly",
                name="Nightly advice-outcome grading + breach check",
                misfire_grace_time=3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Audit job: nightly at 11:45 pm IST")
        else:
            logger.info("[Scheduler] Audit job disabled (audit.enabled=false)")

        # ── Operational watchdog (06:30 IST daily) ──────────────────────────
        # Deliberately early and NOT in the 23:xx cluster: a "your window is
        # open today" notice delivered at 23:45 has already wasted the day it
        # is announcing. 06:30 on a Saturday leaves the whole weekend to act.
        if cfg("watchdog.enabled", fallback=True):
            scheduler.add_job(
                func=self._watchdog_job,
                trigger=CronTrigger(hour=int(cfg("watchdog.hour", fallback=6)),
                                    minute=int(cfg("watchdog.minute", fallback=30)),
                                    timezone="Asia/Kolkata"),
                id="ops_watchdog",
                name="Operational watchdog (milestones + invariants)",
                misfire_grace_time=6 * 3600,
                coalesce=True,
                replace_existing=True,
            )
            logger.info("[Scheduler] Watchdog job: daily at 6:30 am IST")
        else:
            logger.info("[Scheduler] Watchdog job disabled (watchdog.enabled=false)")

        return scheduler

    def _on_job_error(self, event) -> None:
        """EVENT_JOB_ERROR hook — one critical ops alert per crashed job run
        (AUD-084 rider). Never raises: alerting must not hurt the scheduler."""
        job_id = str(getattr(event, "job_id", "unknown"))
        exc = getattr(event, "exception", None)
        logger.error("[Scheduler] Job %s CRASHED: %r", job_id, exc)
        try:
            from core.delivery.ops_alerts import alert_job_crashed
            alert_job_crashed(job_id, repr(exc))
        except Exception as alert_exc:
            logger.warning("[Scheduler] crash alert failed (non-fatal): %s", alert_exc)

    # ------------------------------------------------------------------
    # Job implementations
    # ------------------------------------------------------------------

    def _bhavcopy_sync_job(self) -> None:
        """Top up the EOD market cache with the last week's trading days.
        days_back=7 self-heals transient NSE outages. Non-fatal by construction."""
        from services.data.fetchers.bhavcopy import sync_recent

        _job_banner("Daily Bhavcopy Sync")
        try:
            result = sync_recent(days_back=7)
            logger.info(
                "[Scheduler] Bhavcopy sync — synced=%d skipped=%d failed=%s pruned=%d",
                result["synced"], result["skipped"], result["failed"], result["pruned"],
            )
        except Exception as exc:
            logger.error("[Scheduler] Bhavcopy sync FAILED: %s", exc, exc_info=True)
        _job_banner("Daily Bhavcopy Sync", done=True)

    def _discovery_weekly_job(self) -> None:
        """Weekly discovery funnel (spec §6): non-fatal by construction —
        run_discovery_cycle() contains every stage failure."""
        from core.discovery import run_discovery_cycle

        _job_banner("Weekly Discovery Funnel")
        try:
            result = run_discovery_cycle()
            logger.info(
                "[Scheduler] Discovery — universe=%s candidates=%s dives=%s "
                "shelf_added=%s paper_reviewed=%s dark=%s errors=%s",
                result.get("universe_size"), result.get("candidates"),
                result.get("deep_dives"), result.get("shelf", {}).get("added"),
                result.get("paper", {}).get("reviewed"),
                result.get("dark_signals"), result.get("errors"),
            )
            try:
                from core.delivery.ops_alerts import alert_job_zero_output
                alert_job_zero_output(
                    "discovery_deep_dives",
                    produced=int(result.get("deep_dives") or 0),
                    expected=int(result.get("candidates") or 0),
                )
            except Exception:
                pass
        except Exception as exc:
            logger.error("[Scheduler] Discovery FAILED: %s", exc, exc_info=True)
        _job_banner("Weekly Discovery Funnel", done=True)

    def _morning_brief_job(self) -> None:
        """Morning brief (spec §7): run_morning_brief() never raises and skips
        non-trading days internally."""
        from core.delivery.brief import run_morning_brief

        _job_banner("Morning Brief")
        try:
            result = run_morning_brief()
            logger.info("[Scheduler] Morning brief — %s", result)
        except Exception as exc:
            logger.error("[Scheduler] Morning brief FAILED: %s", exc, exc_info=True)
        _job_banner("Morning Brief", done=True)

    def _weekly_review_job(self) -> None:
        """Weekly review + index-constituent diff (spec §7 / §10 Phase C)."""
        from core.delivery.index_watch import run_index_watch
        from core.delivery.weekly import run_weekly_review

        _job_banner("Weekly Review + Index Watch")
        try:
            idx = run_index_watch()
            logger.info("[Scheduler] Index watch — %s", idx)
        except Exception as exc:
            logger.error("[Scheduler] Index watch FAILED: %s", exc, exc_info=True)
        try:
            result = run_weekly_review()
            logger.info("[Scheduler] Weekly review — %s", result)
        except Exception as exc:
            logger.error("[Scheduler] Weekly review FAILED: %s", exc, exc_info=True)
        _job_banner("Weekly Review + Index Watch", done=True)

    def _daily_review_job(self) -> None:
        """
        Review the previous trading session for all configured tickers.
        Holiday-aware (AUD-051): the day after a weekday NSE holiday reviews
        the last real session, not the holiday. The harvest has an aggregate
        budget (300 s x tickers); if it expires, the finished reviews stand,
        stragglers are logged, and the pipeline below still runs (AUD-084 —
        a slow day must not kill the trading day).
        After the reviews, the Compass portfolio pipeline runs event-triggered
        (AUD-043) — advisor → autopilot → value point → digest.
        """
        from core.intelligence.rl.workflows.daily_review import run_daily_review
        from core.intelligence.rl.nse_calendar import now_ist, trading_days_ago

        review_date = trading_days_ago(now_ist().date(), 1)

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

        succeeded = 0
        stragglers: list[str] = []
        # F5: how many reviews actually saw company news. Reviews that early-return
        # (no envelope / no actual close) never reach the news fetch and report no
        # flag — they count as neither, so the ratio stays honest.
        news_fetched = 0
        news_blind = 0
        # F2: of the blind reviews, how many were given market-wide macro context
        # instead of nothing. Separates "rescued" from "truly context-less" for
        # the 20-trading-day miss-taxonomy comparison.
        news_macro_rescued = 0
        # AUD-084: the old "3-minute per-ticker timeout" was fiction —
        # as_completed only ever yields FINISHED futures, so result(timeout=)
        # never blocked. The only real cap is the aggregate as_completed budget,
        # and its TimeoutError rises from the GENERATOR, outside the old inner
        # try — on Tue 2026-07-14 it escaped, skipping the alerts and the
        # portfolio pipeline (13 reviews saved, 0 trades, zero alerts).
        # Contain it: harvest what finished, log the stragglers, always fall
        # through to the alert + pipeline tail. shutdown(wait=False) releases
        # this thread; a straggler finishing later still persists its review.
        executor = _cf.ThreadPoolExecutor(max_workers=max_w)
        try:
            futures = {
                executor.submit(_review_one, entry): entry
                for entry in ticker_entries
            }
            try:
                for future in _cf.as_completed(futures, timeout=300 * max(len(ticker_entries), 1)):
                    try:
                        ticker, sector, summary, err = future.result()
                        if err is not None:
                            logger.error(
                                "[Scheduler] Daily review FAILED for %s: %s", ticker, err, exc_info=True
                            )
                        else:
                            succeeded += 1
                            news_flag = summary.get("news_available")
                            if news_flag is True:
                                news_fetched += 1
                            elif news_flag is False:
                                news_blind += 1
                            if summary.get("macro_fallback_used") is True:
                                news_macro_rescued += 1
                            logger.info(
                                "[Scheduler] %s %s sector=%s — status=%s direction=%s lessons=%s weights=v%s",
                                ticker, review_date, sector,
                                summary.get("status"),
                                summary.get("direction_correct"),
                                summary.get("lessons_added"),
                                summary.get("weight_version"),
                            )
                    except Exception as exc:
                        logger.error("[Scheduler] Unexpected error in daily review: %s", exc, exc_info=True)
            except _cf.TimeoutError:
                stragglers = [e["sym"] for f, e in futures.items() if not f.done()]
                logger.error(
                    "[Scheduler] Daily review harvest budget exhausted — %d unfinished: %s; "
                    "continuing with %d completed reviews (AUD-084)",
                    len(stragglers), stragglers, succeeded,
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # F5: one aggregate line per run — the pre-fix baseline for the news
        # query work and the only place the blind rate is visible at a glance.
        logger.info(
            "[Scheduler] news_context: %d fetched / %d blind of %d reviewed "
            "(%d macro-rescued)",
            news_fetched, news_blind, news_fetched + news_blind, news_macro_rescued,
        )

        try:
            # AUD-039: "all reviews failed but the job logged complete" must page.
            from core.delivery.ops_alerts import alert_job_zero_output
            alert_job_zero_output("daily_review", produced=succeeded,
                                  expected=len(ticker_entries))
        except Exception:
            pass
        try:
            # AUD-090b: a partial day (13/16 on Tue 7/14) was invisible.
            from core.delivery.ops_alerts import alert_job_partial_output
            alert_job_partial_output("daily_review", produced=succeeded,
                                     expected=len(ticker_entries))
        except Exception:
            pass

        # Compass: advisor + autopilot + digest run EVENT-TRIGGERED on review
        # completion (AUD-043 — this hook existed only on the HTTP path before;
        # the scheduled job never traded). Non-fatal: a pipeline failure must
        # never mark the reviews themselves as failed.
        pipeline_ok = False
        pipeline_error = ""
        try:
            from core.portfolio.pipeline import run_post_review_pipeline
            summary = run_post_review_pipeline(review_date)
            pipeline_ok = True
            logger.info("[Scheduler] Post-review portfolio pipeline: %s", summary)
        except Exception as exc:
            pipeline_error = str(exc)[:300]
            logger.error(
                "[Scheduler] Post-review portfolio pipeline FAILED (non-fatal): %s",
                exc, exc_info=True,
            )

        try:
            # AUD-090d: last-run-outcome surface for GET /scheduler/status.
            from services.data.stores.job_outcomes import record_job_outcome
            record_job_outcome(
                "daily_review",
                review_date=review_date.isoformat(),
                produced=succeeded,
                expected=len(ticker_entries),
                stragglers=stragglers,
                pipeline_ok=pipeline_ok,
                pipeline_error=pipeline_error,
                news_fetched=news_fetched,     # F5 sensing telemetry
                news_blind=news_blind,
                news_macro_rescued=news_macro_rescued,   # F2 attribution telemetry
            )
        except Exception:
            pass

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

    def _backup_job(self) -> None:
        """Job 15 — nightly data/ backup (AUD-088). Archive-creation failures
        raise so the EVENT_JOB_ERROR listener pages a human; a missing off-site
        copy only warns (run_backup_job logs it)."""
        from services.data.backup import run_backup_job
        summary = run_backup_job()
        logger.info("[Scheduler] nightly backup done: emailed=%s bytes=%d",
                    summary["emailed"], summary["bytes"])

    def _universe_recompute_job(self) -> None:
        """Job 16 — Atlas Universe recompute (C4). No-op unless ATLAS_ENABLED;
        recompute_universe() is hot-path safe (never raises)."""
        from core.portfolio.universe import recompute_universe
        result = recompute_universe()
        logger.info("[Scheduler] universe recompute: %s", result)

    def _cost_rollup_job(self) -> None:
        """Job 17 — Atlas cost-by-user rollup (C8, BP4). Dormant unless
        ATLAS_ENABLED; rollup_cost_by_user_day() is hot-path safe (never raises)."""
        from services.data.stores import atlas_store
        if not atlas_store.enabled():
            return
        from services.data.stores.log_store import rollup_cost_by_user_day
        result = rollup_cost_by_user_day()
        logger.info("[Scheduler] cost rollup: %s", result)

    def _retention_job(self) -> None:
        """Job 18 — Atlas retention prune (C9). No-op unless ATLAS_ENABLED;
        run_retention() is hot-path safe (never raises)."""
        from core.portfolio.retention import run_retention
        result = run_retention()
        logger.info("[Scheduler] retention prune: %s", result)

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

    def _audit_nightly_job(self) -> None:
        """Grade matured calls, then check the breach rules.

        Never raises: the auditor must not be able to take down the scheduler
        it shares a process with.
        """
        from datetime import date as _d
        _job_banner("Audit — nightly grading")
        try:
            summary = grade_due(_d.today())
            logger.info("[Scheduler] audit graded %s row(s): %s",
                        summary.get("graded"), summary.get("lanes"))
            # The auditor is itself watched (design section 8.1). "Expected" is
            # the rows that SHOULD have graded — matured and attempted — so a
            # run where prices are failing surfaces as a partial output rather
            # than as a quietly smaller report. Rows not yet matured are not
            # counted: they are not a failure.
            from core.delivery.ops_alerts import alert_job_partial_output
            produced = int(summary.get("graded", 0))
            expected = produced + int(summary.get("skipped_unpriceable", 0))
            alert_job_partial_output("audit_nightly", produced, expected)

            # Persist the run summary so the watchdog can tell "graded nothing
            # because there was nothing to do" from "graded nothing because it
            # is broken". alert_job_partial_output cannot: it returns early
            # when expected == 0, and on 2026-08-07 graded=0 AND
            # skipped_unpriceable=0, so the 0/119 run raised no alert at all.
            try:
                from core.audit.store import AuditOutcomeStore
                from core.utils.atomic_io import atomic_write_json
                atomic_write_json(_AUDIT_SUMMARY_PATH, {
                    "date": _d.today().isoformat(),
                    "graded": produced,
                    "already_present": int(summary.get("already_present", 0)),
                    "skipped_unpriceable": int(summary.get("skipped_unpriceable", 0)),
                    "pending_rows": len(AuditOutcomeStore().load_all()),
                }, indent=None)
            except Exception as exc:
                logger.warning("[Scheduler] audit summary persist failed: %s", exc)
        except Exception as exc:
            logger.warning("[Scheduler] audit grading failed: %s", exc, exc_info=True)
            _job_banner("Audit — nightly grading", done=True)
            return

        try:
            report = build_audit_report()
            breaches = evaluate_breaches(report)
            if breaches:
                logger.warning("[Scheduler] audit breaches: %s",
                               [b["rule"] for b in breaches])
                emit_breaches(breaches)
            else:
                logger.info("[Scheduler] audit verdict %s — no breaches",
                            report.get("verdict"))
        except Exception as exc:
            logger.warning("[Scheduler] audit breach check failed: %s", exc, exc_info=True)
        _job_banner("Audit — nightly grading", done=True)

    def _watchdog_job(self) -> None:
        """Evaluate milestones + invariants and notify on transitions.

        Never raises: the watchdog must not take down the scheduler it shares
        a process with.
        """
        _job_banner("Operational watchdog")
        try:
            from core.ops.watchdog.runner import run_watchdog
            out = run_watchdog()
            logger.info("[Scheduler] watchdog evaluated=%s notified=%s levels=%s",
                        out["evaluated"], out["notified"], out["levels"])
        except Exception as exc:
            logger.error("[Scheduler] watchdog FAILED: %s", exc, exc_info=True)
        _job_banner("Operational watchdog", done=True)

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

        # Learning Evidence Report (self-ablation experiment, design 2026-07-19):
        # did the adaptive layer beat frozen-base weights this month? Emailed so
        # the verdict (INERT / BENEFICIAL / HARMFUL / UNPROVEN) is seen, not
        # just archived. Failure here never breaks the scorecard job.
        try:
            from core.intelligence.rl.eval.learning_evidence import (
                build_learning_evidence,
                render_report,
                save_report,
            )
            from core.delivery.channels import send_email

            report = build_learning_evidence([month])
            json_path, _txt_path = save_report(report)
            logger.info(
                "[Scheduler] Learning evidence for %s: %s — saved to %s",
                month, report["verdict"], json_path,
            )
            body = render_report(report)
            # Verification layer (2026-08-07): the money-side auditor rides the
            # same envelope — one monthly report, not two. A failure here must
            # never cost us the Learning Evidence email.
            try:
                body += render_audit_section(build_audit_report())
            except Exception as audit_exc:
                logger.warning("[Scheduler] audit section failed (non-fatal): %s",
                               audit_exc)
            send_email(
                subject=f"[StockAgent] Learning Evidence {month}: {report['verdict']}",
                body=body,
            )
        except Exception as exc:
            logger.warning(
                "[Scheduler] Learning evidence build failed for %s: %s", month, exc, exc_info=True
            )
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
        try:
            # AUD-039: a genuinely quiet week can produce 0 too — one deduped
            # push beats the silent 100%-LLM-failure day (2026-07-11).
            from core.delivery.ops_alerts import alert_job_zero_output
            alert_job_zero_output("event_ingestion", produced=total, expected=len(tickers))
        except Exception:
            pass
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
                if result.get("reforecasts"):
                    try:
                        from datetime import date as _date
                        from core.delivery.alerts import AlertEvent, emit_alerts_broadcast
                        emit_alerts_broadcast(   # AUD-015
                            [AlertEvent(
                                date=_date.today().isoformat(),
                                kind="preopen_reforecast", symbol=t,
                                message=f"overnight shock re-forecast "
                                        f"(severity {result.get('severity', 0.0):.2f}, "
                                        f"{result.get('direction', 'neutral')})",
                                severity="critical")
                             for t in result["reforecasts"]],
                            title="Pre-open shock re-forecasts",
                        )
                    except Exception as exc:
                        logger.warning(
                            "[Scheduler] preopen alert emit failed (non-fatal): %s", exc)
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
