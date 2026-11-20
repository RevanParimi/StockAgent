"""PR-017 — every deep dive graded at the conviction it was issued with, beside
the screen's other candidates and a bare model: invariant tests.

Every expected figure is worked out by hand in the comments, never read back
from the implementation. The NSE calendar is pinned (no holidays), so the
sessions are the weekdays: Fri 6 Mar 2026, then Mon 9 Mar, Tue 10 Mar, ...
A dive on Saturday 7 Mar enters at Monday 9 Mar's open.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import core.intelligence.rl.nse_calendar as cal
from backend.shared.schemas.audit import AuditOutcome
from backend.shared.schemas.discovery import DeepDiveResult
from backend.shared.schemas.portfolio import AppliedCorpAction
from core.audit import idea_lanes as L
from core.audit import ideas as I
from core.audit.outcomes import grade_due
from core.audit.report import build_report, render_section
from core.audit.store import AuditOutcomeStore
from core.config import settings
from core.discovery import bare_judge as BJ
from core.discovery.dive_record import DiveRecord
from core.portfolio.corp_actions import ActionRecord
from core.portfolio.executable import PanelBar

SAT = date(2026, 3, 7)
FRI, MON, TUE = date(2026, 3, 6), date(2026, 3, 9), date(2026, 3, 10)
FAR = date(2027, 6, 30)            # every horizon of a March 2026 call has ended


@pytest.fixture(autouse=True)
def _no_holidays(monkeypatch):
    monkeypatch.setattr(cal, "_NSE_HOLIDAYS", frozenset())


def weekday_after(day: date, n: int) -> date:
    """The n-th weekday after `day`, counted by hand (no application code)."""
    d, k = day, 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d


def weekdays(start: date, count: int) -> list[date]:
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class Panel:
    """{(symbol, day): (open, close)}; every day in `days` has a file."""

    def __init__(self, bars: dict, days=None):
        self.bars = dict(bars)
        self.days = set(days) if days is not None else {d for _s, d in bars}

    def __call__(self, symbol, day):
        if day not in self.days:
            return PanelBar(None, None, False)
        hit = self.bars.get((symbol, day))
        return PanelBar(*hit, True) if hit else PanelBar(None, None, True)


def flat_panel(symbols, start=FRI, count=220, open_=100.0, close=100.0):
    days = weekdays(start, count)
    return Panel({(s, d): (open_, close) for s in symbols for d in days}, days=days)


class Bench:
    """The Nifty at 1000 on every weekday unless told otherwise."""

    def __init__(self, closes: dict | None = None, default: float = 1000.0):
        self.closes, self.default = dict(closes or {}), default
        self.asked: list[date] = []

    def close_on(self, d):
        self.asked.append(d)
        return self.closes.get(d, self.default)

    def pct_change(self, start, end):       # the shelf lane's reader
        return round((self.close_on(end) / self.close_on(start) - 1.0) * 100.0, 4)


def no_actions(symbol):
    return ActionRecord(covers_from="2020-01-01", rows=1)


def dive(symbol, day, conviction, verdict="BUY", graph="generic", close=100.0):
    return DeepDiveResult(symbol=symbol, sector="generic", graph=graph, conviction=conviction,
                          verdict=verdict, thesis="t", entry_low=97.0, entry_high=102.0,
                          invalidation_level=88.0, close=close, composite=0.6,
                          dive_date=day.isoformat(), data_gate="actionable")


@pytest.fixture
def disc(tmp_path, monkeypatch):
    folder = tmp_path / "disc"
    folder.mkdir()
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(folder))
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)
    return folder


UID = None


@pytest.fixture
def store(tmp_path):
    global UID
    UID = settings.PORTFOLIO_DEFAULT_USER_ID
    return AuditOutcomeStore(user_id=UID, base_dir=str(tmp_path / "pf"))


def grade(store, disc, panel, *, on=FAR, bench=None, corp=no_actions):
    return L.grade_idea_lanes(on, UID, store=store, bench=bench or Bench(),
                              discovery_dir=str(disc), panel=panel, corp_actions=corp)


def rows_of(store, lane=None, ref=None):
    return [r for r in store.load_all()
            if (lane is None or r.lane == lane) and (ref is None or r.ref == ref)]


# ---------------------------------------------------------------------------
# The card's example: the conviction is the dive's own
# ---------------------------------------------------------------------------

def test_a_dive_keeps_its_own_conviction_whatever_redives_followed(disc, store):
    """ABC dived on Sat 7 Mar at 0.62; re-dived on Sat 4 Apr at 0.80, and the
    shelf now says 0.80. The 7 Mar dive is graded at 0.62 at every horizon,
    the 4 Apr one at 0.80."""
    record = DiveRecord(str(disc))
    record.append_run([dive("ABC", SAT, 0.62)], on=SAT, screen_date="2026-03-06")
    redive_day = date(2026, 4, 4)
    record.append_run([dive("ABC", redive_day, 0.80)], on=redive_day,
                      screen_date="2026-04-03", redives={"ABC"})
    (disc / "shelf.json").write_text(json.dumps({"ideas": [{
        "symbol": "ABC", "sector": "generic", "added": "2026-03-07", "conviction": 0.80,
        "close_at_add": 100.0}]}), encoding="utf-8")
    grade(store, disc, flat_panel(["ABC"]))
    first = rows_of(store, "dive", "dive:2026-03-07|ABC")
    later = rows_of(store, "dive", "dive:2026-04-04|ABC")
    assert len(first) == 5 and len(later) == 5          # 10, 30, 60, 90, 180
    assert {r.conviction for r in first} == {0.62}
    assert {r.conviction for r in later} == {0.80}
    assert "kind:redive" in later[0].triggers and "kind:new" in first[0].triggers


def test_the_seed_keeps_the_conviction_each_shelf_event_was_written_with(disc, store):
    """Before dives.jsonl existed: the shelf events of the same example, and a
    memo naming a rejected dive. The first write seeds both dives of ABC at
    their own convictions, the rejected one with its verdict."""
    (disc / "shelf_events.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"ts": "2026-03-07T07:00:00+00:00", "event": "added", "symbol": "ABC",
         "detail": "conviction=0.62"},
        {"ts": "2026-04-04T07:00:00+00:00", "event": "redived", "symbol": "ABC",
         "detail": "conviction 0.62 -> 0.80, gate actionable, band 97-102"},
        {"ts": "2026-04-04T07:00:00+00:00", "event": "dropped", "symbol": "XYZ",
         "detail": "displaced by ABC"},
    ]) + "\n", encoding="utf-8")
    (disc / "dives.json").write_text(json.dumps({
        "REJ": {"date": "2026-04-04", "conviction": 0.41, "verdict": "NEUTRAL",
                "data_gate": "actionable"},
        "ABC": {"date": "2026-04-04", "conviction": 0.8, "verdict": "BUY",
                "data_gate": "actionable"}}), encoding="utf-8")
    (disc / "shelf.json").write_text(json.dumps({"ideas": [{
        "symbol": "ABC", "sector": "pharma", "graph": "native", "added": "2026-03-07",
        "conviction": 0.80}]}), encoding="utf-8")
    record = DiveRecord(str(disc))
    record.append_run([dive("NEW", date(2026, 4, 11), 0.7)], on=date(2026, 4, 11),
                      screen_date="2026-04-10")
    by_ref = {r["ref"]: r for r in record.dive_rows()}
    assert by_ref["dive:2026-03-07|ABC"]["conviction"] == 0.62
    assert by_ref["dive:2026-03-07|ABC"]["verdict"] == ""          # not recorded then
    assert by_ref["dive:2026-03-07|ABC"]["graph"] == "native"      # the shelf's
    assert by_ref["dive:2026-04-04|ABC"]["conviction"] == 0.8
    assert by_ref["dive:2026-04-04|ABC"]["verdict"] == "BUY"       # the memo's, same day
    assert by_ref["dive:2026-04-04|REJ"]["verdict"] == "NEUTRAL"
    assert by_ref["dive:2026-04-11|NEW"]["recorded"] == "at_dive"
    # The memo's newest day is 4 Apr: days from 5 Mar on are covered, so the
    # 7 Mar and 4 Apr days get run rows, and so does the run itself.
    runs = {r["run_date"]: r for r in record.run_rows()}
    assert sorted(runs) == ["2026-03-07", "2026-04-04", "2026-04-11"]
    assert runs["2026-04-04"]["symbols"] == ["ABC", "REJ"]
    # Seeded once: a second run adds its own rows only.
    before = len(record.load())
    record.append_run([dive("TWO", date(2026, 4, 18), 0.7)], on=date(2026, 4, 18))
    assert len(record.load()) == before + 2


def test_a_day_the_memo_no_longer_covers_gets_no_run_row(disc):
    """Memo's newest day 4 Apr, 30 days: covered from 5 Mar. A shelf add on
    20 Feb is seeded as a dive, but its day gets no run row."""
    (disc / "shelf_events.jsonl").write_text(json.dumps(
        {"ts": "2026-02-20T07:00:00+00:00", "event": "added", "symbol": "OLD",
         "detail": "conviction=0.70"}) + "\n", encoding="utf-8")
    (disc / "dives.json").write_text(json.dumps({"REJ": {
        "date": "2026-04-04", "conviction": 0.41, "verdict": "SELL"}}), encoding="utf-8")
    rows = DiveRecord(str(disc)).seed_rows(on=date(2026, 4, 11))
    assert {r["ref"] for r in rows if r["row"] == "dive"} == {
        "dive:2026-02-20|OLD", "dive:2026-04-04|REJ"}
    assert [r["run_date"] for r in rows if r["row"] == "run"] == ["2026-04-04"]


# ---------------------------------------------------------------------------
# Entry, horizons, the Nifty
# ---------------------------------------------------------------------------

def test_the_entry_is_the_open_of_the_first_session_after_the_dive(disc, store):
    """Saturday's dive read Friday's close (100). Friday opened at 90, Monday
    at 101: the entry is Monday's 101. A dive run on Monday (a catch-up) did
    not see Monday's open in time: Tuesday's 104."""
    record = DiveRecord(str(disc))
    record.append_run([dive("SATD", SAT, 0.7)], on=SAT)
    record.append_run([dive("MOND", MON, 0.7)], on=MON)
    days = weekdays(FRI, 220)
    bars = {}
    for s in ("SATD", "MOND"):
        for d in days:
            bars[(s, d)] = (100.0, 100.0)
        bars[(s, FRI)] = (90.0, 100.0)
        bars[(s, MON)] = (101.0, 102.0)
        bars[(s, TUE)] = (104.0, 104.0)
    grade(store, disc, Panel(bars, days=days))
    sat_rows = rows_of(store, "dive", "dive:2026-03-07|SATD")
    mon_rows = rows_of(store, "dive", "dive:2026-03-09|MOND")
    assert {(r.entry_on, r.entry_close, r.reference_close) for r in sat_rows} == {
        ("2026-03-09", 101.0, 100.0)}
    assert {(r.entry_on, r.entry_close) for r in mon_rows} == {("2026-03-10", 104.0)}
    for r in rows_of(store):
        assert r.entry_on > r.issued_on                  # never a bar on or before the call


def test_five_horizons_counted_from_the_dive_day(disc, store):
    """Horizon h ends at the close of the h-th weekday after Saturday 7 Mar:
    10 -> Fri 20 Mar, 30 -> Fri 17 Apr, 60 -> Fri 29 May, 90 -> Fri 10 Jul,
    180 -> Fri 13 Nov. Opens at 100, the horizon closes at 110: +10%; the Nifty
    from Friday 6 Mar's close, 1000, to 1050 everywhere after: +5%; excess +5."""
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    days = weekdays(FRI, 220)
    panel = Panel({("ABC", d): (100.0, 110.0) for d in days}, days=days)
    bench = Bench({FRI: 1000.0}, default=1050.0)
    summary = grade(store, disc, panel, bench=bench)
    got = {r.horizon_td: r for r in rows_of(store, "dive")}
    assert sorted(got) == [10, 30, 60, 90, 180]
    for h, r in got.items():
        assert r.graded_on == weekday_after(SAT, h).isoformat()
        assert r.return_pct == pytest.approx(10.0)
        assert r.bench_entry == 1000.0 and r.bench_pct == pytest.approx(5.0)
        assert r.excess_pct == pytest.approx(5.0)
        assert r.correct is None and r.lane == "dive"
    assert weekday_after(SAT, 10) == date(2026, 3, 20)
    assert weekday_after(SAT, 180) == date(2026, 11, 13)
    assert summary["dive"]["graded"] == 5


