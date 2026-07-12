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
