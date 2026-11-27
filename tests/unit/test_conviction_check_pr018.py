"""PR-018 — the monthly conviction check and its predeclared rule.

Every expected figure is worked out by hand in the comments. The rule, from the
card (docs/planning/PI-2026-09/stories/PR-018.md): conviction predicts when,
at 30 sessions, the 0.75-and-above group's mean excess is at least 2 points
over the 0.55-to-0.65 group's, each with 30 or more, at two monthly looks in a
row, and no row is counted in two looks.

First Sundays used here: 3 Jan, 7 Feb, 7 Mar, 4 Apr 2027.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from backend.shared.schemas.audit import AuditOutcome
from core.audit import ideas as I
from core.audit.report import build_report, render_section
from core.audit.store import AuditOutcomeStore
from core.portfolio import results as R
from core.portfolio.store import PortfolioStore

JAN, FEB, MAR, APR = date(2027, 1, 3), date(2027, 2, 7), date(2027, 3, 7), date(2027, 4, 4)


def test_the_months_used_here_are_first_sundays():
    for day in (JAN, FEB, MAR, APR):
        assert day.weekday() == 6 and day.day <= 7


def dive(name, excess, *, conviction=0.6, verdict="BUY", graded_on="2026-12-30", h=30,
         lane="dive", user="primary"):
    return AuditOutcome(ref=f"dive:2026-11-14|{name}", lane=lane, user_id=user, symbol=name,
                        verdict=verdict, issued_on="2026-11-14", horizon_td=h,
                        graded_on=graded_on, entry_close=100.0, exit_close=100.0 + excess,
                        return_pct=excess, bench_entry=1000.0, bench_exit=1000.0,
                        bench_pct=0.0, excess_pct=excess, correct=None, graded_at="x",
                        conviction=conviction)


def many(prefix, count, excess, conviction, **kw):
    return [dive(f"{prefix}{k}", excess, conviction=conviction, **kw) for k in range(count)]


def pair(prefix, *, top, low, n_top=30, n_low=30, graded_on="2026-12-30"):
    """`n_top` dives at 0.80 each gaining `top`, `n_low` at 0.60 each `low`."""
    return (many(f"{prefix}T", n_top, top, 0.80, graded_on=graded_on)
            + many(f"{prefix}L", n_low, low, 0.60, graded_on=graded_on))


class Months:
    """Run the check month by month the way the scorecard does: each month's
    row keeps its look, and the next month reads the stored rows."""

    def __init__(self):
        self.rows: list[AuditOutcome] = []
        self.stored: list[dict] = []

    def run(self, on: date, new_rows=()):
        self.rows += list(new_rows)
        monday = R.week_of(on).monday.isoformat()
        earlier, used, passed = I.stored_looks(self.stored, week_start=monday)
        check = I.conviction_check(self.rows, as_of=on, earlier=earlier, used=used,
                                   passed_before=passed)
        self.stored.append({"week_start": monday, "conviction_check": check})
        return check


# -- the groups -----------------------------------------------------------------

@pytest.mark.parametrize("conviction, verdict, group", [
    (0.00, "SELL", "rejected"),
    (0.40, "NEUTRAL", "rejected"),
    (0.5499, "BUY", "rejected"),          # a BUY under the floor is rejected
    (0.55, "BUY", "buy_055"),             # a boundary goes to the higher group
    (0.6499, "STRONG BUY", "buy_055"),
    (0.65, "BUY", "buy_065"),
    (0.7499, "BUY", "buy_065"),
    (0.75, "BUY", "buy_075"),
    (1.00, "strong buy", "buy_075"),
    (0.70, "NEUTRAL", ""),                # not a BUY at 0.55+: no group
    (0.80, "SELL", ""),
    (0.80, "", ""),                       # a seeded dive with no verdict
    (0.00, "INSUFFICIENT DATA", ""),      # no judgement
])
def test_each_dive_falls_in_one_group_at_the_conviction_it_was_issued_with(
        conviction, verdict, group):
    assert I.conviction_group(dive("A", 1.0, conviction=conviction, verdict=verdict)) == group


def test_only_dive_rows_are_grouped():
    for lane in ("bare", "shelf"):
        assert I.conviction_group(dive("A", 1.0, conviction=0.8, lane=lane)) == ""


def test_the_table_reads_30_sessions_the_first_row_of_a_dive_and_nothing_after_as_of():
    """Two dives at 0.60 (+1, +3: mean +2) count. Not counted: the same dive
    written again (+99), a 10-session grade, a grade after the week's end, a
    screen row."""
    rows = [dive("A", 1.0), dive("B", 3.0), dive("A", 99.0),
            dive("C", 50.0, h=10), dive("D", 50.0, graded_on="2027-01-04"),
            dive("E", 50.0, lane="screen")]
    table = I.conviction_table(rows, as_of=JAN)
    low = table["groups"]["buy_055"]
    assert (low["n"], low["mean_excess_pct"], low["judge"]) == (2, 2.0, I.TOO_FEW)
    assert table["graded_dives"] == 2
    assert [table["groups"][g]["n"] for g in ("rejected", "buy_065", "buy_075")] == [0, 0, 0]


def test_dives_in_no_group_are_counted_with_the_reason():
    rows = [dive("A", 1.0, verdict="NEUTRAL", conviction=0.70),
            dive("B", 1.0, verdict="", conviction=0.80),
            dive("C", 1.0, verdict="INSUFFICIENT DATA", conviction=0.0),
            dive("D", 1.0, verdict="NEUTRAL", conviction=0.40)]
    table = I.conviction_table(rows)
    assert (table["not_buy_at_floor"], table["verdict_not_recorded"], table["abstained"]) == \
        (1, 1, 1)
    assert table["groups"]["rejected"]["n"] == 1
    text = I.table_text(table)
    assert "In no group: 1 at 0.55 or more not rated a BUY, 1 with no recorded verdict, " \
           "1 with insufficient data." in text


# -- the rule: too few, pass, flat ---------------------------------------------

def test_29_in_one_group_is_too_few_for_a_look():
    check = Months().run(JAN, pair("a", top=9.0, low=0.0, n_top=29))
    assert check["look"] is None and check["looks"] == 0 and check["passed_on"] is None
    assert check["fresh"] == {"top": 29, "low": 30}
    line = I.conviction_line(check)
    assert "BUY at 0.75 and above: +9.00 (n 29, 29 stocks, too few to judge)" in line
    assert "BUY at 0.55 to under 0.65: +0.00 (n 30, 30 stocks)" in line
    assert "No look this month: it needs 30 BUY dives at 0.75 and above and 30 at 0.55 to " \
           "under 0.65 that no other look has read; there are 29 and 30." in line
    assert "The rule passed" not in line


def test_two_passing_looks_in_a_row_pass_the_rule():
    """The card's example: +4.1 (n 34) against +0.3 (n 41) is a gap of 3.8.
    The second look: +3.5 against +1.0, a gap of 2.5."""
    months = Months()
    first = months.run(JAN, pair("a", top=4.1, low=0.3, n_top=34, n_low=41))
    assert (first["look"]["passed"], first["look"]["gap_points"]) == (True, 3.8)
    assert (first["look"]["top"]["n"], first["look"]["low"]["n"]) == (34, 41)
    assert (first["streak"], first["passed_on"]) == (1, None)
    line = I.conviction_line(first)
    assert "This month's look: +4.10 (n 34, 34 stocks) against +0.30 (n 41, 41 stocks), " \
           "a gap of +3.80 points: passed. 1 of the 2 passes in a row the rule needs." in line
    assert "The rule passed" not in line

    second = months.run(FEB, pair("b", top=3.5, low=1.0, graded_on="2027-02-01"))
    assert (second["look"]["passed"], second["look"]["gap_points"]) == (True, 2.5)
    assert (second["streak"], second["passed_on"]) == (2, "2027-02-07")
    line = I.conviction_line(second)
    assert "The rule passed on 7 Feb 2027: by this rule, conviction predicts returns." in line
    assert "nothing changes until you do" in line
    assert "passes in a row the rule needs" not in line


def test_a_flat_gap_does_not_pass_and_at_300_dives_is_said_plainly():
    """Both groups +1.0: gap 0. With 239 more at 0.70 there are 299 graded
    dives: nothing said yet. One more makes 300."""
    months = Months()
    first = months.run(JAN, pair("a", top=1.0, low=1.0)
                       + many("m", 239, 1.0, 0.70))
    assert (first["look"]["passed"], first["look"]["gap_points"]) == (False, 0.0)
    assert (first["graded_dives"], first["long_run"]) == (299, None)
    assert "dives are graded" not in I.conviction_line(first)

    second = months.run(FEB, [dive("one-more", 1.0, conviction=0.70, graded_on="2027-02-01")])
    assert (second["graded_dives"], second["long_run"]) == \
        (300, {"state": "flat", "gap_points": 0.0})
    line = I.conviction_line(second)
    assert "300 dives are graded. Over all of them, BUY at 0.75 and above (n 30) against " \
           "BUY at 0.55 to under 0.65 (n 30) shows a gap of +0.00 points, short of the 2 the " \
           "rule asks: conviction is not shown to predict returns." in line
    assert "an independent challenge to every BUY, two runs that must agree, or a better " \
           "model." in line


def test_a_negative_gap_says_higher_conviction_did_worse():
    """Top -2.0 against low +1.0: gap -3.0."""
    check = Months().run(JAN, pair("a", top=-2.0, low=1.0) + many("m", 240, 0.0, 0.70))
    assert check["long_run"] == {"state": "negative", "gap_points": -3.0}
    assert "a gap of -3.00 points, so higher conviction did worse: conviction is not shown " \
           "to predict returns." in I.conviction_line(check)


def test_300_dives_with_a_thin_top_group_is_too_few_not_flat():
    check = Months().run(JAN, pair("a", top=1.0, low=1.0, n_top=12)
                         + many("m", 258, 1.0, 0.70))
    assert check["graded_dives"] == 300
    assert check["long_run"] == {"state": "too_few", "gap_points": None}
    line = I.conviction_line(check)
    assert "300 dives are graded, but BUY at 0.75 and above has 12 and BUY at 0.55 to " \
           "under 0.65 has 30: too few to judge whether conviction predicts." in line
    assert "higher conviction did worse" not in line and "short of the 2" not in line


def test_a_gap_over_the_margin_across_all_dives_says_nothing_about_flat():
    """300 dives, gap 5.0 over all: the card's plain statement is only for flat
    or negative; one passing look is not yet a pass."""
    check = Months().run(JAN, pair("a", top=6.0, low=1.0) + many("m", 240, 0.0, 0.70))
    assert (check["long_run"], check["passed_on"]) == (None, None)


@pytest.mark.parametrize("top, low, passed, shown", [
    (2.01, 0.01, True, 2.00),         # the floats differ by 1.9999999999999998
    (4.3, 2.3, True, 2.00),
    (2.0, 0.0, True, 2.00),
    (4.31, 2.3, True, 2.01),
    (4.294, 2.3, False, 1.99),        # prints +4.29 against +2.30
    (4.2951, 2.3049, True, 2.00),     # prints +4.30 against +2.30: judged as printed
    (4.2949, 2.3, False, 1.99),
])
def test_at_least_two_points_is_judged_on_the_means_the_line_prints(top, low, passed, shown):
    check = Months().run(JAN, pair("a", top=top, low=low))
    assert check["look"]["passed"] is passed
    assert check["look"]["gap_points"] == shown
    line = I.conviction_line(check)
    printed = re.search(r"This month's look: ([+-]\d+\.\d\d) \([^)]*\) against "
                        r"([+-]\d+\.\d\d) \([^)]*\), a gap of ([+-]\d+\.\d\d)", line)
    # the reader's own subtraction of the printed means gives the printed gap
    assert round(float(printed[1]) - float(printed[2]), 2) == float(printed[3]) == shown
    assert f"a gap of {shown:+.2f} points: {'passed' if passed else 'not passed'}." in line


def test_a_group_says_how_many_stocks_its_dives_are_of():
    """30 dives of 3 stocks, each dived ten times."""
    top = [dive(f"x{k}", 4.0, conviction=0.8) for k in range(30)]
    for k, row in enumerate(top):
        row.symbol = f"STOCK{k % 3}"
    check = Months().run(JAN, top + many("L", 30, 1.0, 0.60))
    assert (check["look"]["top"]["n"], check["look"]["top"]["stocks"]) == (30, 3)
    assert "BUY at 0.75 and above: +4.00 (n 30, 3 stocks)" in I.conviction_line(check)


def test_a_gap_just_below_zero_is_negative_not_short():
    """Top +0.5 against low +1.0: -0.5."""
    check = Months().run(JAN, pair("a", top=0.5, low=1.0) + many("m", 240, 0.0, 0.70))
    assert check["long_run"] == {"state": "negative", "gap_points": -0.5}
    assert "so higher conviction did worse" in I.conviction_line(check)


def test_no_flat_verdict_while_a_run_of_passes_is_open():
    """January: 100 and 100 both flat (a failed look) plus 100 at 0.70. February
    passes (+3.0 against 0.0), but over all dives the top is 90/130 = +0.69
    over the low 0.0: short of 2. A conclusion now would contradict the open
    run, so none is given."""
    months = Months()
    months.run(JAN, pair("a", top=0.0, low=0.0, n_top=100, n_low=100)
               + many("m", 100, 0.0, 0.70))
    check = months.run(FEB, pair("b", top=3.0, low=0.0, graded_on="2027-02-01"))
    assert (check["look"]["passed"], check["streak"], check["passed_on"]) == (True, 1, None)
    assert check["long_run"] == {"state": "flat", "gap_points": 0.69}
    line = I.conviction_line(check)
    assert "+0.69 points, short of the 2 the rule asks. The latest look passed, so there is " \
           "no conclusion until the next look." in line
    assert "For you to choose" not in line and "not shown to predict" not in line


def test_once_passed_no_flat_verdict_is_ever_added():
    """Two passes, then 300 flat dives that sink the gap over all of them."""
    months = Months()
    months.run(JAN, pair("a", top=4.0, low=1.0))
    months.run(FEB, pair("b", top=4.0, low=1.0, graded_on="2027-02-01"))
    check = months.run(MAR, pair("c", top=0.0, low=0.0, n_top=150, n_low=150,
                                 graded_on="2027-03-01"))
    assert check["graded_dives"] == 420 and check["long_run"] is None
    line = I.conviction_line(check)
    assert "The rule passed on 7 Feb 2027" in line
    assert "not shown to predict" not in line and "For you to choose" not in line


def test_the_pass_date_is_the_day_the_rule_first_passed():
    months = Months()
    months.run(JAN, pair("a", top=4.0, low=1.0))
    months.run(FEB, pair("b", top=4.0, low=1.0, graded_on="2027-02-01"))
    third = months.run(MAR, pair("c", top=4.0, low=1.0, graded_on="2027-03-01"))
    assert (third["passed_on"], third["streak"]) == ("2027-02-07", 3)


@pytest.mark.parametrize("third_passed", [True, False])
def test_the_looks_alone_give_the_first_day_two_passed_in_a_row(third_passed):
    """No stored pass date to lean on: the looks of January and February give
    7 Feb, whatever March's look did."""
    looks = [{"on": "2027-01-03", "passed": True}, {"on": "2027-02-07", "passed": True},
             {"on": "2027-03-07", "passed": third_passed}]
    check = I.conviction_check([], as_of=APR, earlier=looks)
    assert check["passed_on"] == "2027-02-07"
    assert check["streak"] == (3 if third_passed else 0)