def test_a_horizon_not_yet_ended_is_not_graded(disc, store):
    """On Fri 20 Mar only the 10-session horizon has ended."""
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    grade(store, disc, flat_panel(["ABC"]), on=date(2026, 3, 20))
    assert [r.horizon_td for r in rows_of(store)] == [10]
    grade(store, disc, flat_panel(["ABC"]), on=date(2026, 3, 19))
    assert len(rows_of(store)) == 1


def test_a_dive_with_no_entry_price_is_skipped_and_counted(disc, store):
    """Monday has a file but no bar for GAP (suspended): no grade at any
    horizon, one dive counted. The 10-session day's file (Fri 20 Mar) not in
    on that day is pending, not a failure; on 31 Mar, 11 days late, past the
    panel's 7 retry days, it never will be: no exit price."""
    DiveRecord(str(disc)).append_run([dive("GAP", SAT, 0.7), dive("OK", SAT, 0.7)], on=SAT)
    panel = flat_panel(["OK"])
    summary = grade(store, disc, panel)
    assert rows_of(store, ref="dive:2026-03-07|GAP") == []
    assert summary["dive"]["no_entry_price"] == 1
    assert summary["dive"]["skipped_unpriceable"] == 0      # not a broken run
    assert len(rows_of(store, ref="dive:2026-03-07|OK")) == 5
    late = flat_panel(["GAP", "OK"])
    late.days.discard(date(2026, 3, 20))
    store2 = AuditOutcomeStore(user_id=UID, base_dir=str(disc.parent / "pf2"))
    pending = grade(store2, disc, late, on=date(2026, 3, 20))
    assert pending["dive"]["pending"] == 2 and pending["dive"]["no_exit_price"] == 0
    gone = grade(store2, disc, late, on=date(2026, 3, 31))
    assert gone["dive"]["no_exit_price"] == 2 and store2.load_all() == []


