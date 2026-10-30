"""FIX-018: the switch gate sets aside a decision whose result can never be known, named and
within a cap.

Independent invariants, each from the card's acceptance criteria:

- the card's table, as hand-built populations with each status worked by hand (and the
  status the FIX-016 rule gave, which counted every missing result), plus three set aside at
  20, 30 and 50 decisions;
- an independent oracle written from the card in exact fractions over random populations; a
  set-aside decision weighs exactly as if it were absent, except through the cap; turning a
  graded decision into a temporary gap never turns a non-pass into a pass; no look passes
  with more set aside than the cap;
- through the real price path (FIX-016's market model): a demerger between the closes and an
  empty NSE list set the decision aside; a failed read of NSE's list and a Yahoo-only close
  fail the week; a decision graded at 10 sessions with a lasting gap at 30 is set aside at
  both; a registry basis change is lasting;
- in random markets: which decisions are set aside does not change when the two rules'
  verdicts are swapped, a lasting gap stays lasting with the same reason once every failed
  read is repaired, and no gap is temporary after that;
- grading's read of NSE's list tells a failed read from an empty answer; the holding sync
  still receives [] for both.
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from math import ceil

import pytest

from backend.shared.schemas.portfolio import Portfolio
from core.intelligence.rl.nse_calendar import trading_days_after
from core.portfolio import exit_shadow as xs
from tests.unit.test_exit_evidence_pr009 import D, _held
from tests.unit.test_exit_fix016 import (
    _KNOWN_ROWS, _ODD_ROWS, REGISTRY, _Market, _no_ratio, _real_rows, _session,
)

AS_OF = date(2026, 12, 31)
LASTING, TEMPORARY = "lasting", "temporary"        # the card's two kinds, spelled out


def test_the_cap_is_fixed_as_the_card_says():
    assert (xs.GATE_MAX_SET_ASIDE, xs.GATE_MAX_SET_ASIDE_PCT) == (2, 10.0)
    assert (xs.LASTING, xs.TEMPORARY, xs.CANNOT_JUDGE) == (LASTING, TEMPORARY, "cannot_judge")


# -- Hand-built populations ------------------------------------------------------------------------
#
# A decision: its review day, its stock, whether the evidence rule sold it, and per horizon its
# gap against the benchmark (a Fraction), LASTING or TEMPORARY (no result), or "pending" at 30.
# The evidence rule was right on a sale when the gap is below 0, on a keep when it is not, and
# its result is -gap on a sale and +gap on a keep.

def _population(graded, aside=0, temporary=0, aside_at=(10, 30), span_days=80, right=None):
    """`graded` decisions graded at both horizons, the evidence rule selling each: the first
    `right` (60% rounded up) right with +2 (the stock fell 2%), the rest wrong with -1 (it rose
    1%). Then `aside` decisions with a lasting gap at `aside_at` (graded right at the other
    horizon, if any), then `temporary` with no result at both horizons that may yet be read.
    Each its own stock; review days spread over `span_days`."""
    right = ceil(Fraction(6, 10) * graded) if right is None else right
    total = graded + aside + temporary
    out = []
    for i in range(total):
        d = {"day": date(2026, 6, 1) + timedelta(days=round(i * span_days / max(1, total - 1))),
             "symbol": f"S{i}", "sold": True}
        for h in (10, 30):
            if i < graded:
                d[h] = Fraction(-2) if i < right else Fraction(1)
            elif i < graded + aside:
                d[h] = LASTING if h in aside_at else Fraction(-2)
            else:
                d[h] = TEMPORARY
        out.append(d)
    return out


def _as_grades(decisions) -> list[dict]:
    """The decisions as grade_disagreements reports them."""
    out = []
    for d in decisions:
        for h in (10, 30):
            v = d[h]
            g = {"date": d["day"].isoformat(), "symbol": d["symbol"], "horizon_td": h,
                 "status": "graded", "right": None, "result_pct": None, "no_result": "",
                 "no_basis": "", "evidence_sold": d["sold"]}
            if v == "pending":
                g["status"] = "pending"
            elif v in (LASTING, TEMPORARY):
                g.update(status="ungraded", no_result=v,
                         no_basis=f"{v} cause of {d['symbol']} at {h}")
            else:
                g["right"] = (v < 0) if d["sold"] else (v >= 0)
                g["result_pct"] = float(-v if d["sold"] else v)
            out.append(g)
    return out


def _fix016_rule(grades) -> str:
    """The gate as FIX-016 left it: every missing result counted, none set aside."""
    return xs.gate_look([dict(g, no_result="") for g in grades])["status"]


# The card's table: (population, status after this story, decisions judged, reasons).
TABLE = [
    # 15 graded + 1 demerger: 1 of 16 (6%) set aside; judged on 15: 9 right (60%), a mean of
    # (9 x 2 - 6 x 1) / 15 = +0.80 at both horizons: passes, "not worse"
    (_population(15, aside=1), xs.PASS, 15, []),
    (_population(15, aside=1, aside_at=(30,)), xs.PASS, 15, []),   # lasting at 30 only
    (_population(15, aside=1, aside_at=(10,)), xs.PASS, 15, []),   # lasting at 10 only
    # 15 graded + 2 set aside: 2 of 17 (12%), above 10%
    (_population(15, aside=2), xs.CANNOT_JUDGE, 15,
     ["2 of the 17 decisions are set aside (more than 10%)"]),
    # 18 graded + 2 set aside: 2 of 20 is exactly 10%; 11 of 18 right, (22 - 7) / 18 = +0.83
    (_population(18, aside=2), xs.PASS, 18, []),
    # 14 graded + 1 set aside: 14 of the 15 it needs
    (_population(14, aside=1), xs.NOT_ENOUGH, 14,
     ["14 of the 15 decisions it needs have reached 30 sessions, not counting 1 set aside"]),
    # 15 graded + 1 set aside + 1 with no NSE close this Sunday: judged on 16, 9 right (56%),
    # and the 16th has no result, so the money check fails this week
    (_population(15, aside=1, temporary=1), xs.FAIL, 16,
     ["1 decision with no result at 10 sessions, so the money check cannot pass",
      "1 decision with no result at 30 sessions, so the money check cannot pass"]),
    # 3 set aside at 20, 30 and 50 decisions: 11 of 17 (+0.94), 17 of 27 (+0.89) and 29 of 47
    # (+0.85) right would pass; 3 is more than 2
    (_population(17, aside=3), xs.CANNOT_JUDGE, 17,
     ["3 of the 20 decisions are set aside (at most 2 may be)"]),
    (_population(27, aside=3), xs.CANNOT_JUDGE, 27,
     ["3 of the 30 decisions are set aside (at most 2 may be)"]),
    (_population(47, aside=3), xs.CANNOT_JUDGE, 47,
     ["3 of the 50 decisions are set aside (at most 2 may be)"]),
    # "cannot judge" replaces only a pass: a population that fails (7 of 15 right) or is short
    # (10 judged) keeps its status, whatever is set aside
    (_population(15, aside=3, right=7), xs.FAIL, 15,
     ["right on 7 of 15 at 10 sessions (needs 50%)", "right on 7 of 15 at 30 sessions (needs 50%)"]),
    (_population(10, aside=3), xs.NOT_ENOUGH, 10,
     ["10 of the 15 decisions it needs have reached 30 sessions, not counting 3 set aside"]),
]


@pytest.mark.parametrize("decisions, status, judged, reasons", TABLE)
def test_the_cards_table_by_hand(decisions, status, judged, reasons):
    grades = _as_grades(decisions)
    look = xs.gate_look(grades)
    aside = [d for d in decisions if LASTING in (d[10], d[30])]
    assert (look["status"], look["matured"], look["judged"], look["reasons"]) == (
        status, len(decisions), judged, reasons)
    assert look["set_aside"] == [
        {"date": d["day"].isoformat(), "symbol": d["symbol"],
         "reason": f"lasting cause of {d['symbol']} at {min(h for h in (10, 30) if d[h] == LASTING)}"}
        for d in aside]
    assert look["better"] is False                    # 60% to 65% right is short of 70%
    # FIX-016's rule counted each of them as a missing result: every row of the card's table
    # failed every week (the last row, 13 in all, was short of 15 under it too).
    assert _fix016_rule(grades) == (xs.FAIL if len(decisions) >= 15 else xs.NOT_ENOUGH)
    if status == xs.PASS:
        mean = sum(Fraction(2) if d[10] == -2 else Fraction(-1)
                   for d in decisions if d not in aside) / judged
        assert look["mean_result_pct"] == {"10": pytest.approx(float(mean)),
                                           "30": pytest.approx(float(mean))}


def test_the_lines_name_each_decision_set_aside_and_cannot_judge_breaks_the_run():
    rows_block = {"rows": 20, "decisions": 20, "repeat_days": 0,
                  "tally": [{"horizon_td": h, "graded": 17, "right": 11, "ungraded": 3,
                             "no_basis": 3, "no_basis_symbols": ["S17", "S18", "S19"],
                             "pending": 0, "vs_cash": 17, "vs_nifty": 0,
                             "mean_result_pct": 0.94, "mean_nifty_result_pct": 0.94}
                            for h in (10, 30)]}
    twenty = _population(17, aside=3)
    day = {d["symbol"]: d["day"].isoformat() for d in twenty}
    assert (day["S17"], day["S18"], day["S19"]) == ("2026-08-12", "2026-08-16", "2026-08-20")
    look = xs.gate_look(_as_grades(twenty))
    text = xs.scorecard_text(dict(rows_block, gate=look, recommend=False))
    assert text.endswith(
        " Switch gate: cannot judge (3 of the 20 decisions are set aside (at most 2 may be))."
        " Set aside, as their results can never be known: S17, decided 2026-08-12: lasting cause "
        "of S17 at 10; S18, decided 2026-08-16: lasting cause of S18 at 10; S19, decided "
        "2026-08-20: lasting cause of S19 at 10."), text
    one = xs.gate_look(_as_grades(_population(15, aside=1)))
    assert xs.scorecard_text(dict(rows_block, gate=one, recommend=False)).endswith(
        "; it must pass again next week. Set aside, as its result can never be known: S15, "
        "decided 2026-08-20: lasting cause of S15 at 10.")
    # Never a pass: "cannot judge" breaks the two-week run either way round.
    assert xs.recommends(one, {"status": xs.PASS}) is True
    assert xs.recommends(look, {"status": xs.PASS}) is False
    assert xs.recommends(one, {"status": xs.CANNOT_JUDGE}) is False


# -- The oracle --------------------------------------------------------------------------------------

def _oracle(decisions) -> tuple[str, bool]:
    """The card's gate in exact fractions. A decision past 30 sessions with a lasting gap at
    either horizon is set aside; the rest are judged as FIX-016 judged all of them (a
    temporary gap is not right and leaves the mean unknown); a pass with more than 2 set
    aside, or more than a tenth of those past 30 sessions, cannot be judged."""
    matured = [d for d in decisions if d[30] != "pending"]
    aside = [d for d in matured if LASTING in (d[10], d[30])]
    judged = [d for d in matured if all(d is not a for a in aside)]
    n = len(judged)
    if n < 15:
        return xs.NOT_ENOUGH, False
    days = [d["day"] for d in judged]
    if (max(days) - min(days)).days < 56:
        return xs.NOT_ENOUGH, False
    ok, better = True, True
    for h in (10, 30):
        known = [d for d in judged if isinstance(d[h], Fraction)]
        right = sum(1 for d in known if ((d[h] < 0) if d["sold"] else (d[h] >= 0)))
        if Fraction(right, n) < Fraction(1, 2):
            ok = False
        if len(known) < n:
            ok, better = False, False
            continue
        mean = sum((-d[h] if d["sold"] else d[h]) for d in judged) / n
        if mean < 0:
            ok = False
        if not (Fraction(right, n) >= Fraction(7, 10) and mean > 0):
            better = False
    top = max(sum(1 for d in judged if d["symbol"] == s) for s in {d["symbol"] for d in judged})
    if Fraction(top, n) > Fraction(3, 10):
        ok = False
    if not ok:
        return xs.FAIL, False
    if len(aside) > 2 or Fraction(len(aside), len(matured)) > Fraction(1, 10):
        return xs.CANNOT_JUDGE, False
    return xs.PASS, better


def _random_population(rnd: random.Random) -> list[dict]:
    """13-26 decisions; a stock is one decision per day. Half the populations lean right and
    profitable, so passes and "better" occur; gaps are lasting about 1 horizon in 18,
    temporary 1 in 50."""
    n = rnd.randint(13, 26)
    names = rnd.randint(4, n)
    span = rnd.randint(50, 90)
    skew = rnd.random() < 0.5
    out, taken = [], set()
    while len(out) < n:
        day, symbol = date(2026, 6, 1) + timedelta(days=rnd.randint(0, span)), f"S{rnd.randrange(names)}"
        if (day, symbol) in taken:
            continue
        taken.add((day, symbol))
        sold = rnd.random() < 0.5
        d = {"day": day, "symbol": symbol, "sold": sold}
        for h in (10, 30):
            k = 0 if rnd.random() < 0.1 else rnd.randint(-600, 600)
            if skew and rnd.random() < 0.75:
                k = abs(k) * (-1 if sold else 1)
            roll = rnd.random()
            d[h] = LASTING if roll < 0.055 else TEMPORARY if roll < 0.075 else Fraction(k, 100)
        if rnd.random() < 0.04:
            d[30] = "pending"
        out.append(d)
    return out


def test_the_gate_agrees_with_an_independent_oracle_and_only_the_cap_lets_a_gap_help():
    rnd = random.Random(20261029)
    seen = Counter()
    keys = ("status", "judged", "right", "mean_result_pct", "unknown_result", "span_days",
            "better")
    for _ in range(2000):
        decisions = _random_population(rnd)
        look = xs.gate_look(_as_grades(decisions))
        assert (look["status"], look["better"]) == _oracle(decisions), decisions
        seen[look["status"]] += 1
        seen["better"] += look["better"]
        aside = {(a["date"], a["symbol"]) for a in look["set_aside"]}
        matured = look["matured"]
        within = len(aside) <= 2 and len(aside) * 10 <= matured
        seen["pass with one or two set aside"] += look["status"] == xs.PASS and bool(aside)
        # No look passes with more set aside than the cap.
        if look["status"] == xs.PASS:
            assert within, look
        # A decision set aside weighs exactly as if it were absent, except through the cap.
        rest = [d for d in decisions if (d["day"].isoformat(), d["symbol"]) not in aside]
        alone = xs.gate_look(_as_grades(rest))
        assert alone["set_aside"] == []
        if within:
            assert {k: look[k] for k in keys} == {k: alone[k] for k in keys}
        else:
            assert look["status"] == (xs.CANNOT_JUDGE if alone["status"] == xs.PASS
                                      else alone["status"])
        # Turning a graded decision into a temporary gap: never a pass from a non-pass, and a
        # judged decision's pass becomes a fail.
        for i, d in enumerate(decisions):
            for h in (10, 30):
                if not isinstance(d[h], Fraction):
                    continue
                changed = [dict(x) for x in decisions]
                changed[i][h] = TEMPORARY
                after = xs.gate_look(_as_grades(changed))["status"]
                assert after == _oracle(changed)[0]
                if look["status"] != xs.PASS:
                    assert after != xs.PASS, (decisions, i, h)
                elif d[30] != "pending" and (d["day"].isoformat(), d["symbol"]) not in aside:
                    assert after == xs.FAIL
                    seen["pass lost to a temporary gap"] += 1
    assert all(seen[k] > 20 for k in (xs.PASS, xs.FAIL, xs.NOT_ENOUGH, xs.CANNOT_JUDGE, "better",
                                      "pass with one or two set aside",
                                      "pass lost to a temporary gap")), seen


# -- Through the real price path ---------------------------------------------------------------------
#
# FIX-016's market model: prices in real terms, NSE's raw close and action list and Yahoo's
# adjusted series written from what the actions do. The population is 15 sales by the evidence
# rule, S0-S8 then fell 2% (right, +2) and S9-S14 rose 1% (wrong, -1): (9 x 2 - 6 x 1) / 15 =
# +0.80, right on 9 of 15, over more than 8 weeks. S15, and S16 where named, are sales of stocks
# that then rose 5% (wrong, -5).

SPEC = [(True, -2.0)] * 9 + [(True, 1.0)] * 6


def _prices(market, monkeypatch) -> dict:
    quotes, actions = market.install(monkeypatch)
    return dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)


def _decided(rows, i) -> date:
    return date.fromisoformat(rows[i]["date"])


def test_a_demerger_between_the_closes_sets_the_decision_aside_and_the_rest_are_judged(
        monkeypatch):
    """S15 demerges 40% of its value three sessions after its decision: its raw close is then
    105 x 0.6 = ₹63, and NSE's row says only "Demerger". No re-read can put ₹63 in the old
    shares, so S15 is set aside at both horizons, named, and the gate judges the other 15 by
    hand: right on 9 of 15 at +0.80, a pass, and two weeks running it recommends the switch.
    Under FIX-016's rule the same grades failed every week."""
    market = _Market()
    rows = _real_rows(market, SPEC + [(True, 5.0)], span_days=80)
    ex = trading_days_after(_decided(rows, 15), 3)
    market.demerge("S15", ex, 0.6)
    prices = _prices(market, monkeypatch)
    reason = _no_ratio("demerger", ex.isoformat(), rows[15]["date"])
    grades = xs.grade_disagreements(rows, as_of=AS_OF, **prices)
    assert [(g["status"], g["no_result"], g["no_basis"]) for g in grades if g["symbol"] == "S15"] == [
        ("ungraded", LASTING, reason)] * 2
    assert {g["no_result"] for g in grades if g["symbol"] != "S15"} == {""}
    block = xs.scorecard_block(rows, as_of=AS_OF, **prices)
    look = block["gate"]
    assert (look["status"], look["matured"], look["judged"], look["right"],
            look["mean_result_pct"], look["unknown_result"]) == (
        xs.PASS, 16, 15, {"10": 9, "30": 9}, {"10": 0.8, "30": 0.8}, {"10": 0, "30": 0})
    assert look["set_aside"] == [{"date": rows[15]["date"], "symbol": "S15", "reason": reason}]
    assert _fix016_rule(grades) == xs.FAIL
    again = xs.scorecard_block(rows, as_of=AS_OF + timedelta(days=7), previous_look=look,
                               **prices)
    assert again["recommend"] is True
    text = xs.scorecard_text(again)
    assert "Switch gate: passed two weeks running" in text
    assert text.endswith(f" Set aside, as its result can never be known: S15, decided "
                         f"{rows[15]['date']}: {reason}.")


