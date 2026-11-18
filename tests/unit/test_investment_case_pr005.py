"""PR-005: an investment case for every position.

Independent invariants, one per acceptance criterion of the card, each worked
from the fixture's own numbers:

- a case built from the fixture bundle holds only figures of that bundle (a
  property over every text field), and each evidence fact only figures of the
  input it cites; a stub that invents, rounds or re-units a figure, cites
  another input's figure, cites an input that does not exist, or answers
  malformed JSON is rejected and the deterministic case is stored, naming why;
- issue time (FIX-004): no input known at or after the case's `as_of` is in
  the bundle (a property over random publication times), and nothing it
  cites is dated after it;
- each buy path (a SWITCH and a deployment buy through `execute_advice`, a
  manual add through the route) writes exactly one version 1 case; a re-run
  of the same review date writes none; an ADD, or a buy into a holding
  already held, writes none;
- a contradicting fixture event marks the matching pillar `challenged` and
  cites it; a news event's challenge never sells; each event is read once;
- a backfilled case is `after_purchase`; a dry run writes nothing;
- a member reads only their own cases;
- the routed input: the invalidation price is stored in the buy day's basis
  (RR-L1: a demerger, capital reduction or rights issue between the dive and
  the buy leaves no price; a neighbour one day outside the window does),
  bounded by the stop and the noise line (each side of the window), and a
  price converted at purchase is not converted again.

The buy day is Friday 23 Oct 2026; the deep dive Saturday 17 Oct.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.shared.schemas.discovery import ShelfIdea
from backend.shared.schemas.dossier import GuidanceItem, TickerDossier
from backend.shared.schemas.events import CompanyEvent
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.config import settings
from core.intelligence.rl.nse_calendar import IST, is_trading_day, session_close_at
from core.portfolio import cases as C
from core.portfolio import exit_shadow as xs
from core.portfolio.advisor import case_broken_reasons
from core.portfolio.corp_actions import action_record, parse_action

SYM = "ABCBANK"
BUY = date(2026, 10, 23)                       # Friday
DIVE = "2026-10-17"                            # Saturday
AS_OF = session_close_at(BUY)                  # 15:30 IST on the buy day
NOW = datetime(2026, 10, 23, 16, 45, tzinfo=IST)
ENTRY = 212.0
DIVIDEND_AUG = {"subject": "Dividend - Rs 5 Per Share", "exDate": "14-Aug-2026"}


def test_the_fixture_calendar():
    assert is_trading_day(BUY) and not is_trading_day(date(2026, 10, 17))
    assert AS_OF.isoformat() == "2026-10-23T15:30:00+05:30"


# -- Fixtures ----------------------------------------------------------------------------

def _record(run_at="2026-10-17T05:00:00", thesis="Loan growth with steady asset quality.",
            gate="actionable", target=255.0, quarters=3, symbol=SYM):
    """A score-history row (run_at naive UTC: 10:30 IST on 17 Oct)."""
    return {"ticker": symbol, "run_at": run_at, "verdict": "BUY", "final_score": 0.74,
            "investment_thesis": thesis,
            "conviction_drivers": json.dumps(["Loans +18% YoY, GNPA 1.9%",
                                              "P/B 1.3 vs 5-year median 1.5"]),
            "top_risks": json.dumps(["GNPA above 2.5% at Q3 results"]),
            "report_json": json.dumps({
                "decision_gate": {"status": gate}, "price_target": target,
                "recovery_timeline_quarters": quarters,
                "agent_outputs": {"fundamentals": {"reasoning":
                                                   "Revenue Rs 1,200 Cr, up 18.4% on the year"}}}),
            "id": 41}


def _idea(level=200.0, thesis="Loan growth with steady asset quality. Valuation below "
                              "its own history.", dived=DIVE, symbol=SYM):
    return ShelfIdea(symbol=symbol, sector="banking_bfsi", added=dived, dived=dived,
                     conviction=0.74, verdict="BUY", thesis=thesis, entry_low=205.0,
                     entry_high=218.0, invalidation_level=level, status="promoted")


def _dossier(updated="2026-10-22"):
    return TickerDossier(ticker=SYM, sector="banking_bfsi", created_at="2026-09-01",
                         last_updated=updated,
                         guidance=[GuidanceItem(date="2026-10-15", source="con-call",
                                                guidance="Management guides loan growth of "
                                                         "18% for FY27"),
                                   GuidanceItem(date="2026-10-24", source="con-call",
                                                guidance="Guidance cut to 12%")])


def _event(published, category="results", direction="positive", materiality="high",
           source="nse_announcement", what="Q2 profit rose 22% on loan growth.", n=1,
           symbol=SYM):
    return CompanyEvent(id=f"{symbol}-{n}-{published}", symbol=symbol, what=what,
                        category=category, direction=direction, materiality=materiality,
                        source=source, published_at=published,
                        fetched_at="2026-10-25T18:30:00+05:30", classifier="rules")


RECORDS = [_record(),
           # run after the buy session's close (16:30 IST): never an input of that case
           _record(run_at="2026-10-23T11:00:00", thesis="A later view.", target=300.0)]
EVENTS = [_event("2026-10-20T10:00:00+05:30"),
          _event("2026-10-23T16:10:00+05:30", what="Q2 provisions rose 40%.",
                 direction="negative", n=2)]


def _bundle(as_of=AS_OF, ideas=None, records=None, events=None, dossier="default"):
    return C.build_bundle(SYM, as_of, records=RECORDS if records is None else records,
                          ideas=[_idea()] if ideas is None else ideas,
                          dossier=_dossier() if dossier == "default" else dossier,
                          events=EVENTS if events is None else events)


VALID = {
    "pillars": [
        {"claim": "Loan growth with steady asset quality",
         "evidence": [{"fact": "Loans +18% YoY, GNPA 1.9%", "ref": "A1"}],
         "watch_categories": ["results", "guidance"]},
        {"claim": "Valuation below its own history",
         "evidence": [{"fact": "P/B 1.3 vs 5-year median 1.5", "ref": "A1"}],
         "watch_categories": ["rating"]}],
    "expectation": "Profits keep compounding with loan growth near 18%.",
    "invalidation_business": ["GNPA above 2.5% at Q3 results"],
    "watch_next": [{"what": "Whether loan growth holds at 18% for FY27", "ref": "D1"}],
    "one_line": "A bank growing loans 18% a year with GNPA at 1.9%."}


def _answer(**over) -> str:
    data = json.loads(json.dumps(VALID))
    data.update(over)
    return json.dumps(data)


def _model(answer: str):
    calls = []

    def call(system, user):
        calls.append((system, user))
        return answer
    call.calls = calls
    return call


def _write(tmp_path, answer=None, bundle=None, record="default", atr=2.0, stop=8.0,
           model="default", now=NOW, path="deploy"):
    store = C.CaseStore("u1", str(tmp_path))
    m = _model(answer or _answer()) if model == "default" else model
    case, why = C.write_case(
        store, symbol=SYM, opened_on=BUY, entry_price=ENTRY, buy_path=path,
        bundle=bundle or _bundle(), model=m, now=now, atr_pct=atr, stop_pct=stop,
        record=action_record([DIVIDEND_AUG], SYM) if record == "default" else record)
    return store, case, why


def _texts(case) -> list[str]:
    out = [p.claim for p in case.pillars] + [case.expectation.text, case.one_line]
    out += case.invalidation.business + [w.what for w in case.watch_next if w.ref]
    return out


# -- Figures --------------------------------------------------------------------------------

def test_figures_are_compared_exactly_with_their_units():
    assert C.ungrounded("loans +18%", "Loans +18% YoY") == []
    assert C.ungrounded("loans 18%", "Loans 18.4%") == ["18%"]              # rounded
    assert C.ungrounded("revenue ₹1,200", "Revenue Rs 1,200 Cr") == ["1,200"]   # unit dropped
    assert C.ungrounded("revenue 1,200 crore", "Revenue Rs 1,200 Cr") == []    # same unit
    assert C.ungrounded("revenue 12 crore", "Revenue Rs 1,200 Cr") == ["12 crore"]
    assert C.ungrounded("12 lakh", "1,200 Cr") == ["12 lakh"]
    assert C.ungrounded("1,20,000 shares", "120000 shares") == []           # Indian commas
    assert C.ungrounded("by FY28", "FY27 guidance") == ["28"]               # inside a word
    assert C.ungrounded("up 5 per cent", "up 5%") == []
    assert C.ungrounded("P/B 1.3x", "P/B 1.3") == []                        # x is no unit
    assert C.ungrounded("no figures here", "") == []


# -- A case holds only the bundle's figures ------------------------------------------------

def test_a_case_from_the_fixture_bundle_holds_only_its_figures(tmp_path):
    """The stub's answer keeps every rule, so the model's case is stored. By hand: entry
    ₹212.00; the idea's level ₹200.00, with NSE's list reaching back past the dive and no
    bonus or split, so ₹200.00 on the buy day; the window with ATR 2% and a stop of 8%:
    stop 212 × 0.92 = ₹195.04, noise line 212 × (1 − 1.5 × 2%) = ₹205.64, and 195.04 <
    200 ≤ 205.64, so the price is used. The target ₹255 is the analysis's, in months 3 × 3."""
    store, case, why = _write(tmp_path)
    assert why == "" and case.author == "model" and case.fallback_reason == ""
    assert (case.symbol, case.opened_on, case.entry_price, case.version) == (SYM, "2026-10-23",
                                                                            212.0, 1)
    assert case.written == "at_purchase" and case.buy_path == "deploy"
    assert (case.invalidation.price, case.invalidation.stop_price,
            case.invalidation.noise_line) == (200.0, 195.04, 205.64)
    assert (case.expectation.target, case.expectation.horizon_months) == (255.0, 9)
    bundle = _bundle()
    everything = bundle.all_text() + f"\nStock: {SYM}. Bought on 2026-10-23."
    for text in _texts(case):
        assert C.ungrounded(text, everything) == [], text
    for pillar in case.pillars:
        for ev in pillar.evidence:
            assert C.ungrounded(ev.fact, bundle.text(ev.ref)) == [], ev
            assert (ev.source, ev.date) == (bundle.input(ev.ref).kind,
                                            bundle.input(ev.ref).known_at[:10])
    assert store.versions(SYM) == [case]


