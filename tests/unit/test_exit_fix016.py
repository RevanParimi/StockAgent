"""FIX-016: the evidence exit's inputs and its switch gate, fixed before the shadow starts.

Independent invariants, each from the card's acceptance criteria:

- verdict: a SELL run on or before the buy day never sells; a SELL 22 sessions
  old sells and one 23 sessions old does not; a newer BUY over an older SELL
  does not sell;
- events: a high-negative news article never sells, by any route, and is a
  watch item; the same event filed with NSE sells; a pledge invocation typed by
  the disclosure rules sells; every event source is decided one way or the other;
- benchmark: stock -3%, Nifty -5%: a plain EXIT graded against cash says selling
  was right, a SWITCH graded against the Nifty says it was wrong; the benchmark
  is the one stored on the decision day, whatever comes after;
- money check: hand-built populations (the card's 8-right/-3.6% example fails;
  50% with a positive mean passes; "better" only at 70% with a positive mean)
  and an independent oracle written from the card in exact fractions; a graded
  decision turned into a missing one never turns a fail into a pass.

Rework 1 (the fresh review's F1, F2, I1):

- one price basis: a bonus or split between a decision and its horizon is not a
  result (the review's RV1 and RV2, through the real price path with only
  Yahoo's series, NSE's close and NSE's action list faked); a basis that cannot
  be established gives no result, named, and never helps the evidence rule;
- a SWITCH whose buy leg the executor refuses leaves the money in cash, and its
  row says so;
- the research verdict's reason shows the IST day the freshness rule used.

Rework 2 (the fresh re-review's RR-F1):

- a demerger between a decision and its horizon is not a fall: no ratio converts it, so
  the decision has no result, named (the re-review's RR1 and RR2 through the real price
  path; RR3, a new basis only the instrument registry records, and a rename that keeps
  the basis); every change no ratio converts, by NSE's own wording, and a row naming a
  bonus and a split, are no result too; a graded result is always the return in real
  terms (random markets).

The review day is Friday 23 Oct 2026, as in tests/unit/test_exit_evidence_pr009.py.
NSE holidays 14 Sep, 2 Oct and 20 Oct: counting back from 23 Oct, 10 sessions is
Thursday 8 Oct, 22 sessions is Monday 21 Sep and 23 sessions is Friday 18 Sep.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest

from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.events import SOURCES
from core.intelligence.rl.nse_calendar import trading_days_after, trading_days_ago
from core.portfolio import exit_shadow as xs
from core.portfolio.advisor import CASE_EVENT_SOURCES, ExitEvidence, case_broken_reasons, decide
from tests.unit.test_exit_evidence_pr009 import (
    D, _event, _holding, _no_actions, _nse, _pipeline_world, _record, _signals, _world,
)

HOLIDAYS = {date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20)}


def _sessions_after(day: date, until: date = D) -> int:
    """Exchange sessions after `day` up to `until`, counted by hand: weekdays
    that are not one of the fixture's holidays."""
    n, d = 0, day + timedelta(days=1)
    while d <= until:
        n += d.weekday() < 5 and d not in HOLIDAYS
        d += timedelta(days=1)
    return n


def test_the_fixture_sessions():
    assert xs.RESEARCH_VERDICT_SESSIONS == 22
    assert (_sessions_after(date(2026, 9, 21)), _sessions_after(date(2026, 9, 18))) == (22, 23)
    assert _sessions_after(date(2026, 9, 20)) == 23            # a Sunday before the 22nd session
    assert _sessions_after(date(2026, 10, 8)) == 10
    assert trading_days_ago(D, 22) == date(2026, 9, 21) and trading_days_ago(D, 10) == date(2026, 10, 8)


def _decision(ev: ExitEvidence, close: float = 500.0):
    """The evidence rule's verdict on a holding where the price-path rule sees nothing."""
    holding = _holding("AAA", 500.0, sessions=ev.sessions_held or 0)
    assert decide(_signals("AAA", close=close), holding, "balanced").verdict == "HOLD"
    return decide(_signals("AAA", close=close), holding, "balanced", exit_rule="evidence",
                  evidence=ev)


def _ist(day: str, hh_mm: str = "10:30") -> str:
    """A score-history run_at (naive UTC) for an IST wall-clock time."""
    t = datetime.fromisoformat(f"{day}T{hh_mm}:00") - timedelta(hours=5, minutes=30)
    return t.isoformat()


# -- A fresh verdict --------------------------------------------------------------------------

def test_a_sell_counts_until_it_is_22_sessions_old():
    """Bought 25 Aug, 40 sessions before 23 Oct."""
    def verdict(run_at):
        return xs.exit_evidence(_holding(sessions=40), D, records=[_record(run_at=run_at)])
    assert _holding(sessions=40).buy_date == "2026-08-25"
    twenty_two = verdict(_ist("2026-09-21"))
    assert twenty_two.research_verdict == "SELL"
    assert _decision(twenty_two).triggers == ["case_broken"]
    for stale in (_ist("2026-09-18"),                        # 23 sessions old
                  _ist("2026-09-20", "23:59")):              # a Sunday: 23 sessions after it
        ev = verdict(stale)
        assert (ev.research_verdict, ev.research_run_at) == ("", ""), stale
        assert _decision(ev).verdict == "HOLD"
    # One minute later it is Monday 21 Sep in IST: 22 sessions old.
    assert verdict(_ist("2026-09-21", "00:01")).research_verdict == "SELL"


def test_a_sell_the_buyer_could_have_seen_never_sells():
    """The card's example: a stock added by hand on 8 Oct although its analysis two weeks
    earlier said SELL. Ten sessions later (23 Oct) the evidence rule keeps it. Any run on
    the buy day itself could have been seen before buying too; from the next IST day a
    SELL counts."""
    assert _holding(sessions=10).buy_date == "2026-10-08"

    def verdict(run_at):
        return xs.exit_evidence(_holding(sessions=10), D, records=[_record(run_at=run_at)])
    for seen in (_ist("2026-09-24"), _ist("2026-10-07"), _ist("2026-10-08", "09:30"),
                 _ist("2026-10-08", "23:59")):
        ev = verdict(seen)
        assert ev.sessions_held == 10 and ev.research_verdict == "", seen
        assert _decision(ev).verdict == "HOLD"
    for after in (_ist("2026-10-09", "00:01"), _ist("2026-10-15")):
        ev = verdict(after)
        assert ev.research_verdict == "SELL", after
        assert _decision(ev).triggers == ["case_broken"]


def test_a_newer_buy_over_an_older_sell_does_not_sell():
    def verdict(*records):
        return xs.exit_evidence(_holding(sessions=40), D, records=list(records)).research_verdict
    sell, buy = _record(run_at=_ist("2026-10-13")), _record(verdict="BUY", run_at=_ist("2026-10-19"))
    assert verdict(sell, buy) == "BUY"
    assert verdict(_record(verdict="BUY", run_at=_ist("2026-10-13")),
                   _record(run_at=_ist("2026-10-19"))) == "SELL"
    # A BUY from before the buy does not hide a SELL after it, nor stand in for one.
    held_10 = xs.exit_evidence(_holding(sessions=10), D, records=[
        _record(verdict="BUY", run_at=_ist("2026-10-07")), _record(run_at=_ist("2026-10-12"))])
    assert held_10.research_verdict == "SELL"
    assert xs.exit_evidence(_holding(sessions=10), D, records=[
        _record(verdict="BUY", run_at=_ist("2026-10-07"))]).research_verdict == ""


def test_an_unreadable_buy_date_lets_no_verdict_count():
    holding = _holding(sessions=40)
    holding.buy_date = "not a date"
    ev = xs.exit_evidence(holding, D, records=[_record(run_at=_ist("2026-10-22"))])
    assert (ev.research_verdict, ev.sessions_held) == ("", None)


def test_through_the_pipeline_a_sell_from_before_a_hand_added_buy_never_sells(monkeypatch,
                                                                              tmp_path):
    """The card's example under `evidence`, through the real pipeline and autopilot."""
    import core.portfolio.pipeline as pipeline
    for run_at, sells in ((_ist("2026-09-24"), False), (_ist("2026-10-09"), True)):
        store = _world(monkeypatch, tmp_path / run_at[:10], "evidence",
                       holdings=[_holding("FFF", 500.0, sessions=10)], closes={"FFF": 495.0},
                       records=[_record("FFF", "SELL", run_at=run_at)])
        pipeline.run_post_review_pipeline(D)
        row = next(r for r in store.load_exit_shadow() if r["symbol"] == "FFF")
        sold = [t.symbol for t in store.load_transactions() if t.side == "SELL"]
        assert (row["evidence_verdict"] == "EXIT", sold == ["FFF"]) == (sells, sells), run_at
        assert row["evidence"]["research_verdict"] == ("SELL" if sells else "")


# -- Only a filed or rule-typed event sells --------------------------------------------------------

def _news(**kw):
    return _event(**kw).model_copy(update={"source": "news", "classifier": "bulk-model",
                                           "publisher": "A Daily"})


def test_every_event_source_is_decided():
    """A source added later must be put on one side on purpose: news is the only one
    that never sells alone."""
    assert set(CASE_EVENT_SOURCES) == set(SOURCES) - {"news"}


@pytest.mark.parametrize("source", SOURCES)
def test_a_high_negative_event_sells_only_from_a_filing_or_a_rule_typed_disclosure(source):
    event = _event(published="2026-10-21T10:00:00+05:30").model_copy(update={"source": source})
    ev = xs.exit_evidence(_holding(), D, events=[event])
    if source == "news":
        assert ev.negative_events == [] and [e["id"] for e in ev.watch_events] == [event.id]
        assert case_broken_reasons(ev, 500.0) == [] and _decision(ev).verdict == "HOLD"
    else:
        assert ev.watch_events == [] and [e["id"] for e in ev.negative_events] == [event.id]
        assert _decision(ev).triggers == ["case_broken"]


def test_a_news_article_is_a_watch_item_in_the_row_and_never_a_reason():
    news = _news(published="2026-10-21T10:00:00+05:30")
    filed = _event(published="2026-10-22T10:00:00+05:30", n=2)
    holding = _holding()
    ev = xs.exit_evidence(holding, D, events=[news])
    legacy = decide(_signals(), holding, "balanced")
    row = xs.shadow_row(on=D, user_id="u1", mode="shadow", close=500.0, legacy=legacy,
                        evidence_rec=_decision(ev), evidence=ev, buy_date=holding.buy_date)
    assert row.evidence["event_ids"] == [] and row.evidence["watch_event_ids"] == [news.id]
    assert row.case_broken_reasons == [] and row.disagree is False and row.benchmark == ""
    # The same article filed with NSE sells; with both, only the filing is a reason.
    both = xs.exit_evidence(holding, D, events=[news, filed])
    assert case_broken_reasons(both, 500.0) == [
        "negative results event of 2026-10-22: Quarterly profit fell 40% on a large write-off."]
    assert [e["id"] for e in both.watch_events] == [news.id]


def test_a_news_article_cannot_sell_by_another_route():
    """Put straight into the selling list, or with no source at all, an event still
    never breaks the case: case_broken_reasons checks the source itself."""
    brief = {"id": "n1", "published_at": "2026-10-21T10:00:00+05:30", "category": "results",
             "what": "A headline."}
    for event in ({**brief, "source": "news"}, brief, {**brief, "source": ""}):
        ev = ExitEvidence(sessions_held=20, negative_events=[event])
        assert case_broken_reasons(ev, 500.0) == [], event
        assert _decision(ev).verdict == "HOLD"
    assert _decision(ExitEvidence(sessions_held=20, negative_events=[
        {**brief, "source": "nse_board_meeting"}])).triggers == ["case_broken"]


def test_a_pledge_invocation_typed_by_the_disclosure_rules_sells():
    """The recorded NSE Reg 31 row (VINCOFE, filed 22 Oct 20:49 IST), turned into an
    invocation: the rules type it high and negative, and it sells the holding."""
    from core.events import disclosures as dz
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "company_events"
    rows = json.loads((fixture / "nse_disclosures_20261023.json").read_text("utf-8"))
    row = dict(rows["pledge_events"][0], eventDetailsType="Invocation")
    now = datetime.fromisoformat("2026-10-23T08:15:00+05:30")
    (event,), _, _ = dz.pledge_events([row], "VINCOFE", "AAA", now, now.isoformat(),
                                      date(2026, 10, 16))
    assert (event.source, event.classifier, event.direction, event.materiality) == (
        "nse_pledge", "rules", "negative", "high")
    ev = xs.exit_evidence(_holding(), D, events=[event])
    assert _decision(ev).triggers == ["case_broken"]
    assert case_broken_reasons(ev, 500.0)[0].startswith(
        "negative pledge event of 2026-10-22: A lender invoked a pledge given by a promoter")


