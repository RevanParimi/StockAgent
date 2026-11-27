"""PR-007: plain, fact-grounded buy and sell explanations.

Every expected figure is worked by hand from each fixture's own numbers, never
asked of the code under test. The invariants:

- one fixture per verdict (EXIT by the stop, by the trailing stop and by the
  broken case; TRIM; ADD; SWITCH, both legs; HOLD through a fall) gives the four
  parts, each at most two sentences, and every figure in them is one of the
  fixture's own (listed by hand);
- **the "why" names the rule that actually fired, first** (the card's hard
  review): a sale by the safety limit never mentions bad news that did not
  sell it, a switch's buy never takes the sold stock's triggers as its reason,
  and a model's sentence that claims our reason is dropped;
- a model answer with an invented figure (digits or words), a banned word, a
  stop as a percentage, two sentences, our voice or no JSON is dropped whole,
  and the fallback is free of banned words; a sale and the review never ask the
  model;
- the stop is a rupee price, never a percentage;
- the banned-word list holds over every template and random trigger, note and
  fact combinations, hostile facts included;
- the routed inputs: SA-050 R4, PR-009 L2, FIX-024 L1, FIX-025 L2/L3,
  FIX-028 I-1 and FIX-031 R1;
- narration never blocks the pipeline, drafts once, and one user's words never
  reach another's.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.schemas.cases import (CaseInput, CaseEvidence, Expectation, Invalidation,
                                          InvestmentCase, Pillar)
from backend.shared.schemas.portfolio import (AdviceRecord, Holding, Portfolio, TradeCosts,
                                              TransactionRecord)
from core.config import settings
from core.portfolio import explain
from core.portfolio import plain_words as words
from core.portfolio.advisor import ExitEvidence, case_broken_reasons
from core.portfolio.cases import figures
from core.portfolio.digest import keep_day_record
from core.portfolio.explain import Context, ExplanationStore


@pytest.fixture(autouse=True)
def _caps(monkeypatch):
    for name, value in {"ADVISOR_MAX_POSITION_PCT": 10.0, "ADVISOR_MAX_SECTOR_PCT": 30.0,
                        "ADVISOR_MIN_HOLD_SESSIONS": 10, "ADVISOR_PLAIN_REASONS": True,
                        "ADVISOR_NARRATE_MODEL": "test/narrate"}.items():
        monkeypatch.setattr(settings, name, value)


# -- fixtures -------------------------------------------------------------------

def rec(verdict="EXIT", triggers=("stop_breach",), close=86.0, pnl=-14.0, stop=12.0,
        notes=(), switch_to="", symbol="XYZ", **extra):
    return AdviceRecord(date="2026-11-12", user_id="u", symbol=symbol, verdict=verdict,
                        close=close, unrealised_pnl_pct=pnl, stop_pct=stop,
                        triggers=list(triggers), notes=list(notes),
                        switch_candidate=switch_to, rationale_hash="h1", **extra)


def holding(symbol="XYZ", avg=100.0, qty=40.0, dividends=0.0, bought="2026-10-01"):
    return Holding(symbol=symbol, sector="infra", qty=qty, avg_buy_price=avg,
                   adj_avg_price=avg, adj_qty=qty, buy_date=bought,
                   dividends_received=dividends)


def sale(verdict="EXIT", triggers=("stop_breach",), qty=40.0, price=86.0, cost=100.0,
         realized=-560.0, pct=-14.0, left=0.0, note="exit_full", costs=10.0, symbol="XYZ"):
    return TransactionRecord(
        txn_id=f"sell-{symbol}", date="2026-11-12", ts="2026-11-13T11:00:00+00:00",
        user_id="u", symbol=symbol, side="SELL", qty=qty, price=price, value=qty * price,
        cash_before=0.0, cash_after=qty * price - costs, holding_qty_after=left,
        realized_pnl=realized, verdict=verdict, advice_ref="2026-11-12|XYZ|h1",
        triggers=list(triggers), note=note, cost_basis=cost, pnl_pct=pct,
        reason="The machine's own EXIT narrative with MACRO_CRISIS.",
        costs=TradeCosts(total=costs))


def buy(verdict="DEPLOY", symbol="ABC", qty=120.0, price=2500.0, note="deploy_idle_cash: x",
        triggers=("deploy_idle_cash",), ref="2026-11-12|ABC|deploy_idle_cash", held=None):
    return TransactionRecord(
        txn_id=f"buy-{symbol}", date="2026-11-12", ts="2026-11-13T11:00:00+00:00",
        user_id="u", symbol=symbol, side="BUY", qty=qty, price=price, value=qty * price,
        cash_before=1e6, cash_after=1e6 - qty * price, holding_qty_after=held or qty,
        verdict=verdict, advice_ref=ref, triggers=list(triggers), note=note,
        reason="The idea's thesis, cut at 800 char")


def case(symbol="ABC", one_line="Orders cover two years of sales.", stop=2200.0,
         level=2300.0, target=3200.0, business=("Margins fall if steel gets dearer.",)):
    return InvestmentCase(
        symbol=symbol, user_id="u", opened_on="2026-11-12", entry_price=2500.0,
        pillars=[Pillar(claim=one_line,
                        evidence=[CaseEvidence(fact="Orders of 4,000 crore", ref="A1",
                                               source="analysis", date="2026-11-07")])],
        expectation=Expectation(text="Earnings grow", target=target, horizon_months=12),
        invalidation=Invalidation(price=level, stop_price=stop, business=list(business)),
        one_line=one_line, written="at_purchase", author="model", buy_path="deploy",
        created_at="2026-11-12T16:40:00+05:30", as_of="2026-11-12T15:30:00+05:30",
        inputs=[CaseInput(ref="E1", kind="event", known_at="2026-11-05T18:10:00+05:30")])


def explained(txn, *, ctx=None, the_case=None, siblings=None, opened="2026-10-01",
              nifty=None, call=None):
    return explain.explain_trade(txn, ctx=ctx or Context(), case=the_case, bundle=None,
                                 siblings=siblings or [txn], opened=opened, nifty=nifty,
                                 call=call)


def parts_text(parts) -> str:
    return " ".join(parts[k] for k in words.PARTS)


def assert_contract(parts, allowed: set):
    """Four parts, each at most two sentences, no banned word, no stop as a
    percentage, and every figure one of `allowed` (worked by hand)."""
    assert words.check_parts(parts) == "", (words.check_parts(parts), parts)
    for key in words.PARTS:
        assert words.banned_in(parts[key]) == [], (key, parts[key])
        assert len(words.sentences(parts[key])) <= 2, (key, parts[key])
    text = parts_text(parts)
    assert not re.search(r"(?i)\d\s*%[^.]{0,20}\bstop\b|\bstop\b[^.]{0,30}\d\s*%", text), text
    strays = [(v, u, s) for v, u, s in figures(text) if (v, u) not in allowed]
    assert not strays, (strays, text)


def plain(*pairs) -> set:
    """{(value, unit)} from numbers (unit "") and "N%" strings."""
    out = set()
    for p in pairs:
        if isinstance(p, str) and p.endswith("%"):
            out.add((float(p[:-1]), "%"))
        else:
            out.add((float(p), ""))
    return out


DATES = plain(12, 2026, 1)          # "12 Nov 2026", "1 Oct 2026"


# -- one fixture per verdict ----------------------------------------------------

def test_a_sale_by_the_safety_limit():
    """40 XYZ, cost 100, sold at 86: loss (100-86)*40 = 560, 14.0%. Stop 12%:
    100 * 0.88 = 88.00. Proceeds 3,440 - 10 costs = 3,430. Nifty +3.1%."""
    txn = sale()
    ctx = Context(rec=rec(), holding=holding())
    row = explained(txn, ctx=ctx, nifty=3.1)
    p = row["parts"]
    assert p["did"] == ("We sold all 40 shares of XYZ at ₹86.00 (review of 12 Nov 2026), a "
                        "loss of ₹560 (14.0%) before costs. Between 1 Oct 2026 and 12 Nov "
                        "2026 the Nifty 50 index moved +3.1%.")
    assert p["why"] == ("We sold because the price fell to or below our safety limit of "
                        "₹88.00, the most we let a holding lose.")
    assert p["wrong_if"] == words.NO_REBUY
    assert p["next"] == ("The money of ₹3,430 goes back to cash, where a later buy that passes "
                         "our checks can use it.")
    assert_contract(p, DATES | plain(40, 86, 560, "14%", 50, "3.1%", 88, 3430))


def test_the_safety_limit_counts_the_dividends_the_sale_carried():
    """Cost 100, sold 86, 2.00 a share of dividends on 40: realised
    (86-100)*40 + 80 = -480. Stop 12% -> 88.00 - 2.00 = 86.00, the price."""
    row = explained(sale(realized=-480.0, pct=-12.0), ctx=Context(rec=rec()))
    assert "our safety limit of ₹86.00," in row["parts"]["why"]


def test_a_sale_by_the_trailing_stop_names_the_peak_and_the_line():
    """Peak 150, stop 10% -> line 135.00; sold at 130, cost 100: profit
    30*40 = 1,200, 30.0%."""
    from types import SimpleNamespace
    txn = sale(triggers=("trailing_stop_breach",), price=130.0, realized=1200.0, pct=30.0)
    ctx = Context(rec=rec(triggers=("trailing_stop_breach",), close=130.0, pnl=30.0, stop=10.0),
                  signals=SimpleNamespace(peak_close_since_entry=150.0))
    p = explained(txn, ctx=ctx)["parts"]
    assert p["why"] == ("We sold because after rising, it fell back further than we allow from "
                        "its highest price since we bought it (₹150.00), through our safety "
                        "line of ₹135.00.")
    assert_contract(p, DATES | plain(40, 130, 1200, "30%", 150, 135, 5190))


@pytest.mark.parametrize("evidence, said, allowed", [
    # an NSE results filing: the event and its date
    ({"negative_events": [{"id": "e1", "source": "nse_announcement", "category": "results",
                           "published_at": "2026-11-05T18:10:00+05:30",
                           "what": "Quarterly revenue fell 4% and the outlook was cut."}]},
     "bad news came out on 5 Nov 2026: Quarterly revenue fell 4% and the outlook was cut",
     plain(5, 2026, "4%")),
    # the research verdict and its IST day: 20:00 UTC on 4 Nov is 01:30 on 5 Nov
    ({"research_verdict": "STRONG SELL", "research_run_at": "2026-11-04T20:00:00"},
     "our latest research on it on 5 Nov 2026 rated it a strong sell", plain(5, 2026)),
    # the close and the level, in the close's own basis (a 1:1 bonus since the dive)
    ({"invalidation_level": 227.5, "invalidation_level_at_dive": 455.0},
     "it closed at ₹225.00, at or below ₹227.50, the price at which we had said the reason to "
     "own it would no longer hold (₹455.00 when we set it, before a bonus or share split)",
     plain(225, 227.5, 455)),
])
def test_a_sale_by_the_broken_case_names_which_reason_broke(evidence, said, allowed):
    """PR-009 L2: one fixture for each of the three reasons."""
    ev = ExitEvidence(sessions_held=20, **evidence).model_dump()
    close = 225.0
    txn = sale(triggers=("case_broken",), price=close, cost=250.0, realized=-1000.0, pct=-10.0)
    ctx = Context(rec=rec(triggers=("case_broken",), close=close, pnl=-10.0), evidence=ev)
    p = explained(txn, ctx=ctx)["parts"]
    assert p["why"] == f"We sold because the reason we owned it broke: {said}."
    assert_contract(p, DATES | allowed | plain(40, 225, 1000, "10%", 8990))


def test_a_news_article_never_names_itself_as_the_reason():
    """A news article cannot break the case (advisor.CASE_EVENT_SOURCES)."""
    ev = ExitEvidence(sessions_held=20, negative_events=[
        {"id": "n1", "source": "news", "published_at": "2026-11-05", "what": "Rumour of fraud"}
    ]).model_dump()
    assert words.case_broken_parts(ev, 100.0) == []


@pytest.mark.parametrize("seed", range(25))
def test_case_broken_parts_agree_with_the_rule_that_sells(seed):
    """The plain parts exist exactly when the rule's own reasons do, one each."""
    rng = random.Random(seed)
    events = [{"id": str(i), "source": rng.choice(["nse_announcement", "news", "nse_pledge"]),
               "published_at": "2026-11-05", "what": "Bad news"} for i in range(rng.randint(0, 2))]
    ev = ExitEvidence(sessions_held=20, negative_events=events,
                      research_verdict=rng.choice(["", "BUY", "SELL", "STRONG SELL"]),
                      research_run_at="2026-11-04T05:00:00",
                      invalidation_level=rng.choice([0.0, 90.0, 110.0]))
    assert len(words.case_broken_parts(ev.model_dump(), 100.0)) == \
        len(case_broken_reasons(ev, 100.0))