@pytest.mark.parametrize("answer, why", [
    (_answer(one_line="A bank growing loans 21% a year."), "the one-line case has a figure "
                                                          "no input has: 21%"),
    (_answer(expectation="Loan growth near 18.0% should continue, about 18.40%."), ""),
    (_answer(expectation="Revenue of ₹1,200 should grow."), "the expectation has a figure no "
                                                           "input has: 1,200"),
    (_answer(pillars=[{"claim": "Cheap", "evidence": [{"fact": "Revenue Rs 1,200 Cr",
                                                       "ref": "A1"}]}]),
     "pillar 1's fact from A1 has a figure A1 does not: 1,200 Cr"),
    (_answer(pillars=[{"claim": "Growth", "evidence": [{"fact": "loans +18%", "ref": "Z9"}]}]),
     "pillar 1 cites Z9, which is not an input"),
    (_answer(pillars=[{"claim": "Growth", "evidence": []}]), "pillar 1 cites no evidence"),
    (_answer(pillars=[{"claim": "Growth", "evidence": [{"fact": "+18%", "ref": "A1"}],
                       "watch_categories": ["weather"]}]),
     "pillar 1 watches a category that does not exist"),
    (_answer(pillars=[VALID["pillars"][0]] * 5), "it gave 5 pillars"),
    ("{not json", "the answer is not JSON"),
    ("[]", "the answer is not a JSON object"),
])
def test_an_answer_that_breaks_a_rule_is_never_stored(tmp_path, answer, why):
    """Each stub breaks one rule (or, the second, keeps them: 18.0% is 18%, and 18.40% is
    18.4%, the same figures). A broken answer leaves the deterministic case, which names the
    rule, and only figures of the bundle."""
    store, case, got = _write(tmp_path, answer=answer)
    assert got == "" and case is not None
    if not why:
        assert case.author == "model"
        return
    assert (case.author, case.fallback_reason) == ("deterministic", why)
    # The deterministic case copies the inputs word for word.
    assert case.pillars[0].claim == "Loan growth with steady asset quality."
    assert case.one_line == case.pillars[0].claim
    assert case.invalidation.business == ["GNPA above 2.5% at Q3 results"]
    bundle = _bundle()
    for text in _texts(case):
        assert C.ungrounded(text, bundle.all_text()) == [], text
    for p in case.pillars:
        for ev in p.evidence:
            assert C.ungrounded(ev.fact, bundle.text(ev.ref)) == [], ev
    assert len(store.versions(SYM)) == 1


