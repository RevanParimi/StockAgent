"""Watchdog scheduler job — registration and failure containment."""
from unittest.mock import patch

from services.scheduler.python.scheduler import AutomobileScheduler


def test_job_registered_at_0630_ist():
    sched = AutomobileScheduler()._scheduler
    job = sched.get_job("ops_watchdog")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "6" and fields["minute"] == "30"
    assert str(job.trigger.timezone) == "Asia/Kolkata"


def test_job_never_raises_even_if_runner_explodes():
    """The watchdog must not take down the scheduler it shares a process with."""
    with patch("core.ops.watchdog.runner.run_watchdog",
               side_effect=RuntimeError("boom")):
        AutomobileScheduler()._watchdog_job()      # must not raise


def test_job_absent_when_disabled():
    with patch("services.scheduler.python.scheduler.cfg") as mock_cfg:
        mock_cfg.side_effect = lambda path, **kw: (
            False if path == "watchdog.enabled" else kw.get("fallback"))
        sched = AutomobileScheduler()._scheduler
        assert sched.get_job("ops_watchdog") is None