def test_grading_again_writes_nothing(disc, store):
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    grade(store, disc, flat_panel(["ABC"]))
    before = store.path.read_bytes()
    again = grade(store, disc, flat_panel(["ABC"]))
    assert store.path.read_bytes() == before
    assert again["dive"]["graded"] == 0 and again["dive"]["already_present"] == 5


def test_a_reference_written_twice_is_graded_once_as_first_written(disc, store):
    """A second run the same day writes ABC again at 0.90: the first (0.70) is
    what the dive said on its day."""
    record = DiveRecord(str(disc))
    record.append_run([dive("ABC", SAT, 0.70)], on=SAT)
    record.append_run([dive("ABC", SAT, 0.90)], on=SAT)
    grade(store, disc, flat_panel(["ABC"]))
    assert {r.conviction for r in rows_of(store, "dive")} == {0.70}
    assert len(rows_of(store, "dive")) == 5


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------

def _bonus(ex: date) -> AppliedCorpAction:
    return AppliedCorpAction(key=f"ABC|{ex}|bonus", ex_date=ex.isoformat(), kind="bonus",
                             desc="Bonus 1:1", ratio=2.0, applied_on=ex.isoformat())


def test_a_bonus_after_the_entry_is_put_in_the_entrys_basis(disc, store):
    """Entered at Monday's open, 100. A 1:1 bonus goes ex on Fri 13 Mar; the
    10-session close (Fri 20 Mar) is 55, which is 110 in the entry's shares:
    +10%, not -45%."""
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    days = weekdays(FRI, 220)
    panel = Panel({("ABC", d): ((100.0, 100.0) if d < date(2026, 3, 13) else (50.0, 55.0))
                   for d in days}, days=days)
    corp = lambda s: ActionRecord(actions=(_bonus(date(2026, 3, 13)),),  # noqa: E731
                                  covers_from="2020-01-01", rows=2)
    grade(store, disc, panel, corp=corp)
    ten = [r for r in rows_of(store, "dive") if r.horizon_td == 10][0]
    assert ten.exit_close == pytest.approx(110.0)
    assert ten.return_pct == pytest.approx(10.0)
    assert "bonus" in ten.basis


