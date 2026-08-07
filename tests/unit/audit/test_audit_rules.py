import pytest

from core.audit.rules import excess, is_correct, pct_change


@pytest.mark.parametrize("verdict", ["HOLD", "ADD"])
def test_long_intent_correct_when_beating_benchmark(verdict):
    assert is_correct(verdict, 2.5) is True
    assert is_correct(verdict, 0.0) is True      # tie counts as correct
    assert is_correct(verdict, -2.5) is False


@pytest.mark.parametrize("verdict", ["TRIM", "EXIT", "SWITCH"])
def test_reduce_intent_correct_when_underperforming(verdict):
    assert is_correct(verdict, -2.5) is True
    assert is_correct(verdict, 0.0) is False     # tie: leaving gained nothing
    assert is_correct(verdict, 2.5) is False


def test_shelf_and_unknown_verdicts_are_never_scored():
    assert is_correct("", 5.0) is None
    assert is_correct("shelf_add", 5.0) is None
    assert is_correct("WHATEVER", -5.0) is None


def test_verdict_matching_is_case_and_space_insensitive():
    assert is_correct("  hold  ", 1.0) is True
    assert is_correct("exit", -1.0) is True


def test_pct_change():
    assert pct_change(100.0, 110.0) == 10.0
    assert pct_change(100.0, 90.0) == -10.0
    assert pct_change(100.0, 100.0) == 0.0


def test_pct_change_rejects_non_positive_entry():
    with pytest.raises(ValueError):
        pct_change(0.0, 110.0)
    with pytest.raises(ValueError):
        pct_change(-5.0, 110.0)


def test_excess_is_difference_of_percentages():
    assert excess(3.54, 1.18) == 2.36
    assert excess(-1.0, 4.0) == -5.0