def test_a_trim_says_what_was_kept_and_what_would_sell_the_rest():
    """13 of 40 sold at 125, cost 100: profit 325 (25.0%), 27 kept; stop 12%
    -> 88.00; proceeds 13*125 - 10 = 1,615."""
    txn = sale(verdict="TRIM", triggers=("trim_profit_confidence_decline",), qty=13.0,
               price=125.0, realized=325.0, pct=25.0, left=27.0, note="")
    ctx = Context(rec=rec("TRIM", ("trim_profit_confidence_decline",), close=125.0, pnl=25.0))
    p = explained(txn, ctx=ctx)["parts"]
    assert p["did"].startswith("We sold 13 shares of XYZ at ₹125.00 (review of 12 Nov 2026), a "
                               "profit of ₹325 (25.0%) before costs, and kept 27 shares.")
    assert p["why"] == ("We sold part of it because it had made a good profit and we had become "
                        "less sure how much further it could rise.")
    assert p["wrong_if"] == ("We still hold the rest, and would sell it if the price falls to "
                             "our safety limit of ₹88.00 or the reason to own it breaks.")
    assert_contract(p, DATES | plain(13, 125, 325, "25%", 27, 88, 1615))


def test_an_add_names_the_forecast_and_its_record():
    """71% of the recent daily calls were right (signals 0.71)."""
    from types import SimpleNamespace
    txn = buy("ADD", "XYZ", 10.0, 110.0, "add_tranche", ("add_bullish_healthy",),
              "2026-11-12|XYZ|h1", held=50.0)
    ctx = Context(signals=SimpleNamespace(direction_accuracy_7d=0.71))
    p = explained(txn, ctx=ctx)["parts"]
    assert p["did"] == ("We bought 10 more shares of XYZ at ₹110.00 (review of 12 Nov 2026), "
                        "and now hold 50 shares.")
    assert p["why"].startswith("We bought more because our price forecast for it points up "
                               "and 71% of its recent daily calls were right.")
    assert_contract(p, DATES | plain(10, 110, 50, "71%"))


def test_a_new_position_is_told_from_its_case_with_the_stop_as_a_price():
    """120 ABC at 2,500: ₹3,00,000. The case's stop 2,200, level 2,300, target
    3,200 in 12 months."""
    p = explained(buy(), the_case=case())["parts"]
    assert p["did"] == ("We bought 120 shares of ABC at ₹2,500.00 (review of 12 Nov 2026), "
                        "about ₹3,00,000.")
    assert p["why"] == ("We bought it because its research rates it a buy, it passed our "
                        "checks, and its price was within the price range we planned to pay. "
                        "The case: Orders cover two years of sales.")
    assert p["wrong_if"] == (
        "We would sell if the price falls to the safety limit of about ₹2,200.00, or if the "
        "reason to own it breaks: bad news in the company's own filings, a fresh sell view "
        "from our research or a close at or below ₹2,300.00 (these count only once it has "
        "been held 10 trading days). A warning sign in the business: Margins fall if steel "
        "gets dearer.")
    assert p["next"] == ("We check it again after each trading day's close. The research "
                         "expects about ₹3,200.00 within about 12 months: a view, not a "
                         "promise.")
    assert_contract(p, DATES | plain(120, 2500, 300000, 2200, 10, 2300, 3200))


def test_a_purchase_below_the_range_says_it_was_cheaper_than_planned():
    txn = buy(note="deploy_idle_cash: x; 3.0% below entry band (₹2,600–₹2,700): cheaper")
    assert "below the price range we planned to pay, so cheaper than planned" in \
        explained(txn)["parts"]["why"]