def test_the_scorecard_carries_a_stored_pass_forward():
    """April's scorecard is given one stored row that says the rule passed."""
    stored = [{"week_start": "2027-03-01",
               "conviction_check": {"look": None, "passed_on": "2027-03-07"}}]
    row = _row_for(APR, [], conviction_scorecards=stored)
    assert row["conviction_check"]["passed_on"] == "2027-03-07"
    assert "The rule passed on 7 Mar 2027" in _line(row)


def test_a_week_built_late_cannot_withdraw_a_stored_pass():
    """January and March pass (February's week was not built), so the rule
    passes on 7 Mar. February is then built late, with a failing look of its
    own dives; April still says it passed."""
    months = Months()
    months.run(JAN, pair("a", top=4.0, low=1.0))
    march = months.run(MAR, pair("c", top=4.0, low=1.0, graded_on="2027-03-01"))
    assert march["passed_on"] == "2027-03-07"
    february = months.run(FEB, pair("b", top=0.0, low=1.0, graded_on="2027-02-01"))
    assert february["passed_on"] is None            # as of February it had not
    assert months.run(APR)["passed_on"] == "2027-03-07"


# -- no row counted in two looks ----------------------------------------------

def test_a_dive_a_look_has_read_is_never_read_by_another():
    months = Months()
    first = months.run(JAN, pair("a", top=4.0, low=1.0))
    assert len(first["look"]["refs"]) == 60

    # February: the same rows are all there is. No look, whatever the table says.
    second = months.run(FEB)
    assert second["look"] is None and second["fresh"] == {"top": 0, "low": 0}
    assert second["groups"]["buy_075"]["n"] == 30          # the table is over all dives
    assert (second["streak"], second["passed_on"]) == (1, None)
    line = I.conviction_line(second)
    assert "there are 0 and 0." in line                    # unread dives, not all dives
    assert "The last look, on 3 Jan 2027, passed." in line

    # March: 30 new at the top but only 29 new low ones is still no look ...
    third = months.run(MAR, pair("b", top=4.0, low=1.0, n_low=29, graded_on="2027-03-01"))
    assert third["look"] is None and third["fresh"] == {"top": 30, "low": 29}
    # ... April has the 30th: the look reads the 60 new dives and none of January's.
    fourth = months.run(APR, [dive("bL29", 1.0, graded_on="2027-04-01")])
    assert (fourth["look"]["top"]["n"], fourth["look"]["low"]["n"]) == (30, 30)
    assert not set(fourth["look"]["refs"]) & set(first["look"]["refs"])
    assert fourth["passed_on"] == "2027-04-04"