def test_two_set_aside_of_17_cannot_be_judged_and_recommend_nothing(monkeypatch):
    market = _Market()
    rows = _real_rows(market, SPEC + [(True, 5.0)] * 2, span_days=80)
    for i in (15, 16):
        market.demerge(f"S{i}", trading_days_after(_decided(rows, i), 3), 0.6)
    prices = _prices(market, monkeypatch)
    block = xs.scorecard_block(rows, as_of=AS_OF, **prices)
    look = block["gate"]
    assert (look["status"], look["judged"], [a["symbol"] for a in look["set_aside"]]) == (
        xs.CANNOT_JUDGE, 15, ["S15", "S16"])
    text = xs.scorecard_text(block)
    assert ("Switch gate: cannot judge (2 of the 17 decisions are set aside (more than 10%)). "
            "Set aside, as their results can never be known: S15, decided ") in text
    again = xs.scorecard_block(rows, as_of=AS_OF + timedelta(days=7), previous_look=look,
                               **prices)
    assert (again["recommend"], again["gate"]["status"]) == (False, xs.CANNOT_JUDGE)


def test_an_empty_list_sets_aside_and_a_failed_read_fails_the_week_until_it_is_read(monkeypatch):
    """S15's NSE list: empty (NSE lists nothing for it, as for 14 configured codes on 29 Oct
    2026), it is set aside for good and the 15 pass. A read that fails that Sunday instead:
    S15 counts, with no result, so the money check fails that week and nothing is set aside.
    The next Sunday the read works: S15 is graded, a sale before a 5% rise, wrong with -5, and
    the 16 pass at (18 - 6 - 5) / 16 = +0.4375, right on 9 of 16."""
    market = _Market()
    rows = _real_rows(market, SPEC + [(True, 5.0)], span_days=80)
    market.unlisted.add("S15")
    look = xs.scorecard_block(rows, as_of=AS_OF, **_prices(market, monkeypatch))["gate"]
    assert (look["status"], look["judged"], look["set_aside"]) == (xs.PASS, 15, [{
        "date": rows[15]["date"], "symbol": "S15",
        "reason": f"NSE's list of its corporate actions is empty, so one since {rows[15]['date']} "
                  "cannot be ruled out"}])

    market.unlisted.clear()
    market.nse_fails.add("S15")
    prices = _prices(market, monkeypatch)
    grades = xs.grade_disagreements(rows, as_of=AS_OF, **prices)
    assert [(g["no_result"], g["no_basis"]) for g in grades if g["symbol"] == "S15"] == [
        (TEMPORARY, f"NSE's list of its corporate actions could not be read, so one since "
                    f"{rows[15]['date']} cannot be ruled out")] * 2
    look = xs.gate_look(grades)
    assert (look["status"], look["judged"], look["right"], look["unknown_result"],
            look["set_aside"]) == (xs.FAIL, 16, {"10": 9, "30": 9}, {"10": 1, "30": 1}, [])

    market.nse_fails.clear()
    look = xs.scorecard_block(rows, as_of=AS_OF + timedelta(days=7),
                              **_prices(market, monkeypatch))["gate"]
    assert (look["status"], look["judged"], look["right"], look["mean_result_pct"]) == (
        xs.PASS, 16, {"10": 9, "30": 9}, {"10": 0.4375, "30": 0.4375})