def _switch(note="exit_full"):
    sell = sale(verdict="SWITCH", triggers=("stop_breach", "switch_candidate_available"),
                note=note)
    leg = buy("SWITCH", "DEF", 10.0, 340.0, "switch from XYZ",
              ("stop_breach", "switch_candidate_available"), "2026-11-12|XYZ|h1")
    ctx = Context(rec=rec("SWITCH", ("stop_breach", "switch_candidate_available"),
                          switch_to="DEF"))
    return sell, leg, ctx


def test_a_switch_sale_says_where_the_money_went():
    sell, leg, ctx = _switch()
    p = explained(sell, ctx=ctx, siblings=[sell, leg])["parts"]
    assert p["why"] == ("We sold because the price fell to or below our safety limit of "
                        "₹88.00, the most we let a holding lose.")
    # 10 DEF at 340 took 3,400 of the 3,430; whole shares leave 30.
    assert p["next"] == ("We used ₹3,400 of the money to buy DEF; the other ₹30 stays in "
                         "cash.")
    assert_contract(p, DATES | plain(40, 86, 560, "14%", 88, 3400, 30))


def test_a_switch_buy_never_takes_the_sold_stocks_triggers_as_its_reason():
    """The buy leg's ledger row carries XYZ's stop_breach: DEF was not bought
    because anything fell to a limit."""
    sell, leg, ctx = _switch()
    p = explained(leg, ctx=ctx, siblings=[sell, leg])["parts"]
    assert p["why"] == ("We bought it to replace XYZ, which we sold the same day: it rated "
                        "more strongly and sits in a part of the market where we held less.")
    assert "safety limit" not in p["why"]


def test_a_skipped_switch_buy_says_why_in_plain_words():
    note = ("exit_full; buy leg skipped: DEF: 5.2% above entry band (₹400–₹420); needs a "
            "fresh deep dive; ₹3,430 stays in cash")
    sell, _leg, ctx = _switch(note)
    p = explained(sell, ctx=ctx, siblings=[sell])["parts"]
    assert p["next"] == ("We meant to move the money into DEF but did not: its price was "
                         "above the range we planned to pay. The money of ₹3,430 stays in "
                         "cash.")


def test_a_hold_through_a_fall_names_what_has_not_happened():
    """Cost 100, close 94: down 6.0%; stop 12% -> 88.00; no rule fired."""
    digest = {"holdings": [{"symbol": "XYZ", "verdict": "HOLD", "pnl_pct": -6.0, "notes": []}]}
    ctx = {"XYZ": Context(rec=rec("HOLD", (), close=94.0, pnl=-6.0), holding=holding())}
    explain.plain_rows(digest, ctx, Portfolio(user_id="u", cash_deployable=1000.0,
                                              autopilot=True), "evidence")
    p = digest["holdings"][0]["plain"]
    assert p["why"] == ("It is down 6.0% on what was paid; none of our selling rules has been "
                        "met, and it is above the safety limit of about ₹88.00.")
    assert_contract({k: p[k] for k in words.PARTS}, plain("6%", 88, 10))


def test_a_hold_while_the_broken_reason_waits_says_so():
    """Held 4 sessions: the case broke but the rule waits for 10."""
    ev = ExitEvidence(sessions_held=4, research_verdict="SELL",
                      research_run_at="2026-11-10T05:00:00").model_dump()
    digest = {"holdings": [{"symbol": "XYZ", "verdict": "HOLD", "pnl_pct": -6.0, "notes": []}]}
    explain.plain_rows(digest, {"XYZ": Context(rec=rec("HOLD", (), close=94.0, pnl=-6.0),
                                               holding=holding(), evidence=ev)},
                       Portfolio(user_id="u", cash_deployable=1.0), "evidence")
    why = digest["holdings"][0]["plain"]["why"]
    assert why == ("It is down 6.0% on what was paid; a reason to doubt it has appeared (our "
                   "latest research on it on 10 Nov 2026 rated it a sell), but such reasons "
                   "count only once it has been held 10 trading days.")


# -- the card's hard review -----------------------------------------------------

def test_a_sale_by_the_limit_never_cites_the_news_that_did_not_sell_it():
    """An NSE results miss is on the record, but the rule that fired is the
    stop (the case rule waited): the why must not mention the miss."""
    ev = ExitEvidence(sessions_held=3, negative_events=[
        {"id": "e1", "source": "nse_announcement", "published_at": "2026-11-11",
         "what": "Results missed badly."}]).model_dump()
    p = explained(sale(), ctx=Context(rec=rec(), evidence=ev))["parts"]
    assert "Results missed" not in parts_text(p)
    assert p["why"].startswith("We sold because the price fell to or below our safety limit")


def test_the_why_names_every_rule_that_fired_before_any_context():
    ev = ExitEvidence(sessions_held=20, research_verdict="SELL",
                      research_run_at="2026-11-04T05:00:00").model_dump()
    txn = sale(triggers=("stop_breach", "case_broken", "shock_reforecast"))
    ctx = Context(rec=rec(triggers=("stop_breach", "case_broken", "shock_reforecast")),
                  evidence=ev)
    why = explained(txn, ctx=ctx, the_case=case("XYZ"))["parts"]["why"]
    first = words.sentences(why)[0]
    assert "safety limit" in first and "reason we owned it broke" in first \
        and "sudden shock" in first
    assert words.sentences(why)[1] == "When we bought it, the case was: Orders cover two " \
                                      "years of sales."


def test_an_unknown_trigger_is_never_shown_as_its_code():
    why = explained(sale(triggers=("brand_new_rule",)),
                    ctx=Context(rec=rec(triggers=("brand_new_rule",))))["parts"]["why"]
    assert why == "We sold because one of our selling rules was met."


# -- the model's sentence --------------------------------------------------------

def answer(reason="The company has orders for two years of work.",
           risk="Margins could shrink if steel gets dearer."):
    return lambda system, user: json.dumps({"reason": reason, "risk": risk})


def test_a_checked_answer_adds_one_sentence_after_the_rule():
    row = explained(buy(), the_case=case(), call=answer())
    assert row["source"] == "model" and row["model"] == "test/narrate"
    assert row["parts"]["why"].endswith("The case: The company has orders for two years of work.")
    assert row["parts"]["wrong_if"].endswith(
        "A warning sign in the business: Margins could shrink if steel gets dearer.")
    assert row["case_version"] == 1 and row["event_refs"] == ["E1"]


@pytest.mark.parametrize("reason, why_not", [
    ("Sales will grow 40% next year.", "has a figure no input has: 40%"),
    ("Orders worth 4,000 rupees lakh are booked.", "has a figure no input has"),
    ("The agent likes its order book.", "banned word: agent"),
    ("The ATR is low for its sector.", "banned word: ATR"),
    ("It suits a NORMAL regime.", "banned word"),
    ("Its stop sits 12% below.", "stop as a percentage"),
    ("It has strong orders. It also grows.", "more than one sentence"),
    ("Orders cover three years of sales.", "has a figure no input has: three"),
    ("Its sales have doubled.", "has a figure no input has: doubled"),
    ("It grew fivefold.", "has a figure no input has: fivefold"),
    ("We sold because results fell.", "speaks of our action"),
    ("Our research likes its order book.", "speaks of our action"),
    ("", "is missing"),
])
def test_a_rule_breaking_answer_is_dropped_whole(reason, why_not):
    row = explained(buy(), the_case=case(), call=answer(reason=reason))
    assert row["source"] == "template"
    assert why_not in row["fallback_reason"], row["fallback_reason"]
    text = parts_text(row["parts"])
    assert reason == "" or reason not in text
    assert "Margins could shrink" not in text        # the good half is dropped with the bad
    assert words.banned_in(text) == []
    assert row["parts"]["why"].endswith("The case: Orders cover two years of sales.")


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", "{\"reason\": 7}"])
def test_an_unreadable_answer_falls_back(raw):
    row = explained(buy(), the_case=case(), call=lambda s, u: raw)
    assert row["source"] == "template"
    assert words.banned_in(parts_text(row["parts"])) == []


def test_a_model_that_cannot_be_reached_falls_back():
    def down(system, user):
        raise TimeoutError("provider did not answer")
    row = explained(buy(), the_case=case(), call=down)
    assert row["source"] == "template" and "model call failed" in row["fallback_reason"]