def test_a_failed_call_and_the_model_switched_off_store_the_deterministic_case(tmp_path,
                                                                                monkeypatch):
    def boom(system, user):
        raise TimeoutError("slow")
    _s, case, _w = _write(tmp_path / "a", model=boom)
    assert (case.author, case.fallback_reason) == ("deterministic",
                                                   "the model call failed: TimeoutError")
    monkeypatch.setattr(settings, "ADVISOR_CASE_MODEL", False)
    monkeypatch.setattr(C, "_call_model", lambda s, u: pytest.fail("no call when it is off"))
    _s, case, _w = _write(tmp_path / "b", model=None)
    assert (case.author, case.fallback_reason) == ("deterministic",
                                                   "the model is off (advisor.case_model)")


def test_the_fallback_stays_honest_without_a_thesis(tmp_path):
    """An idea with no thesis: the pillar says none was written and cites the deep dive's
    conviction and verdict; it borrows no words. With no idea and no analysis, no case."""
    bundle = _bundle(ideas=[_idea(thesis="")], records=[])
    _s, case, _w = _write(tmp_path / "a", answer="{}", bundle=bundle)
    assert case.author == "deterministic"
    assert case.pillars[0].claim == ("No thesis was written; bought on its deep dive's "
                                     "conviction and verdict.")
    assert case.pillars[0].evidence[0].fact == ("deep dive of 2026-10-17: conviction 0.74, "
                                                "verdict BUY")
    assert case.invalidation.business == []
    store, case, why = _write(tmp_path / "b", bundle=_bundle(ideas=[], records=[]))
    assert case is None and why == "no analysis or shelf idea before the buy to build a case from"
    assert store.versions(SYM) == []


# -- Issue time ----------------------------------------------------------------------------

def test_no_input_known_at_or_after_the_case_is_in_its_bundle():
    """The analysis run at 16:30 IST on the buy day, the event filed at 16:10, the guidance
    of 24 Oct and a re-dive of 24 Oct all come after the buy session's close."""
    later_idea = _idea(level=150.0, dived="2026-10-24")
    b = _bundle(ideas=[_idea(), later_idea])
    assert [i.ref for i, _ in b.items] == ["A1", "F1", "S1", "D1", "E1"]
    assert "A later view" not in b.all_text() and "300" not in b.all_text()
    assert "provisions rose 40%" not in b.all_text() and "Guidance cut" not in b.all_text()
    assert "invalidation level: 200.0" in b.text("S1")
    assert all(datetime.fromisoformat(i.known_at) < AS_OF for i, _ in b.items)
    # The undated parts of a dossier updated on the buy day are not inputs.
    assert "recurring" not in " ".join(i.label for i, _ in b.items)