def test_a_bonus_on_the_entry_day_is_already_in_the_open(disc, store):
    """Ex on Monday 9 Mar itself: Monday's open (50) is in the new shares, so
    the 10-session close of 55 is +10% with no ratio applied."""
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    days = weekdays(FRI, 220)
    panel = Panel({("ABC", d): ((100.0, 100.0) if d < MON else (50.0, 55.0)) for d in days},
                  days=days)
    corp = lambda s: ActionRecord(actions=(_bonus(MON),),  # noqa: E731
                                  covers_from="2020-01-01", rows=2)
    grade(store, disc, panel, corp=corp)
    ten = [r for r in rows_of(store, "dive") if r.horizon_td == 10][0]
    assert ten.entry_close == 50.0 and ten.exit_close == 55.0 and ten.basis == ""


def test_a_demerger_leaves_the_horizon_ungraded_and_counted(disc, store):
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    corp = lambda s: ActionRecord(covers_from="2020-01-01", rows=2,  # noqa: E731
                                  basis_changes=(("2026-03-12", "demerger"),))
    summary = grade(store, disc, flat_panel(["ABC"]), corp=corp)
    assert rows_of(store, "dive") == []
    assert summary["dive"]["no_exit_price"] == 5


def test_the_night_reads_at_most_the_cap_of_stocks(disc, store, monkeypatch):
    """Cap 1: the first stock's list is read and graded, the second waits
    (pending), and is graded the next night."""
    monkeypatch.setattr(L, "_max_reads", lambda: 1)
    DiveRecord(str(disc)).append_run([dive("AAA", SAT, 0.7), dive("BBB", SAT, 0.7)], on=SAT)
    read: list[str] = []

    def corp(symbol):
        read.append(symbol)
        return no_actions(symbol)
    first = grade(store, disc, flat_panel(["AAA", "BBB"]), corp=corp)
    assert read == ["AAA"] and first["dive"]["graded"] == 5 and first["dive"]["pending"] == 5
    second = grade(store, disc, flat_panel(["AAA", "BBB"]), corp=corp)
    assert read == ["AAA", "BBB"] and second["dive"]["graded"] == 5


# ---------------------------------------------------------------------------
# The screen lane
# ---------------------------------------------------------------------------

def _screen(disc, screen_date: str, symbols, run_date: str = ""):
    folder = disc / "screens"
    folder.mkdir(exist_ok=True)
    body = {"screen_date": screen_date, "universe_size": 2000, "shortlist_size": 80,
            "candidates": [{"symbol": s, "close": 100.0, "composite": 0.9 - k / 100,
                            "signal_ranks": {}} for k, s in enumerate(symbols)]}
    if run_date:
        body["run_date"] = run_date
    (folder / f"{screen_date}_screen.json").write_text(json.dumps(body), encoding="utf-8")


def test_screen_candidates_the_run_did_not_dive_are_screen_only(disc, store):
    """The 7 Mar run read the 6 Mar screen (AAA, BBB, CCC) and dived AAA."""
    _screen(disc, "2026-03-06", ["AAA", "BBB", "CCC"])
    DiveRecord(str(disc)).append_run([dive("AAA", SAT, 0.7)], on=SAT, screen_date="2026-03-06")
    grade(store, disc, flat_panel(["AAA", "BBB", "CCC"]))
    status = {r.symbol: r.triggers[0] for r in rows_of(store, "screen") if r.horizon_td == 10}
    assert status == {"AAA": "dived", "BBB": "not_dived", "CCC": "not_dived"}
    bbb = [r for r in rows_of(store, "screen") if r.symbol == "BBB"][0]
    assert bbb.ref == "screen:2026-03-07|BBB" and bbb.entry_on == "2026-03-09"
    assert bbb.composite == pytest.approx(0.89) and bbb.conviction is None


