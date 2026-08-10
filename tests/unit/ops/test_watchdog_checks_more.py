"""Watchdog standing invariants — deploy drift, quota rollover, scorecard, audit grading."""
import json
from datetime import date

from core.ops.watchdog import checks as C


class TestRegistryIsCurrent:
    """Compares the registry FILE, not the commit SHA: holding unrelated
    commits back is normal here, so a SHA check would warn every day."""

    def test_satisfied_when_identical(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: "milestones: []\n")
        assert C.run_check("registry_is_current").state == "satisfied"

    def test_satisfied_despite_line_ending_and_trailing_space_noise(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []   \r\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: "milestones: []\n\n")
        assert C.run_check("registry_is_current").state == "satisfied"

    def test_pending_when_origin_has_a_new_milestone(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text",
                            lambda: "milestones:\n  - {id: new}\n")
        r = C.run_check("registry_is_current")
        assert r.state == "pending" and "not deployed" in r.detail

    def test_unknown_when_github_unreachable(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: "milestones: []\n")
        monkeypatch.setattr(C, "_github_registry_text", lambda: None)
        assert C.run_check("registry_is_current").state == "unknown"

    def test_unknown_when_local_unreadable(self, monkeypatch):
        monkeypatch.setattr(C, "_local_registry_text", lambda: None)
        monkeypatch.setattr(C, "_github_registry_text", lambda: "x")
        assert C.run_check("registry_is_current").state == "unknown"

    def test_network_failure_becomes_unknown_not_a_crash(self, monkeypatch):
        def boom():
            raise OSError("dns failure")
        monkeypatch.setattr(C, "_local_registry_text", lambda: "x")
        monkeypatch.setattr(C, "_github_registry_text", boom)
        assert C.run_check("registry_is_current").state == "unknown"


class TestSerperRollover:
    def test_satisfied_when_month_current(self, monkeypatch):
        monkeypatch.setattr(C, "_today", lambda: date(2026, 8, 10))
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": "2026-08"})
        assert C.run_check("serper_counter_current_month").state == "satisfied"

    def test_pending_when_month_stale(self, monkeypatch):
        monkeypatch.setattr(C, "_today", lambda: date(2026, 8, 10))
        monkeypatch.setattr(C, "_api_usage", lambda: {"month": "2026-07"})
        r = C.run_check("serper_counter_current_month")
        assert r.state == "pending" and "2026-07" in r.detail


class TestScorecardWritten:
    def test_satisfied_when_previous_month_file_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        (tmp_path / "2026-08_scorecard.json").write_text("{}")
        assert C.run_check("monthly_scorecard_written").state == "satisfied"

    def test_pending_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2026, 9, 3))
        r = C.run_check("monthly_scorecard_written")
        assert r.state == "pending" and "2026-08" in r.detail

    def test_january_looks_back_to_previous_december(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C, "_scorecard_dir", lambda: tmp_path)
        monkeypatch.setattr(C, "_today", lambda: date(2027, 1, 5))
        r = C.run_check("monthly_scorecard_written")
        assert "2026-12" in r.detail


class TestAuditGradedWhenDue:
    def _write(self, tmp_path, monkeypatch, payload, today=date(2026, 8, 10)):
        p = tmp_path / "audit_last_run.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", p)
        monkeypatch.setattr(C, "_today", lambda: today)

    def test_pending_when_rows_exist_but_none_graded(self, tmp_path, monkeypatch):
        """The 2026-08-07 0/119 signature."""
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 0,
            "skipped_unpriceable": 0, "pending_rows": 119})
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "119" in r.detail

    def test_satisfied_when_carried_forward(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 119,
            "pending_rows": 119})
        assert C.run_check("audit_graded_when_due").state == "satisfied"

    def test_satisfied_when_nothing_to_do(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-08-10", "graded": 0, "already_present": 0,
            "pending_rows": 0})
        assert C.run_check("audit_graded_when_due").state == "satisfied"

    def test_pending_when_nightly_has_gone_stale(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "date": "2026-01-01", "graded": 5, "already_present": 0,
            "pending_rows": 5})
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "stopped running" in r.detail

    def test_pending_when_no_summary_file_yet(self, tmp_path, monkeypatch):
        monkeypatch.setattr(C, "_AUDIT_RUN_PATH", tmp_path / "absent.json")
        r = C.run_check("audit_graded_when_due")
        assert r.state == "pending" and "not completed" in r.detail


def test_manual_confirmation_stays_pending():
    r = C.run_check("manual_confirmation")
    assert r.state == "pending"


def test_every_registry_check_name_is_registered():
    """A milestones.yaml entry naming a check that does not exist would only
    surface at 06:30 as an 'unknown' alert. Catch it at test time instead."""
    from core.ops.watchdog.registry import load_registry
    for entry in load_registry():
        assert entry.check in C.CHECKS, f"{entry.id}: unregistered check {entry.check}"


def test_every_registry_prep_name_is_registered():
    from core.ops.watchdog.prep import PREPS
    from core.ops.watchdog.registry import load_registry
    for entry in load_registry():
        if entry.prep:
            assert entry.prep in PREPS, f"{entry.id}: unregistered prep {entry.prep}"