def test_through_the_pipeline_news_is_watched_and_a_filing_sells(monkeypatch, tmp_path):
    import core.portfolio.pipeline as pipeline
    from core.events.store import EventStore
    for name, event, sells in (("news", _news(symbol="GGG"), False),
                               ("filed", _event(symbol="GGG"), True)):
        store = _world(monkeypatch, tmp_path / name, "evidence",
                       holdings=[_holding("GGG", 500.0, sessions=20)], closes={"GGG": 495.0},
                       records=[_record("GGG", "BUY")])
        events = EventStore(tmp_path / name / "events")
        events.append_new("GGG", [event])
        monkeypatch.setattr(xs.EvidenceReader, "_event_store", lambda self, e=events: e)
        pipeline.run_post_review_pipeline(D)
        row = next(r for r in store.load_exit_shadow() if r["symbol"] == "GGG")
        sold = [t.symbol for t in store.load_transactions() if t.side == "SELL"]
        ids = (row["evidence"]["event_ids"], row["evidence"]["watch_event_ids"])
        assert ids == (([event.id], []) if sells else ([], [event.id])), name
        assert (row["evidence_verdict"], sold) == (("EXIT", ["GGG"]) if sells else ("HOLD", []))


# -- The money's real alternative ---------------------------------------------------------------

@pytest.mark.parametrize("legacy, evidence, deploys, benchmark", [
    ("EXIT", "HOLD", False, "cash"), ("HOLD", "EXIT", False, "cash"),
    ("SWITCH", "HOLD", False, "nifty"), ("HOLD", "SWITCH", False, "nifty"),
    ("TRIM", "EXIT", False, "cash"), ("ADD", "SWITCH", False, "nifty"),
    ("EXIT", "HOLD", True, "nifty"), ("HOLD", "EXIT", True, "nifty"),
    ("EXIT", "SWITCH", False, ""), ("HOLD", "TRIM", False, ""), ("EXIT", "EXIT", True, ""),
])
def test_where_the_money_went(legacy, evidence, deploys, benchmark):
    assert xs.decision_benchmark(legacy, evidence, deploys_cash=deploys) == benchmark


def _switch_world():
    """BBB (automobile) with a fresh SELL; ZZZ, an IT idea well above its confidence, in a
    sector the portfolio does not hold, so an EXIT becomes a SWITCH into ZZZ. Its entry band
    ₹48.50-₹51.00 holds ZZZ's ₹50 close, so the executor would buy it (rework 1, F2)."""
    holding = _holding("BBB", 200.0, sessions=20)
    ev = xs.exit_evidence(holding, D, records=[_record("BBB", "SELL")])
    idea = ShelfIdea(symbol="ZZZ", sector="it", added="2026-10-01", dived="2026-10-01",
                     conviction=0.9, status="active", entry_low=48.5, entry_high=51.0)
    return holding, ev, dict(shelf_ideas=[idea], sector_weights={"automobile": 40.0},
                             held_symbols={"BBB"})


def test_minus_3_against_minus_5_a_plain_exit_was_right_a_switch_was_wrong():
    """By hand: decided at ₹100 with the Nifty at 1000; 10 and 30 sessions on the stock is
    ₹97 (-3%) and the Nifty 950 (-5%).
    - Plain EXIT, against cash: selling saved 3%. Right; result +3.
    - SWITCH, against the Nifty: the money went into a market that lost 5%; keeping lost
      only 3. Wrong; result -2.
    - The price-path rule sold and the evidence rule kept: against cash keeping lost 3%
      (wrong, -3); against the Nifty keeping beat it by 2 (right, +2)."""
    holding, ev, switch = _switch_world()
    sig = _signals("BBB", close=100.0)
    plain = decide(sig, holding, "balanced", exit_rule="evidence", evidence=ev)
    switched = decide(sig, holding, "balanced", exit_rule="evidence", evidence=ev, **switch)
    kept = decide(sig, holding, "balanced")
    assert (plain.verdict, switched.verdict, switched.switch_candidate, kept.verdict) == (
        "EXIT", "SWITCH", "ZZZ", "HOLD")
    legacy_sig = _signals("BBB", close=100.0, thesis_intact=False, envelope_direction="DOWN")
    legacy_sold = decide(legacy_sig, holding, "balanced")
    legacy_switched = decide(legacy_sig, holding, "balanced", **switch)
    evidence_kept = decide(legacy_sig, holding, "balanced", exit_rule="evidence",
                           evidence=ExitEvidence(sessions_held=20))
    assert (legacy_sold.verdict, legacy_switched.verdict, evidence_kept.verdict) == (
        "EXIT", "SWITCH", "HOLD")

    decided = date(2026, 9, 1)
    rows = []
    for symbol, legacy, by_evidence in (("P", kept, plain), ("S", kept, switched),
                                        ("L", legacy_sold, evidence_kept),
                                        ("W", legacy_switched, evidence_kept)):
        row = xs.shadow_row(on=decided, user_id="u1", mode="shadow", close=100.0,
                            legacy=legacy, evidence_rec=by_evidence, evidence=ev,
                            buy_date=f"2026-08-0{len(rows) + 1}").model_dump()
        rows.append({**row, "symbol": symbol})
    assert [r["benchmark"] for r in rows] == ["cash", "nifty", "cash", "nifty"]
    grades = xs.grade_disagreements(
        rows, as_of=date(2026, 12, 31), stock_quote_on=_nse(97.0), corp_actions=_no_actions,
        bench_close_on=lambda d: 1000.0 if d == decided else 950.0)
    got = {(g["symbol"], g["horizon_td"]): (g["return_pct"], g["excess_pct"], g["gap_pct"],
                                            g["right"], g["result_pct"]) for g in grades}
    for h in (10, 30):
        assert got[("P", h)] == (-3.0, 2.0, -3.0, True, 3.0)
        assert got[("S", h)] == (-3.0, 2.0, 2.0, False, -2.0)
        assert got[("L", h)] == (-3.0, 2.0, -3.0, False, -3.0)
        assert got[("W", h)] == (-3.0, 2.0, 2.0, True, 2.0)


def test_the_benchmark_is_read_from_the_row_and_never_re_derived(monkeypatch):
    """The same decision graded against each benchmark; then under every exit-rule
    setting; then with later rows of the same holding naming another benchmark."""
    import backend.shared.config.settings.loader as loader
    decided = date(2026, 9, 1)
    row = {"date": decided.isoformat(), "symbol": "AAA", "close": 100.0, "mode": "shadow",
           "buy_date": "2026-05-04", "price_bar_date": "", "legacy_verdict": "HOLD",
           "evidence_verdict": "EXIT", "disagree": True}
    prices = dict(stock_quote_on=_nse(97.0), corp_actions=_no_actions,
                  bench_close_on=lambda d: 1000.0 if d == decided else 950.0)

    def graded(rows):
        return [(g["horizon_td"], g["status"], g["right"], g["result_pct"])
                for g in xs.grade_disagreements(rows, as_of=date(2026, 12, 31), **prices)]
    cash = graded([{**row, "benchmark": "cash"}])
    assert cash == [(10, "graded", True, 3.0), (30, "graded", True, 3.0)]
    assert graded([{**row, "benchmark": "nifty"}]) == [(10, "graded", False, -2.0),
                                                       (30, "graded", False, -2.0)]
    # A row naming no benchmark is never a result (and so never helps the gate).
    for missing in ({**row}, {**row, "benchmark": ""}, {**row, "benchmark": "gold"}):
        assert graded([missing]) == [(10, "ungraded", None, None), (30, "ungraded", None, None)]
    # With no Nifty close, a decision against cash is still graded on the stock alone
    # (no Nifty figure beside it); one against the Nifty is not.
    no_nifty = dict(stock_quote_on=_nse(97.0), corp_actions=_no_actions,
                    bench_close_on=lambda d: (_ for _ in ()).throw(LookupError("no Nifty")))
    for benchmark, status, result in (("cash", "graded", 3.0), ("nifty", "ungraded", None)):
        got = xs.grade_disagreements([{**row, "benchmark": benchmark}], as_of=date(2026, 12, 31),
                                     **no_nifty)
        assert [(g["status"], g["result_pct"], g["excess_pct"], g["nifty_result_pct"])
                for g in got] == [(status, result, None, None)] * 2, benchmark
    # A later configuration changes nothing stored.
    real = loader.cfg
    for mode in ("legacy", "shadow", "evidence"):
        monkeypatch.setattr(loader, "cfg", lambda path, *a, m=mode, **k: (
            m if path == "advisor.exit_rule" else real(path, *a, **k)))
        assert graded([{**row, "benchmark": "cash"}]) == cash
    # The holding's first disagreeing row decides; a later day's SWITCH (an idea arrived)
    # does not re-grade it.
    later = {**row, "date": "2026-09-02", "evidence_verdict": "SWITCH", "benchmark": "nifty"}
    assert graded([{**row, "benchmark": "cash"}, later]) == cash


def test_through_the_pipeline_each_row_stores_its_benchmark(monkeypatch, tmp_path):
    """PR-009's four holdings in shadow: AAA sold by the price-path rule, BBB by the evidence
    rule, both plain EXITs into cash; CCC and DDD agree. Then with the IT idea ZZZ on offer
    both sales become SWITCHes, graded against the Nifty (the autopilot is off there, so no
    buy leg is priced: the rows are the point)."""
    import core.portfolio.pipeline as pipeline
    from core.portfolio.pricing import SessionClose
    store = _pipeline_world(monkeypatch, tmp_path / "plain", "shadow")
    pipeline.run_post_review_pipeline(D)
    rows = {r["symbol"]: r for r in store.load_exit_shadow()}
    assert {s: r["benchmark"] for s, r in rows.items()} == {
        "AAA": "cash", "BBB": "cash", "CCC": "", "DDD": ""}

    store = _pipeline_world(monkeypatch, tmp_path / "switch", "shadow")
    portfolio = store.load()
    portfolio.autopilot = False
    store.save(portfolio)
    _holding_, _ev, switch = _switch_world()
    monkeypatch.setattr("core.discovery.candidates.buy_candidates",
                        lambda portfolio, on, ideas, **k: (switch["shelf_ideas"], {}))
    closes = {"AAA": 480.0, "BBB": 190.0, "CCC": 80.0, "DDD": 310.0, "ZZZ": 50.0}
    monkeypatch.setattr(pipeline, "session_close", lambda sym, d: (
        SessionClose(closes[sym], D, "agree"), D))
    pipeline.run_post_review_pipeline(D)
    rows = {r["symbol"]: r for r in store.load_exit_shadow()}
    assert (rows["AAA"]["legacy_verdict"], rows["BBB"]["evidence_verdict"]) == ("SWITCH", "SWITCH")
    assert {s: r["benchmark"] for s, r in rows.items()} == {
        "AAA": "nifty", "BBB": "nifty", "CCC": "", "DDD": ""}


# -- The money check -------------------------------------------------------------------------------

def _rows_and_prices(spec, start=date(2026, 6, 1), span_days=60):
    """One plain-EXIT decision per (sold, move_pct) in `spec`, each its own stock, decided at
    ₹100 on days spread over `span_days`, graded against cash: the stock is at 100 + move at
    every horizon. `sold` means the evidence rule sold it (the price-path rule kept it)."""
    rows, moves = [], {}
    for i, (sold, move) in enumerate(spec):
        day = start + timedelta(days=round(i * span_days / max(1, len(spec) - 1)))
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append({"date": day.isoformat(), "symbol": f"S{i}", "close": 100.0,
                     "mode": "shadow", "buy_date": "2026-05-04", "price_bar_date": "",
                     "legacy_verdict": "HOLD" if sold else "EXIT",
                     "evidence_verdict": "EXIT" if sold else "HOLD", "disagree": True,
                     "benchmark": "cash"})
        moves[f"S{i}"] = move
    return rows, moves


def _block(spec, missing=(), span_days=60):
    rows, moves = _rows_and_prices(spec, span_days=span_days)

    def stock(symbol, day):
        if (symbol, day) in missing_days:
            raise LookupError("no close")
        return 100.0 + moves[symbol]
    missing_days = {(f"S{i}", trading_days_after(date.fromisoformat(rows[i]["date"]), h))
                    for i, h in missing}
    return xs.scorecard_block(rows, as_of=date(2026, 12, 31), stock_quote_on=_nse(stock),
                              bench_close_on=lambda d: 1000.0, corp_actions=_no_actions)


def test_the_cards_example_right_on_8_of_15_and_minus_3_6_a_decision_fails():
    """8 sales saved 2% each (the stock fell 2%); 7 cost 10% each (it rose 10%):
    (8 x 2 - 7 x 10) / 15 = -3.6% a decision. Right on 8 of 15 (53%) passes the count."""
    block = _block([(True, -2.0)] * 8 + [(True, 10.0)] * 7)
    look = block["gate"]
    assert look["right"] == {"10": 8, "30": 8} and look["matured"] == 15
    assert look["mean_result_pct"] == {"10": -3.6, "30": -3.6}
    assert look["status"] == xs.FAIL and look["better"] is False
    assert look["reasons"] == [
        "its mean result at 10 sessions is -3.60% (needs at least +0.00%)",
        "its mean result at 30 sessions is -3.60% (needs at least +0.00%)"]
    assert [t["mean_result_pct"] for t in block["tally"]] == [-3.6, -3.6]
    text = xs.scorecard_text(block)
    assert "it was right on 8 of 15, averaging -3.60% a decision against where the money " \
           "went (15 against cash, 0 against the Nifty; -3.60% against the Nifty alone)" in text
    assert text.endswith("Switch gate: fails (its mean result at 10 sessions is -3.60% (needs "
                         "at least +0.00%); its mean result at 30 sessions is -3.60% (needs at "
                         "least +0.00%)).")


