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
