from unittest.mock import patch

import services.scheduler.python.scheduler as sched


def _scheduler():
    return sched.AutomobileScheduler()


def test_job_grades_then_evaluates_then_emits():
    s = _scheduler()
    with patch.object(sched, "grade_due", return_value={"graded": 3, "lanes": {}}) as g, \
         patch.object(sched, "build_audit_report", return_value={"verdict": "UNPROVEN"}) as b, \
         patch.object(sched, "evaluate_breaches", return_value=[{"rule": "r", "severity": "info", "message": "m"}]) as e, \
         patch.object(sched, "emit_breaches", return_value={"emitted": 1}) as m:
        s._audit_nightly_job()
    assert g.call_count == 1 and b.call_count == 1
    assert e.call_count == 1 and m.call_count == 1


def test_job_never_raises_when_grading_fails():
    s = _scheduler()
    with patch.object(sched, "grade_due", side_effect=RuntimeError("prices down")), \
         patch.object(sched, "emit_breaches") as m:
        s._audit_nightly_job()      # must not raise
    assert m.call_count == 0


def test_job_reports_partial_output_to_the_watchdog():
    """The auditor is itself watched: a run where prices failed must surface
    as a partial output, not as a quietly smaller report."""
    s = _scheduler()
    with patch.object(sched, "grade_due",
                      return_value={"graded": 8, "skipped_unpriceable": 4,
                                    "already_present": 0, "lanes": {}}), \
         patch.object(sched, "build_audit_report", return_value={"verdict": "UNPROVEN"}), \
         patch.object(sched, "evaluate_breaches", return_value=[]), \
         patch("core.delivery.ops_alerts.alert_job_partial_output") as w:
        s._audit_nightly_job()
    w.assert_called_once_with("audit_nightly", 8, 12)


def test_job_is_registered_in_the_scheduler_source():
    """Static check: start() needs a live event loop, so assert on the source
    the scheduler actually registers rather than standing one up."""
    from pathlib import Path
    src = Path(sched.__file__).read_text(encoding="utf-8")
    assert 'id="audit_nightly"' in src
    assert "audit.enabled" in src        # gated by the master switch