def test_half_right_with_a_positive_mean_passes_as_not_worse():
    """8 sales right at +5 each, 8 keeps wrong at -1 each (the stock fell 1%):
    (40 - 8) / 16 = +2.0. A pass, and only "not worse" (50% is short of 70%)."""
    block = _block([(True, -5.0)] * 8 + [(False, -1.0)] * 8)
    look = block["gate"]
    assert (look["status"], look["right"], look["mean_result_pct"], look["better"]) == (
        xs.PASS, {"10": 8, "30": 8}, {"10": 2.0, "30": 2.0}, False)
    assert "Switch gate: passed this week (not worse than the price-path rule in count and " \
           "money); it must pass again next week." in xs.scorecard_text(block)
    # A mean of exactly 0 is "at least 0": 8 right at +1, 8 wrong at -1.
    even = _block([(True, -1.0)] * 8 + [(False, -1.0)] * 8)["gate"]
    assert (even["status"], even["mean_result_pct"]) == (xs.PASS, {"10": 0.0, "30": 0.0})
    # One decision with no price at 10 sessions: its result is unknown, and the pass is gone.
    gone = _block([(True, -5.0)] * 8 + [(False, -1.0)] * 8, missing=[(15, 10)])["gate"]
    assert gone["status"] == xs.FAIL and gone["unknown_result"] == {"10": 1, "30": 0}
    assert gone["reasons"] == [
        "1 decision with no result at 10 sessions, so the money check cannot pass"]


def test_better_only_at_70_percent_with_a_positive_mean():
    # 11 of 15 (73%), mean (11 x 3 - 4 x 2) / 15 = +1.67: better.
    better = _block([(True, -3.0)] * 11 + [(True, 2.0)] * 4)["gate"]
    assert (better["status"], better["better"]) == (xs.PASS, True)
    assert "better: right on at least 70% with a positive mean" in xs.scorecard_text(
        _block([(True, -3.0)] * 11 + [(True, 2.0)] * 4))
    # 10 of 15 (67%), positive mean: a pass, not better.
    ten = _block([(True, -3.0)] * 10 + [(True, 2.0)] * 5)["gate"]
    assert (ten["status"], ten["better"]) == (xs.PASS, False)
    # 11 of 15 with a mean of exactly 0 (kept flat stocks are right at 0, sold flat ones
    # wrong at 0): a pass, not better.
    flat = _block([(False, 0.0)] * 11 + [(True, 0.0)] * 4)["gate"]
    assert (flat["status"], flat["right"]["10"], flat["better"]) == (xs.PASS, 11, False)
    # 11 of 15 losing money: (11 x 1 - 4 x 5) / 15 < 0 fails.
    losing = _block([(True, -1.0)] * 11 + [(True, 5.0)] * 4)["gate"]
    assert (losing["status"], losing["better"]) == (xs.FAIL, False)


def test_the_gate_is_fixed_as_the_card_says():
    assert (xs.GRADE_HORIZONS_TD, xs.GATE_MIN_MATURED, xs.GATE_MIN_SPAN_DAYS) == ((10, 30), 15, 56)
    assert (xs.GATE_MIN_RIGHT_PCT, xs.GATE_MIN_MEAN_RESULT_PCT, xs.BETTER_RIGHT_PCT) == (
        50.0, 0.0, 70.0)
    assert (xs.GATE_MAX_STOCK_PCT, xs.GATE_LOOKS) == (30.0, 2)


# -- The oracle --------------------------------------------------------------------------------------

def _oracle(decisions) -> tuple[str, bool]:
    """The card's gate in exact fractions. `decisions`: dicts with day, symbol, sold and,
    per horizon, the gap (a Fraction) or None when no price, or "pending" at 30."""
    population = [d for d in decisions if d[30] != "pending"]
    n = len(population)
    if n < 15:
        return xs.NOT_ENOUGH, False
    days = [d["day"] for d in population]
    if (max(days) - min(days)).days < 56:
        return xs.NOT_ENOUGH, False
    ok, better = True, True
    for h in (10, 30):
        gaps = [d[h] for d in population]
        right = sum(1 for d in population if d[h] is not None
                    and ((d[h] < 0) if d["sold"] else (d[h] >= 0)))
        if Fraction(right, n) < Fraction(1, 2):
            ok = False
        if any(g is None for g in gaps):
            ok, better = False, False
            continue
        mean = sum((-g if d["sold"] else g) for d, g in zip(population, gaps)) / n
        if mean < 0:
            ok = False
        if not (Fraction(right, n) >= Fraction(7, 10) and mean > 0):
            better = False
    top = max(sum(1 for d in population if d["symbol"] == s) for s in {d["symbol"] for d in population})
    if Fraction(top, n) > Fraction(3, 10):
        ok = False
    return (xs.PASS, better) if ok else (xs.FAIL, False)


def _as_grades(decisions) -> list[dict]:
    """The decisions as grade_disagreements reports them."""
    out = []
    for d in decisions:
        for h in (10, 30):
            gap = d[h]
            g = {"date": d["day"].isoformat(), "symbol": d["symbol"], "horizon_td": h,
                 "status": "graded", "right": None, "result_pct": None, "evidence_sold": d["sold"]}
            if gap == "pending":
                g["status"] = "pending"
            elif gap is None:
                g["status"] = "ungraded"
            else:
                g["right"] = (gap < 0) if d["sold"] else (gap >= 0)
                g["result_pct"] = float(-gap if d["sold"] else gap)
            out.append(g)
    return out


def _random_population(rnd: random.Random) -> list[dict]:
    """13-21 decisions; a stock is one row per day, as the store keeps it. Half the
    populations lean right and profitable, so passes and "better" occur."""
    n = rnd.randint(13, 21)
    names = rnd.randint(3, n)
    span = rnd.randint(50, 80)
    start = date(2026, 6, 1)
    skew = rnd.random() < 0.5
    out, taken = [], set()
    while len(out) < n:
        day, symbol = start + timedelta(days=rnd.randint(0, span)), f"S{rnd.randrange(names)}"
        if (day, symbol) in taken:
            continue
        taken.add((day, symbol))
        sold = rnd.random() < 0.5
        d = {"day": day, "symbol": symbol, "sold": sold}
        for h in (10, 30):
            k = 0 if rnd.random() < 0.1 else rnd.randint(-600, 600)
            if skew and rnd.random() < 0.75:
                k = abs(k) * (-1 if sold else 1)
            d[h] = None if rnd.random() < 0.02 else Fraction(k, 100)
        if rnd.random() < 0.04:
            d[30] = "pending"
        out.append(d)
    return out


def test_the_gate_agrees_with_an_independent_oracle_and_a_missing_grade_never_helps():
    rnd = random.Random(20261024)
    seen = {"pass": 0, "better": 0, "fail_money_only": 0, "fail": 0, "not_enough": 0,
            "pass_lost_to_a_missing_grade": 0}
    for _ in range(2000):
        decisions = _random_population(rnd)
        look = xs.gate_look(_as_grades(decisions))
        expected = _oracle(decisions)
        assert (look["status"], look["better"]) == expected, decisions
        seen["better"] += expected[1]
        seen[look["status"]] += 1
        if look["status"] == xs.FAIL and all(r.startswith(("its mean", "1 ", "2 ", "3 "))
                                             for r in look["reasons"]):
            seen["fail_money_only"] += 1
        # Turn each graded result into a missing one: never a pass from a non-pass, and a
        # pass becomes a fail.
        for i, d in enumerate(decisions):
            for h in (10, 30):
                if d[h] is None or d[h] == "pending":
                    continue
                changed = [dict(x) for x in decisions]
                changed[i][h] = None
                after = xs.gate_look(_as_grades(changed))["status"]
                assert after == _oracle(changed)[0]
                if look["status"] != xs.PASS:
                    assert after != xs.PASS, (decisions, i, h)
                elif d[30] != "pending":
                    assert after == xs.FAIL
                    seen["pass_lost_to_a_missing_grade"] += 1
    assert all(v > 20 for v in seen.values()), seen       # every branch was exercised


# == Rework 1 (fresh review F1, F2, I1) ============================================================
#
# F1: the stock's return between a decision's close and each horizon is in one price basis. A
# bonus or split cuts the raw price by its ratio and leaves the company's value alone, so the
# horizon close is put into the decision close's basis with every one that went ex between them,
# from NSE's list read at grading. When that basis cannot be established the decision has no
# result that week: it fails the money check, as a missing close does.
# F2: a SWITCH whose buy leg the executor refuses leaves the money in cash; its row says cash.

DIVIDEND_2025 = {"subject": "Dividend - Rs 2 Per Share", "exDate": "14-Aug-2025"}


def _nse_row(kind: str, ex: date, ratio: str = "1:1") -> dict:
    """An NSE actions() row ex `ex`: a "bonus" (`ratio` new:held), a "split" (from Rs 10 to
    Rs 2, ratio 5), or an "unreadable" bonus row that names no ratio."""
    day = ex.strftime("%d-%b-%Y")
    if kind == "bonus":
        return {"subject": f"Bonus {ratio}", "exDate": day}
    if kind == "split":
        return {"subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- "
                           "Per Share", "exDate": day}
    return {"subject": "Bonus issue - ratio to be announced", "exDate": day}


class _Market:
    """Prices in real terms (what one share held on the decision day is worth) and the bonuses
    or splits that went ex, per symbol, written from what the actions do, not from the code:

    - NSE's close is the raw price: the value divided by the ratio of every action ex on or
      before the day;
    - Yahoo's series, read at grading, is auto-adjusted: the raw close divided again by the
      ratio of every action ex after the day;
    - NSE's action list is a 2025 dividend (so it reaches back past every decision) and each
      action's row.

    `nse_down`: days NSE's close does not answer. `unlisted`: symbols whose NSE action list
    comes back empty. NSE knows only the codes in `value`; any other code's list is empty.

    Rework 2: `demergers[symbol]` is (ex, kept, row): from `ex` the stock trades at `kept` of
    its value, the rest having left for another listing, so NSE's raw close is the value times
    every `kept` ex on or before the day; NSE's row says "Demerger" and gives no fraction.
    With `yahoo_adjusts_demergers`, Yahoo's series also scales each close before a demerger
    by its `kept`, as it may. `rows[symbol]` are further NSE rows, for the list only."""

    def __init__(self):
        self.value: dict = {}
        self.actions: dict = {}
        self.demergers: dict = {}
        self.rows: dict = {}
        self.nse_down: set = set()
        self.unlisted: set = set()
        self.yahoo_adjusts_demergers = False

    def _factor(self, symbol: str, counts) -> float:
        factor = 1.0
        for ex, ratio, _row in self.actions.get(symbol, []):
            if counts(ex):
                factor *= ratio
        return factor

    def _kept(self, symbol: str, counts) -> float:
        kept = 1.0
        for ex, fraction, _row in self.demergers.get(symbol, []):
            if counts(ex):
                kept *= fraction
        return kept

    def raw(self, symbol: str, day: date) -> float:
        return (self.value[symbol](day) * self._kept(symbol, lambda ex: ex <= day)
                / self._factor(symbol, lambda ex: ex <= day))

    def adjusted(self, symbol: str, day: date) -> float:
        later = self._kept(symbol, lambda ex: ex > day) if self.yahoo_adjusts_demergers else 1.0
        return self.raw(symbol, day) * later / self._factor(symbol, lambda ex: ex > day)

    def bonus(self, symbol: str, ex: date) -> None:
        """A 1:1 bonus: one new share for each held, ratio 2."""
        self.actions.setdefault(symbol, []).append((ex, 2.0, _nse_row("bonus", ex)))

    def demerge(self, symbol: str, ex: date, kept: float) -> None:
        self.demergers.setdefault(symbol, []).append(
            (ex, kept, {"subject": "Demerger", "exDate": ex.strftime("%d-%b-%Y")}))

    def install(self, monkeypatch):
        """Fakes the three boundaries and returns the real grading lookups
        (results.stock_quote_fn, results.corp_actions_fn)."""
        import pandas as pd
        import yfinance
        from backend.shared.data.fetchers import symbol_resolver
        from core.intelligence.rl.nse_calendar import is_trading_day
        from core.portfolio import results
        from services.data.fetchers import close_verifier, corporate_events
        market = self

        def download(sym, start, end, **_k):
            symbol = str(sym).split(".")[0]
            if symbol not in market.value:
                return pd.DataFrame()
            days, d = [], date.fromisoformat(start)
            while d < date.fromisoformat(end):
                if is_trading_day(d):
                    days.append(d)
                d += timedelta(days=1)
            return pd.DataFrame({"Close": [market.adjusted(symbol, d) for d in days]},
                                index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]))

        def nse_session(ticker, target_date=None):
            # The NSE code the real fetcher asks for: the registry's, else the ticker.
            symbol = symbol_resolver.nse_symbol(ticker, target_date).split(".")[0].upper()
            if symbol not in market.value or target_date in market.nse_down:
                return None, None
            return market.raw(symbol, target_date), target_date

        class Client:
            def actions(self, symbol):
                # NSE answers only a code it lists (rework 3): an app code such as a registry
                # alias's TVSMOTORS gets nothing, as NSE answered on 29 Oct 2026.
                if symbol in market.unlisted or symbol not in market.value:
                    return []
                return ([DIVIDEND_2025]
                        + [row for _ex, _r, row in market.actions.get(symbol, [])]
                        + [row for _ex, _k, row in market.demergers.get(symbol, [])]
                        + market.rows.get(symbol, []))

            def exit(self):
                pass

        monkeypatch.setattr(yfinance, "download", download)
        monkeypatch.setattr(close_verifier, "_fetch_nse_session", nse_session)
        monkeypatch.setattr(symbol_resolver, "_load_cache", lambda: {})
        monkeypatch.setattr(corporate_events, "_make_nse_client", lambda: Client())
        monkeypatch.setattr(results, "_SETTLED_QUOTES", {})
        return results.stock_quote_fn(), results.corp_actions_fn()