def test_a_grade_written_late_for_an_earlier_day_is_read_once_by_the_next_look():
    """A grade dated before January's look but written after it (a price that
    came late) is not in January's look and is in February's."""
    months = Months()
    january = months.run(JAN, pair("a", top=4.0, low=1.0))
    late = dive("late", 4.0, conviction=0.80, graded_on="2026-12-29")
    february = months.run(FEB, pair("b", top=4.0, low=1.0, n_top=29, graded_on="2027-02-01")
                          + [late])
    assert late.ref not in january["look"]["refs"]
    assert late.ref in february["look"]["refs"] and february["look"]["top"]["n"] == 30


def test_a_failed_look_starts_the_run_again():
    months = Months()
    assert months.run(JAN, pair("a", top=4.0, low=1.0))["streak"] == 1
    failed = months.run(FEB, pair("b", top=1.0, low=1.0, graded_on="2027-02-01"))
    assert (failed["streak"], failed["passed_on"]) == (0, None)
    third = months.run(MAR, pair("c", top=4.0, low=1.0, graded_on="2027-03-01"))
    assert (third["streak"], third["passed_on"]) == (1, None)
    fourth = months.run(APR, pair("d", top=4.0, low=1.0, graded_on="2027-04-01"))
    assert fourth["passed_on"] == "2027-04-04"


