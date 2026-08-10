"""Watchdog runner — state persistence, delivery, and failure containment."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog import runner as R

IST = ZoneInfo("Asia/Kolkata")

ATLAS_YAML = """
milestones:
  - id: atlas_c11_cutover
    kind: milestone
    title: "Atlas C11 live cutover"
    check: atlas_cutover_pending
    window: {weekdays: [sat, sun]}
    deadline: 2026-08-16
    action: "Set ATLAS_ENABLED=true."
"""


def _reg(tmp_path, body):
    p = tmp_path / "milestones.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def _clean_preflight(tmp_path):
    (tmp_path / "portfolio").mkdir(exist_ok=True)
    (tmp_path / "portfolio" / "primary").mkdir(exist_ok=True)


def _wire(monkeypatch, tmp_path, yaml_body=ATLAS_YAML):
    from core.ops.watchdog import checks as C
    monkeypatch.setattr(R, "_REGISTRY_PATH", _reg(tmp_path, yaml_body))
    monkeypatch.setattr(R, "_STATE_PATH", tmp_path / "watchdog_state.json")
    monkeypatch.setattr(C, "_DATA_DIR", tmp_path)
    monkeypatch.delenv("ATLAS_ENABLED", raising=False)
    _clean_preflight(tmp_path)


def test_emits_and_persists_state(tmp_path, monkeypatch):
    sent = []
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))

    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 1 and out["notified"] == 1
    assert sent and sent[0][0].severity == "warning"
    assert "atlas_c11_cutover" in sent[0][0].kind
    state = json.loads((tmp_path / "watchdog_state.json").read_text())
    assert state["entries"]["atlas_c11_cutover"]["last_level"] == "warning"


def test_second_run_same_day_is_silent(tmp_path, monkeypatch):
    sent = []
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))

    now = datetime(2026, 8, 15, 6, 30, tzinfo=IST)
    R.run_watchdog(now=now)
    out2 = R.run_watchdog(now=now)
    assert out2["notified"] == 0 and len(sent) == 1


def test_broken_registry_alerts_instead_of_raising(tmp_path, monkeypatch):
    sent = []
    _wire(monkeypatch, tmp_path, "milestones: [{id: x}]")
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))
    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["evaluated"] == 0
    assert sent and sent[0][0].severity == "critical"
    assert "registry" in sent[0][0].message.lower()


def test_delivery_failure_does_not_raise(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(
        R, "_broadcast",
        lambda events, title: (_ for _ in ()).throw(RuntimeError("smtp down")))
    out = R.run_watchdog(now=datetime(2026, 8, 15, 6, 30, tzinfo=IST))
    assert out["notified"] == 0            # send failed, but no exception


def test_state_not_advanced_when_send_fails(tmp_path, monkeypatch):
    """A dropped notification must be retried tomorrow, not marked as sent."""
    _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(
        R, "_broadcast",
        lambda events, title: (_ for _ in ()).throw(RuntimeError("down")))
    now = datetime(2026, 8, 15, 6, 30, tzinfo=IST)
    R.run_watchdog(now=now)

    sent = []
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.append(events))
    out = R.run_watchdog(now=now)
    assert out["notified"] == 1 and sent