@pytest.mark.parametrize("bonus", [True, False])
def test_rv1_a_bonus_after_the_decision_is_not_a_result(monkeypatch, tmp_path, bonus):
    """The review's RV1, pinned. The real pipeline writes PR-009's rows on Friday 23 Oct: BBB
    sold by the evidence rule at ₹190, AAA by the price-path rule at ₹480, both plain EXITs
    into cash. Both stay flat in real terms. With the bonus, each goes ex on a 1:1 bonus three
    sessions later (Wednesday 28 Oct), so NSE's raw close is ₹95 and ₹240 from then on.

    By hand, in the decision's own basis (₹95 is ₹190 in the old shares): a return of 0 at 10
    and at 30 sessions. BBB's sale saved nothing, so the evidence rule was wrong (an EXIT is
    right only on a fall) with a result of 0; AAA's keep lost nothing, so it was right with a
    result of 0. Without the basis the bonus read as -50%: +50 to the seller, -50 to the
    keeper. With no bonus (the control) the same grades, and no ratio applied."""
    import core.portfolio.pipeline as pipeline
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    pipeline.run_post_review_pipeline(D)
    rows = [r for r in store.load_exit_shadow() if r["disagree"]]
    assert sorted((r["symbol"], r["evidence_verdict"], r["benchmark"], r["close"])
                  for r in rows) == [("AAA", "HOLD", "cash", 480.0), ("BBB", "EXIT", "cash", 190.0)]
    ex = trading_days_after(D, 3)
    assert ex == date(2026, 10, 28)
    market = _Market()
    market.value = {"BBB": lambda d: 190.0, "AAA": lambda d: 480.0}
    if bonus:
        market.bonus("BBB", ex)
        market.bonus("AAA", ex)
    quotes, actions = market.install(monkeypatch)
    assert quotes("BBB", trading_days_after(D, 10)).close == (95.0 if bonus else 190.0)

    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    got = {(g["symbol"], g["horizon_td"]): (g["status"], g["return_pct"], g["right"],
                                            g["result_pct"], g["basis"]) for g in grades}
    note = "×2 for the bonus ex 2026-10-28" if bonus else ""
    for h in (10, 30):
        assert got[("BBB", h)] == ("graded", 0.0, False, 0.0, note)
        assert got[("AAA", h)] == ("graded", 0.0, True, 0.0, note)


def _real_rows(market: _Market, spec, start=date(2026, 6, 1), span_days=60) -> list[dict]:
    """One plain-EXIT decision per (sold, move_pct) in `spec`, each its own stock S0, S1, ...,
    decided at ₹100 on review days spread over `span_days`; in real terms the stock is at
    100 + move after its review day. `sold`: the evidence rule sold it."""
    from core.intelligence.rl.nse_calendar import is_trading_day
    rows = []
    for i, (sold, move) in enumerate(spec):
        day = start + timedelta(days=round(i * span_days / max(1, len(spec) - 1)))
        while not is_trading_day(day):
            day += timedelta(days=1)
        rows.append({"date": day.isoformat(), "symbol": f"S{i}", "close": 100.0,
                     "mode": "shadow", "buy_date": "2026-05-04", "price_bar_date": "",
                     "legacy_verdict": "HOLD" if sold else "EXIT",
                     "evidence_verdict": "EXIT" if sold else "HOLD", "disagree": True,
                     "benchmark": "cash"})
        market.value[f"S{i}"] = lambda d, day=day, move=move: 100.0 if d <= day else 100.0 + move
    return rows


def test_rv2_one_bonus_no_longer_passes_the_cards_failing_example(monkeypatch):
    """The review's RV2, pinned, through the real price path. The card's example: 15 sales by
    the evidence rule; S0-S7 then fell 2% (right, +2) and S8-S14 rose 10% (wrong, -10):
    (8 x 2 - 7 x 10) / 15 = -3.6% a decision. S14 goes ex on a 1:1 bonus three sessions after
    its decision, so its raw close at both horizons is ₹55. By hand, ₹55 is ₹110 in the old
    shares: +10%, and the sale is still wrong with -10. The gate still fails at -3.6% and right
    on 8 of 15, and the week after it does not recommend the switch (with the defect it read
    9 of 15 and +0.07%, a pass two weeks running)."""
    market = _Market()
    rows = _real_rows(market, [(True, -2.0)] * 8 + [(True, 10.0)] * 7)
    market.bonus("S14", trading_days_after(date.fromisoformat(rows[14]["date"]), 3))
    quotes, actions = market.install(monkeypatch)
    prices = dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)
    s14 = [(g["return_pct"], g["right"], g["result_pct"], g["basis"][:2])
           for g in xs.grade_disagreements(rows[14:], as_of=date(2026, 12, 31), **prices)]
    assert s14 == [(10.0, False, -10.0, "×2")] * 2
    block = xs.scorecard_block(rows, as_of=date(2026, 12, 31), **prices)
    look = block["gate"]
    assert (look["status"], look["right"], look["mean_result_pct"]) == (
        xs.FAIL, {"10": 8, "30": 8}, {"10": -3.6, "30": -3.6})
    again = xs.scorecard_block(rows, as_of=date(2026, 12, 31) + timedelta(days=7),
                               previous_look=look, **prices)
    assert again["recommend"] is False and again["gate"]["status"] == xs.FAIL
    assert "passed" not in xs.scorecard_text(again)


def test_the_price_basis_rule_by_hand():
    """`horizon_in_basis` on hand-made quotes and NSE lists. The decision's close is Thursday
    1 Oct's bar, stored on the review day Monday 5 Oct (2 Oct is a holiday); the horizon's bar
    is Friday 30 Oct at a raw ₹100. Expected closes in the old shares, by hand."""
    from core.portfolio.corp_actions import action_record
    from core.portfolio.pricing import SessionClose
    start, decided, bar = date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 30)
    d20, d26, nov2 = date(2026, 10, 20), date(2026, 10, 26), date(2026, 11, 2)

    def listed(*rows):
        return action_record([DIVIDEND_2025, *rows], "AAA")
    nse = SessionClose(100.0, bar, "nse")
    agree = SessionClose(100.0, bar, "agree")
    yahoo = SessionClose(100.0, bar, "yfinance")
    cases = [
        # nothing between the two closes
        (listed(), nse, 100.0, ""),
        # a 1:1 bonus between: ₹100 is ₹200 in the old shares; ex on the horizon's bar too
        (listed(_nse_row("bonus", d20)), nse, 200.0, "×2 for the bonus ex 2026-10-20"),
        (listed(_nse_row("bonus", d20)), agree, 200.0, "×2 for the bonus ex 2026-10-20"),
        (listed(_nse_row("bonus", bar)), nse, 200.0, "×2 for the bonus ex 2026-10-30"),
        # ex on the close's own bar: the stored close is already in the new shares
        (listed(_nse_row("bonus", start)), nse, 100.0, ""),
        # ex after the horizon's bar: NSE's raw close is still in the old shares
        (listed(_nse_row("bonus", nov2)), nse, 100.0, ""),
        # a bonus and a 10 -> 2 split: x2 x5
        (listed(_nse_row("bonus", d20), _nse_row("split", d26)), nse, 1000.0,
         "×2 for the bonus ex 2026-10-20, ×5 for the split ex 2026-10-26"),
        # the same bonus listed twice counts once
        (listed(_nse_row("bonus", d20), {"subject": "Bonus 1:1 (revised)", "exDate": "20-Oct-2026"}),
         nse, 200.0, "×2 for the bonus ex 2026-10-20"),
        # Yahoo's alone, with no action after its bar, is in its bar's basis
        (listed(_nse_row("bonus", d20)), yahoo, 200.0, "×2 for the bonus ex 2026-10-20"),
        # an unreadable row after the horizon's bar is not in NSE's raw close
        (listed(_nse_row("unreadable", nov2)), nse, 100.0, ""),
    ]
    for record, quote, close, note in cases:
        assert xs.horizon_in_basis(quote, record, start, decided) == (close, note, ""), (
            record, quote)

    unknown = [
        (None, nse, "NSE's list of its corporate actions is empty or was not read, so one "
                    "since 2026-10-01 cannot be ruled out"),
        (action_record([], "AAA"), nse, "NSE's list of its corporate actions is empty or was "
                                        "not read, so one since 2026-10-01 cannot be ruled out"),
        (action_record([_nse_row("bonus", d20)], "AAA"), nse,
         "NSE's list of its corporate actions starts 2026-10-20, after the decision's close "
         "(2026-10-01)"),
        (listed(_nse_row("unreadable", d20)), nse,
         "NSE lists a split or bonus on 2026-10-20 that could not be read"),
        (listed(_nse_row("unreadable", nov2)), yahoo,
         "NSE lists a split or bonus on 2026-11-02 that could not be read"),
        (listed(_nse_row("bonus", d20), _nse_row("bonus", d20, "1:2")), nse,
         "NSE lists two bonus ratios ex 2026-10-20 (2 and 1.5)"),
        (listed(_nse_row("bonus", decided)), nse,
         "a bonus or split went ex on 2026-10-05, after the close's bar (2026-10-01) and by the "
         "review day (2026-10-05), so the stored close may be on either side of it"),
        (listed(_nse_row("bonus", nov2)), yahoo,
         "the horizon close is Yahoo's alone (NSE's did not answer), and Yahoo adjusts it for "
         "the bonus or split ex 2026-11-02"),
        (listed(), SessionClose(100.0, None, "nse"), "the horizon close is undated"),
        (listed(), SessionClose(100.0, date(2026, 9, 30), "nse"),
         "the horizon close is from 2026-09-30, before the decision's close (2026-10-01)"),
    ]
    for record, quote, gap in unknown:
        assert xs.horizon_in_basis(quote, record, start, decided) == (None, "", gap), gap


def test_a_basis_that_cannot_be_established_is_no_result_and_never_helps(monkeypatch):
    """Through the real price path. 8 sales right at +5 each (the stocks fell 5%) and 8 keeps
    wrong at -1 each (they fell 1%): (8 x 5 - 8 x 1) / 16 = +2.00, a pass ("not worse"). Then
    NSE's action list for S15, a keep that was wrong, comes back empty: whether a bonus or
    split moved its price cannot be ruled out, so S15 has no result at either horizon; the
    count is unchanged (it was not right), and the money check, missing one result, fails.
    The line names S15."""
    spec = [(True, -5.0)] * 8 + [(False, -1.0)] * 8
    market = _Market()
    rows = _real_rows(market, spec)
    quotes, actions = market.install(monkeypatch)
    passing = xs.scorecard_block(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                 bench_close_on=lambda d: 1000.0, corp_actions=actions)["gate"]
    assert (passing["status"], passing["mean_result_pct"]) == (xs.PASS, {"10": 2.0, "30": 2.0})

    market = _Market()
    rows = _real_rows(market, spec)
    market.unlisted.add("S15")
    quotes, actions = market.install(monkeypatch)
    block = xs.scorecard_block(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                               bench_close_on=lambda d: 1000.0, corp_actions=actions)
    look = block["gate"]
    assert (look["status"], look["right"], look["unknown_result"]) == (
        xs.FAIL, {"10": 8, "30": 8}, {"10": 1, "30": 1})
    assert look["reasons"] == [
        "1 decision with no result at 10 sessions, so the money check cannot pass",
        "1 decision with no result at 30 sessions, so the money check cannot pass"]
    assert [(t["ungraded"], t["no_basis"], t["no_basis_symbols"]) for t in block["tally"]] == [
        (1, 1, ["S15"])] * 2
    assert ("1 with no result at 10 sessions, as a corporate action could not be ruled out or "
            "allowed for (S15); 1 with no result at 30 sessions, as a corporate action could not "
            "be ruled out or allowed for (S15).") in xs.scorecard_text(block)
    s15 = [g for g in xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                             bench_close_on=lambda d: 1000.0, corp_actions=actions)
           if g["symbol"] == "S15"]
    assert [(g["status"], g["result_pct"], g["right"], g["no_basis"][:30]) for g in s15] == [
        ("ungraded", None, None, "NSE's list of its corporate ac")] * 2