def test_issue_time_holds_for_any_publication_time():
    """Property: an event is an input exactly when it was published before `as_of` (and
    within the look-back); the stored case's every cited date is on or before its day."""
    rng = random.Random(5)
    for minutes in [0, -1, 1] + [rng.randint(-60 * 24 * 70, 60 * 24 * 3) for _ in range(200)]:
        at = AS_OF + timedelta(minutes=minutes)
        b = _bundle(events=[_event(at.isoformat())], records=[], dossier=None)
        has = any(i.kind == "event" for i, _ in b.items)
        within = at.date().toordinal() >= AS_OF.date().toordinal() - C.EVENT_LOOKBACK_DAYS
        assert has == (at < AS_OF and within), at


# -- The invalidation price ----------------------------------------------------------------

@pytest.mark.parametrize("level, used, side", [
    (470.0, True, ""), (485.0, True, ""),
    (455.0, False, "at or below the stop price 460.00"),
    (460.0, False, "at or below the stop price 460.00"),
    (490.0, False, "above the noise line 485.00"),
    (485.01, False, "above the noise line 485.00"),
])
def test_the_window_of_the_card_example(level, used, side):
    """Entry ₹500, ATR 2%, a stop of 8%: stop ₹460, noise line 500 × (1 − 1.5 × 2%) = ₹485.
    ₹470 is used; ₹455 (below the stop) and ₹490 (noise) are not, and the gap says which
    side; the edges: ₹460 is not above the stop, ₹485 is 1.5 ATR below the entry."""
    inv = C.purchase_invalidation(SYM, _idea(level=level), BUY, 500.0,
                                  action_record([DIVIDEND_AUG], SYM), 2.0, 8.0)
    assert (inv.price is not None) == used
    assert (inv.stop_price, inv.noise_line) == (460.0, 485.0)
    if used:
        assert inv.price == level and inv.gap == ""
    else:
        assert inv.price is None and side in inv.gap


def test_an_unknown_atr_or_no_level_leaves_no_price():
    inv = C.purchase_invalidation(SYM, _idea(), BUY, ENTRY, action_record([DIVIDEND_AUG], SYM),
                                  0.0, 0.0)
    assert inv.price is None and "the ATR on the purchase day is unknown" in inv.gap
    assert C.purchase_invalidation(SYM, None, BUY, ENTRY, None, 2.0, 8.0).gap == \
        "no shelf idea before the buy"
    assert C.purchase_invalidation(SYM, _idea(level=0.0), BUY, ENTRY, None, 2.0, 8.0).gap == \
        "the shelf idea set no invalidation level"


def _nse(*rows):
    return action_record([DIVIDEND_AUG, *rows], SYM)


@pytest.mark.parametrize("subject, kind", [
    ("Demerger", "demerger"), ("Capital Reduction", "capital reduction"),
    ("Rights 1:15 @ Premium Rs 1247", "rights issue")])
def test_rr_l1_a_basis_change_between_the_dive_and_the_buy_leaves_no_price(subject, kind):
    """Dived 17 Oct at the level ₹200 (the card's ₹455 for ₹500, at this fixture's scale).
    A row that changes the basis with no ratio, ex 20 Oct, between the dive and the buy:
    no price, the kind named. Its neighbour one day outside, ex 16 Oct (the dive's close
    already after it), leaves the price."""
    inside = C.purchase_invalidation(SYM, _idea(), BUY, ENTRY,
                                     _nse({"subject": subject, "exDate": "20-Oct-2026"}),
                                     2.0, 8.0)
    assert inside.price is None
    assert inside.gap == (f"level 200.00 not used: a {kind} went ex on 2026-10-20, from the "
                          "dive day on, and gives no ratio, so the price basis is unknown")
    before = C.purchase_invalidation(SYM, _idea(), BUY, ENTRY,
                                     _nse({"subject": subject, "exDate": "16-Oct-2026"}),
                                     2.0, 8.0)
    assert before.price == 200.0


def test_rr_l1_the_shelf_rule_refuses_the_same_rows_and_a_registry_break(monkeypatch):
    """Without a case the evidence rule reads the shelf idea's level (PR-009). A demerger
    between the dive and the buy, or after the buy, leaves it unused, so a close far below
    fires nothing; a demerger one day before the dive does not. A registry basis change
    does the same."""
    holding = Holding(symbol=SYM, sector="banking_bfsi", qty=10, avg_buy_price=ENTRY,
                      adj_avg_price=ENTRY, adj_qty=10, buy_date=BUY.isoformat())
    review = date(2026, 11, 13)
    for ex, used in (("20-Oct-2026", False), ("02-Nov-2026", False), ("16-Oct-2026", True)):
        ev = xs.exit_evidence(holding, review, ideas=[_idea()],
                              actions=_nse({"subject": "Demerger", "exDate": ex}))
        assert (ev.invalidation_level == 200.0) == used, ex
        if not used:
            assert "demerger" in ev.gaps[0] and case_broken_reasons(ev, 100.0) == []
    monkeypatch.setattr(xs, "identity_break",
                        lambda s, a, b: "price basis changed between them" if s == SYM else "")
    ev = xs.exit_evidence(holding, review, ideas=[_idea()], actions=_nse())
    assert ev.invalidation_level == 0.0
    assert ev.gaps == ["invalidation level 200.00 not used: the instrument registry says the "
                       "price basis changed between them"]