def test_the_model_is_told_only_company_facts_never_the_trade():
    """No price paid, quantity or stop reaches the model, so no position can
    reach another user through it."""
    seen = {}

    def capture(system, user):
        seen["prompt"] = system + user
        return "{}"
    explained(buy(price=2467.35, qty=137.0), the_case=case(stop=2211.0, level=2305.0),
              call=capture)
    for secret in ("2467", "2,467", "137", "338", "2211", "2,211", "2305", "ABC|", "u|"):
        assert secret not in seen["prompt"], (secret, seen["prompt"])
    assert "Orders cover two years of sales." in seen["prompt"]


def test_a_sale_never_asks_the_model_and_quotes_the_record():
    """The card's hard review: a model could write a cause for a sale ("sold
    because results missed"), so a sale makes no call at all."""
    def never(system, user):
        raise AssertionError("a sale asked the model")
    row = explained(sale(), ctx=Context(rec=rec()), the_case=case("XYZ"), call=never)
    assert row["source"] == "template" and row["model"] == ""
    assert words.sentences(row["parts"]["why"])[1] == \
        "When we bought it, the case was: Orders cover two years of sales."


def test_without_company_facts_no_call_is_made():
    calls = []
    row = explained(buy(), call=lambda s, u: calls.append(1) or "{}")
    assert calls == [] and row["fallback_reason"] == "no company facts recorded"


@pytest.mark.parametrize("sentence", [
    "It sells most of its output to the US market.",
    "A new tax regime lowers its costs.",
    "Its largest buyer is Tata Motors Pvt. Ltd. and its associates.",
    "It is one of the larger makers in its field.",
    "Orders cover two years of sales.",
])
def test_plain_business_english_is_not_thrown_away(sentence):
    facts = "In one line: Orders cover two years of sales.\nReason: Tata Motors buys from it."
    assert words.check_company_sentence(sentence, facts, "reason") == "", sentence


def test_the_skip_reasons_are_read_from_the_producers_own_words():
    """Each string below is built by the code that refuses the buy, then put
    in the SWITCH note as the executor writes it, behind a symbol that must
    not be read as a reason (ASMTEC is not an ASM measure)."""
    from types import SimpleNamespace
    from core.discovery.shelf import (close_before_decision, other_company, resale_wait,
                                      verdict_wait)
    from core.portfolio import autopilot as ap
    from core.portfolio import sizing
    idea = SimpleNamespace(symbol="ASMTEC", source="discovery", verdict="NEUTRAL",
                           model_verdict="", entry_low=400.0, entry_high=420.0,
                           invalidation_level=380.0, last_deep_dive="2026-11-01", dived_on=None)
    report = ({"ASMTEC": {"status": "A", "measures": ["LT-ASM"]}}, "2026-11-03")
    size = sizing.BuySize(qty=0, wanted=66000.0, budget=0.0, binding="", limit="")
    capped = sizing.BuySize(qty=0, wanted=66000.0, budget=0.0, binding="position cap",
                            limit="the 10% position cap")
    expected = [
        (sizing.entry_check(500.0, idea)[1], "its price was above the range we planned to pay"),
        (sizing.entry_check(370.0, idea)[1],
         "its price had fallen to where its research would no longer hold"),
        (sizing.entry_check(500.0, None)[1],
         "it had no planned price range on record, so it needs fresh research"),
        (sizing.surveillance_issue("ASMTEC", report),
         "the exchange's watch list did not clear it (its report of 3 Nov 2026)"),
        (resale_wait(idea, date(2026, 11, 2), None) or "sold on 2026-11-02, after its deep "
         "dive of 2026-11-01; waits for a new deep dive",
         "we had sold it recently and are waiting for new research"),
        (verdict_wait(idea), "its research did not support a buy"),
        (other_company("ASMTEC", "ASM"), "its research did not support a buy"),
        (close_before_decision(date(2026, 10, 30), datetime(2026, 10, 31, tzinfo=timezone.utc),
                               False, "deep dive"), "no suitable closing price was available"),
        ("no price for the review session", "no suitable closing price was available"),
        ("its close is from bar 2026-11-11, not the review session",
         "no suitable closing price was available"),
        ("identity: the listing changed", "we could not confirm that its price was its own"),
        (sizing.under_one_share_note(capped, 135000.0, "proceeds"),
         "a limit on how much we put in one place left no room"),
        (sizing.under_one_share_note(size, 135000.0, "proceeds"),
         "the money was not enough for even one share"),
        ("already in the ledger; needs manual reconciliation", "its record needs a check"),
    ]
    for reason, said in expected:
        assert reason, said
        sell = sale(verdict="SWITCH")
        ap._note_skipped_buy(sell, "ASMTEC", 3430.0, reason)
        assert words.plain_skip(ap.switch_skip_reason(sell.note)) == said, (reason, sell.note)


def test_a_capped_switch_says_what_stayed_in_cash():
    """Proceeds 3,430; the buy took 2 shares at 340 + 3 costs = 683, so 2,747
    stays."""
    sell, leg, ctx = _switch()
    leg = leg.model_copy(update={"qty": 2.0, "value": 680.0, "costs": TradeCosts(total=3.0)})
    p = explained(sell, ctx=ctx, siblings=[sell, leg])["parts"]
    assert p["next"] == ("We used ₹683 of the money to buy DEF; the other ₹2,747 stays in "
                         "cash.")


def test_a_fallback_never_copies_a_cut_or_jargon_sentence():
    long = case(one_line="The envelope is bullish and the agent agrees.")
    long = long.model_copy(update={"pillars": [
        long.pillars[0].model_copy(update={"claim": "The market regime is calm."})]})
    row = explained(buy(), the_case=long)
    assert "The case:" not in row["parts"]["why"]
    assert words.banned_in(parts_text(row["parts"])) == []


def test_the_analysis_thesis_is_read_whole_when_there_is_no_case():
    """The ledger keeps the idea's thesis cut at 800; the facts come from the
    analysis the case would read."""
    from core.portfolio.cases import Bundle
    thesis = "First sentence about demand. " + "More detail follows. " * 60 + "The end."
    bundle = Bundle(symbol="ABC", as_of=datetime(2026, 11, 12, tzinfo=timezone.utc))
    bundle.items.append((CaseInput(ref="A1", kind="analysis", known_at="2026-11-07"),
                         f"verdict BUY, score 0.8\nthesis: {thesis}\nrisk: Costs may rise."))
    facts = explain.company_facts(None, bundle)
    assert facts.why_lines[0].startswith("Analysis thesis: First sentence about demand.")
    assert facts.template_why == "First sentence about demand."
    assert facts.risk_lines == ["risk: Costs may rise."]


class _Cases:
    def __init__(self, *cases):
        self._cases = cases

    def versions(self, symbol):
        return [c for c in self._cases if c.symbol == symbol]


def _run(tmp_path, monkeypatch, txns, cases, ledger, contexts=None):
    asked = []
    from core.portfolio.cases import Bundle

    def inputs(symbol, as_of, ideas):
        asked.append((symbol, as_of.date().isoformat()))
        b = Bundle(symbol=symbol, as_of=as_of)
        b.items.append((CaseInput(ref="A1", kind="analysis", known_at="2026-09-30"),
                        "verdict BUY\nthesis: Demand was rising when it was analysed."))
        return b
    monkeypatch.setattr(explain, "_company_inputs", inputs)
    rows = explain.explain_run("u", date(2026, 11, 12), base_dir=str(tmp_path), txns=txns,
                               contexts=contexts or {}, digest=None, ledger=ledger,
                               case_store=cases, model=False)
    return rows, asked


def _bought_on(day, symbol="XYZ", ref="b0"):
    return buy(symbol=symbol, ref=ref).model_copy(update={"date": day,
                                                          "txn_id": f"open-{symbol}-{day}"})


def test_an_earlier_holdings_case_never_explains_a_new_purchase(tmp_path, monkeypatch):
    """ABC was held, sold and bought again today; today's case was not
    written. The old holding's case is another purchase's reasons."""
    old = case("ABC", one_line="An old reason from the last holding.").model_copy(
        update={"opened_on": "2026-08-01"})
    rows, asked = _run(tmp_path, monkeypatch, [buy()], _Cases(old), [buy()])
    why = rows["txn:buy-ABC"]["parts"]["why"]
    assert "old reason" not in why
    assert asked == [("ABC", "2026-11-12")]