def test_a_yahoo_only_close_after_a_later_bonus_has_no_result_until_nse_answers(monkeypatch):
    """S0 is sold by the evidence rule at ₹100 on Monday 1 Jun and stays flat in real terms. A
    1:1 bonus goes ex on Monday 3 Aug, after both horizons, and the decision is graded the
    next Sunday. NSE's close does not answer for the horizon days, and Yahoo's series, read
    after the bonus, shows ₹50 for them: that is a later price basis, so there is no result,
    named. The next week NSE answers ₹100 (its raw close, before the bonus): a return of 0,
    the sale wrong with a result of 0."""
    market = _Market()
    rows = _real_rows(market, [(True, 0.0)])
    market.bonus("S0", date(2026, 8, 3))
    horizons = [trading_days_after(date(2026, 6, 1), h) for h in (10, 30)]
    assert horizons[1] < date(2026, 8, 3)
    market.nse_down = set(horizons)
    quotes, actions = market.install(monkeypatch)
    assert (quotes("S0", horizons[0]).close, quotes("S0", horizons[0]).source) == (50.0, "yfinance")
    graded = xs.grade_disagreements(rows, as_of=date(2026, 8, 9), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert [(g["status"], g["no_basis"]) for g in graded] == [(
        "ungraded", "the horizon close is Yahoo's alone (NSE's did not answer), and Yahoo "
                    "adjusts it for the bonus or split ex 2026-08-03")] * 2

    market.nse_down = set()
    graded = xs.grade_disagreements(rows, as_of=date(2026, 8, 16), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert [(g["status"], g["return_pct"], g["right"], g["result_pct"]) for g in graded] == [
        ("graded", 0.0, False, 0.0)] * 2


def test_an_action_list_that_cannot_be_read_is_no_result():
    """A lookup that raises is a list not read: no result, named, never a guess."""
    rows = _rows_and_prices([(True, -5.0)])[0]

    def broken(symbol):
        raise ConnectionError("NSE refused")
    graded = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=_nse(95.0),
                                    bench_close_on=lambda d: 1000.0, corp_actions=broken)
    assert [(g["status"], g["result_pct"], g["no_basis"][:26]) for g in graded] == [
        ("ungraded", None, "NSE's list of its corporat")] * 2


def test_the_scorecard_reads_nse_once_per_stock_and_keeps_only_settled_closes(monkeypatch):
    """The weekly scorecard's lookups: one NSE action list per stock for the whole scorecard,
    however many horizons; a past day's close is kept for later weeks only when it is that
    day's own bar in NSE's raw basis (here NSE's, then Yahoo's alone, which is not kept)."""
    from core.portfolio import corp_actions, results
    market = _Market()
    rows = _real_rows(market, [(True, -2.0), (False, 3.0)])
    reads = []
    quotes, actions = market.install(monkeypatch)
    real_fetch = corp_actions.fetch_corp_actions
    monkeypatch.setattr(corp_actions, "fetch_corp_actions",
                        lambda s: reads.append(s) or real_fetch(s))
    xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                           bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert sorted(reads) == ["S0", "S1"]
    day = trading_days_after(date(2026, 6, 1), 10)
    assert (("S0", day) in results._SETTLED_QUOTES) is True
    results._SETTLED_QUOTES.clear()
    market.nse_down = {day}
    assert quotes("S0", day).source == "yfinance" and ("S0", day) not in results._SETTLED_QUOTES


# -- F2: a SWITCH whose buy leg would not land ---------------------------------------------------

def test_a_switch_buy_lands_only_where_the_executor_would_buy():
    """`switch_buy_lands` mirrors the executor's checks before sizing. ZZZ's idea has the band
    ₹48.50-₹51.00 and an invalidation level of ₹45. In record mode (not enforcing) the executor
    buys at a carried-forward close or an unresolved identity, and warns."""
    from core.portfolio.pricing import SessionClose
    idea = ShelfIdea(symbol="ZZZ", sector="it", added="2026-10-01", dived="2026-10-01",
                     conviction=0.9, status="active", entry_low=48.5, entry_high=51.0,
                     invalidation_level=45.0)
    no_band = ShelfIdea(symbol="ZZZ", sector="it", added="2026-10-01", dived="2026-10-01",
                        conviction=0.9, status="active")
    fresh, stale = SessionClose(50.0, D, "agree"), SessionClose(50.0, date(2026, 10, 22), "agree")
    cases = [
        (fresh, idea, {}, True),
        (SessionClose(48.0, D, "agree"), idea, {}, True),        # below the band: cheaper
        (SessionClose(51.0, D, "agree"), idea, {}, True),        # the top of the band
        (SessionClose(51.5, D, "agree"), idea, {}, False),       # above it
        (SessionClose(45.0, D, "agree"), idea, {}, False),       # at the invalidation level
        (None, idea, {}, False),                                 # no close
        (SessionClose(None, None, "none"), idea, {}, False),
        (fresh, None, {}, False),                                # not an idea on offer
        (fresh, no_band, {}, False),                             # no band on record
        (stale, idea, {}, True),
        (stale, idea, dict(enforcing=True), False),
        (fresh, idea, dict(identity_issue="unresolved"), True),
        (fresh, idea, dict(identity_issue="unresolved", enforcing=True), False),
        (fresh, idea, dict(enforcing=True), True),
    ]
    for quote, offered, kw, lands in cases:
        assert xs.switch_buy_lands(quote, D, offered, **kw) is lands, (quote, offered, kw)


@pytest.mark.parametrize("legacy, evidence, deploys, lands, benchmark", [
    ("SWITCH", "HOLD", False, False, "cash"), ("HOLD", "SWITCH", False, False, "cash"),
    ("SWITCH", "HOLD", False, True, "nifty"), ("SWITCH", "HOLD", True, False, "nifty"),
    ("EXIT", "HOLD", False, True, "cash"), ("SWITCH", "EXIT", False, False, ""),
])
def test_where_a_switchs_money_went(legacy, evidence, deploys, lands, benchmark):
    assert xs.decision_benchmark(legacy, evidence, deploys_cash=deploys,
                                 switch_lands=lands) == benchmark


def test_the_row_asks_only_about_the_selling_rules_switch():
    """The evidence rule SWITCHes BBB into ZZZ and the price-path rule keeps it: the row asks
    whether a buy of ZZZ would land, once, and records cash when it would not. A plain EXIT, an
    agreement or a row without the question asks nothing."""
    holding, ev, switch = _switch_world()
    sig = _signals("BBB", close=100.0)
    switched = decide(sig, holding, "balanced", exit_rule="evidence", evidence=ev, **switch)
    plain = decide(sig, holding, "balanced", exit_rule="evidence", evidence=ev)
    kept = decide(sig, holding, "balanced")
    asked = []

    def row(by_evidence, lands=False, ask=True):
        def switch_lands(symbol):
            asked.append(symbol)
            return lands
        return xs.shadow_row(on=D, user_id="u1", mode="shadow", close=100.0, legacy=kept,
                             evidence_rec=by_evidence, evidence=ev, buy_date="2026-08-03",
                             switch_lands=switch_lands if ask else None).benchmark
    assert (row(switched), asked) == ("cash", ["ZZZ"])
    assert (row(switched, lands=True), asked) == ("nifty", ["ZZZ", "ZZZ"])
    assert (row(plain), row(kept), row(switched, ask=False)) == ("cash", "", "nifty")
    assert asked == ["ZZZ", "ZZZ"]


@pytest.mark.parametrize("zzz_close, benchmark, bought", [(50.0, "nifty", True),
                                                          (55.0, "cash", False)])
def test_through_the_pipeline_a_switch_the_executor_refuses_is_graded_against_cash(
        monkeypatch, tmp_path, zzz_close, benchmark, bought):
    """PR-009's four holdings in shadow with the autopilot on, and the IT idea ZZZ on offer
    (band ₹48.50-₹51.00): the price-path rule's SWITCH of AAA is executed, the evidence rule's
    SWITCH of BBB only recorded. At ₹50 the executor buys ZZZ, and both rows say nifty. At ₹55,
    7.8% above the band, it refuses the buy, AAA's proceeds stay in cash, and both rows say
    cash: where the money went."""
    import core.portfolio.autopilot as ap
    import core.portfolio.pipeline as pipeline
    from core.portfolio.pricing import SessionClose
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    _h, _ev, switch = _switch_world()
    monkeypatch.setattr("core.discovery.candidates.buy_candidates",
                        lambda portfolio, on, ideas, **k: (switch["shelf_ideas"], {}))
    closes = {"AAA": 480.0, "BBB": 190.0, "CCC": 80.0, "DDD": 310.0, "ZZZ": zzz_close}

    def quote(sym, d):
        return SessionClose(closes[sym], D, "agree"), D
    monkeypatch.setattr(pipeline, "session_close", quote)
    monkeypatch.setattr(ap, "session_close", quote)
    pipeline.run_post_review_pipeline(D)
    rows = {r["symbol"]: r for r in store.load_exit_shadow()}
    assert (rows["AAA"]["legacy_verdict"], rows["BBB"]["evidence_verdict"]) == ("SWITCH", "SWITCH")
    assert (rows["AAA"]["benchmark"], rows["BBB"]["benchmark"]) == (benchmark, benchmark)
    txns = store.load_transactions()
    assert ("ZZZ" in {t.symbol for t in txns if t.side == "BUY"}) is bought
    sale = next(t for t in txns if t.side == "SELL" and t.symbol == "AAA")
    assert ("7.8% above entry band" in sale.note and "stays in cash" in sale.note) == (not bought)


@pytest.mark.parametrize("error", [ConnectionError, ValueError])
def test_through_the_pipeline_a_destination_whose_fetch_fails_is_a_refused_buy(
        monkeypatch, tmp_path, error):
    """Rework 2, the re-review's I1. As above, but ZZZ's close fetch fails with an error that
    is not PriceUnavailableError. The executor skips a buy whose fetch fails, so AAA's
    proceeds stay in cash; both rows are still written, and each says cash."""
    import core.portfolio.autopilot as ap
    import core.portfolio.pipeline as pipeline
    from core.portfolio.pricing import SessionClose
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    _h, _ev, switch = _switch_world()
    monkeypatch.setattr("core.discovery.candidates.buy_candidates",
                        lambda portfolio, on, ideas, **k: (switch["shelf_ideas"], {}))
    closes = {"AAA": 480.0, "BBB": 190.0, "CCC": 80.0, "DDD": 310.0}

    def quote(sym, d):
        if sym == "ZZZ":
            raise error("both close sources refused")
        return SessionClose(closes[sym], D, "agree"), D
    monkeypatch.setattr(pipeline, "session_close", quote)
    monkeypatch.setattr(ap, "session_close", quote)
    pipeline.run_post_review_pipeline(D)
    rows = {r["symbol"]: r for r in store.load_exit_shadow()}
    assert (rows["AAA"]["legacy_verdict"], rows["BBB"]["evidence_verdict"]) == ("SWITCH", "SWITCH")
    assert (rows["AAA"]["benchmark"], rows["BBB"]["benchmark"]) == ("cash", "cash")
    assert "ZZZ" not in {t.symbol for t in store.load_transactions() if t.side == "BUY"}


# -- I1: the reason names the IST day the rule used -------------------------------------------

def test_the_reason_shows_the_ist_day_the_freshness_rule_used():
    """A SELL run at 00:01 IST on Friday 9 Oct is stored as 18:31 on 8 Oct (naive UTC). For a
    holding bought on Thursday 8 Oct it counts (a later IST day), and the reason says 9 Oct."""
    holding = _holding("AAA", 500.0, sessions=10)
    assert holding.buy_date == "2026-10-08"
    ev = xs.exit_evidence(holding, D, records=[_record("AAA", "SELL",
                                                       run_at=_ist("2026-10-09", "00:01"))])
    assert ev.research_run_at == "2026-10-08T18:31:00"
    assert case_broken_reasons(ev, 500.0) == ["research verdict SELL (2026-10-09)"]


# == Rework 2 (fresh re-review RR-F1) ==============================================================
#
# A demerger between a decision's close and its horizon is not a fall: part of the company's value
# leaves for another listing, and NSE's row ("Demerger") gives no fraction, so no ratio puts the
# horizon close in the decision's basis. The decision then has no result, named. The same holds for
# every row no ratio converts (a scheme, a consolidation, a capital reduction, a rights issue, a row
# naming a bonus and a split) and for a new basis the instrument registry records.

# NSE's own subjects, from its public lists read on 25 Oct 2026, and the kind each is.
NSE_WORDING = [
    ("Demerger", "demerger"),
    ("Scheme Of Arrangement", "scheme of arrangement"),
    ("Merger", "scheme of arrangement"),
    ("Rights 1:15 @ Premium Rs 1247", "rights issue"),
    ("Rights 9:77 Partly Paid @ Premium Rs 100/-", "rights issue"),
    ("Rights - 4:25 Fully Paid Up Shares @ Premium Rs 500/- Per Share", "rights issue"),
    ("Rights Eq 1:6/Dif Vot 1:6", "rights issue"),
]
# Kinds those lists did not hold, worded the way NSE words the others.
OTHER_WORDING = [
    ("Spin Off", "demerger"),
    ("Amalgamation", "scheme of arrangement"),
    ("Consolidation Of Shares From Re 1/- Per Share To Rs 10/- Per Share", "consolidation"),
    ("Capital Reduction", "capital reduction"),
    ("Reduction Of Share Capital", "capital reduction"),
    ("Bonus 1:1/Rights 1:5 @ Premium Rs 100/-", "rights issue"),
]
# Rows that leave the price basis alone (dividends are a stated limit, KT section 6).
NEUTRAL_WORDING = ["Buy Back", "Buyback", "Annual General Meeting", "Agm", "E-Voting",
                   "Agm/Div-Rs.3.50 Per Share", "Interim Dividend - Rs 2 Per Share",
                   "Div Fin-100% + Spl-25%"]
BONUS_AND_SPLIT = ("Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- "
                   "Per Share")


def _no_ratio(kind: str, ex: str, after: str) -> str:
    return (f"NSE lists a {kind} ex {ex}, after the decision's close ({after}), and no ratio "
            "puts the horizon close in the decision's price basis across it")


def _pipeline_decisions(monkeypatch, tmp_path) -> list[dict]:
    """PR-009's pipeline on Friday 23 Oct: BBB sold by the evidence rule at ₹190, AAA by the
    price-path rule at ₹480, both plain EXITs into cash."""
    import core.portfolio.pipeline as pipeline
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    pipeline.run_post_review_pipeline(D)
    rows = [r for r in store.load_exit_shadow() if r["disagree"]]
    assert sorted((r["symbol"], r["evidence_verdict"], r["benchmark"], r["close"])
                  for r in rows) == [("AAA", "HOLD", "cash", 480.0), ("BBB", "EXIT", "cash", 190.0)]
    return rows


def test_rr1_a_demerger_after_the_decision_is_no_result(monkeypatch, tmp_path):
    """The re-review's RR1, pinned, through the real pipeline and price path. BBB and AAA stay
    flat in real terms, and each demerges 40% of its value on Wednesday 28 Oct, three sessions
    after the decision, so NSE's raw close is then ₹114 and ₹288. By hand, BBB's sale saved
    nothing and AAA's keep lost nothing; read as prices, each fell 40% (+40 to the seller, -40
    to the keeper). NSE's row says only "Demerger", and no ratio tells the two apart: no result
    at 10 and at 30 sessions for both, named, and the scorecard line names both stocks."""
    rows = _pipeline_decisions(monkeypatch, tmp_path)
    ex = trading_days_after(D, 3)
    market = _Market()
    market.value = {"BBB": lambda d: 190.0, "AAA": lambda d: 480.0}
    market.demerge("BBB", ex, 0.6)
    market.demerge("AAA", ex, 0.6)
    quotes, actions = market.install(monkeypatch)
    assert quotes("BBB", trading_days_after(D, 10)).close == pytest.approx(114.0)
    prices = dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), **prices)
    reason = _no_ratio("demerger", "2026-10-28", "2026-10-23")
    assert sorted((g["symbol"], g["horizon_td"], g["status"], g["result_pct"], g["right"],
                   g["no_basis"]) for g in grades) == [
        (s, h, "ungraded", None, None, reason) for s in ("AAA", "BBB") for h in (10, 30)]
    block = xs.scorecard_block(rows, as_of=date(2026, 12, 31), **prices)
    assert [(t["no_basis"], t["no_basis_symbols"]) for t in block["tally"]] == [
        (2, ["AAA", "BBB"])] * 2
    assert ("2 with no result at 10 sessions, as a corporate action could not be ruled out or "
            "allowed for (AAA, BBB)") in xs.scorecard_text(block)