def test_a_yahoo_only_close_fails_the_week_until_nses_close_answers(monkeypatch):
    """S15 goes ex on a 1:1 bonus 35 sessions after its decision, after both horizons, and
    NSE's close does not answer on S15's horizon days: Yahoo's series, read after the bonus, is
    in the later basis, so S15 has no result for now, the week fails and nothing is set aside.
    When NSE answers, S15 is graded (wrong, -5) and the 16 pass."""
    market = _Market()
    rows = _real_rows(market, SPEC + [(True, 5.0)], span_days=80)
    decided = _decided(rows, 15)
    market.bonus("S15", trading_days_after(decided, 35))
    market.nse_down = {trading_days_after(decided, h) for h in (10, 30)}
    grades = xs.grade_disagreements(rows, as_of=AS_OF, **_prices(market, monkeypatch))
    s15 = [g for g in grades if g["symbol"] == "S15"]
    assert [(g["status"], g["no_result"]) for g in s15] == [("ungraded", TEMPORARY)] * 2
    assert all(g["no_basis"].startswith("the horizon close is Yahoo's alone") for g in s15)
    look = xs.gate_look(grades)
    assert (look["status"], look["unknown_result"], look["set_aside"]) == (
        xs.FAIL, {"10": 1, "30": 1}, [])
    market.nse_down = set()
    look = xs.scorecard_block(rows, as_of=AS_OF, **_prices(market, monkeypatch))["gate"]
    assert (look["status"], look["judged"], look["unknown_result"]) == (
        xs.PASS, 16, {"10": 0, "30": 0})