def test_a_sale_without_a_case_reads_the_analysis_known_when_bought(tmp_path, monkeypatch):
    """Bought 1 Oct, sold 12 Nov: the facts are those known on 1 Oct, never
    the analysis that may have turned to sell it since."""
    ledger = [_bought_on("2026-10-01"), sale()]
    rows, asked = _run(tmp_path, monkeypatch, [sale()], _Cases(), ledger)
    assert asked == [("XYZ", "2026-10-01")]
    assert rows["txn:sell-XYZ"]["parts"]["why"].endswith(
        "The analysis at the time we bought it said: Demand was rising when it was analysed.")


def test_a_case_written_after_the_purchase_is_never_called_the_reason_then(tmp_path,
                                                                          monkeypatch):
    late = case("XYZ").model_copy(update={"opened_on": "2026-10-01",
                                          "written": "after_purchase"})
    rows, asked = _run(tmp_path, monkeypatch, [sale()], _Cases(late),
                       [_bought_on("2026-10-01"), sale()])
    why = rows["txn:sell-XYZ"]["parts"]["why"]
    assert "The reason recorded after we bought it was: Orders cover two years of sales." in why
    assert "When we bought it" not in why and asked == []


def test_a_sale_whose_purchase_is_not_in_the_ledger_claims_no_reason(tmp_path, monkeypatch):
    rows, asked = _run(tmp_path, monkeypatch, [sale()], _Cases(case("XYZ")), [sale()])
    why = rows["txn:sell-XYZ"]["parts"]["why"]
    assert asked == [] and len(words.sentences(why)) == 1


def test_a_top_up_says_the_stop_on_its_new_average():
    """40 at 100 plus 10 at 110: average 102.00; stop 12% -> 89.76."""
    txn = buy("ADD", "XYZ", 10.0, 110.0, "add_tranche", ("add_bullish_healthy",),
              "2026-11-12|XYZ|h1", held=50.0)
    p = explained(txn, ctx=Context(rec=rec("ADD", ("add_bullish_healthy",), close=110.0,
                                           pnl=10.0), holding=holding()))["parts"]
    assert "safety limit of about ₹89.76" in p["wrong_if"]


def test_a_topped_up_row_reads_the_holding_as_the_run_left_it():
    """The digest row after a top-up: 50 at 102.00; stop 12% -> 89.76."""
    digest = {"holdings": [{"symbol": "XYZ", "verdict": "ADD", "pnl_pct": 7.8, "notes": []}]}
    after = Portfolio(user_id="u", cash_deployable=1.0, autopilot=True,
                      holdings=[holding(avg=102.0, qty=50.0)])
    explain.plain_rows(digest, {"XYZ": Context(rec=rec("ADD", (), close=110.0, pnl=10.0),
                                               holding=holding())}, after, "evidence")
    assert "₹89.76" in digest["holdings"][0]["plain"]["wrong_if"]


# -- the review's buying ---------------------------------------------------------

DEP = {"date": "2026-11-12", "bought": [], "holdings_after": 9, "target_holdings": 20,
       "invested_after_pct": 46.1, "target_pct": 80.0,
       "reasons": ["no further qualifying idea"],
       "ideas": [{"symbol": "QALPHA", "outcome": "band", "why": "4.0% above entry band (x)"},
                 {"symbol": "QBETA", "outcome": "band", "why": "12.1% above entry band (y)"},
                 {"symbol": "QGAMMA", "outcome": "sold", "why": "sold on 2026-11-02"}]}


def test_the_review_card_in_plain_words():
    parts = explain.explain_review(DEP, "2026-11-12")["parts"]
    assert parts["did"] == "At the review of 12 Nov 2026 we bought nothing new."
    assert parts["why"] == ("No other idea passed all our checks. 2 ideas were priced above the "
                            "range we planned to pay (by 4.0% to 12.1%), and 1 idea had been "
                            "sold recently and waits for new research.")
    assert parts["next"] == ("Now we hold 9 of the 20 holdings we aim for, and 46.1% of the "
                             "money is in stocks against a goal of 80.0%. We wait rather than "
                             "chase.")
    assert_contract(parts, plain(12, 2026, 2, "4%", "12.1%", 1, 9, 20, "46.1%", "80%"))


@pytest.mark.parametrize("reason, lead, change", [
    ("regime NORMAL, target reached: 80.0% invested against a target of 80.0% (₹8,00,000)",
     "share of money we wanted in stocks", "below the goal again"),
    ("2 new positions today, the daily limit of 2", "at most 2 new stocks a day",
     "at a later review"),
    ("15 holdings, the maximum of 15", "most stocks we allow", "after we sell one we hold"),
    ("market regime MACRO_CRISIS: no new positions, cash held on purpose",
     "calls for holding cash", "market's condition allows"),
    ("no target set for market regime ODD: no new positions", "No goal is set",
     "market's condition allows"),
    ("market regime unavailable for 2026-11-12: India VIX did not answer; no new positions",
     "could not read the market's condition", "market's condition allows"),
    ("no equity above the cash floor to invest", "beyond the cash we keep aside",
     "once there is money"),
    ("no further qualifying idea", "No other idea passed all our checks",
     "within the range we planned to pay"),
])
def test_every_way_the_buying_stops_says_why_and_what_would_change_it(reason, lead, change):
    parts = explain.review_parts(dict(DEP, reasons=[reason]), "2026-11-12")
    assert lead in parts["why"] and change in parts["wrong_if"], parts
    assert words.check_parts(parts) == ""


def test_the_stop_reasons_are_the_deployment_rules_own_words():
    """Each reason built by deployment.py itself, so a reworded rule fails
    here and cannot silently fall to the generic lead."""
    from core.portfolio import deployment
    b = deployment.Breadth(deploy=True, min_holdings=10, target_holdings=12, max_holdings=15,
                           shares={"NORMAL": 80.0, "MACRO_CRISIS": 0.0})
    open_day = deployment.target("NORMAL", 1000.0, b, 10.0)

    def stopped(**kw):
        base = dict(equity=1000.0, invested=0.0, holdings=0, opened=0, max_new=2)
        return deployment.stop_reason(open_day, b, **{**base, **kw})
    cases = [
        (stopped(invested=900.0), "share of money we wanted"),
        (stopped(holdings=15), "most stocks we allow"),
        (stopped(opened=2), "at most 2 new stocks a day"),
        (deployment.target("MACRO_CRISIS", 1000.0, b, 10.0).closed, "calls for holding cash"),
        (deployment.target("ODD", 1000.0, b, 10.0).closed, "No goal is set"),
        (deployment.target(None, 1000.0, b, 10.0, gap="market regime unavailable for "
                           "2026-11-12: India VIX did not answer").closed,
         "could not read the market's condition"),
        (deployment.target(None, 1000.0, b, 10.0).closed,
         "could not read the market's condition"),
        (deployment.stop_reason(deployment.target("NORMAL", 5.0, b, 10.0), b, equity=5.0,
                                invested=0.0, holdings=0, opened=0, max_new=2),
         "beyond the cash we keep aside"),
    ]
    for reason, lead in cases:
        assert reason, lead
        assert lead in explain._stop({"reasons": [reason]})[0], (reason, lead)


def test_a_day_nothing_may_open_tells_no_goal():
    """target_pct 0: no "against a goal of 0.0%"."""
    parts = explain.review_parts(dict(DEP, target_pct=0.0, reasons=[
        "market regime MACRO_CRISIS: no new positions, cash held on purpose"]), "2026-11-12")
    assert "goal of" not in parts["next"] and "9 of the 20" in parts["next"]


# -- banned words over every template ---------------------------------------------

TRIGGERS = ["stop_breach", "trailing_stop_breach", "thesis_break", "case_broken",
            "bought_on_other_analysis", "shock_reforecast", "crisis_regime_bearish",
            "trim_profit_confidence_decline", "trim_profit_reversion_elevated",
            "add_bullish_healthy", "switch_candidate_available", "an_unknown_rule"]
NOTES = list(words.NOTE_ORDER) + ["SOMETHING_NEW"]
HOSTILE = ["the ATR agent saw a MACRO_CRISIS regime", "envelope reversion prior",
           "data gate rationale hash", "EXIT now (conviction streak)",
           "India VIX did not answer", "Revenue fell 4%."]