def test_a_pass_stays_recorded_and_a_later_failed_look_is_said():
    months = Months()
    months.run(JAN, pair("a", top=4.0, low=1.0))
    months.run(FEB, pair("b", top=4.0, low=1.0, graded_on="2027-02-01"))
    later = months.run(MAR, pair("c", top=0.0, low=1.0, graded_on="2027-03-01"))
    assert (later["passed_on"], later["streak"]) == ("2027-02-07", 0)
    line = I.conviction_line(later)
    assert "The rule passed on 7 Feb 2027" in line
    assert "The latest look, on 7 Mar 2027, did not pass." in line


def test_stored_looks_are_ordered_and_a_later_weeks_dives_are_never_reread():
    """A week built late must not read what a later week's look already did,
    nor count that later look in its own run."""
    def stored(week_start, refs, passed):
        return {"week_start": week_start,
                "conviction_check": {"look": {"on": week_start, "passed": passed,
                                              "refs": refs}}}

    rows = [stored("2027-03-01", ["c"], True), stored("2027-01-04", ["a"], False),
            stored("2027-02-01", ["b"], True),
            {"week_start": "2027-01-11"},                        # a week with no check
            {"week_start": "2027-01-18", "conviction_check": {"look": None}},
            {"week_start": "2027-01-25", "conviction_check": "garbled"}]
    rows[1]["conviction_check"]["passed_on"] = "2027-01-04"
    rows[0]["conviction_check"]["passed_on"] = "2027-03-01"       # a later week's
    earlier, used, passed = I.stored_looks(rows, week_start="2027-02-01")
    assert [l["on"] for l in earlier] == ["2027-01-04"]
    assert used == {"a", "c"}          # this week's own stored look is not "used"
    assert passed == "2027-01-04"      # only an earlier week's stored pass