def test_graded_at_10_sessions_with_a_lasting_gap_at_30_is_set_aside_at_both(monkeypatch):
    """S15 is a sale before a 2% fall, right with +2 at 10 sessions. It demerges 15 sessions
    after its decision, between its two horizons, so at 30 sessions it has no result for good.
    It is set aside at both horizons: its right 10-session grade is not counted (9 of 15 right
    at 10, not 10 of 16)."""
    market = _Market()
    rows = _real_rows(market, SPEC + [(True, -2.0)], span_days=80)
    market.demerge("S15", trading_days_after(_decided(rows, 15), 15), 0.6)
    prices = _prices(market, monkeypatch)
    grades = {g["horizon_td"]: g for g in xs.grade_disagreements(rows[15:], as_of=AS_OF, **prices)}
    assert (grades[10]["status"], grades[10]["right"], grades[10]["result_pct"]) == (
        "graded", True, 2.0)
    assert (grades[30]["status"], grades[30]["no_result"]) == ("ungraded", LASTING)
    look = xs.scorecard_block(rows, as_of=AS_OF, **prices)["gate"]
    assert (look["status"], look["judged"], look["right"], look["mean_result_pct"]) == (
        xs.PASS, 15, {"10": 9, "30": 9}, {"10": 0.8, "30": 0.8})
    assert [a["symbol"] for a in look["set_aside"]] == ["S15"]


