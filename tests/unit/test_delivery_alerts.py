# tests/unit/test_delivery_alerts.py
"""Compass Phase C — deduped alert engine (spec §7 event alerts)."""
import json
from unittest.mock import patch

import core.delivery.alerts as al
from core.delivery.alerts import AlertEvent, emit_alerts, load_recent_alerts


def _ev(kind="advisor_exit", symbol="OLDCO", msg="stop breached"):
    return AlertEvent(date="2026-07-09", kind=kind, symbol=symbol,
                      message=msg, severity="critical")


def test_emit_delivers_once_and_dedupes(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out1 = emit_alerts([_ev()], sent_log=log)
        out2 = emit_alerts([_ev()], sent_log=log)          # same key -> deduped
    assert out1["emitted"] == 1 and out2["emitted"] == 0
    assert m.call_count == 1
    body = m.call_args.args[1]
    assert "OLDCO" in body and "stop breached" in body


def test_emit_bundles_multiple_events_into_one_send(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    events = [_ev(), _ev(kind="shelf_add", symbol="NEWCO", msg="new idea")]
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out = emit_alerts(events, sent_log=log)
    assert out["emitted"] == 2 and m.call_count == 1


def test_empty_or_fully_duplicate_batch_skips_delivery(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        assert emit_alerts([], sent_log=log)["emitted"] == 0
    assert m.call_count == 0


def test_load_recent_alerts_tail(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}):
        emit_alerts([_ev(symbol=f"S{i}") for i in range(5)], sent_log=log)
    recent = load_recent_alerts(limit=3, sent_log=log)
    assert len(recent) == 3
    # newest first — the Inbox renders this list top-to-bottom
    assert recent[0]["symbol"] == "S4"
    assert recent[-1]["symbol"] == "S2"


def test_emit_never_raises_on_delivery_failure(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", side_effect=RuntimeError("channel down")):
        out = emit_alerts([_ev()], sent_log=log)
    assert out["emitted"] == 1 and out["delivered"] is False


def test_undelivered_alert_retries_next_emit_then_dedupes(tmp_path):
    """AUD-085 rider: appending the sent-log BEFORE the outcome cemented failed
    sends — after the user subscribes, the same-day alert must go out."""
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver",
                      return_value={"delivered": False, "push": 0, "email": 0}):
        assert emit_alerts([_ev()], sent_log=log)["emitted"] == 1
    with patch.object(al, "deliver",
                      return_value={"delivered": True, "push": 1, "email": 0}) as m:
        out2 = emit_alerts([_ev()], sent_log=log)   # transport appeared → retry
        out3 = emit_alerts([_ev()], sent_log=log)   # delivered → now dedupes
    assert out2["emitted"] == 1 and out2["delivered"] is True
    assert out3["emitted"] == 0
    assert m.call_count == 1


def test_legacy_records_without_delivered_key_still_dedupe(tmp_path):
    """Records written before the delivered flag existed are treated as sent."""
    log = tmp_path / "alerts_sent.jsonl"
    log.write_text(json.dumps({"date": "2026-07-09", "kind": "advisor_exit",
                               "symbol": "OLDCO", "user_id": ""}) + "\n",
                   encoding="utf-8")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out = emit_alerts([_ev()], sent_log=str(log))
    assert out["emitted"] == 0 and m.call_count == 0


def test_emit_same_event_different_users_both_deliver(tmp_path):
    """Dedupe is user-aware: emits are per-user (brief.py/pipeline.py), so
    the same event for two different users must not suppress each other."""
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out_a = emit_alerts([_ev()], user_id="a", sent_log=log)
        out_b = emit_alerts([_ev()], user_id="b", sent_log=log)
    assert out_a["emitted"] == 1 and out_b["emitted"] == 1
    assert m.call_count == 2


def test_emit_same_event_same_user_still_dedupes(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out1 = emit_alerts([_ev()], user_id="a", sent_log=log)
        out2 = emit_alerts([_ev()], user_id="a", sent_log=log)
    assert out1["emitted"] == 1 and out2["emitted"] == 0
    assert m.call_count == 1


def test_emit_alerts_delivers_inbox_deeplink(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(al, "deliver",
                        lambda *a, **k: captured.update(k) or {"delivered": True})
    al.emit_alerts(
        [al.AlertEvent(date="2026-07-22", kind="test", symbol="X",
                       message="m", severity="warning")],
        user_id="u1", sent_log=str(tmp_path / "sent.jsonl"))
    assert captured["url"] == "/#/inbox/alerts"


def test_alert_event_advice_ref_defaults_empty_and_not_in_dedupe_key():
    from core.delivery.alerts import AlertEvent
    plain = AlertEvent(date="2026-07-17", kind="advisor_exit", symbol="MARUTI",
                       message="m", severity="warning")
    tagged = plain.model_copy(update={"advice_ref": "2026-07-17|MARUTI|abc"})
    assert plain.advice_ref == ""
    # dedupe must be unaffected — adding provenance must not re-notify
    assert plain.key() == tagged.key()
