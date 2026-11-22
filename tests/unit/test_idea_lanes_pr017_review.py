"""PR-017's fresh review (23 Nov 2026): the cases that caught planted bugs the
story's own tests let through (evidence/PR-017-review.md, finding L1).

Each pins one invariant of the idea lanes with a figure worked by hand:
the conviction a re-dive was issued with (RV1), price identity across a
change only the instrument registry records (RV2), the first actionable
open of a screen two runs read (RV3), a bonus ex on the horizon day (RV4),
one stock dived twice in one run (RV5), idea rows kept out of the
scorecard's shelf and advice figures (RV7) and the shelf's floor taken as
inclusive (RV8). The calendar and fixtures are the story file's (no
holidays: Sat 7 Mar 2026 enters at Mon 9 Mar's open).
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from core.audit import ideas as I
from core.discovery import bare_judge as BJ
from core.discovery.dive_record import DiveRecord
from core.portfolio.corp_actions import ActionRecord
from tests.unit.test_idea_lanes_pr017 import (  # noqa: F401  (fixtures and helpers)
    FRI, SAT, Panel, _bonus, _bundle, _no_holidays, _screen, disc, dive, flat_panel, grade,
    rows_of, store, weekday_after, weekdays,
)


def test_rv1_a_redived_event_the_memo_no_longer_holds_is_seeded_at_its_new_conviction(disc):
    """ABC re-dived on 4 Apr, 0.62 -> 0.80; the memo no longer holds it (its
    newest day is 9 May). The seed says 0.80 for 4 Apr, never the 0.62
    before."""
    (disc / "shelf_events.jsonl").write_text(json.dumps(
        {"ts": "2026-04-04T07:00:00+00:00", "event": "redived", "symbol": "ABC",
         "detail": "conviction 0.62 -> 0.80, gate actionable, band 97-102"}) + "\n",
        encoding="utf-8")
    (disc / "dives.json").write_text(json.dumps({"ZZZ": {
        "date": "2026-05-09", "conviction": 0.4, "verdict": "NEUTRAL"}}), encoding="utf-8")
    rows = {r["ref"]: r for r in DiveRecord(str(disc)).seed_rows(on=date(2026, 5, 16))
            if r["row"] == "dive"}
    assert rows["dive:2026-04-04|ABC"]["conviction"] == 0.80
    assert rows["dive:2026-04-04|ABC"]["source"] == "shelf_event:redived"


def test_rv2_a_change_only_the_registry_records_leaves_the_horizon_ungraded(
        disc, store, monkeypatch):
    """The instrument registry records a relisting NSE's list does not show:
    no row at any horizon, each counted as no exit price."""
    from core.portfolio import exit_shadow
    monkeypatch.setattr(exit_shadow, "identity_break",
                        lambda symbol, start, until: "relisting on 2026-03-12")
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    summary = grade(store, disc, flat_panel(["ABC"]))
    assert rows_of(store, "dive") == []
    assert summary["dive"]["no_exit_price"] == 5


def test_rv3_two_runs_read_one_screen_the_earliest_run_day_is_the_call(disc, store):
    """The Saturday run and a Monday catch-up both read Friday's screen: its
    candidates were actionable from Monday's open (the Saturday run), not
    Tuesday's."""
    _screen(disc, "2026-03-06", ["AAA", "BBB"])
    record = DiveRecord(str(disc))
    record.append_run([dive("AAA", SAT, 0.7)], on=SAT, screen_date="2026-03-06")
    record.append_run([dive("CCC", date(2026, 3, 9), 0.7)], on=date(2026, 3, 9),
                      screen_date="2026-03-06")
    grade(store, disc, flat_panel(["AAA", "BBB", "CCC"]))
    bbb = [r for r in rows_of(store, "screen") if r.symbol == "BBB"]
    assert {r.ref for r in bbb} == {"screen:2026-03-07|BBB"}
    assert {r.entry_on for r in bbb} == {"2026-03-09"}


def test_rv4_a_bonus_ex_on_the_horizon_day_is_applied(disc, store):
    """Ex on Fri 20 Mar, the 10-session day itself: that close (55) is already
    in the new shares, so it is 110 in the entry's: +10%."""
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    days = weekdays(FRI, 220)
    ex = weekday_after(SAT, 10)
    panel = Panel({("ABC", d): ((100.0, 100.0) if d < ex else (50.0, 55.0)) for d in days},
                  days=days)
    corp = lambda s: ActionRecord(actions=(_bonus(ex),), covers_from="2020-01-01",  # noqa: E731
                                  rows=2)
    grade(store, disc, panel, corp=corp)
    ten = [r for r in rows_of(store, "dive") if r.horizon_td == 10][0]
    assert ten.exit_close == pytest.approx(110.0) and ten.return_pct == pytest.approx(10.0)


def test_rv5_one_stock_dived_twice_in_one_run_is_one_call(disc, store):
    """A shelf idea's re-dive and the same stock among the screen's candidates
    in one run: one reference, graded once at the first answer; the bare
    judge is not asked (a re-dive)."""
    dives = [dive("ABC", SAT, 0.66), dive("ABC", SAT, 0.71)]
    DiveRecord(str(disc)).append_run(dives, on=SAT, redives={"ABC"})
    asked: list[str] = []
    out = BJ.judge(dives, {"ABC": _bundle("ABC")}, on=SAT, redives={"ABC"},
                   base_dir=str(disc), call=lambda s, u: asked.append(u) or ("{}", "m"))
    assert asked == [] and out["asked"] == 0
    grade(store, disc, flat_panel(["ABC"]))
    got = rows_of(store, "dive")
    assert len(got) == 5 and {r.conviction for r in got} == {0.66}


def test_rv7_idea_rows_cannot_reach_the_shelf_line_or_the_advice_grades(disc, store):
    """A dive graded +50% does not move the scorecard's shelf idea quality
    (shelf rows only) nor its advice grades (advice rows only)."""
    from core.portfolio import results
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.9)], on=SAT)
    days = weekdays(FRI, 220)
    grade(store, disc, Panel({("ABC", d): (100.0, 150.0) for d in days}, days=days))
    rows = store.load_all()
    assert rows and all(r.lane == "dive" for r in rows)
    quality = results.idea_quality(rows, 10, as_of=date(2027, 6, 30))
    assert quality["graded"] == 0 and quality["beat"] == 0
    assert quality["median_excess_pct"] is None
    assert results.advice_grades(rows) == {}


def test_rv8_the_shelf_floor_is_inclusive(disc):
    """BUY at exactly 0.55 is a BUY dive; at 0.5499 it is rejected; STRONG BUY
    at 0.60 is a BUY dive; INSUFFICIENT DATA is in no group."""
    def row(verdict, conviction):
        return SimpleNamespace(lane="dive", verdict=verdict, conviction=conviction)
    assert I.group_of(row("BUY", 0.55), 0.55) == "buy_dives"
    assert I.group_of(row("BUY", 0.5499), 0.55) == "rejected_dives"
    assert I.group_of(row("STRONG BUY", 0.60), 0.55) == "buy_dives"
    assert I.group_of(row("INSUFFICIENT DATA", 0.70), 0.55) == ""