@pytest.mark.parametrize("via, kind", [("demerger", LASTING), ("rename", "")])
def test_a_basis_change_only_the_registry_records_is_lasting(monkeypatch, tmp_path, via, kind):
    """FIX-016's RR3 registry: from 28 Oct BBB is priced from another code. As a demerger the
    registry records a new basis, which no re-read changes; as a rename it is graded."""
    code, basis, after = ("BBBA", "BBBA", 114.0) if via == "demerger" else ("BBBN", "BBB", 190.0)
    registry = tmp_path / "instruments.yaml"
    registry.write_text(REGISTRY.format(code=code, basis=basis, via=via), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(registry))
    market = _Market()
    market.value = {"BBB": lambda d: 190.0, code: lambda d: after}
    row = {"date": D.isoformat(), "symbol": "BBB", "close": 190.0, "mode": "shadow",
           "buy_date": "2026-09-01", "price_bar_date": D.isoformat(), "legacy_verdict": "HOLD",
           "evidence_verdict": "EXIT", "disagree": True, "benchmark": "cash"}
    grades = xs.grade_disagreements([row], as_of=AS_OF, **_prices(market, monkeypatch))
    assert [g["no_result"] for g in grades] == [kind] * 2


def test_a_missing_close_a_missing_benchmark_or_an_unread_list_is_temporary():
    """Each may be read next week, so each counts against the evidence rule this week."""
    from core.portfolio.pricing import SessionClose
    from tests.unit.test_exit_evidence_pr009 import _no_actions
    row = {"date": "2026-06-01", "symbol": "AAA", "close": 100.0, "mode": "shadow",
           "buy_date": "2026-05-04", "price_bar_date": "", "legacy_verdict": "HOLD",
           "evidence_verdict": "EXIT", "disagree": True, "benchmark": "cash"}

    def no_close(symbol, day):
        raise LookupError("no close")

    def unread(symbol):
        raise ConnectionError("NSE refused")
    nse = lambda symbol, day: SessionClose(95.0, day, "nse")            # noqa: E731
    cases = [
        ([row], no_close, _no_actions),
        ([row], lambda symbol, day: SessionClose(None, day, "nse"), _no_actions),
        ([dict(row, benchmark="")], nse, _no_actions),
        ([row], nse, unread),
    ]
    for rows, quotes, actions in cases:
        grades = xs.grade_disagreements(rows, as_of=AS_OF, stock_quote_on=quotes,
                                        bench_close_on=lambda d: 1000.0, corp_actions=actions)
        assert [(g["status"], g["no_result"]) for g in grades] == [("ungraded", TEMPORARY)] * 2
    graded = xs.grade_disagreements([row], as_of=AS_OF, stock_quote_on=nse,
                                    bench_close_on=lambda d: 1000.0, corp_actions=_no_actions)
    assert [(g["status"], g["no_result"], g["right"]) for g in graded] == [("graded", "", True)] * 2