# -- the scorecard ----------------------------------------------------------------

def _row_for(on: date, audit_rows, **kw):
    return R.build_row(week=R.week_of(on), txns=[], points=[], audit_rows=audit_rows,
                       close_on=lambda d: 100.0, holdings=None, **kw)


def _line(row, label="Conviction check"):
    return next((l["text"] for l in row["lines"] if l.get("label") == label), None)


@pytest.mark.parametrize("sunday, shown", [
    (date(2027, 1, 3), True), (date(2027, 2, 7), True),     # day 7 is still the first
    (date(2027, 1, 10), False), (date(2027, 8, 8), False),  # day 8 is the second
    (date(2027, 1, 31), False),
])
def test_only_the_months_first_sunday_carries_the_check(sunday, shown):
    assert sunday.weekday() == 6
    row = _row_for(sunday, [], conviction_scorecards=[])
    assert ("conviction_check" in row) is shown
    assert (_line(row) is not None) is shown


def test_without_the_stored_rows_there_is_no_check_even_on_a_first_sunday():
    row = _row_for(JAN, pair("a", top=4.0, low=1.0))
    assert "conviction_check" not in row and _line(row) is None


def test_an_empty_record_says_none_graded_and_no_look():
    line = _line(_row_for(JAN, [], conviction_scorecards=[]))
    assert "rejected, under 0.55: none graded yet" in line
    assert "BUY at 0.75 and above: none graded yet" in line
    assert "there are 0 and 0." in line


