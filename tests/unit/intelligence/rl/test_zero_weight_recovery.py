"""
tests/unit/intelligence/rl/test_zero_weight_recovery.py
=======================================================
An agent pinned at weight 0.0 must keep a route back.

Prod evidence (2026-08-24). `AgentAccuracy.hit_rate()` blends calibration at
`RL_CALIBRATION_WEIGHT` (0.5), and calibration hits are sparse in practice
(typically 1/7). That drags a directionally excellent agent down into the
(WEIGHT_PENALTY_HIT_RATE, WEIGHT_BOOST_HIT_RATE) = (0.40, 0.70) band, where
neither the boost nor the penalty branch fires. For an agent at a normal weight
that dead band is harmless hysteresis. For one already pinned at 0.0 it is
permanent silence: no boost to lift it, and no penalty because it is on the
floor already.

Measured on prod — agents at exactly 0.0, direction rate vs blended rate:

    KPITTECH   pattern_analysis  7/7 = 1.00 -> blended 0.57   stuck 25 versions
    TATAELXSI  pattern_analysis  6/7 = 0.86 -> blended 0.68   stuck 16 versions
    YESBANK    pattern_analysis  5/7 = 0.71 -> blended 0.48   stuck  6 versions

A 7-of-7 agent contributing nothing for 25 weight versions is not the adapter
correctly discounting a bad signal — it is a trapdoor. 0.0 is otherwise NOT
absorbing: 14 of 24 historical zero spells recovered in 2-30 versions. Only the
dead-band ones never do.

The escape is deliberately narrow: it reads the RAW direction hit rate, applies
only at exactly 0.0, and changes nothing for any agent above the floor.
"""
from __future__ import annotations

import pytest

from core.intelligence.rl.agents.weight_adapter import WeightAdapter
from core.schemas.feedback import AgentAccuracy, DailyFeedbackLog

AGENTS = ["pattern_analysis", "risk_macro"]


def _log() -> DailyFeedbackLog:
    return DailyFeedbackLog(ticker="TESTZERO", sector="automobile",
                            cycle_id="TESTZERO_2026-08", entries=[])


def _deltas(current_weights, accuracy):
    """Raw deltas, with the blamed-agent path deliberately out of the picture."""
    return WeightAdapter()._compute_deltas(
        accuracy=accuracy,
        feedback_log=_log(),
        todays_primary_miss="risk_macro",
        todays_miss_type="data_gap",          # NO_PENALTY: no bias branch
        agents=AGENTS,
        current_weights=current_weights,
    )


def _perfect_direction_poor_calibration() -> AgentAccuracy:
    """KPITTECH's real shape: 7/7 on direction, 1/7 on calibration.

    Blended = 0.5*1.00 + 0.5*0.143 = 0.57 -> inside the (0.40, 0.70) dead band.
    """
    return AgentAccuracy(direction_hits=7, total=7,
                         calibration_hits=1, calibration_total=7)


def test_the_dead_band_is_real_for_this_accuracy_shape():
    """Pin the precondition: this agent earns neither boost nor penalty."""
    acc = _perfect_direction_poor_calibration()
    assert acc.direction_hit_rate() == pytest.approx(1.0)
    assert 0.40 < acc.hit_rate() < 0.70


def test_zeroed_agent_with_excellent_direction_accuracy_gets_a_route_back():
    """The bug: at 0.0 the dead band means permanent silence."""
    deltas = _deltas(
        current_weights={"pattern_analysis": 0.0, "risk_macro": 1.0},
        accuracy={"pattern_analysis": _perfect_direction_poor_calibration()},
    )
    assert deltas["pattern_analysis"] > 0.0


def test_agent_above_the_floor_is_left_to_the_normal_dead_band():
    """The escape must not fire for a normally-weighted agent: no behaviour change."""
    deltas = _deltas(
        current_weights={"pattern_analysis": 0.11, "risk_macro": 0.89},
        accuracy={"pattern_analysis": _perfect_direction_poor_calibration()},
    )
    assert deltas["pattern_analysis"] == pytest.approx(0.0)


def test_zeroed_agent_that_is_genuinely_bad_stays_at_zero():
    """TVSMOTOR's shape: 0/7 on direction. Zeroing it was correct — keep it there."""
    deltas = _deltas(
        current_weights={"pattern_analysis": 0.0, "risk_macro": 1.0},
        accuracy={"pattern_analysis": AgentAccuracy(
            direction_hits=0, total=7, calibration_hits=2, calibration_total=7)},
    )
    assert deltas["pattern_analysis"] <= 0.0