def test_a_split_before_or_on_the_buy_day_is_applied_once_at_purchase():
    """A 10→2 split (×5) ex 20 Oct, between the dive and the buy: ₹1,000 at the dive is
    ₹200 on the buy day (T1: the same ex on the buy day itself, 23 Oct, also divides). The
    case stores ₹200; on review days NSE still lists the split, and the price is not
    divided again. A 1:1 bonus the sync applies after the buy halves it once: ₹100."""
    split = lambda day: {"subject": "Face Value Split (Sub-Division) - From Rs 10/- Per "  # noqa
                                    "Share To Rs 2/- Per Share", "exDate": day}
    for day in ("20-Oct-2026", "23-Oct-2026"):
        inv = C.purchase_invalidation(SYM, _idea(level=1000.0), BUY, ENTRY, _nse(split(day)),
                                      2.0, 8.0)
        assert (inv.price, inv.price_at_dive) == (200.0, 1000.0), day
        assert "(÷5)" in inv.note
    case = SimpleNamespace(symbol=SYM, opened_on=BUY.isoformat(),
                           invalidation=SimpleNamespace(price=200.0, gap=""))
    held = Holding(symbol=SYM, sector="banking_bfsi", qty=10, avg_buy_price=ENTRY,
                   adj_avg_price=ENTRY, adj_qty=10, buy_date=BUY.isoformat())
    review = date(2026, 11, 13)
    assert C.level_after_buy(case, held, review, _nse(split("20-Oct-2026"))) == (200.0, "", "")
    held.applied_actions = [parse_action({"subject": "Bonus 1:1", "exDate": "02-Nov-2026",
                                          "symbol": SYM})]
    level, note, gap = C.level_after_buy(case, held, review, _nse(split("20-Oct-2026")))
    assert (level, gap) == (100.0, "")
    assert note == "200.00 on the buy day, adjusted for the bonus ex 2026-11-02 (÷2)"
    # A rights issue after the buy: the basis is unknown, the price is not used.
    level, _n, gap = C.level_after_buy(case, held, review,
                                       _nse({"subject": "Rights 1:15 @ Premium Rs 1247",
                                             "exDate": "04-Nov-2026"}))
    assert level == 0.0 and "rights issue went ex on 2026-11-04, after the buy" in gap


def test_the_evidence_rule_reads_the_case_and_not_the_shelf(tmp_path):
    """With a case, its price decides: ₹200 at a close of ₹199 breaks the case. A case with
    no price (its level was refused at purchase) is not replaced by the shelf's ₹200."""
    _s, case, _w = _write(tmp_path)
    held = Holding(symbol=SYM, sector="banking_bfsi", qty=10, avg_buy_price=ENTRY,
                   adj_avg_price=ENTRY, adj_qty=10, buy_date=BUY.isoformat())
    review = date(2026, 11, 13)
    ev = xs.exit_evidence(held, review, ideas=[_idea(level=150.0)], actions=_nse(), case=case)
    assert (ev.invalidation_level, ev.case_version) == (200.0, 1)
    assert ev.invalidation_source.startswith("investment case of 2026-10-23, v1, 200.00")
    assert case_broken_reasons(ev, 199.0)[0].startswith("close 199.00 at or below the "
                                                        "invalidation level 200.00")
    _s, refused, _w = _write(tmp_path / "noise", atr=5.0)    # noise line 212 × 0.925 = 196.10
    assert refused.invalidation.price is None
    ev = xs.exit_evidence(held, review, ideas=[_idea()], actions=_nse(), case=refused)
    assert ev.invalidation_level == 0.0 and case_broken_reasons(ev, 100.0) == []
    assert ev.gaps[0].startswith("invalidation price not used: the investment case has no "
                                 "invalidation price: level 200.00 not used: above the noise")


# -- Pillars --------------------------------------------------------------------------------

def _held():
    return Holding(symbol=SYM, sector="banking_bfsi", qty=10, avg_buy_price=ENTRY,
                   adj_avg_price=ENTRY, adj_qty=10, buy_date=BUY.isoformat())


def test_a_contradicting_event_challenges_its_pillar_and_a_news_one_never_sells(tmp_path):
    """Pillar 2 watches `rating`. A high negative rating downgrade in the news on 27 Oct
    challenges it, citing the event; pillar 1 (results, guidance) stays intact. The holding
    is past its minimum period and the close above the case's price: nothing sells."""
    store, case, _w = _write(tmp_path)
    news = _event("2026-10-27T09:00:00+05:30", category="rating", direction="negative",
                  source="news", what="A broker cut its rating to sell.", n=7)
    review = date(2026, 11, 13)
    nxt = C.review_pillars(store, _held(), [news], review)
    assert nxt.version == 2 and [p.status for p in nxt.pillars] == ["intact", "challenged"]
    challenge = nxt.pillars[1].challenges[0]
    assert (challenge.event_id, challenge.source, challenge.category) == (news.id, "news",
                                                                          "rating")
    assert store.versions(SYM)[0] == case           # version 1 never edited
    ev = xs.exit_evidence(_held(), review, events=[news], ideas=[_idea()], actions=_nse(),
                          case=store.latest(SYM, BUY.isoformat()))
    assert ev.challenged_pillars == [{"claim": "Valuation below its own history",
                                      "by": [news.id], "sources": ["news"]}]
    assert ev.sessions_held >= settings.ADVISOR_MIN_HOLD_SESSIONS
    assert case_broken_reasons(ev, 205.0) == []
    # Read once: the same event again writes nothing.
    assert C.review_pillars(store, _held(), [news], review) is None


