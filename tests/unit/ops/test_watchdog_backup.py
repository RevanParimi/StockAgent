"""SA-007: the watchdog makes a missing or unproven backup visible."""
import base64
import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.ops.watchdog import checks as C
from core.ops.watchdog.registry import load_registry
from services.data import backup

KEY = base64.b64encode(bytes(range(32))).decode()


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def _status(tmp_path, monkeypatch, **overrides):
    status = {"last_run_at": _ago(7), "archive": "stockagent-backup-20260929-180000.zip",
              "drill": {"ok": True, "errors": [], "warnings": []},
              "offsite": {"target": "s3", "confirmed": True, "reason": None},
              "last_offsite_confirmed_at": _ago(7)}
    status.update(overrides)
    (tmp_path / "backups").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backups" / "backup_status.json").write_text(json.dumps(status))
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    return C.run_check("backup_recoverable")


def test_registered_as_a_daily_invariant():
    entry = next(e for e in load_registry("config/milestones.yaml") if e.id == "backup_recoverable")
    assert entry.kind == "invariant" and entry.check == "backup_recoverable"
    assert entry.schedule == "daily"


def test_pending_before_any_backup_ran(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    r = C.run_check("backup_recoverable")
    assert r.state == "pending" and "No backup status yet" in r.detail


def test_satisfied_when_drilled_and_confirmed(tmp_path, monkeypatch):
    r = _status(tmp_path, monkeypatch)
    assert r.state == "satisfied" and "confirmed off-site" in r.detail


def test_pending_when_the_job_stopped(tmp_path, monkeypatch):
    r = _status(tmp_path, monkeypatch, last_run_at=_ago(40), last_offsite_confirmed_at=_ago(40))
    assert r.state == "pending" and "has stopped" in r.detail


def test_pending_when_the_drill_failed(tmp_path, monkeypatch):
    r = _status(tmp_path, monkeypatch,
                drill={"ok": False, "errors": ["users.db: schema differs"], "warnings": []})
    assert r.state == "pending" and "FAILED its restore drill (users.db: schema differs)" in r.detail


def test_pending_when_no_copy_was_ever_confirmed(tmp_path, monkeypatch):
    reason = "not configured: BACKUP_OFFSITE_TARGET is unset"
    r = _status(tmp_path, monkeypatch, last_offsite_confirmed_at=None,
                offsite={"target": None, "confirmed": False, "reason": reason})
    assert r.state == "pending"
    assert "No off-site copy has ever been confirmed" in r.detail and reason in r.detail
    # The owner deferred the bucket (2026-09-29): remind weekly, not daily.
    assert r.repeat_days == 7 and "repeats weekly" in r.detail


def test_a_configured_target_that_never_worked_warns_daily(tmp_path, monkeypatch):
    """A half-done setup (target set, key missing) is a fault, not a deferral."""
    r = _status(tmp_path, monkeypatch, last_offsite_confirmed_at=None,
                offsite={"target": "s3", "confirmed": False,
                         "reason": "BACKUP_ENCRYPTION_KEY is unset; an unencrypted off-site "
                                   "copy is refused"})
    assert r.state == "pending" and r.repeat_days == 1
    assert "No off-site copy has ever been confirmed (BACKUP_ENCRYPTION_KEY is unset" in r.detail


def test_flagged_data_warns_daily_even_without_a_target(tmp_path, monkeypatch):
    """Deferring the bucket must not slow down a rewritten-ledger warning."""
    warning = "ledger portfolio/primary/transactions.jsonl was rewritten since x.zip"
    r = _status(tmp_path, monkeypatch, last_offsite_confirmed_at=None,
                drill={"ok": True, "errors": [], "warnings": [warning]},
                offsite={"target": None, "confirmed": False,
                         "reason": "not configured: BACKUP_OFFSITE_TARGET is unset"})
    assert r.state == "pending" and r.repeat_days == 1
    assert warning in r.detail and "no off-site target is configured" in r.detail


_NO_TARGET = {"target": None, "confirmed": False,
              "reason": "not configured: BACKUP_OFFSITE_TARGET is unset"}


@pytest.mark.parametrize("state", [
    {"drill": {"ok": False, "errors": ["users.db: schema differs"], "warnings": []},
     "last_offsite_confirmed_at": None},                          # the drill failed
    {"last_run_at": _ago(40), "last_offsite_confirmed_at": None},  # the job stopped
    {"last_offsite_confirmed_at": _ago(31)},                       # target unset after copies existed
])
def test_every_real_failure_stays_daily_without_a_target_too(tmp_path, monkeypatch, state):
    r = _status(tmp_path, monkeypatch, offsite=_NO_TARGET, **state)
    assert r.state == "pending" and r.repeat_days == 1, r.detail


def test_weekly_reminder_through_the_real_registry_and_ladder(tmp_path, monkeypatch):
    """The registry entry, the check and the engine together: with no target the
    owner hears on day 0 and day 7; a failed drill on day 8 warns that day."""
    from datetime import date as _date

    from core.ops.watchdog.engine import evaluate
    from zoneinfo import ZoneInfo
    entry = next(e for e in load_registry("config/milestones.yaml") if e.id == "backup_recoverable")
    unconfigured = {"last_offsite_confirmed_at": None,
                    "offsite": {"target": None, "confirmed": False,
                                "reason": "not configured: BACKUP_OFFSITE_TARGET is unset"}}
    failed = dict(unconfigured, drill={"ok": False, "errors": ["users.db: schema differs"],
                                       "warnings": []})
    state, fired = {}, []
    for day in range(10):
        r = _status(tmp_path, monkeypatch, **(failed if day == 8 else unconfigured))
        now = datetime.combine(_date(2026, 10, 1 + day), datetime.min.time(),
                               tzinfo=ZoneInfo("Asia/Kolkata")).replace(hour=6, minute=30)
        notes, state = evaluate([entry], {entry.id: r}, now, state)
        if notes:
            fired.append(day)
    assert fired == [0, 7, 8]


def test_pending_the_first_night_a_copy_is_missed(tmp_path, monkeypatch):
    """One failed night is reported the next morning, not after 36 hours."""
    r = _status(tmp_path, monkeypatch, last_offsite_confirmed_at=_ago(31),
                offsite={"target": "s3", "confirmed": False, "reason": "PUT x: HTTP 403 AccessDenied"})
    assert r.state == "pending"
    assert "not confirmed (PUT x: HTTP 403 AccessDenied)" in r.detail and "31h old" in r.detail


def test_pending_when_the_drill_flagged_the_data(tmp_path, monkeypatch):
    warning = "ledger portfolio/primary/transactions.jsonl shrank from 300 to 100 bytes"
    r = _status(tmp_path, monkeypatch, drill={"ok": True, "errors": [], "warnings": [warning]})
    assert r.state == "pending" and warning in r.detail


def test_unreadable_status_notifies_as_unknown(tmp_path, monkeypatch):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "backup_status.json").write_text("{not json")
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    assert C.run_check("backup_recoverable").state == "unknown"