# -- Random markets: what is set aside, and what stays so ---------------------------------------------

def test_set_aside_depends_only_on_prices_lists_and_the_registry_and_a_lasting_gap_stays(
        monkeypatch):
    """Random markets, through the real price path. Each decision's stock moves after its
    review day, and NSE lists up to three rows for it ex from 5 sessions before the decision to
    35 after (bonuses and splits in the words the record reads, neutral rows, and FIX-016's odd
    rows), or a demerger; NSE's close is down on some days; some lists are empty and some cannot
    be read. Expected:

    - swapping which rule sold each stock leaves every grade's status, kind and reason, and
      the decisions set aside, the same;
    - once every failed read is repaired (NSE's close answers every day and every list is
      read), a lasting gap is still lasting with the same reason, a temporary one is graded or
      lasting, and none is temporary."""
    rnd = random.Random(20261030)
    seen = Counter()
    for _trial in range(6):
        market = _Market()
        rows = []
        for i in range(25):
            symbol = f"W{i}"
            day = trading_days_after(date(2026, 6, 1), rnd.randrange(0, 40))
            move = rnd.choice([-7.0, -2.5, 0.0, 3.0, 12.0])
            market.value[symbol] = lambda d, day=day, move=move: 100.0 if d <= day else 100.0 + move
            listed = set()
            for _n in range(rnd.randrange(0, 4)):
                subject, kind, effect = rnd.choice(_KNOWN_ROWS if rnd.random() < 0.6 else _ODD_ROWS)
                ex = _session(day, rnd.randrange(-5, 36))
                if (subject, ex) in listed:
                    continue
                listed.add((subject, ex))
                row = {"subject": subject, "exDate": ex.strftime("%d-%b-%Y")}
                bucket = market.actions if kind == "ratio" else market.demergers
                bucket.setdefault(symbol, []).append((ex, effect, row))
            if rnd.random() < 0.15:
                market.demerge(symbol, _session(day, rnd.randrange(-5, 36)), 0.6)
            roll = rnd.random()
            if roll < 0.1:
                market.unlisted.add(symbol)
            elif roll < 0.25:
                market.nse_fails.add(symbol)
            sold = rnd.random() < 0.5
            rows.append({"date": day.isoformat(), "symbol": symbol,
                         "close": market.raw(symbol, day), "mode": "shadow",
                         "buy_date": "2026-05-04", "price_bar_date": day.isoformat(),
                         "legacy_verdict": "HOLD" if sold else "EXIT",
                         "evidence_verdict": "EXIT" if sold else "HOLD", "disagree": True,
                         "benchmark": "cash"})
        market.nse_down = {trading_days_after(date(2026, 6, 1), k) for k in range(80)
                           if rnd.random() < 0.3}
        swapped = [dict(r, legacy_verdict=r["evidence_verdict"],
                        evidence_verdict=r["legacy_verdict"]) for r in rows]

        def classes(grades):
            return {(g["symbol"], g["horizon_td"]): (g["status"], g["no_result"], g["no_basis"])
                    for g in grades}
        prices = _prices(market, monkeypatch)
        first = xs.grade_disagreements(rows, as_of=AS_OF, **prices)
        flipped = xs.grade_disagreements(swapped, as_of=AS_OF, **_prices(market, monkeypatch))
        assert classes(first) == classes(flipped)
        assert xs.gate_look(first)["set_aside"] == xs.gate_look(flipped)["set_aside"]
        assert {g["right"] for g in first if g["status"] == "graded"} == {True, False}

        market.nse_down, market.nse_fails = set(), set()
        repaired = classes(xs.grade_disagreements(rows, as_of=AS_OF,
                                                  **_prices(market, monkeypatch)))
        for key, (status, kind, reason) in classes(first).items():
            seen[kind or status] += 1
            if kind == LASTING:
                assert repaired[key] == (status, kind, reason), key
            elif kind == TEMPORARY:
                assert repaired[key][1] != TEMPORARY, key
                seen["temporary, then " + (repaired[key][1] or "graded")] += 1
        assert TEMPORARY not in {kind for _s, kind, _r in repaired.values()}
    assert all(seen[k] > 5 for k in ("graded", LASTING, TEMPORARY, "temporary, then graded",
                                     "temporary, then lasting")), seen


