"""
Monthly scorecard scheduler job (spec 2026-06-12, section 6).

`AutomobileScheduler._scorecard_monthly_job` builds + saves the *previous*
calendar month's scorecard, gated on settings.SCORECARD_ENABLED, and never
raises (mirrors `_ledger_cleanup_job`'s non-fatal contract). These tests
monkeypatch `build_scorecard` / `save_scorecard` so no filesystem I/O
happens — only the previous-month argument and non-fatal behavior are
verified.
"""
from datetime import date

import core.intelligence.rl.eval.scorecard as scorecard_mod
import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)


def test_scorecard_monthly_job_builds_previous_month(monkeypatch):
    calls = []

    def fake_build_scorecard(month, tickers=None):
        calls.append(month)
        return "SENTINEL_SCORECARD"

    saved = []

    def fake_save_scorecard(sc):
        saved.append(sc)
        from pathlib import Path
        return Path("data/eval/scorecards/fake_scorecard.json")

    monkeypatch.setattr(scorecard_mod, "build_scorecard", fake_build_scorecard)
    monkeypatch.setattr(scorecard_mod, "save_scorecard", fake_save_scorecard)

    today = date.today()
    expected_prev = scorecard_mod._previous_month(f"{today.year}-{today.month:02d}")

    scheduler = _scheduler()
    scheduler._scorecard_monthly_job()

    assert calls == [expected_prev]
    assert saved == ["SENTINEL_SCORECARD"]


def test_scorecard_monthly_job_non_fatal_on_build_failure(monkeypatch):
    def boom(month, tickers=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(scorecard_mod, "build_scorecard", boom)

    scheduler = _scheduler()
    # Must not raise.
    scheduler._scorecard_monthly_job()


def test_previous_month_year_rollover():
    assert scorecard_mod._previous_month("2026-01") == "2025-12"
    assert scorecard_mod._previous_month("2026-06") == "2026-05"
