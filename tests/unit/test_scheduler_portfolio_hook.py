"""Compass Phase A — digest/advisor fire on review completion, never on clock."""
import asyncio
from datetime import date

import services.api.routes.scheduler_api as sched


def test_review_task_triggers_portfolio_pipeline(monkeypatch):
    calls = {}
    monkeypatch.setattr(sched, "_run_reviews", lambda t, d, s=False: [
        {"ticker": "MARUTI", "date": "2026-07-06", "status": "completed"},
    ])
    monkeypatch.setattr(
        sched, "run_post_review_pipeline",
        lambda review_date: calls.setdefault("date", review_date) or {"status": "completed"},
    )
    asyncio.run(sched._review_task(
        [{"sym": "MARUTI", "sector": "automobile"}], [date(2026, 7, 6)],
    ))
    assert calls["date"] == date(2026, 7, 6)


def test_review_task_survives_pipeline_failure(monkeypatch):
    monkeypatch.setattr(sched, "_run_reviews", lambda t, d, s=False: [])

    def boom(review_date):
        raise RuntimeError("pipeline exploded")
    monkeypatch.setattr(sched, "run_post_review_pipeline", boom)
    # Must not raise — reviews already succeeded, pipeline failure is telemetry.
    asyncio.run(sched._review_task(
        [{"sym": "MARUTI", "sector": "automobile"}], [date(2026, 7, 6)],
    ))


def test_run_reviews_respects_cadence(monkeypatch):
    ran = []
    # _run_reviews imports run_daily_review INSIDE the function body, so patch
    # the source module attribute — the late import picks up the patched name.
    import core.intelligence.rl.workflows.daily_review as dr
    monkeypatch.setattr(
        dr, "run_daily_review",
        lambda ticker, review_date, sector=None: ran.append(ticker) or {"status": "completed"},
    )
    monday = date(2026, 7, 6)   # weekday 0 — weekly names not due
    results = sched._run_reviews(
        [
            {"sym": "MARUTI", "sector": "automobile"},                       # legacy: daily
            {"sym": "INFY", "sector": "it_sector", "cadence": "weekly"},     # not due Monday
        ],
        [monday],
    )
    assert "MARUTI" in ran and "INFY" not in ran
    statuses = {r["ticker"]: r["status"] for r in results}
    assert statuses["INFY"] == "skipped_cadence"


def test_scheduled_daily_review_job_triggers_pipeline(monkeypatch):
    """AUD-043: the APScheduler cron job itself (not just the HTTP path) must
    event-trigger the portfolio pipeline after reviews complete."""
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl

    calls = {}
    monkeypatch.setattr(dr, "run_daily_review",
                        lambda t, d, sector=None: {"status": "completed"})
    monkeypatch.setattr(pl, "run_post_review_pipeline",
                        lambda d: calls.setdefault("date", d) or {"status": "completed"})
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"}])

    sch.AutomobileScheduler()._daily_review_job()

    assert "date" in calls, "scheduled job never invoked the portfolio pipeline"
    # review date must be the last trading day strictly before today (AUD-051)
    from core.intelligence.rl.nse_calendar import is_trading_day, now_ist
    assert calls["date"] < now_ist().date()
    assert is_trading_day(calls["date"])


def test_scheduled_daily_review_job_survives_pipeline_failure(monkeypatch):
    import services.scheduler.python.scheduler as sch
    import core.intelligence.rl.workflows.daily_review as dr
    import core.portfolio.pipeline as pl

    monkeypatch.setattr(dr, "run_daily_review",
                        lambda t, d, sector=None: {"status": "completed"})

    def boom(review_date):
        raise RuntimeError("pipeline exploded")
    monkeypatch.setattr(pl, "run_post_review_pipeline", boom)
    monkeypatch.setattr(sch, "get_active_tickers_with_sector",
                        lambda: [{"sym": "MARUTI", "sector": "automobile"}])

    sch.AutomobileScheduler()._daily_review_job()   # must not raise
