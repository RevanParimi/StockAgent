"""
tests/unit/intelligence/rl/test_absurd_price_error.py
=====================================================
Guard against a broken INPUT being learned from as if it were a forecast miss.

Prod evidence (2026-08-24 investigation): TATAMOTORS 2026-06-01..06-11 ran with
`predicted_close ~5917-5925` against `actual ~372-396` — a ~15.5x gap, i.e. a
stale pre-split envelope ramping +0.99/day. All nine rows were classified
`magnitude` with `direction_correct=True`, so a corporate-action data fault was
fed into the weight adapter at a 0.25x penalty for nine consecutive sessions and
polluted `agent_accuracy.avg_error`. It self-healed on 06-12 and no row has
exceeded 50% since, but nothing would catch a recurrence.

A price error beyond `rl.absurd_price_error_pct` is not a forecast error — no
model predicts 15x wrong. It is a stale envelope, a split, or a bad fetch. Treat
it as `data_stale` (a NO_PENALTY miss type) and skip the weight update entirely
so the garbage row never reaches the learned state.
"""
from __future__ import annotations

import pytest

from tests.unit.intelligence.rl.test_shock_path import (
    REVIEW_DATE,
    SECTOR,
    TICKER,
    _fb_output,
    _patch_common,
    _setup_store,
)


def _run(dr, monkeypatch, tmp_path, actual_close, miss_type="model_bias"):
    """Run one review with a chosen actual close and FeedbackAgent verdict."""
    _setup_store(tmp_path)
    _patch_common(dr, monkeypatch, tmp_path, actual_close=actual_close)

    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(
        FeedbackAgent, "run",
        lambda self, fb_input, ledger: _fb_output(miss_type),
    )
    return dr.run_daily_review(TICKER, REVIEW_DATE, sector=SECTOR)


def test_absurd_price_error_is_reclassified_as_data_stale(tmp_path, monkeypatch):
    """predicted 100.0 vs actual 5.0 = -95%: a broken input, not a model miss."""
    import core.intelligence.rl.workflows.daily_review as dr

    summary = _run(dr, monkeypatch, tmp_path, actual_close=5.0,
                   miss_type="model_bias")

    assert summary["status"] == "completed"
    assert summary["miss_type"] == "data_stale"


def test_absurd_price_error_skips_the_weight_update(tmp_path, monkeypatch):
    """A garbage row must never reach the learned weights or agent_accuracy."""
    import core.intelligence.rl.workflows.daily_review as dr
    from core.intelligence.rl.agents.weight_adapter import WeightAdapter

    calls: list = []
    original = WeightAdapter.update

    def _spy(self, **kwargs):
        calls.append(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(WeightAdapter, "update", _spy)

    summary = _run(dr, monkeypatch, tmp_path, actual_close=5.0,
                   miss_type="model_bias")

    assert summary["status"] == "completed"
    assert calls == []


def test_ordinary_large_miss_is_left_alone(tmp_path, monkeypatch):
    """-20% is a real (bad) forecast. The guard must not swallow genuine misses."""
    import core.intelligence.rl.workflows.daily_review as dr

    summary = _run(dr, monkeypatch, tmp_path, actual_close=80.0,
                   miss_type="model_bias")

    assert summary["status"] == "completed"
    assert summary["miss_type"] == "model_bias"


def test_guard_can_be_disabled_by_raising_the_threshold(tmp_path, monkeypatch):
    """The threshold is a config knob, not a hardcoded constant."""
    import core.intelligence.rl.workflows.daily_review as dr

    monkeypatch.setattr(dr.settings, "RL_ABSURD_PRICE_ERROR_PCT", 1000.0)

    summary = _run(dr, monkeypatch, tmp_path, actual_close=5.0,
                   miss_type="model_bias")

    assert summary["status"] == "completed"
    assert summary["miss_type"] == "model_bias"