def test_results_recheck_every_pillar(tmp_path):
    """Positive results re-check each pillar (the day is recorded, nothing challenged);
    negative results challenge all of them. A `deal` event no pillar watches, an event
    before the case and one after the review's close change nothing."""
    store, _case, _w = _write(tmp_path)
    review = date(2026, 11, 13)
    quiet = [_event("2026-10-28T10:00:00+05:30", category="deal", direction="negative", n=3),
             _event("2026-10-22T10:00:00+05:30", direction="negative", n=4),
             _event("2026-11-13T16:00:00+05:30", direction="negative", n=5)]
    nxt = C.review_pillars(store, _held(), quiet, review)
    assert nxt.version == 2 and all(p.status == "intact" for p in nxt.pillars)
    good = _event("2026-11-02T18:00:00+05:30", n=6)
    nxt = C.review_pillars(store, _held(), [good], review)
    assert [p.last_checked for p in nxt.pillars] == ["2026-11-13"] * 2
    assert all(p.status == "intact" for p in nxt.pillars)
    bad = _event("2026-11-10T18:00:00+05:30", direction="negative", n=8,
                 what="Q2 profit fell 30%.")
    nxt = C.review_pillars(store, _held(), [bad], review)
    assert all(p.status == "challenged" and p.challenges[-1].event_id == bad.id
               for p in nxt.pillars)
    assert [c.version for c in store.versions(SYM)] == [1, 2, 3, 4]


# -- The buy paths ------------------------------------------------------------------------

def _history(symbol):
    """60 sessions to the buy day with a true range of 2% of a ₹212 close (ATR 2%), then
    two later days with a 20% range that a case must not read."""
    days = pd.bdate_range(end=pd.Timestamp(BUY), periods=60)
    later = pd.bdate_range(start=pd.Timestamp(BUY) + pd.Timedelta(days=1), periods=2)
    rows = [(212 * 1.01, 212 * 0.99, 212.0)] * 60 + [(250.0, 200.0, 212.0)] * 2
    return pd.DataFrame(rows, columns=["High", "Low", "Close"], index=days.append(later))


@pytest.fixture
def buying(monkeypatch):
    """Case writing on, with the fixture's inputs: the bundle from RECORDS, EVENTS and
    the dossier (the ideas the buy path passes), NSE's list with one dividend, the price
    history above, and a stub model answering VALID."""
    monkeypatch.setattr(settings, "ADVISOR_CASE_WRITE", True)
    monkeypatch.setattr(settings, "ADVISOR_CASE_MODEL", True)
    model = _model(_answer())
    monkeypatch.setattr(C, "_call_model", model)
    monkeypatch.setattr(C, "_corp_record", lambda s: action_record([DIVIDEND_AUG], s))
    monkeypatch.setattr(C, "_price_history", _history)
    monkeypatch.setattr(C, "read_inputs", lambda s, as_of, ideas=(), sector="": C.build_bundle(
        s, as_of, records=RECORDS, ideas=ideas, dossier=_dossier(), events=EVENTS))
    monkeypatch.setattr(C, "_now", lambda: NOW)
    return model


def test_the_purchase_stop_reads_the_history_up_to_the_buy_day():
    """ATR 2% (the two wide later days are not read); the pipeline's bucket is mid
    (no market cap), so the stop is clamp(3 × 2%, 12%, 18%) = 12%."""
    assert C.purchase_stop(SYM, BUY, "balanced", _history) == (2.0, 12.0)


def _portfolio_store(tmp_path, holdings=(), cash=500_000.0):
    from core.portfolio.store import PortfolioStore
    s = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "pf"))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = list(holdings), cash, cash, True
    s.save(p)
    return s