def test_a_screen_no_run_row_covers_is_graded_as_dived_unknown(disc, store):
    """A screen of 13 Mar that recorded its run day (Sat 14 Mar) but no run of
    the dive record read it: graded from Mon 16 Mar, dived unknown."""
    _screen(disc, "2026-03-13", ["DDD"], run_date="2026-03-14")
    grade(store, disc, flat_panel(["DDD"]))
    rows = rows_of(store, "screen")
    assert {r.triggers[0] for r in rows} == {"dived_unknown"}
    assert {r.entry_on for r in rows} == {"2026-03-16"}


# ---------------------------------------------------------------------------
# The bare judge
# ---------------------------------------------------------------------------

def _bundle(symbol):
    return SimpleNamespace(sections={"company_news": f"news about {symbol}",
                                     "fundamentals": "PE 20", "dossier": "PRODUCT MEMORY"})


def test_the_bare_judge_sees_the_evidence_not_the_method(disc):
    asked: list[tuple[str, str]] = []

    def call(system, user):
        asked.append((system, user))
        return json.dumps({"decision": "SKIP", "conviction": 0.4, "reason": "meh"}), "m"
    dives = [dive("NEW", SAT, 0.7), dive("OLD", SAT, 0.7)]
    out = BJ.judge(dives, {"NEW": _bundle("NEW"), "OLD": _bundle("OLD")}, on=SAT,
                   redives={"OLD"}, base_dir=str(disc), call=call)
    assert out["asked"] == 1 and out["answered"] == 1          # a re-dive is not asked
    system, user = asked[0]
    assert "news about NEW" in user and "PE 20" in user
    assert "PRODUCT MEMORY" not in user and "DOSSIER" not in user
    assert "NEW" in user and "2026-03-07" in user
    row = BJ.load(str(disc))[0]
    assert (row["ref"], row["decision"], row["conviction"]) == ("bare:2026-03-07|NEW", "SKIP", 0.4)


def test_at_most_twenty_calls_in_any_seven_days(disc):
    """19 calls already made for Sat 7 Mar; on Sat 14 Mar a new week starts
    (7 Mar is 7 days back, outside (7 Mar, 14 Mar])."""
    (disc / "bare_judgements.jsonl").write_text("".join(json.dumps(
        {"ref": f"bare:2026-03-07|P{k}", "symbol": f"P{k}", "dive_date": "2026-03-07",
         "decision": "BUY", "conviction": 0.6}) + "\n" for k in range(19)), encoding="utf-8")
    call = lambda s, u: (json.dumps({"decision": "BUY", "conviction": 0.6}), "m")  # noqa: E731
    dives = [dive(f"N{k}", SAT, 0.7) for k in range(3)]
    same_week = BJ.judge(dives, {d.symbol: _bundle(d.symbol) for d in dives}, on=SAT,
                         base_dir=str(disc), call=call)
    assert same_week["asked"] == 1 and same_week["skipped_cap"] == 2
    nxt = date(2026, 3, 14)
    week2 = [dive(f"W{k}", nxt, 0.7) for k in range(25)]
    later = BJ.judge(week2, {d.symbol: _bundle(d.symbol) for d in week2}, on=nxt,
                     base_dir=str(disc), call=call)
    assert later["asked"] == 20 and later["skipped_cap"] == 5


def test_an_answer_that_is_not_buy_or_skip_is_kept_and_not_graded(disc, store):
    calls = iter([json.dumps({"decision": "HOLD", "conviction": 0.5}),
                  json.dumps({"decision": "BUY", "conviction": 0.75}),
                  "not json"])
    call = lambda s, u: (next(calls), "m")  # noqa: E731
    dives = [dive("AAA", SAT, 0.7, graph="native"), dive("BBB", SAT, 0.7), dive("CCC", SAT, 0.7)]
    DiveRecord(str(disc)).append_run(dives, on=SAT)
    BJ.judge(dives, {d.symbol: _bundle(d.symbol) for d in dives}, on=SAT,
             base_dir=str(disc), call=call)
    assert [r["decision"] for r in BJ.load(str(disc))] == ["", "BUY", ""]
    grade(store, disc, flat_panel(["AAA", "BBB", "CCC"]))
    bare = rows_of(store, "bare")
    assert {r.symbol for r in bare} == {"BBB"} and len(bare) == 5
    assert {(r.verdict, r.conviction, r.graph) for r in bare} == {("BUY", 0.75, "generic")}


