"""
tests/unit/intelligence/rl/test_preopen_check_scheduler.py
=============================================================
Living Envelope (RL Phase 2.5), Component 3 — scheduler wiring.

Covers:
  - `preopen_shock_check` job is registered on the BackgroundScheduler with
    a Mon-Fri 08:45 IST CronTrigger (mirrors how
    test_scheduler_scorecard_job.py / event_ingest_weekly verify job
    registration and non-fatal behavior).
  - `_preopen_shock_check_job` calls run_preopen_check() and logs the
    result without raising, even when run_preopen_check() (mocked) raises.

All run_preopen_check() calls are mocked — no real Serper/LLM/network
traffic is possible from this test module.
"""

from __future__ import annotations

import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler.__new__(sched.AutomobileScheduler)


# ---------------------------------------------------------------------------
# Job registration
# ---------------------------------------------------------------------------

def test_preopen_shock_check_job_registered(monkeypatch):
    """Building the real scheduler registers a 'preopen_shock_check' job
    with a Mon-Fri 08:45 Asia/Kolkata CronTrigger."""
    # SCHEDULER_ENABLED gates start(), not _build_scheduler() — building the
    # scheduler always registers jobs regardless of the flag.
    scheduler_wrapper = sched.AutomobileScheduler()
    jobs = {j.id: j for j in scheduler_wrapper._scheduler.get_jobs()}

    assert "preopen_shock_check" in jobs
    job = jobs["preopen_shock_check"]

    trigger = job.trigger
    # CronTrigger stores its fields; verify hour/minute/day_of_week match spec.
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "45"
    assert fields["day_of_week"] == "mon-fri"
    assert str(trigger.timezone) == "Asia/Kolkata"

    scheduler_wrapper.stop()


# ---------------------------------------------------------------------------
# Job body — calls run_preopen_check(), never raises
# ---------------------------------------------------------------------------

def test_preopen_shock_check_job_calls_run_preopen_check(monkeypatch):
    calls = []

    def _fake_run_preopen_check(tickers=None):
        calls.append(tickers)
        return {
            "severity": 0.85, "direction": "risk_off",
            "flagged": ["MARUTI"], "reforecasts": ["MARUTI"], "headline": "Crisis",
        }

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    scheduler = _scheduler()
    scheduler._preopen_shock_check_job()

    assert calls == [None]


def test_preopen_shock_check_job_handles_skipped_result(monkeypatch):
    def _fake_run_preopen_check(tickers=None):
        return {"severity": 0.0, "direction": "neutral", "flagged": [], "reforecasts": [], "skipped": "disabled"}

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _fake_run_preopen_check,
    )

    scheduler = _scheduler()
    # Must not raise.
    scheduler._preopen_shock_check_job()


def test_preopen_shock_check_job_non_fatal_on_exception(monkeypatch):
    def _boom(tickers=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "core.intelligence.rl.workflows.preopen_check.run_preopen_check",
        _boom,
    )

    scheduler = _scheduler()
    # Must not raise.
    scheduler._preopen_shock_check_job()