# -- Reading NSE's list ------------------------------------------------------------------------------

class _Client:
    """An NSE client whose actions() answer is `answer` (raised when an exception)."""
    def __init__(self, answer):
        self.answer = answer

    def actions(self, symbol):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def exit(self):
        pass


BONUS = {"subject": "Bonus 1:1", "exDate": "28-Oct-2026"}


@pytest.mark.parametrize("answer, rows", [
    ([], []), ({"data": []}, []), ([BONUS], [BONUS]), ({"data": [BONUS]}, [BONUS]),
    (ConnectionError("corporates-corporateActions 503"), None),
    (TimeoutError("read timed out"), None), ({}, None), ({"data": None}, None), (None, None),
    ("<html>", None), ("client", None),
])
def test_grading_tells_a_failed_read_from_an_empty_answer_and_the_sync_does_not(
        monkeypatch, answer, rows):
    """`read_corp_actions` returns NSE's rows, [] only for an empty answer, and raises when the
    list could not be read (no client, a failed request, an answer of no known shape).
    `fetch_corp_actions`, which the holding sync reads, still returns [] for both."""
    from services.data.fetchers import corporate_events as ce

    def client():
        if answer == "client":
            raise ImportError("nse unavailable")
        return _Client(answer)
    monkeypatch.setattr(ce, "_make_nse_client", client)
    if rows is None:
        with pytest.raises(Exception):
            ce.read_corp_actions("AAA")
        assert ce.fetch_corp_actions("AAA") == []
    else:
        assert ce.read_corp_actions("AAA") == rows == ce.fetch_corp_actions("AAA")