def _hostile_facts(rng) -> dict:
    return {"stop_price": rng.choice([None, 88.0]), "peak_price": rng.choice([None, 150.0]),
            "trail_price": 135.0, "bought_on_other": rng.choice(HOSTILE + [""]),
            "broken": [{"kind": "event", "day": "2026-11-05", "what": rng.choice(HOSTILE)},
                       {"kind": "verdict", "verdict": "SELL", "day": ""},
                       {"kind": "level", "close": 90.0, "level": 95.0, "at_dive": 0.0}],
            "broken_waiting": rng.choice([[], [{"kind": "event", "day": "",
                                                "what": rng.choice(HOSTILE)}]]),
            "manual": rng.random() < 0.5, "autopilot": rng.random() < 0.5,
            "position_cap": 10.0, "sector_cap": 30.0,
            "regime_unavailable": "market regime unavailable for 2026-10-30: "
                                  + rng.choice(HOSTILE),
            "top_up_skipped": rng.choice(["", "top-up skipped: under LT-ASM in NSE's "
                                              "surveillance report of 2026-11-03"]),
            "not_reviewed_plain": rng.choice(["", words.not_reviewed_plain(
                "no daily review or forecast: managed-ticker cap 40 reached")]),
            "exit_rule": rng.choice(["evidence", "legacy"]), "wait_sessions": 10,
            "close": 94.0, "level": rng.choice([None, 90.0]),
            "calls_right_pct": rng.choice([None, 80.0])}


@pytest.mark.parametrize("seed", range(150))
def test_no_template_ever_uses_a_banned_word(seed):
    rng = random.Random(seed)
    parts = words.holding_parts(
        "XYZ", rng.choice(["HOLD", "ADD", "TRIM", "EXIT", "SWITCH", "NO_DATA"]),
        triggers=rng.sample(TRIGGERS, rng.randint(0, 4)),
        notes=rng.sample(NOTES, rng.randint(0, 4)),
        pnl_pct=rng.choice([None, -6.2, 0.0, 12.5]),
        switch_to=rng.choice(["", "DEF"]), facts=_hostile_facts(rng))
    assert words.check_parts(parts) == "", (words.check_parts(parts), parts)
    assert words.banned_in(parts_text(parts)) == [], parts


@pytest.mark.parametrize("seed", range(120))
def test_no_trade_template_ever_uses_a_banned_word(seed):
    rng = random.Random(seed)
    triggers = rng.sample(TRIGGERS, rng.randint(1, 3))
    verdict = rng.choice(["EXIT", "TRIM", "SWITCH", "ADD", "DEPLOY"])
    ev = {"negative_events": [{"source": "nse_announcement", "published_at": "2026-11-05",
                               "what": rng.choice(HOSTILE)}],
          "research_verdict": "SELL", "research_run_at": "2026-11-04T05:00:00",
          "invalidation_level": 90.0}
    hostile_case = case("XYZ", one_line=rng.choice(HOSTILE + ["Orders are strong."]),
                        business=(rng.choice(HOSTILE),))
    if verdict in ("ADD", "DEPLOY"):
        txn = buy(verdict, "XYZ", triggers=triggers)
    else:
        txn = sale(verdict=verdict, triggers=triggers, left=0.0 if verdict != "TRIM" else 5.0,
                   note=rng.choice(["exit_full", "exit_full; buy leg skipped: DEF: sold on "
                                    "2026-11-02, after its deep dive; ₹1 stays in cash"]))
    ctx = Context(rec=rec(verdict if verdict != "DEPLOY" else "ADD", triggers, switch_to="DEF",
                          bought_on_other=rng.choice(HOSTILE)), evidence=ev)
    row = explained(txn, ctx=ctx, the_case=hostile_case)
    assert words.check_parts(row["parts"]) == "", (words.check_parts(row["parts"]),
                                                   row["parts"])
    assert words.banned_in(parts_text(row["parts"])) == [], row["parts"]


# -- the routed inputs -------------------------------------------------------------

def _row(verdict="HOLD", notes=(), cash=1000.0, autopilot=True, **row_extra):
    digest = {"holdings": [{"symbol": "XYZ", "verdict": verdict, "pnl_pct": 1.0,
                            "notes": list(notes), **row_extra}]}
    explain.plain_rows(digest, {"XYZ": Context(rec=rec("HOLD", (), close=101.0, pnl=1.0,
                                                       notes=notes), holding=holding())},
                       Portfolio(user_id="u", cash_deployable=cash, autopilot=autopilot),
                       "evidence")
    return digest["holdings"][0]["plain"]


def test_a_portfolio_without_cash_is_told_its_weight_among_its_holdings():
    """SA-050 R4: no cash on record -> "over 10% of your holdings", nothing
    about the autopilot or buying."""
    p = _row(notes=["POSITION_LARGE"], cash=None, autopilot=False)
    assert "It is over 10% of your holdings." in p["why"]
    text = parts_text(p)
    assert "autopilot" not in text.lower() and "bought" not in text and "portfolio" not in text
    with_cash = _row(notes=["POSITION_LARGE"])
    assert "over 10% of your whole portfolio, so no more of it will be bought" in with_cash["why"]


def test_an_unread_market_names_the_day_and_why_and_never_calls_it_normal():
    """FIX-024 L1."""
    digest = {"holdings": [{"symbol": "XYZ", "verdict": "HOLD", "pnl_pct": 1.0,
                            "notes": ["REGIME_UNAVAILABLE"]}]}
    r = rec("HOLD", (), close=101.0, pnl=1.0, notes=["REGIME_UNAVAILABLE"],
            regime_unavailable="market regime unavailable for 2026-10-30: India VIX did "
                               "not answer")
    explain.plain_rows(digest, {"XYZ": Context(rec=r, holding=holding())},
                       Portfolio(user_id="u", cash_deployable=1.0), "evidence")
    why = digest["holdings"][0]["plain"]["why"]
    assert "could not read the market's condition for 30 Oct 2026 (India VIX did not answer)" \
        in why
    assert "NORMAL" not in why and "normal" not in why.lower() and "calm" not in why.lower()


def test_the_results_note_says_the_date_may_be_after_the_close():
    """FIX-031 R1: the calendar keeps no announcement time."""
    assert "may have been announced after that day's close" in \
        _row(notes=["EARNINGS_GAP_PROTECTION"])["why"]


def test_a_held_back_trim_is_not_told_as_no_rule_met():
    """WAIT_FOR_LTCG keeps a trim trigger: a profit rule did fire."""
    why = _row(notes=["WAIT_FOR_LTCG"])["why"]
    assert "none of our selling rules" not in why
    assert "a reason to take some profit has appeared" in why


def test_advice_to_sell_never_speaks_of_a_sale_that_did_not_happen():
    p = _row("EXIT", cash=None, autopilot=False)
    assert p["wrong_if"] == words.ADVICE_NO_REBUY and "this sale" not in parts_text(p)


def test_several_notes_share_one_sentence():
    p = _row(notes=["SECTOR_CONCENTRATION_HIGH", "POSITION_LARGE", "WAIT_FOR_LTCG"])
    assert len(words.sentences(p["why"])) == 2
    assert p["why"].index("lower long-term rate") < p["why"].index("over 10%") \
        < p["why"].index("over 30%")


def test_a_row_with_no_review_says_why_in_plain_words():
    """FIX-028 I-1."""
    p = _row("NO_DATA", not_reviewed="no daily review or forecast: managed-ticker cap 40 reached")
    assert p["why"] == ("It has not been reviewed: the daily review list is full (limit 40), so "
                        "it has no daily review or forecast yet.")
    from core.delivery.brief import _VERDICT_PLAIN
    assert _VERDICT_PLAIN["NO_DATA"] == "Not reviewed"