def test_a_switch_buy_writes_one_case_and_a_rerun_writes_none(tmp_path, monkeypatch, buying):
    """TATAMOTORS is switched into ABCBANK at ₹212 on the buy day. The case is version 1,
    at purchase, from the inputs before 15:30 (the 16:30 analysis is not read: the target is
    ₹255, not ₹300). Stop 12% (₹186.56) and noise line ₹205.64 hold ₹200. The same review
    day again trades nothing and writes nothing; so does the writer called again."""
    from core.portfolio import autopilot as ap
    from core.portfolio.pricing import SessionClose
    monkeypatch.setattr(ap, "_today_ist", lambda: BUY)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(ap, "session_close", lambda s, d: (SessionClose(ENTRY, d, "agree"), d))
    old = Holding(symbol="TATAMOTORS", sector="automobile", qty=1000, avg_buy_price=100.0,
                  adj_avg_price=100.0, adj_qty=1000, buy_date="2026-06-01")
    store = _portfolio_store(tmp_path, [old], cash=20_000.0)
    switch = AdviceRecord(date=BUY.isoformat(), user_id="u1", symbol="TATAMOTORS",
                          verdict="SWITCH", close=110.0, unrealised_pnl_pct=10.0, stop_pct=8.0,
                          confidence=0.4, switch_candidate=SYM, triggers=["switch"],
                          rationale_hash="h1")
    report: dict = {}
    txns = ap.execute_advice(store, store.load(), [switch], {"TATAMOTORS": 110.0}, BUY,
                             sector_lookup={SYM: "banking_bfsi"}, shelf_index={SYM: _idea()},
                             report=report)
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "TATAMOTORS"), ("BUY", SYM)]
    assert report["cases"] == [{"symbol": SYM, "written": True, "author": "model", "why": ""}]
    cases = C.CaseStore("u1", str(tmp_path / "pf"))
    (case,) = cases.versions(SYM)
    assert (case.version, case.buy_path, case.written, case.entry_price) == (1, "switch",
                                                                             "at_purchase", 212.0)
    assert case.as_of == "2026-10-23T15:30:00+05:30" and case.expectation.target == 255.0
    assert (case.invalidation.price, case.invalidation.stop_price) == (200.0, 186.56)
    assert len(buying.calls) == 1
    assert ap.execute_advice(store, store.load(), [switch], {"TATAMOTORS": 110.0}, BUY,
                             shelf_index={SYM: _idea()}) == []
    assert C.write_for_trades("u1", store.load(), txns, BUY, ideas=[_idea()],
                              base_dir=str(tmp_path / "pf")) == [
        {"symbol": SYM, "written": False, "author": "",
         "why": "a case of this holding exists already"}]
    assert len(cases.versions(SYM)) == 1 and len(buying.calls) == 1


def test_a_deployment_buy_writes_one_case(tmp_path, monkeypatch, buying):
    """Idle-cash deployment opens ABCBANK on the buy day: one version 1 case, `deploy`."""
    from core.portfolio import autopilot as ap
    from core.portfolio import deployment
    from core.portfolio.pricing import SessionClose
    for name, value in {"AUTOPILOT_ENABLED": True, "AUTOPILOT_DEPLOY_IDLE_CASH": True,
                        "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY": 2, "PORTFOLIO_OVERRIDES": {},
                        "DECISION_GATE_MODE": "record"}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(ap, "_today_ist", lambda: BUY)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(ap, "session_close", lambda s, d: (SessionClose(ENTRY, d, "agree"), d))
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: "NORMAL")
    store = _portfolio_store(tmp_path, cash=1_000_000.0)
    report: dict = {}
    idea = _idea()
    idea.sector_reading = None
    from backend.shared.schemas.discovery import SectorReading
    idea.sector_reading = SectorReading(answer="banking_bfsi", reason="stub")
    txns = ap.execute_advice(store, store.load(), [], {}, BUY, shelf_index={SYM: idea},
                             sector_lookup={SYM: "banking_bfsi"}, report=report)
    assert [(t.side, t.symbol, t.verdict) for t in txns] == [("BUY", SYM, "DEPLOY")]
    (case,) = C.CaseStore("u1", str(tmp_path / "pf")).versions(SYM)
    assert (case.version, case.buy_path, case.written) == (1, "deploy", "at_purchase")


def test_an_add_or_a_buy_into_an_older_holding_writes_no_case(tmp_path, buying):
    """Only a buy that opened a position on the review day: an ADD, or a SWITCH into a
    stock already held since June, writes none; nor does a SELL."""
    from backend.shared.schemas.portfolio import Portfolio, TransactionRecord
    older = Holding(symbol=SYM, sector="banking_bfsi", qty=10, avg_buy_price=ENTRY,
                    adj_avg_price=ENTRY, adj_qty=10, buy_date="2026-06-01")
    p = Portfolio(user_id="u1", holdings=[older])
    txns = [TransactionRecord(txn_id=f"t{n}", date=BUY.isoformat(), ts="", user_id="u1",
                              symbol=SYM, side=side, qty=1, price=ENTRY, value=ENTRY,
                              cash_before=0, cash_after=0, holding_qty_after=11,
                              source="autopilot", verdict=verdict)
            for n, (side, verdict) in enumerate((("BUY", "ADD"), ("BUY", "SWITCH"),
                                                 ("SELL", "EXIT")))]
    assert C.write_for_trades("u1", p, txns, BUY, base_dir=str(tmp_path)) == []
    assert C.CaseStore("u1", str(tmp_path)).versions(SYM) == []


def _client(tmp_path, monkeypatch, user="u1"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import services.api.routes.portfolio_api as papi
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "close_on", lambda s, d: ENTRY)
    monkeypatch.setattr(papi, "_resolve_sector", lambda s, sec: "banking_bfsi")
    app = FastAPI()
    app.include_router(papi.router)
    app.dependency_overrides[papi.get_current_user] = lambda: {"user_id": user, "role": "user"}
    return TestClient(app)