def test_the_sync_receives_the_same_for_a_failed_read_and_an_empty_list(monkeypatch, tmp_path):
    """Through the real sync (core/portfolio/corp_actions.py), unchanged until FIX-017: a list
    that cannot be read and an empty one both give the holding nothing to apply and the same
    record."""
    from core.portfolio.corp_actions import action_record, sync_corp_actions
    from core.portfolio.store import PortfolioStore
    from services.data.fetchers import corporate_events as ce
    got = []
    for answer in ([], ConnectionError("corporates-corporateActions 503")):
        monkeypatch.setattr(ce, "_make_nse_client", lambda answer=answer: _Client(answer))
        store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / str(len(got))))
        store.save(Portfolio(user_id="u1", holdings=[_held("2026-09-15")]))
        got.append(sync_corp_actions(store, D))
    assert got[0] == got[1] == {"applied": 0, "symbols": [],
                                "records": {"AAA": action_record([], "AAA")}}


def test_grading_reads_each_list_once_and_names_a_failed_read_as_temporary(monkeypatch):
    """results.corp_actions_fn: a failed read is None, asked once per scorecard like any other;
    an empty answer is a record of no rows. Graded on one quote, the first is temporary and the
    second lasting."""
    from backend.shared.data.fetchers import symbol_resolver
    from core.portfolio import results
    from core.portfolio.corp_actions import action_record
    from core.portfolio.pricing import SessionClose
    from services.data.fetchers import corporate_events as ce
    reads = []

    def client():
        return _Client(ConnectionError("503") if reads[-1] == "FAILS" else [])
    monkeypatch.setattr(symbol_resolver, "_load_cache", lambda: {})
    monkeypatch.setattr(ce, "read_corp_actions",
                        lambda s, real=ce.read_corp_actions: reads.append(s) or real(s))
    monkeypatch.setattr(ce, "_make_nse_client", client)
    lookup = results.corp_actions_fn()
    got = [lookup(s) for s in ("FAILS", "FAILS", "EMPTY", "EMPTY")]
    assert got[:2] == [None, None] and got[2] == got[3] == action_record([], "EMPTY")
    assert reads == ["FAILS", "EMPTY"]
    assert (got[2].rows, got[2].covers_from) == (0, "")
    quote = SessionClose(100.0, date(2026, 11, 6), "nse")
    kinds = [xs.horizon_in_basis(quote, lookup(s), D, D)[3] for s in ("FAILS", "EMPTY")]
    assert kinds == [TEMPORARY, LASTING]
