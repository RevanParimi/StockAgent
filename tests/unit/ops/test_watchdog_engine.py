"""Watchdog engine — the escalation ladder, table-tested against a synthetic clock."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.engine import Notification, evaluate
from core.ops.watchdog.registry import Milestone, Window

IST = ZoneInfo("Asia/Kolkata")


def _now(y, m, d, hh=6, mm=30):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def _atlas(**kw):
    # deadline is the LAST day of the final window (Sun 8/16), not its first.
    # With deadline=8/15 the Sunday of the very weekend you are meant to act on
    # is already classified as lapsed — see test_final_sunday_is_not_lapsed.
    base = dict(id="atlas", kind="milestone", title="Atlas C11",
                check="atlas_cutover_pending", prep="atlas_cutover_prep",
                window=Window(weekdays=(5, 6)), deadline=date(2026, 8, 16),
                lead_days=3, action="Set ATLAS_ENABLED=true.")
    base.update(kw)
    return Milestone(**base)


PENDING = {"atlas": CheckResult("pending", "pre-flight clean")}
SATISFIED = {"atlas": CheckResult("satisfied", "flag set")}


def test_silent_outside_lead_window():
    # Mon 2026-08-10; next window Sat 8/15 is 5 days away, lead is 3.
    notes, state = evaluate([_atlas()], PENDING, _now(2026, 8, 10), {})
    assert notes == []
    assert state["entries"]["atlas"]["last_state"] == "pending"


def test_info_when_lead_window_opens():
    # Wed 2026-08-12 is exactly 3 days before Sat 8/15.
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 12), {})
    assert [n.level for n in notes] == ["info"]
    assert "Atlas C11" in notes[0].title


def test_warning_while_window_open():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})   # Sat
    assert [n.level for n in notes] == ["warning"]


def test_no_duplicate_on_same_day():
    now = _now(2026, 8, 15)
    notes1, state = evaluate([_atlas()], PENDING, now, {})
    notes2, _ = evaluate([_atlas()], PENDING, now, state)
    assert len(notes1) == 1 and notes2 == []


def test_repeats_next_day_while_window_open():
    n1, s = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})     # Sat
    n2, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 16), s)      # Sun
    assert len(n1) == 1 and len(n2) == 1


def test_final_sunday_is_not_lapsed():
    """Regression: with deadline set to the Saturday, the Sunday of the very
    weekend you are meant to act on was misclassified as lapsed and silenced
    by the 7-day repeat gate — losing the last day of the last window."""
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 16), {})  # Sun
    assert [n.level for n in notes] == ["warning"]
    assert "lapsed" not in notes[0].body.lower()


def test_critical_after_deadline_lapses():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 17), {})   # past 8/15
    assert [n.level for n in notes] == ["critical"]
    assert "lapsed" in notes[0].body.lower()


def test_lapsed_repeats_weekly_not_daily():
    n1, s = evaluate([_atlas()], PENDING, _now(2026, 8, 17), {})
    n2, s2 = evaluate([_atlas()], PENDING, _now(2026, 8, 20), s)     # +3d
    n3, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 24), s2)     # +7d
    assert len(n1) == 1 and n2 == [] and len(n3) == 1


def test_satisfied_emits_resolved_once_then_silent():
    _, s = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})
    n2, s2 = evaluate([_atlas()], SATISFIED, _now(2026, 8, 16), s)
    n3, _ = evaluate([_atlas()], SATISFIED, _now(2026, 8, 17), s2)
    assert [n.level for n in n2] == ["resolved"]
    assert n3 == []


def test_satisfied_from_the_start_is_silent():
    notes, _ = evaluate([_atlas()], SATISFIED, _now(2026, 8, 15), {})
    assert notes == []


def test_unknown_notifies_as_warning_once_per_day():
    res = {"atlas": CheckResult("unknown", "check raised: boom")}
    n1, s = evaluate([_atlas()], res, _now(2026, 8, 10), {})
    n2, _ = evaluate([_atlas()], res, _now(2026, 8, 10, 7), s)
    assert [n.level for n in n1] == ["warning"]
    assert "boom" in n1[0].body
    assert n2 == []


def test_blocked_warns_with_different_copy():
    res = {"atlas": CheckResult("blocked", "atlas.db already exists")}
    notes, _ = evaluate([_atlas()], res, _now(2026, 8, 15), {})
    assert [n.level for n in notes] == ["warning"]
    assert "blocked" in notes[0].body.lower()


def test_invariant_with_no_window_warns_when_pending():
    inv = Milestone(id="serper", kind="invariant", title="Serper rollover",
                    check="serper_counter_current_month")
    res = {"serper": CheckResult("pending", "counter stuck on 2026-07")}
    notes, _ = evaluate([inv], res, _now(2026, 9, 2), {})
    assert [n.level for n in notes] == ["warning"]


def test_monthly_invariant_silent_when_already_notified_this_month():
    inv = Milestone(id="sc", kind="invariant", title="Scorecard",
                    check="monthly_scorecard_written", schedule="monthly")
    res = {"sc": CheckResult("pending", "missing")}
    n1, s = evaluate([inv], res, _now(2026, 9, 1), {})
    n2, _ = evaluate([inv], res, _now(2026, 9, 14), s)
    assert len(n1) == 1 and n2 == []


def test_action_text_included_in_body():
    notes, _ = evaluate([_atlas()], PENDING, _now(2026, 8, 15), {})
    assert "ATLAS_ENABLED=true" in notes[0].body


def test_missing_check_result_is_unknown():
    notes, _ = evaluate([_atlas()], {}, _now(2026, 8, 15), {})
    assert [n.level for n in notes] == ["warning"]


def test_severity_maps_resolved_to_info():
    n = Notification("x", "resolved", "t", "b")
    assert n.severity == "info"
    assert Notification("x", "critical", "t", "b").severity == "critical"


def test_last_run_ts_recorded():
    _, state = evaluate([_atlas()], PENDING, _now(2026, 8, 10), {})
    assert state["last_run_ts"] > 0