def test_a_grade_after_the_weeks_sunday_is_not_on_that_weeks_line():
    """A scorecard built late reads nothing graded after its own week."""
    rows = [dive("A", 1.0), dive("B", 99.0, graded_on="2027-01-04")]
    line = _line(_row_for(JAN, rows, conviction_scorecards=[]))
    assert "BUY at 0.55 to under 0.65: +1.00 (n 1, 1 stock, too few to judge)" in line


def test_the_lines_figures_equal_the_audit_reports_for_the_same_rows(tmp_path):
    """Rejected: -1.234 and -2.0, mean -1.617 (n 2). 0.55: 31 x +0.3051
    (n 31). 0.65: +1.0 and +2.0, mean +1.5 (n 2). 0.75: +4.1288 (n 1)."""
    rows = ([dive("r1", -1.234, verdict="NEUTRAL", conviction=0.40),
             dive("r2", -2.0, verdict="BUY", conviction=0.50)]
            + many("l", 31, 0.3051, 0.60)
            + [dive("m1", 1.0, conviction=0.70), dive("m2", 2.0, conviction=0.66),
               dive("t1", 4.1288, conviction=0.90)])
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    for r in rows:
        store.append(r)
    report = build_report(store=store, min_n=1)
    line = _line(_row_for(JAN, store.load_all(), conviction_scorecards=[]))

    expected = {"rejected": ("-1.62", 2), "buy_055": ("+0.31", 31),
                "buy_065": ("+1.50", 2), "buy_075": ("+4.13", 1)}
    for group, (mean, n) in expected.items():
        printed = re.search(re.escape(I.CHECK_LABELS[group]) + r": ([+-]\d+\.\d\d) \(n (\d+)",
                            line)
        assert printed is not None, group
        assert printed.groups() == (mean, str(n)), group
        reported = report["ideas"]["conviction"]["groups"][group]
        assert (f"{reported['mean_excess_pct']:+.2f}", reported["n"]) == (mean, n), group
    # and the report's own text carries the same figures
    section = render_section(report)
    for group, (mean, n) in expected.items():
        assert f"{I.CHECK_LABELS[group]}: {mean} (n {n}" in section


