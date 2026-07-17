"""tests/unit/test_alerts_wave_f.py — AUD-013 rotation + AUD-015 broadcast."""
import json

from core.delivery.alerts import (
    AlertEvent, alert_audience, emit_alerts, emit_alerts_broadcast,
)
from core.delivery.channels import PushStore


def _event(kind="test_kind", symbol="SYM"):
    return AlertEvent(date="2026-07-17", kind=kind, symbol=symbol,
                      message="msg", severity="info")


# ---- AUD-013: rotation ----

def test_sent_log_rotates_past_threshold(tmp_path):
    log = tmp_path / "alerts_sent.jsonl"
    rec = json.dumps({"date": "2026-01-01", "kind": "old", "symbol": "",
                      "user_id": "", "delivered": True})
    log.write_text("\n".join([rec] * 4001) + "\n", encoding="utf-8")
    emit_alerts([_event()], sent_log=str(log))
    lines = log.read_text(encoding="utf-8").splitlines()
    # rotated down to the keep-window plus the freshly appended record
    assert len(lines) == 2001


def test_sent_log_untouched_under_threshold(tmp_path):
    log = tmp_path / "alerts_sent.jsonl"
    rec = json.dumps({"date": "2026-01-01", "kind": "old", "symbol": "",
                      "user_id": "", "delivered": True})
    log.write_text("\n".join([rec] * 10) + "\n", encoding="utf-8")
    emit_alerts([_event()], sent_log=str(log))
    assert len(log.read_text(encoding="utf-8").splitlines()) == 11


# ---- AUD-015: audience + broadcast ----

def test_push_store_user_ids(tmp_path):
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    store.add({"endpoint": "https://e/2"}, user_id="bob")
    assert store.user_ids() == ["alice", "bob"]


def test_alert_audience_includes_default_and_sub_users(tmp_path, monkeypatch):
    from core.config import settings
    import core.delivery.alerts as alerts_mod
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    monkeypatch.setattr(alerts_mod, "_audience_push_store", lambda: store)
    audience = alert_audience()
    assert "alice" in audience
    assert settings.PORTFOLIO_DEFAULT_USER_ID in audience


def test_broadcast_emits_once_per_user(tmp_path, monkeypatch):
    import core.delivery.alerts as alerts_mod
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add({"endpoint": "https://e/1"}, user_id="alice")
    store.add({"endpoint": "https://e/2"}, user_id="bob")
    monkeypatch.setattr(alerts_mod, "_audience_push_store", lambda: store)
    log = tmp_path / "alerts_sent.jsonl"
    result = emit_alerts_broadcast([_event()], sent_log=str(log))
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    users = {r["user_id"] for r in recs}
    assert "alice" in users and "bob" in users
    assert result["emitted"] == len(users)   # one record per audience user


def test_system_alert_sites_broadcast():
    """The 6 system-level alert sites fan out to the whole audience (AUD-015)."""
    import inspect
    from core.delivery import ops_alerts, index_watch
    import core.discovery as discovery
    from core.portfolio import store as pstore, reconcile

    assert "emit_alerts_broadcast" in inspect.getsource(ops_alerts._emit)
    assert "emit_alerts_broadcast" in inspect.getsource(
        ops_alerts.alert_job_partial_output)
    assert "emit_alerts_broadcast" in inspect.getsource(index_watch)
    assert "emit_alerts_broadcast" in inspect.getsource(discovery)
    assert "emit_alerts_broadcast" in inspect.getsource(
        pstore.PortfolioStore._alert_quarantine)
    assert "emit_alerts_broadcast" in inspect.getsource(reconcile._alert)

    # preopen reforecast alert (scheduler job) is system-level too
    import services.scheduler.python.scheduler as sched
    src = inspect.getsource(sched)
    assert "emit_alerts_broadcast(" in src
    assert "import AlertEvent, emit_alerts\n" not in src
