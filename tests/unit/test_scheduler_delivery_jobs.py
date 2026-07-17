"""Compass Phase C — scheduler Jobs 13/14 registration + preopen alert hook."""
from unittest.mock import patch

from core.config import settings
from services.scheduler.python.scheduler import AutomobileScheduler


def _job_ids(sched):
    return {j.id for j in sched._scheduler.get_jobs()}


def test_delivery_jobs_registered_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    ids = _job_ids(AutomobileScheduler())
    assert "morning_brief" in ids and "weekly_review" in ids


def test_delivery_jobs_absent_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", False, raising=False)
    ids = _job_ids(AutomobileScheduler())
    assert "morning_brief" not in ids and "weekly_review" not in ids


def test_morning_brief_cron_is_0850_ist(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    sched = AutomobileScheduler()
    job = sched._scheduler.get_job("morning_brief")
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "8" and fields["minute"] == "50"
    wk = sched._scheduler.get_job("weekly_review")
    wfields = {f.name: str(f) for f in wk.trigger.fields}
    assert wfields["day_of_week"] == "sun" and wfields["hour"] == "18"


def test_nightly_backup_job_registered_at_2330_ist():
    """AUD-088: Job 15 — nightly data backup, always on (local rotation is free)."""
    sched = AutomobileScheduler()
    job = sched._scheduler.get_job("data_backup_nightly")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "23" and fields["minute"] == "30"


def test_backup_job_runs_run_backup_job(monkeypatch):
    sched = AutomobileScheduler()
    with patch("services.data.backup.run_backup_job",
               return_value={"archive": "x.zip", "bytes": 1, "emailed": True, "pruned": 0}) as m:
        sched._backup_job()
    assert m.called


def test_preopen_job_emits_reforecast_alerts(monkeypatch):
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    sched = AutomobileScheduler()
    result = {"severity": 0.9, "direction": "risk_off",
              "flagged": ["MARUTI"], "reforecasts": ["MARUTI"]}
    with patch("core.intelligence.rl.workflows.preopen_check.run_preopen_check",
               return_value=result), \
         patch("core.delivery.alerts.emit_alerts") as m_emit:
        sched._preopen_shock_check_job()
    assert m_emit.called
    events = m_emit.call_args.args[0]
    assert events[0].kind == "preopen_reforecast" and events[0].symbol == "MARUTI"
