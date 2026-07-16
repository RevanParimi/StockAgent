"""Audit Wave 1 (AUD-039) — ops alerts: LLM failure streak + zero-output jobs.

The 2026-07-11 incident: 887× OpenRouter 401 across every job, all jobs logged
"complete", zero alerts. These helpers make that day impossible to miss.
"""
import pytest

import core.delivery.ops_alerts as ops


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "_STATE_PATH", tmp_path / "ops_alerts_state.json")
    sent = []
    monkeypatch.setattr(ops, "_emit", lambda kind, message: sent.append((kind, message)))
    yield sent


def test_llm_failure_streak_alerts_once(_isolated_state):
    sent = _isolated_state
    for _ in range(9):
        ops.record_llm_result(False)
    assert sent == []                       # below threshold
    ops.record_llm_result(False)            # 10th consecutive failure
    assert len(sent) == 1 and sent[0][0] == "llm_failure_streak"
    for _ in range(15):
        ops.record_llm_result(False)        # streak continues within throttle
    assert len(sent) == 1                   # throttled — no alert storm


def test_llm_success_resets_streak(_isolated_state):
    sent = _isolated_state
    for _ in range(9):
        ops.record_llm_result(False)
    ops.record_llm_result(True)             # reset
    for _ in range(9):
        ops.record_llm_result(False)
    assert sent == []                       # never reached 10 consecutively


def test_zero_output_job_alerts(_isolated_state):
    sent = _isolated_state
    ops.alert_job_zero_output("daily_review", produced=0, expected=16)
    assert len(sent) == 1 and sent[0][0] == "job_zero_output_daily_review"
    ops.alert_job_zero_output("daily_review", produced=5, expected=16)
    ops.alert_job_zero_output("discovery", produced=0, expected=0)   # nothing expected
    assert len(sent) == 1


def test_helpers_never_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(ops, "_STATE_PATH", tmp_path / "nested" / "state.json")

    def boom(*a, **k):
        raise RuntimeError("delivery down")
    monkeypatch.setattr(ops, "_emit", boom)
    for _ in range(12):
        ops.record_llm_result(False)        # must not raise even when emit fails
    ops.alert_job_zero_output("x", produced=0, expected=5)


def test_partial_output_job_alerts_warning(_isolated_state, monkeypatch):
    """AUD-090b: 13/16 after a harvest timeout was invisible — zero-output only
    fires at produced==0."""
    import core.delivery.alerts as al
    sent = []
    monkeypatch.setattr(al, "emit_alerts",
                        lambda events, **kw: sent.append(events[0]) or {"emitted": 1})
    ops.alert_job_partial_output("daily_review", produced=13, expected=16)
    assert len(sent) == 1
    assert sent[0].kind == "job_partial_output_daily_review"
    assert sent[0].severity == "warning"
    assert "13/16" in sent[0].message


def test_partial_output_silent_on_full_zero_or_empty(_isolated_state, monkeypatch):
    import core.delivery.alerts as al
    sent = []
    monkeypatch.setattr(al, "emit_alerts",
                        lambda events, **kw: sent.append(events[0]) or {"emitted": 1})
    ops.alert_job_partial_output("j", produced=16, expected=16)   # full — silent
    ops.alert_job_partial_output("j", produced=0, expected=16)    # zero-output's job
    ops.alert_job_partial_output("j", produced=3, expected=0)     # nothing expected
    assert sent == []


def test_job_crashed_alert(_isolated_state):
    sent = _isolated_state
    ops.alert_job_crashed("rl_daily_review", "TimeoutError: 3 futures unfinished")
    assert len(sent) == 1 and sent[0][0] == "job_crashed_rl_daily_review"
    assert "TimeoutError" in sent[0][1]


def test_new_helpers_never_raise(monkeypatch):
    import core.delivery.alerts as al

    def boom(*a, **k):
        raise RuntimeError("delivery down")
    monkeypatch.setattr(al, "emit_alerts", boom)
    monkeypatch.setattr(ops, "_emit", boom)
    ops.alert_job_partial_output("j", produced=1, expected=5)   # must not raise
    ops.alert_job_crashed("j", "boom")                          # must not raise