def test_a_same_day_re_run_keeps_the_days_record():
    """FIX-025 L2 and FIX-028: execution did not run, so the earlier record
    stays; another day's never carries."""
    first = {"date": "2026-11-12", "deployment": {"bought": ["P1"]}, "trades": [{"x": 1}],
             "holdings": [{"symbol": "A", "top_up_skipped": "why"},
                          {"symbol": "B", "not_reviewed": "cap"},
                          {"symbol": "C", "top_up_skipped": "why"}, {"symbol": "GONE"}]}
    again = {"date": "2026-11-12", "trades": [], "holdings": [
        {"symbol": "A", "verdict": "ADD"}, {"symbol": "B", "verdict": "HOLD"},
        {"symbol": "C", "verdict": "HOLD"}]}
    keep_day_record(again, first)
    assert again["deployment"] == {"bought": ["P1"]} and again["trades"] == [{"x": 1}]
    assert again["holdings"] == [
        {"symbol": "A", "verdict": "ADD", "top_up_skipped": "why"},
        {"symbol": "B", "verdict": "HOLD", "not_reviewed": "cap"},
        {"symbol": "C", "verdict": "HOLD"}]
    other = {"date": "2026-11-13", "trades": [], "holdings": [{"symbol": "A"}]}
    keep_day_record(other, first)
    assert other == {"date": "2026-11-13", "trades": [], "holdings": [{"symbol": "A"}]}


# -- stored once, per user, and never blocking ------------------------------------------

def test_one_users_words_never_reach_another(tmp_path):
    """FIX-005: each user's file, and a foreign row in it is not read."""
    mine, theirs = ExplanationStore("u1", str(tmp_path)), ExplanationStore("u2", str(tmp_path))
    theirs.put({"key": "txn:t2", "parts": {}, "date": "2026-11-12"})
    mine.put({"key": "txn:t1", "parts": {}, "date": "2026-11-12"})
    with mine.path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"key": "txn:t2", "user_id": "u2", "parts": {}}) + "\n")
        fh.write("torn line{\n")
    assert list(mine.load()) == ["txn:t1"] and list(theirs.load()) == ["txn:t2"]


def test_drafted_once_and_the_budget_ends_model_calls(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(explain, "_call_model",
                        lambda s, u: calls.append(1) or answer()(s, u))
    txns = [buy(symbol="ABC"), buy(symbol="DEF", ref="2026-11-12|DEF|deploy_idle_cash")]

    class Cases:
        def versions(self, symbol):
            return [case(symbol)]
    ticks = iter([0.0, 0.0, 500.0, 500.0, 500.0, 500.0])
    rows = explain.explain_run("u", date(2026, 11, 12), base_dir=str(tmp_path), txns=txns,
                               contexts={}, digest={"deployment": DEP}, case_store=Cases(),
                               clock=lambda: next(ticks))
    assert len(calls) == 1                      # past the budget: templates
    assert [rows[f"txn:buy-{s}"]["source"] for s in ("ABC", "DEF")] == ["model", "template"]
    assert rows["review:2026-11-12"]["source"] == "template"
    again = explain.explain_run("u", date(2026, 11, 12), base_dir=str(tmp_path), txns=txns,
                                contexts={}, digest={"deployment": DEP}, case_store=Cases())
    assert len(calls) == 1 and again.keys() == rows.keys()


def test_one_trade_that_cannot_be_worded_costs_only_itself(tmp_path, monkeypatch):
    real = explain.explain_trade

    def flaky(txn, **kw):
        if txn.symbol == "ABC":
            raise RuntimeError("boom")
        return real(txn, **kw)
    monkeypatch.setattr(explain, "explain_trade", flaky)
    monkeypatch.setattr(explain, "_company_inputs", lambda *a: None)
    rows = explain.explain_run("u", date(2026, 11, 12), base_dir=str(tmp_path),
                               txns=[buy(), buy(symbol="DEF")], contexts={}, digest=None)
    assert list(rows) == ["txn:buy-DEF"]


def test_a_hand_trade_and_a_dividend_are_not_worded(tmp_path):
    txns = [buy().model_copy(update={"source": "manual"}),
            sale().model_copy(update={"side": "DIV", "txn_id": "d"})]
    assert explain.explain_run("u", date(2026, 11, 12), base_dir=str(tmp_path), txns=txns,
                               contexts={}, digest=None) == {}


# -- the pipeline end to end, the API and the alerts ------------------------------------

def _world(tmp_path, monkeypatch, holdings, cash, ideas, prices):
    from core.portfolio import autopilot as ap
    from core.portfolio import deployment
    import tests.unit.test_deploy_idle_cash_sa049 as story
    for name, value in {
        "PORTFOLIO_COSTS": story.NO_COSTS, "AUTOPILOT_MIN_CASH_FLOOR": 10_000.0,
        "AUTOPILOT_ENABLED": True, "AUTOPILOT_DEPLOY_IDLE_CASH": True,
        "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY": 2,
        "AUTOPILOT_DEPLOY_TARGET_PCT": dict(story.TARGETS), "PORTFOLIO_MIN_HOLDINGS": 10,
        "PORTFOLIO_TARGET_HOLDINGS": 12, "PORTFOLIO_MAX_HOLDINGS": 15,
        "PORTFOLIO_OVERRIDES": {}, "DECISION_GATE_MODE": "record", "ADVISOR_CASE_MODEL": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(ap, "_today_ist", lambda: story.TODAY)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-07-13T11:00:00+00:00")
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: "NORMAL")
    story._report(monkeypatch)
    return story._pipeline_world(tmp_path, monkeypatch, holdings, cash, ideas, prices)


def _two_ideas():
    import tests.unit.test_deploy_idle_cash_sa049 as story
    return [story._idea("P1", 500.0, 0.9, "pharma"), story._idea("P2", 250.0, 0.8, "chemicals")]


def test_the_pipeline_drafts_stores_and_serves_the_words(tmp_path, monkeypatch):
    import core.portfolio.pipeline as pipeline
    calls = []
    monkeypatch.setattr(explain, "_call_model", lambda s, u: calls.append(s) or json.dumps(
        {"reason": "The company sells to many customers.",
         "risk": "Losing a large customer would hurt it.",
         "summary": "Only two ideas were ready."}))
    ideas = _two_ideas()
    store, _ = _world(tmp_path, monkeypatch, [], 1_200_000.0, ideas,
                      {"P1": 500.0, "P2": 250.0})
    day = date(2026, 7, 13)
    assert pipeline.run_post_review_pipeline(day)["status"] == "completed"
    txns = store.load_transactions()
    assert sorted(t.symbol for t in txns) == ["P1", "P2"]
    audit = [(t.reason, t.note) for t in txns]
    stored = ExplanationStore("u", str(store._dir.parent)).load()
    assert {f"txn:{t.txn_id}" for t in txns} <= set(stored)
    n = len(calls)
    assert n == 2                    # one per purchase; none for the review or a row
    digest = store.load_latest_digest()
    assert all("plain" in r for r in digest["holdings"])
    # the same day again: nothing is drafted twice, the day's record stays
    pipeline.run_post_review_pipeline(day)
    assert len(calls) == n
    assert store.load_latest_digest()["deployment"] == digest["deployment"]
    assert store.load_latest_digest()["trades"] == digest["trades"]
    # the audit text is as the executor wrote it
    assert [(t.reason, t.note) for t in store.load_transactions()] == audit

    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(store._dir.parent))
    app = FastAPI()
    app.include_router(papi.router)
    app.dependency_overrides[papi.get_current_user] = lambda: {"user_id": "u", "role": "owner"}
    client = TestClient(app)
    rows = client.get("/portfolio/transactions").json()["transactions"]
    assert all(r["plain"]["why"] and r["plain"]["source"] in ("model", "template")
               for r in rows)
    got = client.get("/portfolio/digest/latest").json()
    assert got["plain_review"]["did"].startswith("At the review of 13 Jul 2026 we bought 2 new")
    assert "New buys: At the review" in \
        client.get("/portfolio/digest/latest", params={"format": "text"}).json()["text"]
    # another user is sent nothing of u's
    app.dependency_overrides[papi.get_current_user] = lambda: {"user_id": "v", "role": "member"}
    assert client.get("/portfolio/transactions").json() == {"transactions": []}


def test_a_sale_through_the_pipeline_is_told_alike_by_alert_and_history(tmp_path,
                                                                      monkeypatch):
    """AAA bought at 200, marked at 100: the stop sells it. The alert says
    exactly what the stored trade words say, and the model is never asked."""
    import core.portfolio.pipeline as pipeline
    import tests.unit.test_deploy_idle_cash_sa049 as story
    monkeypatch.setattr(explain, "_call_model",
                        lambda s, u: pytest.fail("a sale asked the model"))
    store, emitted = _world(tmp_path, monkeypatch, [story._h("AAA", 100, 200.0, "it_sector")],
                            100_000.0, [], {"AAA": 100.0})
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    pipeline.run_post_review_pipeline(date(2026, 7, 13))
    [txn] = [t for t in store.load_transactions() if t.side == "SELL"]
    stored = ExplanationStore("u", str(store._dir.parent)).load()[f"txn:{txn.txn_id}"]
    why = stored["parts"]["why"]
    assert why.startswith("We sold because the price fell to or below our safety limit of ₹")
    [alert] = [e for e in emitted if e.kind == "advisor_exit"]
    assert alert.headline == why and alert.message == why
    assert "MACRO" not in alert.status and alert.status == stored["parts"]["did"]