def test_a_failed_call_counts_against_the_cap_and_never_raises(disc):
    def call(system, user):
        raise TimeoutError("model down")
    out = BJ.judge([dive("AAA", SAT, 0.7)], {"AAA": _bundle("AAA")}, on=SAT,
                   base_dir=str(disc), call=call)
    assert out["asked"] == 1 and out["answered"] == 0
    assert BJ.load(str(disc))[0]["decision"] == ""


def test_no_evidence_no_call(disc):
    call = lambda s, u: pytest.fail("no call without evidence")  # noqa: E731
    out = BJ.judge([dive("AAA", SAT, 0.7)], {"AAA": None}, on=SAT, base_dir=str(disc), call=call)
    assert out["no_evidence"] == 1 and out["asked"] == 0
    weird = BJ.judge([dive("BBB", SAT, 0.7)], {"BBB": object()}, on=SAT, base_dir=str(disc),
                     call=call)
    assert weird["no_evidence"] == 1


# ---------------------------------------------------------------------------
# The report and the scorecard line
# ---------------------------------------------------------------------------

def row(lane, ref, excess, *, verdict="", conviction=None, graph="", h=30, triggers=()):
    return AuditOutcome(ref=ref, lane=lane, user_id="u", symbol=ref.split("|")[-1],
                        verdict=verdict, triggers=list(triggers), issued_on="2026-03-07",
                        horizon_td=h, graded_on="2026-04-17", entry_close=100.0,
                        exit_close=100.0 + excess, return_pct=excess, bench_entry=1000.0,
                        bench_exit=1000.0, bench_pct=0.0, excess_pct=excess, correct=None,
                        graded_at="x", conviction=conviction, graph=graph)


def test_the_groups_and_their_figures():
    """BUY dives: 0.62 BUY native +4, 0.70 STRONG BUY generic -2 (mean +1,
    median +1, 1 of 2 beat it = 50%). Rejected: BUY at 0.50 (+6), NEUTRAL (-1):
    mean +2.5. An abstained dive and one with no verdict are only counted.
    Screen only: the not-dived candidate (+3); the dived one is in no group.
    Bare BUYs: +1; its SKIP is in no group."""
    rows = [row("dive", "dive:a|A", 4.0, verdict="BUY", conviction=0.62, graph="native"),
            row("dive", "dive:a|B", -2.0, verdict="STRONG BUY", conviction=0.70,
                graph="generic"),
            row("dive", "dive:a|C", 6.0, verdict="BUY", conviction=0.50),
            row("dive", "dive:a|D", -1.0, verdict="NEUTRAL", conviction=0.40),
            row("dive", "dive:a|E", 9.0, verdict="INSUFFICIENT DATA", conviction=0.0),
            row("dive", "dive:a|F", 9.0, verdict="", conviction=0.8),
            row("screen", "screen:a|G", 3.0, triggers=("not_dived",)),
            row("screen", "screen:a|A", 4.0, triggers=("dived",)),
            row("bare", "bare:a|A", 1.0, verdict="BUY", conviction=0.6),
            row("bare", "bare:a|B", 5.0, verdict="SKIP", conviction=0.3),
            row("shelf", "shelf:a|A", 50.0, conviction=0.9)]
    block = I.idea_block(rows, (30, 90), floor=0.55)
    at30 = block["horizons"]["30"]
    assert (at30["buy_dives"]["n"], at30["buy_dives"]["mean_excess_pct"],
            at30["buy_dives"]["median_excess_pct"], at30["buy_dives"]["beat_pct"]) == \
        (2, 1.0, 1.0, 50.0)
    assert (at30["rejected_dives"]["n"], at30["rejected_dives"]["mean_excess_pct"]) == (2, 2.5)
    assert (at30["screen_only"]["n"], at30["screen_only"]["mean_excess_pct"]) == (1, 3.0)
    assert (at30["bare_buys"]["n"], at30["bare_buys"]["mean_excess_pct"]) == (1, 1.0)
    assert at30["by_graph"]["native"]["mean_excess_pct"] == 4.0
    assert at30["by_graph"]["generic"]["mean_excess_pct"] == -2.0
    assert (at30["abstained"], at30["verdict_not_recorded"]) == (1, 1)
    for g in I.GROUPS:
        assert at30[g]["judge"] == I.TOO_FEW                   # every n under 30
    assert block["horizons"]["90"]["buy_dives"]["n"] == 0


def test_thirty_ideas_are_judged_and_twenty_nine_are_too_few():
    rows = [row("dive", f"dive:a|S{k}", 1.0, verdict="BUY", conviction=0.6) for k in range(29)]
    assert I.idea_block(rows, (30,), floor=0.55)["horizons"]["30"]["buy_dives"]["judge"] == \
        I.TOO_FEW
    rows.append(row("dive", "dive:a|S29", 1.0, verdict="BUY", conviction=0.6))
    assert I.idea_block(rows, (30,), floor=0.55)["horizons"]["30"]["buy_dives"]["judge"] == ""