@pytest.mark.parametrize("demerger", [False, True])
def test_rr2_one_demerger_no_longer_passes_a_losing_rule(monkeypatch, demerger):
    """The re-review's RR2, pinned. 15 sales by the evidence rule: S0-S7 then fell 2% (right,
    +2 each) and S8-S14 rose 5% (wrong, -5 each): (8 x 2 - 7 x 5) / 15 = -19/15, about -1.27%
    a decision, right on 8 of 15, so it fails. Then S14 demerges 40% three sessions after its
    decision: its raw close at both horizons is 105 x 3/5 = ₹63, still +5% in real terms. With
    the defect it read -37%, right, +37: 9 of 15 at +23/15 = +1.53%, a pass two weeks running.
    Now S14 has no result: still 8 right, the money check cannot pass, and the week after
    nothing is recommended."""
    market = _Market()
    rows = _real_rows(market, [(True, -2.0)] * 8 + [(True, 5.0)] * 7)
    if demerger:
        market.demerge("S14", trading_days_after(date.fromisoformat(rows[14]["date"]), 3), 0.6)
    quotes, actions = market.install(monkeypatch)
    prices = dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)
    look = xs.scorecard_block(rows, as_of=date(2026, 12, 31), **prices)["gate"]
    assert (look["status"], look["right"]) == (xs.FAIL, {"10": 8, "30": 8})
    if demerger:
        assert (look["mean_result_pct"], look["unknown_result"]) == (
            {"10": None, "30": None}, {"10": 1, "30": 1})
        assert look["reasons"] == [
            "1 decision with no result at 10 sessions, so the money check cannot pass",
            "1 decision with no result at 30 sessions, so the money check cannot pass"]
    else:
        mean = float(Fraction(-19, 15))
        assert look["mean_result_pct"] == {"10": pytest.approx(mean), "30": pytest.approx(mean)}
        assert look["reasons"] == [
            "its mean result at 10 sessions is -1.27% (needs at least +0.00%)",
            "its mean result at 30 sessions is -1.27% (needs at least +0.00%)"]
    again = xs.scorecard_block(rows, as_of=date(2026, 12, 31) + timedelta(days=7),
                               previous_look=look, **prices)
    assert again["recommend"] is False and again["gate"]["status"] == xs.FAIL
    assert "passed" not in xs.scorecard_text(again)


REGISTRY = """
version: 1
instruments:
  BBB:
    segments:
      - {{until: 2026-10-28, status: active, symbol: BBB.NS, basis: BBB}}
      - {{from: 2026-10-28, status: active, symbol: {code}.NS, basis: {basis}, via: {via},
         evidence: [{{source: test fixture, ref: "fixture-fix016", date: 2026-10-20}}]}}
"""


@pytest.mark.parametrize("via", ["demerger", "rename"])
def test_rr3_a_new_basis_the_registry_records_is_no_result_and_a_rename_is_graded(
        monkeypatch, tmp_path, via):
    """The re-review's RR3, pinned, with NSE's list silent, so only the registry knows. From
    Wednesday 28 Oct the instrument registry prices BBB from another code. As a demerger, BBBA
    trades the 60% that stayed (₹114) on a new basis: by hand BBB is flat in real terms, read as
    prices it fell 40%, and the registry says the two closes are on two bases, so no result,
    with the registry's reason. As a rename, BBBN is the same shares under a new code (₹190) on
    the same basis: graded, a return of 0, and the sale wrong with 0."""
    rows = [r for r in _pipeline_decisions(monkeypatch, tmp_path) if r["symbol"] == "BBB"]
    code, basis, after = ("BBBA", "BBBA", 114.0) if via == "demerger" else ("BBBN", "BBB", 190.0)
    registry = tmp_path / "instruments.yaml"
    registry.write_text(REGISTRY.format(code=code, basis=basis, via=via), encoding="utf-8")
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(registry))
    market = _Market()
    market.value = {"BBB": lambda d: 190.0, code: lambda d: after}
    quotes, actions = market.install(monkeypatch)
    days = [trading_days_after(D, h) for h in (10, 30)]
    assert [quotes("BBB", d).close for d in days] == [after, after]
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    if via == "rename":
        assert [(g["status"], g["return_pct"], g["right"], g["result_pct"]) for g in grades] == [
            ("graded", 0.0, False, 0.0)] * 2
        return
    assert [(g["status"], g["result_pct"], g["no_basis"]) for g in grades] == [
        ("ungraded", None, "the instrument registry says the price basis changed between "
                           f"2026-10-23 and {d.isoformat()}: BBB (BBB.NS) then BBBA (BBBA.NS)")
        for d in days]


def test_the_action_record_names_each_change_no_ratio_converts():
    """Every row by NSE's wording, each on its own ex-date. The record keeps the plain bonus and
    split as ratios; the rows no ratio converts as (ex-date, kind), whatever else they say (a
    bonus with a rights issue keeps its ratio too); a row naming a bonus and a split as unparsed
    (read as its bonus alone it would be a ratio of 2 where the price fell to a tenth); and
    nothing for a buy back, a meeting or a dividend."""
    from core.portfolio.corp_actions import action_record
    named = NSE_WORDING + OTHER_WORDING
    split = "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"
    subjects = [s for s, _k in named] + NEUTRAL_WORDING + ["Bonus 1:1", split, BONUS_AND_SPLIT]
    ex = [date(2026, 1, 5) + timedelta(days=i) for i in range(len(subjects))]
    record = action_record([{"subject": s, "exDate": d.strftime("%d-%b-%Y")}
                            for s, d in zip(subjects, ex)], "AAA")
    assert record.basis_changes == tuple((ex[i].isoformat(), kind)
                                         for i, (_s, kind) in enumerate(named))
    n = len(named) + len(NEUTRAL_WORDING)
    assert [(a.ex_date, a.kind, a.ratio) for a in record.actions] == [
        (ex[len(named) - 1].isoformat(), "bonus", 2.0),     # the bonus beside a rights issue
        (ex[n].isoformat(), "bonus", 2.0), (ex[n + 1].isoformat(), "split", 5.0)]
    assert record.unparsed == (ex[n + 2].isoformat(),)


def test_a_change_no_ratio_converts_is_no_result_by_hand():
    """`horizon_in_basis` as in the bonus table above: the decision's close is Thursday 1 Oct's
    bar, stored on Monday 5 Oct; the horizon's bar is Friday 30 Oct at a raw ₹100."""
    from core.portfolio.corp_actions import action_record
    from core.portfolio.pricing import SessionClose
    start, decided, bar = date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 30)
    d20, nov2 = date(2026, 10, 20), date(2026, 11, 2)

    def listed(subject, ex):
        row = {"subject": subject, "exDate": ex.strftime("%d-%b-%Y")}
        return action_record([DIVIDEND_2025, row], "AAA")
    nse = SessionClose(100.0, bar, "nse")
    agree = SessionClose(100.0, bar, "agree")
    yahoo = SessionClose(100.0, bar, "yfinance")
    for subject, kind in NSE_WORDING + OTHER_WORDING:
        assert xs.horizon_in_basis(nse, listed(subject, d20), start, decided) == (
            None, "", _no_ratio(kind, "2026-10-20", "2026-10-01")), subject
    for subject in NEUTRAL_WORDING:
        assert xs.horizon_in_basis(nse, listed(subject, d20), start, decided) == (
            100.0, "", ""), subject
    assert xs.horizon_in_basis(nse, listed(BONUS_AND_SPLIT, d20), start, decided) == (
        None, "", "NSE lists a split or bonus on 2026-10-20 that could not be read")

    def demerger(ex, quote):
        return xs.horizon_in_basis(quote, listed("Demerger", ex), start, decided)
    def gone(ex: str) -> str:
        return _no_ratio("demerger", ex, "2026-10-01")
    # ex on the close's own bar: both closes are after it, in one basis
    assert demerger(start, nse) == (100.0, "", "")
    # ex by the review day, or on the horizon's bar: one close on each side
    assert demerger(decided, nse) == (None, "", gone("2026-10-05"))
    assert demerger(bar, nse) == (None, "", gone("2026-10-30"))
    # ex after the horizon's bar: NSE's raw close (or Yahoo's agreeing) is still before it
    assert demerger(nov2, nse) == (100.0, "", "")
    assert demerger(nov2, agree) == (100.0, "", "")
    # ... but Yahoo's alone may be scaled for it
    assert demerger(nov2, yahoo) == (None, "", gone("2026-11-02"))
    # a horizon close carried forward from the decision's own bar, a demerger by the review day
    assert demerger(decided, SessionClose(100.0, start, "nse")) == (None, "", gone("2026-10-05"))


def test_a_row_naming_a_bonus_and_a_split_leaves_the_invalidation_level_unused():
    """PR-009's level, with that row between the dive and the buy. Read as its bonus alone the
    ₹455 level would become ₹227.50 where the price fell to a tenth (x2 and x5, ₹45.50), so the
    test would never fire; the level is unused, and the gap says why. A plain bonus still
    halves it."""
    from core.portfolio.corp_actions import action_record
    holding = _holding("AAA", 500.0, sessions=4)
    dived, ex = date(2026, 10, 1), "12-Oct-2026"
    assert dived.isoformat() < "2026-10-12" < holding.buy_date
    both = action_record([DIVIDEND_2025, {"subject": BONUS_AND_SPLIT, "exDate": ex}], "AAA")
    assert xs.level_in_basis(455.0, dived, holding, D, both) == (
        0.0, "", "NSE lists a split or bonus on 2026-10-12 that could not be read, so its price "
                 "basis is unknown")
    bonus = action_record([DIVIDEND_2025, {"subject": "Bonus 1:1", "exDate": ex}], "AAA")
    assert xs.level_in_basis(455.0, dived, holding, D, bonus)[0] == 227.5


def _session(day: date, k: int) -> date:
    return trading_days_after(day, k) if k >= 0 else trading_days_ago(day, -k)