@pytest.fixture()
def clock(monkeypatch):
    base = datetime.now(timezone.utc).replace(microsecond=0)
    ticks = itertools.count()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(seconds=next(ticks))
    monkeypatch.setattr(backup, "datetime", Clock)


def test_nightly_job_to_watchdog_end_to_end(tmp_path, monkeypatch, clock):
    data = tmp_path / "data"
    (data / "portfolio" / "primary").mkdir(parents=True)
    (data / "portfolio" / "primary" / "transactions.jsonl").write_text('{"t": 1}\n')
    monkeypatch.setattr("core.delivery.channels.send_email", lambda *a, **k: False)
    monkeypatch.setattr(C, "_DATA_DIR", data)
    settings = {"BACKUP_OFFSITE_TARGET": "dir", "BACKUP_ENCRYPTION_KEY": KEY,
                "BACKUP_OFFSITE_DIR": str(tmp_path / "second-disk")}
    for name, value in settings.items():
        monkeypatch.setattr(f"core.config.settings.{name}", value, raising=False)

    backup.run_backup_job(data_dir=data)
    assert C.run_check("backup_recoverable").state == "satisfied"

    # Next night the target is misconfigured onto the volume itself.
    monkeypatch.setattr("core.config.settings.BACKUP_OFFSITE_DIR", str(data / "copy"), raising=False)
    backup.run_backup_job(data_dir=data)
    r = C.run_check("backup_recoverable")
    assert r.state == "pending" and "not off-site" in r.detail
    status = json.loads((data / "backups" / "backup_status.json").read_text())
    assert status["last_offsite_confirmed_at"] is not None          # the earlier copy is remembered
