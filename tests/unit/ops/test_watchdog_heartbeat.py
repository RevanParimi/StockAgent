"""Watchdog heartbeat — the liveness proof that makes silence trustworthy."""
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog import checks as C
from core.ops.watchdog import runner as R
from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.registry import Milestone

IST = ZoneInfo("Asia/Kolkata")

SATISFIED_YAML = """
milestones:
  - id: a
    kind: milestone
    title: "Atlas"
    check: atlas_cutover_pending
"""


def _entries():
    return [Milestone(id="a", kind="milestone", title="Atlas", check="c1"),
            Milestone(id="b", kind="invariant", title="Registry", check="c2")]


def test_heartbeat_lists_every_entry_and_state():
    results = {"a": CheckResult("pending", "not done"),
               "b": CheckResult("satisfied", "in sync")}
    text = R.build_heartbeat(_entries(), results,
                             datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert "Atlas" in text and "Registry" in text
    assert "pending" in text and "satisfied" in text
    assert "2 entr" in text


def _wire(monkeypatch, tmp_path):
    reg = tmp_path / "milestones.yaml"
    reg.write_text(SATISFIED_YAML, encoding="utf-8")
    monkeypatch.setattr(R, "_REGISTRY_PATH", reg)
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(R, "_broadcast", lambda e, title: None)
    monkeypatch.setenv("ATLAS_ENABLED", "true")      # satisfied -> silent


def test_heartbeat_sent_on_sunday_only(tmp_path, monkeypatch):
    emails = []
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "_send_email", lambda subject, body: emails.append(subject))

    R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))   # Saturday
    assert emails == []
    R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))   # Sunday
    assert len(emails) == 1 and "heartbeat" in emails[0].lower()


def test_heartbeat_sent_even_when_nothing_is_due(tmp_path, monkeypatch):
    """Its whole job is to prove liveness on a quiet week."""
    emails = []
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "_send_email", lambda s, b: emails.append((s, b)))
    out = R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert out["notified"] == 0 and len(emails) == 1


def test_heartbeat_failure_does_not_break_the_run(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "_send_email",
                        lambda s, b: (_ for _ in ()).throw(RuntimeError("smtp")))
    out = R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 1        # no exception escaped


def test_heartbeat_still_sent_when_registry_is_broken(tmp_path, monkeypatch):
    """A broken registry is exactly when you must still hear from it."""
    emails = []
    reg = tmp_path / "milestones.yaml"
    reg.write_text("milestones: [{id: x}]", encoding="utf-8")
    monkeypatch.setattr(R, "_REGISTRY_PATH", reg)
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(R, "_broadcast", lambda e, title: None)
    monkeypatch.setattr(R, "_send_email", lambda s, b: emails.append((s, b)))
    R.run_watchdog(now=datetime(2026, 8, 16, 6, 30, tzinfo=IST))
    assert len(emails) == 1
    assert "could not be loaded" in emails[0][1]