def test_a_manual_add_writes_one_case_and_a_member_reads_only_their_own(tmp_path, monkeypatch,
                                                                        buying):
    """u1 adds ABCBANK bought today (23 Oct, at ₹212): one version 1 case, `manual`, at
    purchase. The same add again (a client retry) writes none, nor a second add of the
    held stock. u2 reads no case; u1 reads its one, and every version by symbol."""
    from core.discovery import shelf
    monkeypatch.setattr(shelf.ShelfStore, "load",
                        lambda self: SimpleNamespace(ideas=[_idea()]))
    c1 = _client(tmp_path, monkeypatch, "u1")
    body = {"symbol": SYM, "qty": 10, "buy_date": BUY.isoformat()}
    assert c1.post("/portfolio/holdings", json=body).status_code == 200
    assert c1.post("/portfolio/holdings", json=body).status_code == 200
    assert c1.post("/portfolio/holdings", json=dict(body, qty=5)).status_code == 200
    got = c1.get("/portfolio/cases").json()
    assert got["count"] == 1
    (case,) = got["cases"]
    assert (case["symbol"], case["version"], case["buy_path"], case["written"],
            case["user_id"]) == (SYM, 1, "manual", "at_purchase", "u1")
    assert c1.get(f"/portfolio/cases?symbol={SYM}").json()["count"] == 1
    assert c1.get("/portfolio/cases?symbol=../u2").status_code == 422
    c2 = _client(tmp_path, monkeypatch, "u2")
    assert c2.get("/portfolio/cases").json() == {"cases": [], "count": 0}
    assert c2.get(f"/portfolio/cases?symbol={SYM}").json() == {"cases": [], "count": 0}


def test_a_manual_add_without_an_analysis_or_idea_writes_none(tmp_path, monkeypatch, buying):
    from core.discovery import shelf
    monkeypatch.setattr(shelf.ShelfStore, "load", lambda self: SimpleNamespace(ideas=[]))
    monkeypatch.setattr(C, "read_inputs", lambda s, as_of, ideas=(), sector="": C.build_bundle(
        s, as_of, records=[], ideas=ideas, dossier=None, events=[]))
    c1 = _client(tmp_path, monkeypatch)
    assert c1.post("/portfolio/holdings", json={"symbol": SYM, "qty": 10,
                                                "buy_date": BUY.isoformat()}).status_code == 200
    assert c1.get("/portfolio/cases").json()["count"] == 0
    assert buying.calls == []


# -- Backfill ---------------------------------------------------------------------------------

def test_a_backfilled_case_is_after_purchase(tmp_path, buying):
    """A holding bought on 23 Oct, backfilled on the 16:45 of that day or any later day,
    is `after_purchase`; the dry run writes nothing, and a second run writes nothing."""
    from backend.shared.schemas.portfolio import Portfolio
    p = Portfolio(user_id="u1", holdings=[_held()])
    assert C.backfill("u1", p, ideas=[_idea()], base_dir=str(tmp_path)) == [
        {"symbol": SYM, "opened_on": "2026-10-23", "action": "would write"}]
    assert C.CaseStore("u1", str(tmp_path)).versions(SYM) == []
    rows = C.backfill("u1", p, ideas=[_idea()], apply=True, base_dir=str(tmp_path))
    assert rows == [{"symbol": SYM, "opened_on": "2026-10-23", "action": "written (model)"}]
    (case,) = C.CaseStore("u1", str(tmp_path)).versions(SYM)
    assert (case.written, case.buy_path) == ("after_purchase", "backfill")
    assert C.backfill("u1", p, ideas=[_idea()], apply=True, base_dir=str(tmp_path))[0][
        "action"] == "has a case"


def test_a_late_buy_path_case_is_after_purchase(tmp_path):
    """A case a buy path writes on a later day than the buy (a catch-up run) is not
    labelled at purchase."""
    _s, case, _w = _write(tmp_path, now=datetime(2026, 10, 26, 9, 0, tzinfo=IST))
    assert case.written == "after_purchase"


def test_case_writing_off_writes_nothing(tmp_path, monkeypatch, buying):
    monkeypatch.setattr(settings, "ADVISOR_CASE_WRITE", False)
    assert C.write_for_buy("u1", symbol=SYM, opened_on=BUY, entry_price=ENTRY,
                           buy_path="deploy", base_dir=str(tmp_path)) == (
        None, "case writing is off (advisor.case_write)")
    assert buying.calls == []


def test_the_store_appends_each_version_once_and_never_edits(tmp_path):
    """Two runs racing past the writers' own check: the store takes version 1 once, and a
    version 3 before a version 2 not at all. The file only grows."""
    store, case, _w = _write(tmp_path)
    path = tmp_path / "u1" / "cases" / f"{SYM}.jsonl"
    first = path.read_bytes()
    assert store.append(case) is False
    assert store.append(case.model_copy(update={"version": 3})) is False
    assert store.append(case.model_copy(update={"version": 2, "change": "x"})) is True
    assert path.read_bytes().startswith(first)
    assert [c.version for c in store.versions(SYM)] == [1, 2]
    with pytest.raises(ValueError):
        store.versions("../u2/cases/X")
