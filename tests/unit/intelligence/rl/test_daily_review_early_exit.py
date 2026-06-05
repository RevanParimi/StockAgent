"""Tests for the early-exit guard in daily_review._should_skip_agent_rerun."""


def test_early_exit_when_direction_correct_and_error_small():
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    assert _should_skip_agent_rerun(direction_correct=True, price_error_pct=0.3, threshold=0.5) is True


def test_no_early_exit_when_direction_wrong():
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    assert _should_skip_agent_rerun(direction_correct=False, price_error_pct=0.2, threshold=0.5) is False


def test_no_early_exit_when_error_large():
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    assert _should_skip_agent_rerun(direction_correct=True, price_error_pct=1.5, threshold=0.5) is False


def test_no_early_exit_when_threshold_zero():
    """threshold=0.0 disables early exit entirely."""
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    assert _should_skip_agent_rerun(direction_correct=True, price_error_pct=0.1, threshold=0.0) is False


def test_early_exit_uses_absolute_value_of_error():
    """Negative price_error_pct (overshot downward) also qualifies for early exit."""
    from core.intelligence.rl.workflows.daily_review import _should_skip_agent_rerun
    assert _should_skip_agent_rerun(direction_correct=True, price_error_pct=-0.3, threshold=0.5) is True