def test_a_graded_result_is_always_the_return_in_real_terms(monkeypatch):
    """Random markets, through the real price path. Each decision's stock moves by a random
    amount in real terms after its review day, and may go ex on a 1:1 bonus, on a demerger
    keeping a random fraction, or both, each on a random session from 5 before the decision to
    35 after it; NSE's close is down on some days, and in half the markets Yahoo's series is
    scaled for demergers. Expected from the model alone: a graded decision's return is its move
    in real terms, never a demerger's fall or a bonus's; a decision with a demerger after its
    close and by its horizon has no result; one with NSE's close on its horizon day and no such
    demerger is graded."""
    rnd = random.Random(20261025)
    seen = Counter()
    for _trial in range(6):
        market = _Market()
        market.yahoo_adjusts_demergers = rnd.random() < 0.5
        rows, plan = [], {}
        for i in range(25):
            symbol = f"R{i}"
            day = trading_days_after(date(2026, 6, 1), rnd.randrange(0, 40))
            move = rnd.choice([-7.0, -2.5, 0.0, 3.0, 12.0])
            market.value[symbol] = lambda d, day=day, move=move: 100.0 if d <= day else 100.0 + move
            if rnd.random() < 0.5:
                market.bonus(symbol, _session(day, rnd.randrange(-5, 36)))
            if rnd.random() < 0.5:
                market.demerge(symbol, _session(day, rnd.randrange(-5, 36)), rnd.choice([0.5, 0.8]))
            plan[symbol] = (day, move)
            rows.append({"date": day.isoformat(), "symbol": symbol,
                         "close": market.raw(symbol, day), "mode": "shadow",
                         "buy_date": "2026-05-04", "price_bar_date": day.isoformat(),
                         "legacy_verdict": "HOLD", "evidence_verdict": "EXIT", "disagree": True,
                         "benchmark": "cash"})
        market.nse_down = {trading_days_after(date(2026, 6, 1), k) for k in range(80)
                           if rnd.random() < 0.3}
        quotes, actions = market.install(monkeypatch)
        for g in xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                        bench_close_on=lambda d: 1000.0, corp_actions=actions):
            day, move = plan[g["symbol"]]
            horizon = date.fromisoformat(g["matures"])
            split_off = any(day < ex <= horizon
                            for ex, _k, _r in market.demergers.get(g["symbol"], []))
            nse_answered = horizon not in market.nse_down
            if g["status"] == "graded":
                assert g["return_pct"] == pytest.approx(move, abs=1e-9), g
                seen["graded"] += 1
                seen["graded across a bonus"] += any(
                    day < ex <= horizon for ex, _r, _row in market.actions.get(g["symbol"], []))
                seen["graded from Yahoo alone"] += not nse_answered
            else:
                assert g["status"] == "ungraded" and g["result_pct"] is None and g["no_basis"]
                seen["no result"] += 1
            if split_off:
                assert g["status"] == "ungraded", g
                seen["demerger between"] += 1
            elif nse_answered:
                assert g["status"] == "graded", g
    assert all(seen[k] > 5 for k in ("graded", "graded across a bonus", "graded from Yahoo alone",
                                     "no result", "demerger between")), seen


# == Rework 3 (fresh re-review 2: RR2-F1, RR2-M1) =================================================
#
# The record fails closed. A row is a ratio only when every word in it is one of an equity bonus
# or a face-value split, or of a part that leaves the price basis alone; it is neutral only when
# every word is one of such a part (a dividend, a meeting, a vote, a buy back, interest or a
# redemption). Any other row is not read, so a decision whose closes span it has no result.
# NSE's list is read under the code the close is read under, so a registry alias is graded.

PREFERENCE_BONUS = "Bonus Preference Shares 21:1"      # ZEEL, ex 3 Mar 2014
SHORT_SPLIT = "Fv Splt Frm Rs 10 To Re 1"               # JSWSTEEL, ex 4 Jan 2017


def _listed_row(market: _Market, symbol: str, ex: date, subject: str, kept: float) -> None:
    """A row in NSE's list for `symbol`, ex `ex`, worded `subject`: from `ex` the stock trades
    at `kept` of what one old share is worth (1.0: the row moves nothing)."""
    market.demergers.setdefault(symbol, []).append(
        (ex, kept, {"subject": subject, "exDate": ex.strftime("%d-%b-%Y")}))


def _no_known_kind(subject: str, ex: str, after: str) -> str:
    return _no_ratio(f"corporate action of no known kind ({subject!r})", ex, after)


def _not_read(ex: str) -> str:
    return f"NSE lists a split or bonus on {ex} that could not be read"


def _row_reading(subject: str) -> tuple:
    """What the record makes of one dated row: (its ratios, whether it is a share-count row not
    read as a ratio, the kinds of change it names, "unknown" for a row of no known kind)."""
    from core.portfolio.corp_actions import action_record
    record = action_record([{"subject": subject, "exDate": "05-Jan-2026"}], "AAA")
    kinds = tuple("unknown" if kind.startswith("corporate action of no known kind") else kind
                  for _ex, kind in record.basis_changes)
    return tuple((a.kind, a.ratio) for a in record.actions), bool(record.unparsed), kinds


NOTHING = ((), False, ())
UNREAD = ((), True, ())
SCHEME = "scheme of arrangement"
# NSE's own subjects (symbol and ex-date; the configured symbols' lists read on 29 Oct 2026), and
# what the record must make of each, worked from what the row says.
NSE_ROWS = [
    # the re-review's RR2-F1 rows: a bonus of other securities is no ratio of equity shares
    (PREFERENCE_BONUS, UNREAD),                                                 # ZEEL 2014
    ("Scheme Of Arrangement - Bonus Debentures 6:1", ((), True, (SCHEME,))),   # DRREDDY 2011
    ("Scheme Of Arrangement - Bonus Ncrps 4:1", ((), True, (SCHEME,))),        # TVSMOTOR 2025
    ("Scheme Of Arrangement - Issue Of Bonus Debentures", ((), True, (SCHEME,))),  # BLUEDART 2014
    ("Scheme Of Arangement- Bonus - 1 Debenture For 1 Equity Share Held",
     ((), True, (SCHEME,))),                                                    # BRITANNIA 2019
    # a face-value change in words with no ratio the parser reads
    (SHORT_SPLIT, UNREAD),                                                      # JSWSTEEL 2017
    ("Fv Splt Frm Rs 10 To Rs 2", UNREAD),                                      # KNRCON 2016
    ("Fv Split Rs.10 To Rs.5", UNREAD),                                         # M&M 2010
    ("Face Value Split Rs.10/- To Re.1/- Per Share", UNREAD),                   # SBIN 2014
    ("Agm/Div-Rs.2/Fv Rs10tors5", UNREAD),                                      # BHARTIARTL 2009
    ("Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
     UNREAD),                                                                   # BAJFINANCE 2016
    # a change no ratio converts, in NSE's short or misspelt words
    ("Rhs 3:7@Prem Rs95/Div185%", ((), False, ("rights issue",))),             # HINDALCO 2008
    ("Scheme Of Arangement", ((), False, (SCHEME,))),
    ("Agm/Div-50%/Sch Of Arrang", ((), False, (SCHEME,))),                      # NIIT (undated)
    ("Composite Scheme Of Arrangement", ((), False, (SCHEME,))),                # CESC 2018
    ("Annual General Meeting / Dividend Rs.2/- Per Share / Scheme Of Arrangement",
     ((), False, (SCHEME,))),                                                   # ZEEL 2010
    ("Rights 5:78 @ Premium Rs 110/-", ((), False, ("rights issue",))),        # INOXWIND 2025
    ("Demerger", ((), False, ("demerger",))),                                   # INOXGREEN 2026
    # rows of no known kind: not read, whatever they mean
    ("9 Ccds For Every 40 Equity Shares", ((), False, ("unknown",))),          # INDHOTEL 2014
    ("Interim Dividned - Rs 135 Per Share", ((), False, ("unknown",))),        # NESTLEIND 2020
    # ratios in full: (new + held) / held for a bonus, old / new face value for a split
    ("Bonus 1:3", ((("bonus", 4 / 3),), False, ())),                            # BRIGADE 2026
    ("Annual General Meeting/Dividend - Rs 2.50 Per Share/Bonus 1:10 (Revised)",
     ((("bonus", 1.1),), False, ())),                                           # ICICIBANK 2017
    ("Face Value Split (Sub-Division) - From Rs 4/- Per Share To Rs 2/- Per Share",
     ((("split", 2.0),), False, ())),                                           # NAZARA 2025
    ("Face Value Split (Sub-Division) - From Rs10/- Per Share To Re 1/- Per Share",
     ((("split", 10.0),), False, ())),                                          # NESTLEIND 2024
    # rows that leave the basis alone, in each recent shape and some old ones
    ("Dividend - Rs 1.50 Per Share", NOTHING),                                  # IGL 2026
    ("Interim Dividend - Rs 20 Per Share", NOTHING),                            # LTTS 2026
    ("Annual General Meeting/Dividend - Rs 20 Per Share", NOTHING),             # PIDILITIND 2025
    ("Annual General Meeting", NOTHING),                                        # TCI 2025
    ("Buy Back", NOTHING),                                                      # TCI 2026
    ("Special Dividend - Rs 90 Per Share", NOTHING),                            # ABB 2026
    ("Interim Dividend - Rs 5.75 Per Sh", NOTHING),                             # GRSE 2025
    ("Interim Dividend - Rs 10 Per Share Special Dividend - Rs 66 Per Share", NOTHING),  # TCS 2025
    ("Dividend - Rs 5 Per Share & Special Dividend - Rs 4.50 Per Share", NOTHING),  # CASTROLIND
    ("Dividend - Rs2.50 Per Share", NOTHING),                                   # APOLLOTYRE 2026
    ("Special Dividend Rs -10 Per Share/Interim Dividend Rs - 26 Per Share", NOTHING),  # COLPAL
    ("Dividend - Rs 35 Per Share & Special Dividend Of Rs 100 Per Share/ Special Dividend Of Rs 30",
     NOTHING),                                                                  # PFIZER 2025
    ("Final Dividend - Rs 75 Per Share", NOTHING),                              # NESTLEIND 2023
    ("Interest Payment/Redemption", NOTHING),                                   # IDFCFIRSTB
    ("Second Interim Dividend - Rs 1.15 Per Share (Purpose Revised)", NOTHING),  # TVSMOTOR 2015
    ("Annual General Meeting / Final Dividend Rs.6/- Per Equity Share", NOTHING),  # YESBANK 2013
    ("Annual General Meeting/ Change In Registrar And Transfer Agent", NOTHING),  # SBIN 2018
]
# Wordings no list held: the rule, not a word list, decides.
OTHER_ROWS = [
    ("Return Of Capital", ((), False, ("capital reduction",))),
    ("De Merger", ((), False, ("demerger",))),
    ("Transfer Of Undertaking", ((), False, ("unknown",))),
    ("Dividend In Specie", ((), False, ("unknown",))),
    ("Bonus 1:1 Warrants", UNREAD),
    ("Reverse Split", UNREAD),
    ("Splt Frm Rs 10 To Re 1", UNREAD),
    # a bonus and a split beside a rights issue: never its bonus alone (×2 where the price fell
    # to a tenth), even where only the bonus's own words are read
    ("Bonus 1:1/Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"
     "/Rights 1:5 @ Premium Rs 100/-", ((), True, ("rights issue",))),
    ("", ((), False, ("unknown",))),
]


@pytest.mark.parametrize("subject, reading", NSE_ROWS + OTHER_ROWS)
def test_rr2_every_row_is_read_in_full_or_refused(subject, reading):
    """The re-review's RR2-F1 rows and NSE's other wordings, one row each. A row is a ratio only
    when it is an equity bonus or a face-value split and every word is known; a bonus of
    preference shares, debentures or NCRPS, or a split in short words, is a share-count row not
    read; any other row is neutral only when every word is of a dividend, a meeting, a vote, a
    buy back, interest or a redemption (or a registrar change), else a row of no known kind."""
    assert _row_reading(subject) == reading


def test_rr2_q5_a_bonus_of_preference_shares_no_longer_passes_a_losing_rule(monkeypatch):
    """The re-review's Q5, pinned through the real price path. 15 decisions where the evidence
    rule kept and the price-path rule sold (plain EXITs, cash): S0-S7 then rose 2% (right, +2)
    and S8-S14 fell 5% (wrong, -5): (8 x 2 - 7 x 5) / 15 = -19/15, about -1.27% a decision, a
    fail. Three sessions after its decision S14 issues bonus preference shares worth 7.5% of
    its price, worded as ZEEL's row: the equity trades at 92.5% of what one old share is worth,
    and the number of equity shares does not change. By hand S14 is still wrong (-5 in real
    terms). NSE's row gives no ratio of equity shares, so S14 has no result at both horizons,
    named; the gate fails (right on 8, the money check cannot pass) and the week after
    recommends nothing. With the defect the record read a 22-for-1 bonus: 95 x 0.925 x 22, a
    +1,833% keep, right, and a mean above +100%: a pass."""
    market = _Market()
    rows = _real_rows(market, [(False, 2.0)] * 8 + [(False, -5.0)] * 7)
    decided = date.fromisoformat(rows[14]["date"])
    ex = trading_days_after(decided, 3)
    _listed_row(market, "S14", ex, PREFERENCE_BONUS, 0.925)
    quotes, actions = market.install(monkeypatch)
    assert quotes("S14", trading_days_after(decided, 10)).close == pytest.approx(95 * 0.925)
    assert actions("S14").actions == () and actions("S14").unparsed == (ex.isoformat(),)
    prices = dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)
    s14 = xs.grade_disagreements(rows[14:], as_of=date(2026, 12, 31), **prices)
    assert [(g["status"], g["result_pct"], g["no_basis"]) for g in s14] == [
        ("ungraded", None, _not_read(ex.isoformat()))] * 2
    look = xs.scorecard_block(rows, as_of=date(2026, 12, 31), **prices)["gate"]
    assert (look["status"], look["right"], look["mean_result_pct"], look["unknown_result"]) == (
        xs.FAIL, {"10": 8, "30": 8}, {"10": None, "30": None}, {"10": 1, "30": 1})
    again = xs.scorecard_block(rows, as_of=date(2026, 12, 31) + timedelta(days=7),
                               previous_look=look, **prices)
    assert again["recommend"] is False and again["gate"]["status"] == xs.FAIL


