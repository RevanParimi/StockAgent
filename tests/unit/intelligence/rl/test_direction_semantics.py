"""tests/unit/intelligence/rl/test_direction_semantics.py — AUD-060 fix-forward."""
from core.intelligence.rl.agents.feedback_agent import (
    classify_direction, is_direction_correct,
)


def test_neutral_correct_only_when_flat():
    assert is_direction_correct("NEUTRAL", "FLAT") is True
    assert is_direction_correct("NEUTRAL", "UP") is False
    assert is_direction_correct("NEUTRAL", "DOWN") is False


def test_directional_verdicts_unchanged():
    assert is_direction_correct("BUY", "UP") is True
    assert is_direction_correct("STRONG BUY", "UP") is True
    assert is_direction_correct("BUY", "DOWN") is False
    assert is_direction_correct("SELL", "DOWN") is True
    assert is_direction_correct("STRONG SELL", "UP") is False
    assert is_direction_correct("sell", "DOWN") is True   # case-insensitive


def test_unknown_verdict_treated_like_neutral():
    # HOLD/garbage make no directional claim either — same flat rule
    assert is_direction_correct("HOLD", "FLAT") is True
    assert is_direction_correct("HOLD", "UP") is False


def test_rule_matches_synthetic_generator():
    """The synthetic generator has always used flat-only NEUTRAL credit —
    live and synthetic semantics must now agree (the AUD-060 defect was the
    disagreement)."""
    for actual in ("UP", "DOWN", "FLAT"):
        expected = (actual == "FLAT")
        assert is_direction_correct("NEUTRAL", actual) is expected


def test_classify_direction_flat_band_unchanged():
    # predicted 100, threshold ±0.3%: 100.2 flat, 100.4 up, 99.6 down
    assert classify_direction(100.2, 100.0) == "FLAT"
    assert classify_direction(100.4, 100.0) == "UP"
    assert classify_direction(99.6, 100.0) == "DOWN"