def test_a_row_whose_stock_traded_says_what_the_trade_said():
    digest = {"holdings": [
        {"symbol": "TRIMMED", "verdict": "TRIM", "plain": {"why": "advice"}},
        {"symbol": "TOPPED", "verdict": "ADD", "plain": {"why": "advice"}},
        {"symbol": "REFUSED", "verdict": "ADD", "top_up_skipped": "x",
         "plain": {"why": "refused"}},
        {"symbol": "NEW", "verdict": "NO_DATA", "plain": {"why": "not reviewed"}},
        {"symbol": "CAPPED", "verdict": "NO_DATA", "not_reviewed": "cap",
         "plain": {"why": "list full"}},
        {"symbol": "HELD", "verdict": "HOLD", "plain": {"why": "kept"}}]}
    drafted = {s: {"kind": "trade", "symbol": s, "side": side, "source": "template",
                   "parts": {"why": f"{s} {side}"}}
               for s, side in (("TRIMMED", "SELL"), ("TOPPED", "BUY"), ("REFUSED", "BUY"),
                               ("NEW", "BUY"), ("CAPPED", "BUY"), ("HELD", "BUY"))}
    assert explain.use_trade_words(digest, drafted)
    assert [r["plain"]["why"] for r in digest["holdings"]] == [
        "TRIMMED SELL", "TOPPED BUY", "refused", "NEW BUY", "list full", "kept"]


def test_the_rollback_switch_shows_the_audit_text_again(tmp_path, monkeypatch):
    """plain_reasons off after words were stored: the API sends none of them,
    the brief and the weekly read the audit text."""
    from core.delivery import brief as br
    from core.delivery import weekly as wk
    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.append_transaction(sale())
    store.save_digest({"date": "2026-11-12", "holdings": [
        {"symbol": "XYZ", "verdict": "EXIT", "reason": "audit", "plain": {"why": "plain"}}]})
    kept = ExplanationStore("u", str(tmp_path))
    for key, side in (("txn:sell-XYZ", "SELL"), ("review:2026-11-12", None)):
        kept.put({"key": key, "side": side, "advice_ref": "r1",
                  "parts": {k: "x" for k in words.PARTS}})
    assert wk._plain_sale_words("u", store) == {"r1": "x"}
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(papi.router)
    app.dependency_overrides[papi.get_current_user] = lambda: {"user_id": "u", "role": "owner"}
    client = TestClient(app)
    assert "plain" in client.get("/portfolio/transactions").json()["transactions"][0]
    assert "plain_review" in client.get("/portfolio/digest/latest").json()
    assert br._plain_why({"plain": {"why": "plain"}}) == "plain"
    monkeypatch.setattr(settings, "ADVISOR_PLAIN_REASONS", False)
    assert "plain" not in client.get("/portfolio/transactions").json()["transactions"][0]
    digest = client.get("/portfolio/digest/latest").json()
    assert "plain_review" not in digest and "plain" not in digest["holdings"][0]
    assert br._plain_why({"plain": {"why": "plain"}}) == ""
    assert wk._plain_sale_words("u", store) == {}


def test_reading_a_trades_facts_creates_no_prediction_store(tmp_path):
    """The case writer's read opens the prediction store, which makes a
    folder; the words must not."""
    from pathlib import Path
    explain._company_inputs("SUNPHARMA", datetime(2026, 11, 12, tzinfo=timezone.utc), [])
    assert not any(Path("data/predictions").rglob("SUNPHARMA"))


def test_a_failing_draft_never_blocks_the_run(tmp_path, monkeypatch):
    import core.portfolio.pipeline as pipeline

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ExplanationStore, "put", boom)
    store, emitted = _world(tmp_path, monkeypatch, [], 1_200_000.0, _two_ideas(),
                            {"P1": 500.0, "P2": 250.0})
    assert pipeline.run_post_review_pipeline(date(2026, 7, 13))["status"] == "completed"
    assert len(store.load_transactions()) == 2
    assert store.load_latest_digest()["deployment"]["bought"] == ["P1", "P2"]
    assert sorted(e.symbol for e in emitted if e.kind == "autopilot_trade") == ["P1", "P2"]


def test_with_the_switch_off_nothing_is_drafted_or_worded(tmp_path, monkeypatch):
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(settings, "ADVISOR_PLAIN_REASONS", False)
    store, _ = _world(tmp_path, monkeypatch, [], 1_200_000.0, _two_ideas(),
                      {"P1": 500.0, "P2": 250.0})
    pipeline.run_post_review_pipeline(date(2026, 7, 13))
    assert not ExplanationStore("u", str(store._dir.parent)).path.exists()
    assert all("plain" not in r for r in store.load_latest_digest()["holdings"])


def test_an_alert_uses_the_plain_words_and_no_stop_percentage():
    from core.portfolio.pipeline import advice_alert_fields
    parts = explained(sale(), ctx=Context(rec=rec()))["parts"]
    fields = advice_alert_fields(rec(), {}, parts)
    assert fields["headline"] == parts["why"] and fields["status"] == parts["did"]
    assert fields["next_step"] == parts["next"]
    assert "12.0%" not in " ".join(fields.values())


# -- the backfill ------------------------------------------------------------------------

def _backfill_script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts" / "explain_trades.py"
    spec = importlib.util.spec_from_file_location("explain_trades", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_the_backfill_names_the_event_the_shadow_recorded(tmp_path, monkeypatch):
    """A case sale made before this: its reason is rebuilt from the exit
    shadow's event ids and the event store."""
    from types import SimpleNamespace
    from core.events import store as events_store
    from core.portfolio.store import PortfolioStore
    script = _backfill_script()
    event = SimpleNamespace(id="e9", published_at="2026-11-05T18:10:00+05:30",
                            category="results", what="Profit fell sharply.",
                            source="nse_announcement")
    monkeypatch.setattr(events_store.EventStore, "load", lambda self, symbol: [event])
    monkeypatch.setattr(explain, "_company_inputs", lambda *a: None)
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.append_advice(rec(triggers=("case_broken",)))
    store.append_transaction(sale(triggers=("case_broken",)))
    monkeypatch.setattr(PortfolioStore, "load_exit_shadow", lambda self: [
        {"date": "2026-11-12", "symbol": "XYZ", "evidence": {"event_ids": ["e9"]}}])
    script.backfill("u", apply=True, model=False, base_dir=str(tmp_path), out=lambda s: None)
    why = ExplanationStore("u", str(tmp_path)).load()["txn:sell-XYZ"]["parts"]["why"]
    assert why == ("We sold because the reason we owned it broke: bad news came out on 5 Nov "
                   "2026: Profit fell sharply.")


def test_the_backfill_dry_run_writes_nothing_and_apply_drafts_once(tmp_path, monkeypatch):
    from core.portfolio.store import PortfolioStore
    script = _backfill_script()
    monkeypatch.setattr(explain, "_company_inputs", lambda *a: None)
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.append_advice(rec())
    for txn in (sale(), buy(), buy(symbol="MAN").model_copy(update={"source": "manual"})):
        store.append_transaction(txn)
    lines = []
    out = script.backfill("u", apply=False, model=True, base_dir=str(tmp_path),
                          out=lines.append)
    assert (out["todo"], out["written"]) == (2, 0)
    assert not ExplanationStore("u", str(tmp_path)).path.exists()
    out = script.backfill("u", apply=True, model=False, base_dir=str(tmp_path),
                          out=lines.append)
    assert (out["written"], out["model"]) == (2, 0)
    words_of_sale = ExplanationStore("u", str(tmp_path)).load()["txn:sell-XYZ"]["parts"]
    assert "safety limit of ₹88.00" in words_of_sale["why"]
    assert script.backfill("u", apply=True, model=False, base_dir=str(tmp_path),
                           out=lines.append)["todo"] == 0