def test_the_line_names_every_n_and_too_few():
    rows = [row("dive", "dive:a|A", 4.0, verdict="BUY", conviction=0.62, graph="native")]
    line = I.idea_line(I.idea_block(rows, (30,), floor=0.55), 30)
    assert "paper research" in line
    assert "BUY dives +4.0 points mean, median +4.0, 100% beat it (n 1, too few to judge)" \
        in line
    assert "rejected dives: none graded yet" in line
    assert "native +4.0 points mean" in line and "generic: none graded yet" in line
    empty = I.idea_line(I.idea_block([], (30,)), 30)
    assert empty.startswith("No deep dive")


def test_idea_rows_never_move_the_advice_report(tmp_path):
    """The advice report's figures with only idea rows in the store are those
    of an empty store; the ideas block has its five horizons."""
    store = AuditOutcomeStore(user_id="primary", base_dir=str(tmp_path))
    for h in (10, 30, 60):
        store.append(row("dive", "dive:a|A", 40.0, verdict="BUY", conviction=0.9, h=h))
        store.append(row("screen", "screen:a|B", -40.0, h=h, triggers=("not_dived",)))
    report = build_report(store=store, min_n=1)
    assert report["total_rows"] == 0
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert all(v is None for v in report["mean_excess_pct"].values())
    assert report["conviction_calibration"] == []
    assert sorted(report["ideas"]["horizons"], key=int) == ["10", "30", "60", "90", "180"]
    assert report["ideas"]["horizons"]["10"]["buy_dives"]["mean_excess_pct"] == 40.0
    text = render_section(report)
    assert "At 180 sessions" in text and "BUY dives +40.0 points mean" in text


# ---------------------------------------------------------------------------
# The old lanes' rows keep their shape
# ---------------------------------------------------------------------------

OLD_KEYS = ["ref", "lane", "user_id", "symbol", "verdict", "triggers", "issued_on", "horizon_td",
            "graded_on", "entry_close", "exit_close", "return_pct", "bench_entry", "bench_exit",
            "bench_pct", "excess_pct", "correct", "graded_at", "switch_excess_pct",
            "conviction", "candidate", "miss_class"]


def test_old_shelf_rows_are_byte_for_byte_unchanged(disc, tmp_path):
    """A shelf row already in the store (as the old code wrote it) keeps its
    bytes; a shelf row graded now has exactly the old keys, in the old order."""
    store = AuditOutcomeStore(user_id=settings.PORTFOLIO_DEFAULT_USER_ID,
                              base_dir=str(tmp_path / "pf"))
    old_line = ('{"ref":"shelf:2026-01-02|OLD","lane":"shelf","user_id":"%s","symbol":"OLD",'
                '"verdict":"","triggers":[],"issued_on":"2026-01-02","horizon_td":10,'
                '"graded_on":"2026-01-16","entry_close":100.0,"exit_close":104.0,'
                '"return_pct":4.0,"bench_entry":1000.0,"bench_exit":1010.0,"bench_pct":1.0,'
                '"excess_pct":3.0,"correct":null,"graded_at":"2026-01-16T18:15:00+00:00",'
                '"switch_excess_pct":null,"conviction":0.7,"candidate":"","miss_class":""}\n'
                % settings.PORTFOLIO_DEFAULT_USER_ID)
    store.path.write_text(old_line, encoding="utf-8")
    (disc / "shelf.json").write_text(json.dumps({"ideas": [{
        "symbol": "SHF", "sector": "generic", "added": "2026-03-07", "conviction": 0.7,
        "close_at_add": 100.0}]}), encoding="utf-8")
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    grade_due(FAR, settings.PORTFOLIO_DEFAULT_USER_ID, store=store, bench=Bench(),
              price_fn=lambda s, d: 105.0, base_dir=str(tmp_path / "pf"),
              shelf_path=str(disc / "shelf.json"), sent_log=str(tmp_path / "none.jsonl"),
              verdicts_dir=str(tmp_path / "ipo"), discovery_dir=str(disc),
              panel=flat_panel(["ABC"]), corp_actions=no_actions)
    lines = store.path.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[0] == old_line
    shelf_new = [json.loads(x) for x in lines[1:] if '"lane":"shelf"' in x]
    assert len(shelf_new) == 3                              # 10, 30, 60: horizons_td unchanged
    assert all(list(r) == OLD_KEYS for r in shelf_new)
    dive_new = [json.loads(x) for x in lines[1:] if '"lane":"dive"' in x]
    assert len(dive_new) == 5 and "entry_on" in dive_new[0]


def test_the_lanes_grade_only_for_the_default_user(disc, tmp_path):
    DiveRecord(str(disc)).append_run([dive("ABC", SAT, 0.7)], on=SAT)
    other = AuditOutcomeStore(user_id="member7", base_dir=str(tmp_path / "pf"))
    out = L.grade_idea_lanes(FAR, "member7", store=other, bench=Bench(),
                             discovery_dir=str(disc), panel=flat_panel(["ABC"]),
                             corp_actions=no_actions)
    assert out["dive"]["not_default_user"] and other.load_all() == []