def test_the_old_shelf_calibration_is_untouched_by_dive_rows(tmp_path):
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    for r in pair("a", top=4.0, low=1.0):
        store.append(r)
    assert build_report(store=store, min_n=1)["conviction_calibration"] == []


# -- the real weekly wrapper: the looks are stored and read back -----------------

def _weekly(user, on, tmp_path, today=None):
    store = PortfolioStore(user_id=user, base_dir=str(tmp_path))
    return R.weekly_scorecard(
        user, on, store=store, close_on=lambda d: 100.0, today=today or on,
        stock_close_on=lambda s, d: 100.0, stock_quote_on=lambda s, d: None,
        corp_actions=lambda s: None, stock_series_on=lambda s, d: [],
        panel_on=lambda s, d: None)


def _put(tmp_path, rows, user="primary"):
    store = AuditOutcomeStore(user_id=user, base_dir=str(tmp_path))
    for r in rows:
        store.append(r)


def test_the_weekly_scorecard_stores_each_look_and_the_next_month_reads_it(tmp_path):
    _put(tmp_path, pair("a", top=4.0, low=1.0))
    january = _weekly("primary", JAN, tmp_path)
    assert january["conviction_check"]["look"]["passed"] is True
    # a week that is not a first Sunday stores no check and spends no dive
    assert "conviction_check" not in _weekly("primary", date(2027, 1, 10), tmp_path)

    _put(tmp_path, pair("b", top=4.0, low=1.0, graded_on="2027-02-01"))
    february = _weekly("primary", FEB, tmp_path)
    check = february["conviction_check"]
    assert (check["look"]["top"]["n"], check["look"]["low"]["n"]) == (30, 30)
    assert not set(check["look"]["refs"]) & set(january["conviction_check"]["look"]["refs"])
    assert check["passed_on"] == "2027-02-07"
    assert "The rule passed on 7 Feb 2027" in _line(february)
    # a stored week is returned as it was
    assert _weekly("primary", FEB, tmp_path) == february


def test_a_provisional_week_spends_no_dive(tmp_path):
    """A week not yet over is computed, never stored: its look must not count."""
    _put(tmp_path, pair("a", top=4.0, low=1.0))
    preview = _weekly("primary", JAN, tmp_path, today=date(2027, 1, 1))     # a Friday
    assert preview["provisional"] is True
    real = _weekly("primary", JAN, tmp_path)
    assert real["conviction_check"]["look"]["refs"] == preview["conviction_check"]["look"]["refs"]
    assert real["conviction_check"]["streak"] == 1


def test_a_members_scorecard_carries_no_conviction_check(tmp_path):
    """The dive grades are kept in the default user's store alone."""
    _put(tmp_path, pair("a", top=4.0, low=1.0))
    row = _weekly("member", JAN, tmp_path)
    assert "conviction_check" not in row and _line(row) is None
    assert "conviction_check" in _weekly("primary", JAN, tmp_path)
