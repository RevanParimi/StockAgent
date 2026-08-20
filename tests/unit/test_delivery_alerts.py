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


# -- structured fields for the Inbox card (alert presentation, 2026-08-20) ---

def _structured():
    return AlertEvent(
        date="2026-08-19", kind="watchdog_atlas_c11_cutover_info", symbol="",
        message="[watchdog] Atlas C11 live cutover\n\nComes due on 2026-08-22.",
        severity="info", title="Atlas C11 live cutover",
        headline="Comes due on 2026-08-22 (3 day(s) away).",
        status="ETL already run and VALIDATED by the watchdog.",
        next_step="Set atlas.enabled: true in config.yaml and push.",
        docs="docs/superpowers/specs/2026-07-26-atlas.md")


def test_structured_fields_round_trip_through_the_sent_log(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}):
        emit_alerts([_structured()], sent_log=log)
    rec = load_recent_alerts(limit=1, sent_log=log)[0]
    assert rec["title"] == "Atlas C11 live cutover"
    assert rec["headline"].startswith("Comes due on 2026-08-22")
    assert rec["status"].startswith("ETL already run")
    assert rec["next_step"].startswith("Set atlas.enabled")
    assert rec["docs"].endswith("2026-07-26-atlas.md")


def test_producers_that_pass_only_a_message_still_work(tmp_path):
    """Every existing emitter (pipeline, ops_alerts, thresholds, index_watch)
    constructs AlertEvent with `message` alone. The new fields are additive."""
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}):
        emit_alerts([_ev()], sent_log=log)
    rec = load_recent_alerts(limit=1, sent_log=log)[0]
    assert rec["title"] == "" and rec["next_step"] == "" and rec["headline"] == ""


def test_structured_fields_do_not_change_dedupe(tmp_path):
    """Same rule as advice_ref: presentation must not alter what dedupes."""
    log = str(tmp_path / "alerts_sent.jsonl")
    twin = AlertEvent(date="2026-07-09", kind="advisor_exit", symbol="OLDCO",
                      message="stop breached", severity="critical",
                      title="different", status="different")
    assert twin.title == "different"        # the field is real, not dropped
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        first = emit_alerts([_ev()], sent_log=log)
        second = emit_alerts([twin], sent_log=log)
    assert first["emitted"] == 1 and second["emitted"] == 0
    assert m.call_count == 1


# -- HTML email body (alert presentation, 2026-08-20) ------------------------

def test_alert_html_renders_the_structured_parts():
    html = al.render_alerts_html([_structured()], "StockAgent ops alert")
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Atlas C11 live cutover" in html
    assert "Comes due on 2026-08-22" in html
    assert "Set atlas.enabled: true" in html
    assert "ETL already run" in html


def test_alert_html_escapes_untrusted_content():
    ev = AlertEvent(date="2026-08-19", kind="k", symbol="", severity="info",
                    message="x", title="<script>alert(1)</script>")
    html = al.render_alerts_html([ev], "t")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_alert_html_falls_back_to_message_for_legacy_rows():
    """Rows predating the structured fields must still render as themselves."""
    html = al.render_alerts_html([_ev()], "t")
    assert "stop breached" in html


def test_emit_passes_an_html_body_to_deliver(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "deliver", return_value={"delivered": True}) as m:
        emit_alerts([_structured()], sent_log=log)
    assert "Atlas C11 live cutover" in m.call_args.kwargs["html_body"]


def test_html_kill_switch_sends_text_only(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "_html_enabled", return_value=False), \
         patch.object(al, "deliver", return_value={"delivered": True}) as m:
        emit_alerts([_structured()], sent_log=log)
    assert m.call_args.kwargs.get("html_body") is None


def test_html_render_failure_never_blocks_the_text_alert(tmp_path):
    log = str(tmp_path / "alerts_sent.jsonl")
    with patch.object(al, "render_alerts_html", side_effect=RuntimeError("boom")), \
         patch.object(al, "deliver", return_value={"delivered": True}) as m:
        out = emit_alerts([_structured()], sent_log=log)
    assert out["emitted"] == 1 and out["delivered"] is True
    assert m.call_args.kwargs.get("html_body") is None