@pytest.mark.parametrize("subject, reason", [
    # NSE's misspelling in BRITANNIA's 2019 and 2021 rows: named, as a scheme
    ("Scheme Of Arangement", lambda ex, after: _no_ratio("scheme of arrangement", ex, after)),
    # wording no list held and the record knows nothing of: not read, whatever it means
    ("Transfer Of Undertaking", lambda ex, after: _no_known_kind("Transfer Of Undertaking",
                                                                   ex, after)),
])
def test_rr2_q3_a_demerger_in_wording_the_record_does_not_know_passes_no_losing_rule(
        monkeypatch, subject, reason):
    """The re-review's Q3, pinned through the real price path, and the same with wording the
    record has never seen. The RR2 population: 15 sales by the evidence rule, S0-S7 then fell 2%
    (right, +2) and S8-S14 rose 5% (wrong, -5): -19/15, a fail. Three sessions after its
    decision S14 demerges 40% of its worth, worded `subject`: ₹105 x 0.6 = ₹63, still +5% in
    real terms, so still wrong with -5. S14 has no result at both horizons, named; the gate
    fails and the week after recommends nothing. With the defect S14 read a 37% fall, right,
    +37: 9 of 15 at +1.53%, a pass."""
    market = _Market()
    rows = _real_rows(market, [(True, -2.0)] * 8 + [(True, 5.0)] * 7)
    decided = date.fromisoformat(rows[14]["date"])
    ex = trading_days_after(decided, 3)
    _listed_row(market, "S14", ex, subject, 0.6)
    quotes, actions = market.install(monkeypatch)
    assert quotes("S14", trading_days_after(decided, 10)).close == pytest.approx(63.0)
    prices = dict(stock_quote_on=quotes, bench_close_on=lambda d: 1000.0, corp_actions=actions)
    s14 = xs.grade_disagreements(rows[14:], as_of=date(2026, 12, 31), **prices)
    assert [(g["status"], g["result_pct"], g["no_basis"]) for g in s14] == [
        ("ungraded", None, reason(ex.isoformat(), decided.isoformat()))] * 2
    look = xs.scorecard_block(rows, as_of=date(2026, 12, 31), **prices)["gate"]
    assert (look["status"], look["right"], look["unknown_result"]) == (
        xs.FAIL, {"10": 8, "30": 8}, {"10": 1, "30": 1})
    again = xs.scorecard_block(rows, as_of=date(2026, 12, 31) + timedelta(days=7),
                               previous_look=look, **prices)
    assert again["recommend"] is False


def test_rr2_nses_short_split_wording_is_no_result_not_a_fall(monkeypatch):
    """S0 is sold by the evidence rule at ₹100 and stays flat in real terms. Three sessions
    later it splits from Rs 10 to Re 1 a share, worded as JSWSTEEL's row: NSE's raw close is
    then ₹10, which is ₹100 in the old shares. By hand: a return of 0, the sale wrong with 0;
    read as prices, a 90% fall and +90 to the seller (the defect: the row was neither a ratio
    nor unread). The record cannot read the ratio from "Fv Splt Frm", so the decision has no
    result at both horizons, named. The standard wording of the same split is graded at 0."""
    for subject, expected in [
            (SHORT_SPLIT, "unread"),
            ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share",
             "graded")]:
        market = _Market()
        rows = _real_rows(market, [(True, 0.0)])
        decided = date.fromisoformat(rows[0]["date"])
        ex = trading_days_after(decided, 3)
        market.actions["S0"] = [(ex, 10.0, {"subject": subject,
                                            "exDate": ex.strftime("%d-%b-%Y")})]
        quotes, actions = market.install(monkeypatch)
        assert quotes("S0", trading_days_after(decided, 10)).close == pytest.approx(10.0)
        grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                        bench_close_on=lambda d: 1000.0, corp_actions=actions)
        if expected == "unread":
            assert [(g["status"], g["result_pct"], g["no_basis"]) for g in grades] == [
                ("ungraded", None, _not_read(ex.isoformat()))] * 2
        else:
            assert [(g["status"], g["return_pct"], g["right"], g["result_pct"], g["basis"])
                    for g in grades] == [
                ("graded", 0.0, False, 0.0, f"×10 for the split ex {ex.isoformat()}")] * 2


@pytest.mark.parametrize("alias, code", [("TVSMOTORS", "TVSMOTOR"), ("CANARABANK", "CANBK")])
def test_rr2_m1_a_registry_alias_reads_nses_list_under_nses_code(monkeypatch, alias, code):
    """The re-review's Q6, with the registry's own aliases (config/instruments.yaml). NSE knows
    only its own code: actions("TVSMOTORS") lists nothing, as it answered on 29 Oct 2026. The
    evidence rule sells the alias at ₹2,500; the stock stays flat in real terms, and three
    sessions later it splits from Rs 10 to Rs 2 a share, worded as Canara Bank's 15 May 2024
    row, so NSE's raw close is ₹500. By hand: ₹500 is ₹2,500 in the old shares, a return of 0,
    the sale wrong with 0. Grading asks NSE for the code the close is read under, once, and
    grades it; with the defect it asked for the alias, got nothing, and had no result for
    good."""
    from core.portfolio import corp_actions
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH",
                       str(Path(__file__).resolve().parents[2] / "config" / "instruments.yaml"))
    market = _Market()
    rows = [dict(r, symbol=alias, close=2500.0) for r in _real_rows(market, [(True, 0.0)])]
    decided = date.fromisoformat(rows[0]["date"])
    ex = trading_days_after(decided, 3)
    market.value = {code: lambda d: 2500.0}
    market.actions[code] = [(ex, 5.0, _nse_row("split", ex))]
    quotes, actions = market.install(monkeypatch)
    reads = []
    real_fetch = corp_actions.fetch_corp_actions
    monkeypatch.setattr(corp_actions, "fetch_corp_actions",
                        lambda s: reads.append(s) or real_fetch(s))
    assert quotes(alias, trading_days_after(decided, 10)).close == 500.0
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                    bench_close_on=lambda d: 1000.0, corp_actions=actions)
    assert reads == [code]
    assert [(g["status"], g["return_pct"], g["right"], g["result_pct"], g["basis"])
            for g in grades] == [
        ("graded", 0.0, False, 0.0, f"×5 for the split ex {ex.isoformat()}")] * 2
    assert real_fetch(alias) == []          # NSE lists nothing under the alias


def test_rr2_a_row_the_record_cannot_read_leaves_the_invalidation_level_unused():
    """PR-009's level, with ZEEL's or JSWSTEEL's wording between the dive and the buy. Read as
    a 22-for-1 bonus the ₹455 level became ₹20.68, and the short split wording was not seen at
    all, so the level stayed ₹455 where the price fell to a tenth: either way the test never
    fired or fired at once. Now the level is unused, and the gap says why."""
    from core.portfolio.corp_actions import action_record
    holding = _holding("AAA", 500.0, sessions=4)
    dived, ex = date(2026, 10, 1), "12-Oct-2026"
    assert dived.isoformat() < "2026-10-12" < holding.buy_date
    for subject in (PREFERENCE_BONUS, SHORT_SPLIT):
        record = action_record([DIVIDEND_2025, {"subject": subject, "exDate": ex}], "AAA")
        assert xs.level_in_basis(455.0, dived, holding, D, record) == (
            0.0, "", "NSE lists a split or bonus on 2026-10-12 that could not be read, so its "
                     "price basis is unknown"), subject


# A row NSE might list between a decision's closes, and what it does to the price: (subject,
# kind, effect). "ratio": the raw price falls by the ratio (a bonus or a split, in words the
# record reads); "kept": the stock trades at that fraction of its worth from the ex day (an
# action whose wording no ratio converts, or that the record does not know); "none": nothing
# changes (a dividend is a stated limit and moves nothing here).
_KNOWN_ROWS = [
    ("Bonus 1:1", "ratio", 2.0),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", "ratio", 5.0),
    ("Interim Dividend - Rs 4 Per Share", "none", 1.0),
    ("Annual General Meeting/Dividend - Rs 8 Per Share", "none", 1.0),
    ("Buy Back", "none", 1.0),
    ("E-Voting", "none", 1.0),
]
_ODD_ROWS = [
    (PREFERENCE_BONUS, "kept", 0.925),
    (SHORT_SPLIT, "ratio", 10.0),
    ("Fv Split Rs.10 To Rs.5", "ratio", 2.0),
    ("Bonus Debentures 6:1", "kept", 0.9),
    ("Rhs 3:7@Prem Rs95/Div185%", "kept", 0.93),
    ("Scheme Of Arangement", "kept", 0.6),
    ("Transfer Of Undertaking", "kept", 0.7),
    ("Bonus 1:1 Warrants", "kept", 0.95),
    ("Dividend In Specie", "kept", 0.8),
]


def test_a_graded_result_is_always_the_return_in_real_terms_whatever_nse_writes(monkeypatch):
    """Random markets, through the real price path. Each decision's stock moves by a random
    amount in real terms after its review day, and NSE lists up to three rows for it, each ex on
    a random session from 5 before the decision to 35 after it: a bonus or split in the words
    the record reads, a dividend, a meeting or a buy back that moves nothing, or a row in other
    words (the re-review's misread rows and wordings no list held) that moves the price by an
    amount the model knows and the row does not say. Expected from the model alone: a graded
    decision's return is its move in real terms; a decision with an odd row after its close
    and by its horizon has no result; one with NSE's close on its horizon day and only known
    rows between is graded."""
    rnd = random.Random(20261029)
    seen = Counter()
    for _trial in range(6):
        market = _Market()
        rows, plan = [], {}
        for i in range(25):
            symbol = f"W{i}"
            day = trading_days_after(date(2026, 6, 1), rnd.randrange(0, 40))
            move = rnd.choice([-7.0, -2.5, 0.0, 3.0, 12.0])
            market.value[symbol] = lambda d, day=day, move=move: 100.0 if d <= day else 100.0 + move
            odd, listed = [], set()
            for _n in range(rnd.randrange(0, 4)):
                subject, kind, effect = rnd.choice(_KNOWN_ROWS if rnd.random() < 0.5 else _ODD_ROWS)
                ex = _session(day, rnd.randrange(-5, 36))
                if (subject, ex) in listed:     # one row listed twice is one action
                    continue
                listed.add((subject, ex))
                row = {"subject": subject, "exDate": ex.strftime("%d-%b-%Y")}
                if kind == "ratio":
                    market.actions.setdefault(symbol, []).append((ex, effect, row))
                else:
                    market.demergers.setdefault(symbol, []).append((ex, effect, row))
                if (subject, kind, effect) in _ODD_ROWS:
                    odd.append(ex)
            plan[symbol] = (day, move, odd)
            rows.append({"date": day.isoformat(), "symbol": symbol,
                         "close": market.raw(symbol, day), "mode": "shadow",
                         "buy_date": "2026-05-04", "price_bar_date": day.isoformat(),
                         "legacy_verdict": "HOLD", "evidence_verdict": "EXIT", "disagree": True,
                         "benchmark": "cash"})
        market.nse_down = {trading_days_after(date(2026, 6, 1), k) for k in range(80)
                           if rnd.random() < 0.3}
        quotes, actions = market.install(monkeypatch)
        for g in xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_quote_on=quotes,
                                        bench_close_on=lambda d: 1000.0, corp_actions=actions):
            day, move, odd = plan[g["symbol"]]
            horizon = date.fromisoformat(g["matures"])
            between = [ex for ex in odd if day < ex <= horizon]
            if g["status"] == "graded":
                assert g["return_pct"] == pytest.approx(move, abs=1e-9), g
                seen["graded"] += 1
                seen["graded across a known row"] += any(
                    day < ex <= horizon
                    for ex, *_r in market.actions.get(g["symbol"], [])
                    + market.demergers.get(g["symbol"], []))
            else:
                assert g["status"] == "ungraded" and g["result_pct"] is None and g["no_basis"]
                seen["no result"] += 1
            if between:
                assert g["status"] == "ungraded", g
                seen["odd row between"] += 1
            elif horizon not in market.nse_down:
                assert g["status"] == "graded", g
    assert all(seen[k] > 5 for k in ("graded", "graded across a known row", "no result",
                                     "odd row between")), seen
