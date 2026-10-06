"""SA-038 — the real registry after the lapsed milestones were judged.

A `manual_confirmation` entry is pending until it is deleted, and once its
deadline passes the engine re-sends a critical alert every 7 days. By
2026-09-23, 8 of 9 milestones had lapsed, so the 06:30 ops mail carried a
"LAPSED" critical that meant "nobody wrote the judgement down". SA-038 judged
each one: deleted with evidence or a recorded decision, or re-dated with a
dated reason.

These tests read config/milestones.yaml itself. They do not depend on how any
check is implemented: every check is forced to `pending` (what a
manual_confirmation always returns), which is the worst case for the ladder.
"""
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.ops.watchdog import checks as C
from core.ops.watchdog import runner as R
from core.ops.watchdog.checks import CheckResult
from core.ops.watchdog.registry import load_registry

IST = ZoneInfo("Asia/Kolkata")

# The first scheduled 06:30 run after the judgement (Wed 7 Oct 2026).
FIRST_RUN = datetime(2026, 10, 7, 6, 30, tzinfo=IST)

# Judged closed or folded into a story, with the evidence or decision in
# docs/planning/PI-2026-09/evidence/SA-038-implementation.md. Re-adding one
# of these ids means re-opening a judged item: do it under a new id instead.
RETIRED = {
    "atlas_c11_cutover",             # atlas.enabled is true; its check self-satisfies
    "hard_bind_observation",         # folded into SA-012 / SA-014 (defective target)
    "b2_data_health_prod_verify",    # met 26 Aug; the B6 half is on SA-002
    "e1_error_capture_prod_verify",  # (a)(b)(d) met 26 Aug; (c) not applicable
    "f3_checkpoint",                 # probe 6 Oct: 98% of post-F3 lessons carry evidence
    "a1_routing_prod_verify",        # probe 6 Oct: no automobile copy of another sector's ticker
    "b1_run_history_prod_verify",    # probe 6 Oct: 888 rows since 26 Aug, never reset
    "ipo_p0_live_window_check",      # IPO-0a closed 6 Oct (owner): brief 22 Sep, ledger 54 rows
}

REDATED_RE = re.compile(
    r"^RE-DATED (\d{4}-\d{2}-\d{2}) by (SA-\d{3}) \(was (\d{4}-\d{2}-\d{2})")


def _milestones():
    return [e for e in load_registry("config/milestones.yaml") if e.kind == "milestone"]


def test_no_milestone_is_past_its_deadline_on_the_first_run():
    """The acceptance in data terms: nothing is lapsed at the judgement."""
    lapsed = [(e.id, e.deadline) for e in _milestones()
              if e.deadline is not None and e.deadline < FIRST_RUN.date()]
    assert lapsed == []


def test_first_run_sends_no_critical_even_with_every_check_pending(tmp_path, monkeypatch):
    """End to end through the real runner, from the state production holds
    after weeks of weekly LAPSED alerts: every milestone, retired or not, was
    last notified critical 7 days earlier, so a still-lapsed entry would fire
    again on this run."""
    entries = load_registry("config/milestones.yaml")
    ids = {e.id for e in entries}
    prior = {"entries": {i: {"last_level": "critical", "last_notified_date": "2026-09-30",
                             "last_state": "pending"}
                         for i in ids | RETIRED}}
    state_path = tmp_path / "watchdog_state.json"
    state_path.write_text(json.dumps(prior), encoding="utf-8")
    sent = []
    monkeypatch.setattr(R, "_STATE_PATH", state_path)
    monkeypatch.setattr(C, "run_check", lambda name: CheckResult("pending", "forced"))
    monkeypatch.setattr(R, "_run_preps", lambda *a: {})
    monkeypatch.setattr(R, "_broadcast", lambda events, title: sent.extend(events))

    def _no_mail(*a):
        raise AssertionError("no heartbeat on a Wednesday")
    monkeypatch.setattr(R, "_send_email", _no_mail)

    out = R.run_watchdog(now=FIRST_RUN)

    assert out["evaluated"] == len(entries)
    assert [e.kind for e in sent if e.severity == "critical"] == []
    assert not any(rid in e.kind for e in sent for rid in RETIRED)
    saved = json.loads(state_path.read_text(encoding="utf-8"))["entries"]
    assert RETIRED.isdisjoint(saved)          # no ghost state for deleted entries
    assert set(saved) == ids


def test_judged_entries_are_gone():
    ids = {e.id for e in load_registry("config/milestones.yaml")}
    assert RETIRED.isdisjoint(ids)


def test_every_manual_milestone_has_a_deadline():
    """Without a deadline or window a pending entry is a standing invariant:
    it warns every day for ever, and it can never lapse into the weekly
    critical that forces a judgement."""
    undated = [e.id for e in _milestones()
               if e.check == "manual_confirmation" and e.deadline is None]
    assert undated == []


def test_every_redated_entry_states_when_and_why():
    redated = [e for e in _milestones() if e.action.startswith("RE-DATED")]
    for e in redated:
        m = REDATED_RE.match(e.action)
        assert m, f"{e.id}: re-date line must read 'RE-DATED <date> by <story> (was <date>'"
        on, was = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(3))
        assert was < on < e.deadline, f"{e.id}: was {was}, re-dated {on}, deadline {e.deadline}"
        reason = e.action[m.end():].split(".", 1)[0]
        assert len(reason.split()) >= 5, f"{e.id}: the reason is missing"
