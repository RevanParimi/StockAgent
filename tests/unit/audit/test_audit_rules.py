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


# -- switch pairs (2026-08-20) ----------------------------------------------

from core.audit.rules import is_switch_correct


@pytest.mark.parametrize("origin,dest,expected", [
    (-2.0, -20.0, False),   # the case the old grade got WRONG: origin fell, so
                            # is_correct() scored this SWITCH correct — but the
                            # destination fell ten times harder.
    (-20.0, -2.0, True),    # rotating genuinely helped
    (5.0, 9.0, True),       # both up, destination further
    (9.0, 5.0, False),      # both up, staying was better
    (3.0, 3.0, False),      # a dead heat is not a win; rotation has costs
])
def test_is_switch_correct_compares_the_pair(origin, dest, expected):
    assert is_switch_correct(origin, dest) is expected


def test_switch_lane_and_pair_fields_exist_on_the_outcome_row():
    from backend.shared.schemas.audit import AuditOutcome
    row = AuditOutcome(
        ref="switch:2026-08-20|OLD|NEW", lane="switch", user_id="u",
        symbol="OLD", issued_on="2026-08-20", horizon_td=10,
        graded_on="2026-09-03", entry_close=100.0, exit_close=98.0,
        return_pct=-2.0, bench_entry=1000.0, bench_exit=1000.0,
        bench_pct=0.0, excess_pct=-2.0, correct=False,
        graded_at="2026-09-03T00:00:00+00:00",
        switch_excess_pct=-20.0, candidate="NEW", miss_class="knowledge")
    assert row.lane == "switch" and row.candidate == "NEW"
    assert row.miss_class == "knowledge"