def test_the_shipped_horizons_and_caps():
    import yaml
    from pathlib import Path
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / "config.yaml")
                            .read_text(encoding="utf-8"))
    assert config["audit"]["idea_horizons_td"] == [10, 30, 60, 90, 180]
    assert config["audit"]["horizons_td"] == [10, 30, 60]    # the other lanes keep theirs
    assert config["discovery"]["bare_judge_max_per_week"] == 20
    assert L.idea_horizons() == (10, 30, 60, 90, 180)


# ---------------------------------------------------------------------------
# The discovery run, end to end
# ---------------------------------------------------------------------------

def test_the_run_records_every_dive_before_the_memo_and_asks_the_bare_judge(
        tmp_path, monkeypatch):
    """Sat 4 Jul: the screen of Fri 3 Jul offers NEWA and NEWB, both dived.
    The memo already holds a rejected dive of 20 Jun (OLDR, NEUTRAL 0.41). The
    run's record holds OLDR (seeded, as the memo said before this run rewrote
    it), NEWA and NEWB at their convictions (0.7, 0.3) and one run row naming
    the screen; the bare judge was asked about both, with each one's own
    evidence and without its dossier."""
    import core.discovery as disc_mod
    import core.discovery.deep_dive as dd
    import tests.unit.test_idea_supply_pr004 as pr004

    on = date(2026, 7, 4)
    env = pr004._cycle_env(tmp_path, monkeypatch, screen=[pr004.cand("NEWA"), pr004.cand("NEWB")],
                           conviction={"NEWA": 0.7, "NEWB": 0.3})
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(disc_mod, "autopilot_sales", lambda: {})
    monkeypatch.setattr(disc_mod, "no_longer_held", lambda s: set())
    folder = tmp_path / "disc"
    (folder / "dives.json").write_text(json.dumps({"OLDR": {
        "date": "2026-06-20", "conviction": 0.41, "verdict": "NEUTRAL",
        "data_gate": "actionable"}}), encoding="utf-8")
    stub = env["analyst"].orchestrator

    def with_bundle(sector):
        orch = stub(sector)
        inner = orch.analyse

        def analyse(symbol, sector_question=None):
            report = inner(symbol, sector_question=sector_question)
            orch._last_bundle = SimpleNamespace(sections={
                "company_news": f"news about {symbol}", "dossier": "PRODUCT MEMORY"})
            return report
        orch.analyse = analyse
        return orch
    monkeypatch.setattr(dd, "get_orchestrator", with_bundle)
    asked: list[str] = []

    def call(system, user):
        asked.append(user)
        return json.dumps({"decision": "BUY", "conviction": 0.6, "reason": "r"}), "m"
    monkeypatch.setattr(BJ, "_call", call)

    result = disc_mod.run_discovery_cycle(on=on)

    record = DiveRecord(str(folder))
    by_ref = {r["ref"]: r for r in record.dive_rows()}
    assert by_ref["dive:2026-06-20|OLDR"]["recorded"] == "backfill"
    assert by_ref["dive:2026-06-20|OLDR"]["verdict"] == "NEUTRAL"
    assert (by_ref["dive:2026-07-04|NEWA"]["conviction"],
            by_ref["dive:2026-07-04|NEWB"]["conviction"]) == (0.7, 0.3)
    assert by_ref["dive:2026-07-04|NEWA"]["close"] == 100.0
    runs = [r for r in record.run_rows() if r["recorded"] == "at_dive"]
    assert [(r["run_date"], r["screen_date"], r["symbols"]) for r in runs] == [
        ("2026-07-04", "2026-07-03", ["NEWA", "NEWB"])]
    assert result["bare_judge"]["asked"] == 2 and len(asked) == 2
    assert any("news about NEWA" in u for u in asked)
    assert all("PRODUCT MEMORY" not in u for u in asked)
    # The memo itself moved on after the record was written.
    memo = json.loads((folder / "dives.json").read_text(encoding="utf-8"))
    assert {"NEWA", "NEWB"} <= set(memo)


def test_a_dive_without_a_price_is_counted_in_the_report(disc, store):
    """GAP (no bar on its entry Monday) and OK, both dived on 7 Mar: at every
    horizon 2 dives reached it and 1 is graded; the report says so."""
    DiveRecord(str(disc)).append_run([dive("GAP", SAT, 0.7), dive("OK", SAT, 0.7)], on=SAT)
    grade(store, disc, flat_panel(["OK"]))
    graded = store.load_all()
    cover = I.dive_coverage(DiveRecord(str(disc)).dive_rows(), graded, (10, 180), today=FAR)
    assert cover == {"10": {"reached": 2, "graded": 1, "not_graded": 1},
                     "180": {"reached": 2, "graded": 1, "not_graded": 1}}
    early = I.dive_coverage(DiveRecord(str(disc)).dive_rows(), graded, (10, 180),
                            today=date(2026, 3, 20))
    assert early["180"] == {"reached": 0, "graded": 0, "not_graded": 0}
    report = build_report(store=store)
    assert report["ideas"]["coverage"]["10"]["not_graded"] == 1
    assert "1 of 2 dives that reached it have no grade" in render_section(report)
