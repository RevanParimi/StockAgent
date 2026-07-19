"""tests/unit/test_fallback_events.py — Wave I fallback observability.

Legacy-pool fallback engagements must leave a durable record (they cost
~6-8x the unified path's Serper credits) and be countable for
/scheduler/status.
"""
import json

import services.data.stores.fallback_events as fe


def _use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(fe, "_EVENTS_PATH", tmp_path / "fallback_events.jsonl")


def test_record_fallback_appends_row(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    fe.record_fallback("automobile", "MARUTI")
    row = json.loads((tmp_path / "fallback_events.jsonl").read_text().splitlines()[-1])
    assert row["sector"] == "automobile"
    assert row["ticker"] == "MARUTI"
    assert row["reason"] == "unified_analyst_failed"
    assert row["ts"]


def test_fallback_count_today(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    fe.record_fallback("automobile", "MARUTI")
    fe.record_fallback("it_sector", "TCS")
    path = tmp_path / "fallback_events.jsonl"
    with open(path, "a", encoding="utf-8") as fh:  # stale + corrupt rows ignored
        fh.write(json.dumps({"ts": "2020-01-01T00:00:00+00:00", "ticker": "OLD"}) + "\n")
        fh.write("NOT JSON\n")
    assert fe.fallback_count_today() == 2


def test_count_zero_when_absent(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert fe.fallback_count_today() == 0


def test_orchestrator_fallback_records_event():
    """The engagement point in _run_agents must call record_fallback."""
    import inspect
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
    src = inspect.getsource(BaseSectorOrchestrator._run_agents)
    assert "record_fallback" in src
