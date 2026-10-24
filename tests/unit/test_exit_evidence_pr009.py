"""PR-009: exit on evidence, not on a price-path miss (shadow, then switch).

Independent invariants, each from the card's acceptance criteria:

- the ₹500 example: legacy EXIT, evidence HOLD, both recorded with reasons;
- each `case_broken` path fires on its own fixture and not one unit short of
  it; within the minimum holding period only stops fire;
- a stale, future or misattributed event, and a research run after the review
  day or an abstained one, never fire it;
- property: over random signals the evidence rule fires `stop_breach` and
  `trailing_stop_breach` exactly when the legacy rule does;
- in `shadow` the advice and transaction ledgers are byte-identical to
  `legacy`; one shadow row per holding per review day however often the
  pipeline re-runs; `shadow` is the default;
- grading reads only the decision close and prices up to the horizon's day,
  and an unmatured disagreement is pending, never scored;
- the gate: a tally that passes at 30 sessions but fails at 10 does not
  recommend a switch, nor the reverse; the other conditions each block it.

The review day is Friday 23 Oct 2026. Tuesday 20 Oct is an NSE holiday, so its
last 5 sessions are 16, 19, 21, 22 and 23 Oct.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

import pytest

from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.events import CompanyEvent
from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.config import settings
from core.intelligence.rl.nse_calendar import (
    is_trading_day, trading_days_after, trading_days_ago,
)
from core.portfolio import exit_shadow as xs
from core.portfolio.advisor import (
    AdvisorSignals, ExitEvidence, case_broken_reasons, decide,
)

D = date(2026, 10, 23)


def test_the_fixture_calendar():
    assert is_trading_day(D) and not is_trading_day(date(2026, 10, 20))
    assert trading_days_ago(D, 5) == date(2026, 10, 15)
    assert settings.ADVISOR_MIN_HOLD_SESSIONS == 10


def _bought(sessions_ago: int) -> str:
    """A buy date `sessions_ago` sessions before D, so the holding has been
    held exactly that many sessions on D."""
    return trading_days_ago(D, sessions_ago).isoformat()


def _holding(symbol="AAA", price=500.0, sessions=20, qty=10.0):
    return Holding(symbol=symbol, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date=_bought(sessions))


def _signals(symbol="AAA", close=500.0, pnl=0.0, **over) -> AdvisorSignals:
    base = dict(symbol=symbol, sector="automobile", close=close, atr_stop_pct=12.0,
                unrealised_pnl_pct=pnl, holding_age_days=30, forecast_gate="actionable")
    base.update(over)
    return AdvisorSignals(**base)


def _event(symbol="AAA", published="2026-10-21T10:00:00+05:30", direction="negative",
           materiality="high", category="results", n=1) -> CompanyEvent:
    return CompanyEvent(id=f"{symbol}-{n}-{published}", symbol=symbol,
                        what="Quarterly profit fell 40% on a large write-off.",
                        category=category, direction=direction, materiality=materiality,
                        source="nse_announcement", published_at=published,
                        fetched_at="2026-10-23T18:30:00+05:30", classifier="rules")


def _record(symbol="AAA", verdict="SELL", run_at="2026-10-22T11:00:00", gate="actionable"):
    """A score-history row as the store keeps it: run_at is naive UTC."""
    return {"ticker": symbol, "run_at": run_at, "verdict": verdict, "final_score": 0.3,
            "report_json": json.dumps({"decision_gate": {"status": gate}})}


def _idea(symbol="AAA", level=455.0, dived="2026-10-01", status="promoted"):
    return ShelfIdea(symbol=symbol, sector="automobile", added=dived, dived=dived,
                     conviction=0.7, invalidation_level=level, status=status)


# NSE's actions() rows as the corp-action sync fetches them.
DIVIDEND_AUG = {"subject": "Dividend - Rs 5 Per Share", "exDate": "14-Aug-2026"}
BONUS_OCT = {"subject": "Bonus 1:1", "exDate": "21-Oct-2026"}


def _listed(symbol="AAA", *rows):
    """What the review day's sync fetched for `symbol`: by default one
    dividend of 14 Aug, so the list reaches back before every fixture dive."""
    from core.portfolio.corp_actions import action_record
    return action_record(list(rows) or [DIVIDEND_AUG], symbol)


def _evidence(symbol="AAA", sessions=20, events=(), records=(), ideas=(), actions=None):
    return xs.exit_evidence(_holding(symbol, sessions=sessions), D, events=events,
                            records=records, ideas=ideas, actions=actions)


def _both(signals, holding, evidence):
    legacy = decide(signals, holding, "balanced")
    by_evidence = decide(signals, holding, "balanced", exit_rule="evidence",
                         evidence=evidence)
    return legacy, by_evidence


# -- The ₹500 example ------------------------------------------------------------------

def test_the_500_rupee_example_legacy_exits_evidence_holds_both_recorded():
    """Bought at ₹500 four sessions ago for its order book. The market falls
    2%, the stock 4% to ₹480; the review says "not intact" and the path ends
    more than 1% lower (₹470), so the legacy rule EXITs. The evidence rule:
    no negative event, a BUY verdict, ₹480 above the ₹455 invalidation level,
    and 4 sessions held. It HOLDs.

    (The card's path end of ₹478 is within the 1% flat band of ₹480, so the
    legacy rule would not fire on it; any end below ₹475.20 does.)"""
    holding = _holding("AAA", 500.0, sessions=4)
    sig = _signals("AAA", close=480.0, pnl=-4.0, thesis_intact=False,
                   envelope_direction="DOWN")
    # Dived 1 Oct, bought 16 Oct: NSE's list reaches back to 14 Aug with no
    # bonus or split, so the dive's ₹455 is today's ₹455.
    ev = _evidence("AAA", sessions=4, records=[_record("AAA", "BUY")],
                   ideas=[_idea("AAA", 455.0)], actions=_listed())
    assert ev.sessions_held == 4 and ev.invalidation_level == 455.0 and ev.gaps == []
    legacy, by_evidence = _both(sig, holding, ev)
    assert (legacy.verdict, legacy.triggers) == ("EXIT", ["thesis_break"])
    assert (by_evidence.verdict, by_evidence.triggers) == ("HOLD", [])

    row = xs.shadow_row(on=D, user_id="u1", mode="shadow", close=480.0, legacy=legacy,
                        evidence_rec=by_evidence, evidence=ev, buy_date=holding.buy_date)
    assert row.disagree is True and row.buy_date == "2026-10-16"
    assert (row.legacy_verdict, row.legacy_triggers) == ("EXIT", ["thesis_break"])
    assert (row.evidence_verdict, row.evidence_triggers) == ("HOLD", [])
    assert row.case_broken_reasons == [] and row.sessions_held == 4
    assert row.evidence["research_verdict"] == "BUY"
    assert row.evidence["invalidation_level"] == 455.0
    assert row.evidence["invalidation_source"] == "shelf idea dived 2026-10-01, promoted"


# -- Each case_broken path, and one unit short of it -------------------------------------

def _evidence_decision(ev, close=500.0):
    sig = _signals("AAA", close=close)            # legacy: nothing fires
    legacy, by_evidence = _both(sig, _holding("AAA", 500.0, sessions=ev.sessions_held or 0), ev)
    assert legacy.verdict == "HOLD"
    return by_evidence


def test_a_high_negative_event_in_the_window_fires_and_its_neighbours_do_not():
    fires = _evidence(events=[_event(published="2026-10-16T09:00:00+05:30")])
    rec = _evidence_decision(fires)
    assert (rec.verdict, rec.triggers) == ("EXIT", ["case_broken"])
    assert case_broken_reasons(fires, 500.0) == [
        "negative results event of 2026-10-16: Quarterly profit fell 40% on a large write-off."]
    # One unit short on each axis: a session too old, medium, neutral, positive.
    for short in (_event(published="2026-10-15T18:00:00+05:30"),
                  _event(materiality="medium"),
                  _event(direction="neutral"),
                  _event(direction="positive")):
        ev = _evidence(events=[short])
        assert ev.negative_events == [] and _evidence_decision(ev).verdict == "HOLD"


def test_a_stale_future_misattributed_or_undated_event_never_fires():
    # The holiday between sessions is inside the window.
    assert _evidence(events=[_event(published="2026-10-20T12:00:00+05:30")]).negative_events
    undated = _event()
    undated.published_at = None
    for ev in (_event(published="2026-10-24T09:00:00+05:30"),    # after the review day
               _event(published="2026-10-01T09:00:00+05:30"),    # weeks old
               _event(symbol="BBB"),                             # another company's
               undated):
        evidence = _evidence(events=[ev])
        assert evidence.negative_events == [], ev
        assert _evidence_decision(evidence).verdict == "HOLD"


@pytest.mark.parametrize("verdict", ["SELL", "STRONG SELL"])
def test_an_actionable_sell_verdict_fires(verdict):
    ev = _evidence(records=[_record(verdict=verdict)])
    assert _evidence_decision(ev).triggers == ["case_broken"]
    assert case_broken_reasons(ev, 500.0) == [f"research verdict {verdict} (2026-10-22)"]


def test_a_verdict_that_is_not_an_actionable_sell_on_the_day_does_not_fire():
    for records in (
        [_record(verdict="NEUTRAL")],
        [_record(gate="abstain")],
        [_record(verdict="INSUFFICIENT DATA", gate="abstain")],
        # 24 Oct 00:01 IST: after the review day
        [_record(run_at="2026-10-23T18:31:00")],
        # superseded by a later actionable BUY
        [_record(run_at="2026-10-20T10:00:00"), _record(verdict="BUY")],
        # another company's
        [_record(symbol="BBB")],
    ):
        ev = _evidence(records=records)
        assert ev.research_verdict != "SELL", records
        assert _evidence_decision(ev).verdict == "HOLD"
    # 23 Oct 23:59 IST is still the review day; an abstained later run does not
    # hide the latest actionable one.
    assert _evidence(records=[_record(run_at="2026-10-23T18:29:00")]).research_verdict == "SELL"
    assert _evidence(records=[_record(), _record(verdict="BUY", run_at="2026-10-23T05:00:00",
                                                 gate="abstain")]).research_verdict == "SELL"


def test_the_invalidation_level_fires_at_the_level_and_not_a_paisa_above():
    ev = _evidence(ideas=[_idea(level=455.0)])
    assert _evidence_decision(ev, close=455.0).triggers == ["case_broken"]
    assert _evidence_decision(ev, close=455.01).verdict == "HOLD"
    assert case_broken_reasons(ev, 450.0) == [
        "close 450.00 at or below the invalidation level 455.00 "
        "(shelf idea dived 2026-10-01, promoted)"]


def test_the_invalidation_level_is_the_latest_dive_on_or_before_the_review_day():
    ideas = [_idea(level=455.0, dived="2026-09-01", status="dropped"),
             _idea(level=470.0, dived="2026-10-10", status="promoted"),
             _idea(level=490.0, dived="2026-10-24", status="active"),     # after D
             _idea("BBB", level=600.0, dived="2026-10-22")]
    assert xs.invalidation_for(ideas, "AAA", D) == (
        470.0, "shelf idea dived 2026-10-10, promoted", date(2026, 10, 10))
    assert xs.invalidation_for([_idea(level=0.0)], "AAA", D) == (0.0, "", None)
    assert xs.invalidation_for(ideas, "CCC", D) == (0.0, "", None)


def test_within_the_minimum_holding_period_only_stops_fire():
    sell = [_record()]
    at_nine = _evidence(sessions=9, records=sell)
    at_ten = _evidence(sessions=10, records=sell)
    assert (at_nine.sessions_held, at_ten.sessions_held) == (9, 10)
    assert _evidence_decision(at_nine).verdict == "HOLD"
    assert _evidence_decision(at_ten).triggers == ["case_broken"]
    # The stop does not wait: one session in, a 20% loss against a 12% stop.
    one = _evidence(sessions=1, records=sell)
    holding = _holding("AAA", 500.0, sessions=1)
    sig = _signals("AAA", close=400.0, pnl=-20.0)
    legacy, by_evidence = _both(sig, holding, one)
    assert legacy.triggers == by_evidence.triggers == ["stop_breach"]
    # The record still names the broken reason while the rule waits.
    row = xs.shadow_row(on=D, user_id="u1", mode="shadow", close=500.0,
                        legacy=decide(_signals(), holding, "balanced"),
                        evidence_rec=decide(_signals(), holding, "balanced",
                                            exit_rule="evidence", evidence=at_nine),
                        evidence=at_nine, buy_date=holding.buy_date)
    assert row.case_broken_reasons == ["research verdict SELL (2026-10-22)"]
    assert row.evidence_verdict == "HOLD" and row.disagree is False


def test_no_evidence_never_fires_and_an_unknown_rule_is_refused():
    assert case_broken_reasons(None, 1.0) == []
    rec = decide(_signals(), _holding(), "balanced", exit_rule="evidence", evidence=None)
    assert rec.verdict == "HOLD"
    with pytest.raises(ValueError):
        decide(_signals(), _holding(), "balanced", exit_rule="shadow")


def test_an_unreadable_source_is_named_not_silent():
    class Broken:
        def load(self, symbol):
            raise OSError("disk gone")
    reader = xs.EvidenceReader([_idea()], event_store=Broken(),
                               score_records=lambda s: [_record()])
    ev = reader.read(_holding(), D)
    assert ev.gaps == ["company events unread: disk gone"]
    assert ev.research_verdict == "SELL" and ev.invalidation_level == 455.0


# -- Property: the stops are the same code under both rules ------------------------------

def _random_case(rnd: random.Random):
    price = rnd.uniform(50, 2000)
    close = price * rnd.uniform(0.6, 1.6)
    peak = rnd.choice([None, close * rnd.uniform(1.0, 1.6), price * rnd.uniform(0.8, 1.5)])
    sig = AdvisorSignals(
        symbol="AAA", sector=rnd.choice(["automobile", "it"]), close=close,
        atr_stop_pct=rnd.uniform(8, 22), unrealised_pnl_pct=(close / price - 1) * 100,
        holding_age_days=rnd.randint(0, 400), regime_label=rnd.choice(
            ["NORMAL", "RISK_OFF", "MACRO_CRISIS"]),
        thesis_intact=rnd.choice([None, True, False]),
        reforecast_reason=rnd.choice(["", "external_shock", "thesis_break", "preopen_shock",
                                      "Thesis break on 2026-10-22: ..."]),
        envelope_direction=rnd.choice(["UP", "DOWN", "FLAT"]),
        confidence_trend=rnd.uniform(-0.2, 0.2), reversion_prior=rnd.uniform(0, 0.4),
        direction_accuracy_7d=rnd.choice([None, rnd.uniform(0, 1)]),
        position_weight_pct=rnd.uniform(0, 15), sector_weight_pct=rnd.uniform(0, 40),
        confidence=rnd.uniform(0.2, 0.9), peak_close_since_entry=peak)
    holding = Holding(symbol="AAA", sector=sig.sector, qty=10, avg_buy_price=price,
                      adj_avg_price=price, adj_qty=10, buy_date="2026-01-05")
    ev = ExitEvidence(
        sessions_held=rnd.choice([None, rnd.randint(0, 40)]),
        negative_events=rnd.choice([[], [{"id": "e", "published_at": "2026-10-22",
                                          "category": "results", "what": "w"}]]),
        research_verdict=rnd.choice(["", "BUY", "SELL", "STRONG SELL", "NEUTRAL"]),
        research_run_at="2026-10-22T10:00:00",
        invalidation_level=rnd.choice([0.0, close * rnd.uniform(0.8, 1.2)]))
    return sig, holding, ev


def test_property_stops_fire_exactly_when_the_legacy_rule_fires_them():
    rnd = random.Random(20261023)
    seen = {"stop_breach": 0, "trailing_stop_breach": 0, "case_broken": 0, "thesis_break": 0}
    for _ in range(4000):
        sig, holding, ev = _random_case(rnd)
        legacy, by_evidence = _both(sig, holding, ev)
        for code in ("stop_breach", "trailing_stop_breach", "shock_reforecast",
                     "crisis_regime_bearish"):
            assert (code in legacy.triggers) == (code in by_evidence.triggers), (code, sig, ev)
        if "stop_breach" in legacy.triggers or "trailing_stop_breach" in legacy.triggers:
            assert by_evidence.verdict in ("EXIT", "SWITCH")
        assert "case_broken" not in legacy.triggers and "thesis_break" not in by_evidence.triggers
        if "thesis_break" not in legacy.triggers and "case_broken" not in by_evidence.triggers:
            assert (legacy.verdict, legacy.triggers, legacy.notes, legacy.rationale_hash) == \
                (by_evidence.verdict, by_evidence.triggers, by_evidence.notes,
                 by_evidence.rationale_hash)
        for code in seen:
            seen[code] += code in legacy.triggers or code in by_evidence.triggers
    assert all(n > 50 for n in seen.values()), seen      # every branch was exercised


# -- The mode switch ----------------------------------------------------------------------

def test_shadow_is_the_default_and_an_unknown_value_reads_as_shadow(monkeypatch):
    assert xs.exit_rule_mode() == "shadow"            # config.yaml as shipped
    import backend.shared.config.settings.loader as loader
    for value, mode in (("legacy", "legacy"), (" Evidence ", "evidence"),
                        ("evidense", "shadow"), ("", "shadow"), (None, "shadow")):
        monkeypatch.setattr(loader, "cfg", lambda key, fallback=None, v=value: v)
        assert xs.exit_rule_mode() == mode
    assert xs.acting_rule("shadow") == xs.acting_rule("legacy") == "legacy"
    assert xs.acting_rule("evidence") == "evidence"


# -- The pipeline end to end, in each mode --------------------------------------------------

AAA_EXAMPLE = dict(close=480.0, pnl=-4.0, thesis_intact=False, envelope_direction="DOWN")


def _pipeline_world(monkeypatch, tmp_path, mode):
    """Four holdings on D, prices and events stubbed:
    AAA the ₹500 example (legacy EXIT, evidence HOLD);
    BBB an actionable SELL, held 20 sessions (legacy HOLD, evidence EXIT);
    CCC a stop breach (both EXIT); DDD nothing (both HOLD)."""
    import core.portfolio.autopilot as ap
    import core.portfolio.pipeline as pipeline
    from core.events.store import EventStore
    from core.portfolio.pricing import SessionClose
    from core.portfolio.store import PortfolioStore

    port_dir = tmp_path / "portfolio"
    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(port_dir))
    monkeypatch.setattr(settings, "AUTOPILOT_ENABLED", True)
    store = PortfolioStore(user_id="u1", base_dir=str(port_dir))
    store.save(Portfolio(user_id="u1", cash_deployable=10_000.0, capital_in=50_000.0,
                         autopilot=True, holdings=[
                             _holding("AAA", 500.0, sessions=4),
                             _holding("BBB", 200.0, sessions=20),
                             _holding("CCC", 100.0, sessions=20),
                             _holding("DDD", 300.0, sessions=20)]))
    closes = {"AAA": 480.0, "BBB": 190.0, "CCC": 80.0, "DDD": 310.0}
    signals = {"AAA": AAA_EXAMPLE, "BBB": dict(close=190.0, pnl=-5.0),
               "CCC": dict(close=80.0, pnl=-20.0), "DDD": dict(close=310.0, pnl=3.3)}

    events = EventStore(tmp_path / "events")
    events.append_new("DDD", [_event("DDD", direction="positive")])
    monkeypatch.setattr(xs.EvidenceReader, "_event_store", lambda self: events)
    monkeypatch.setattr(xs.EvidenceReader, "_score_records", lambda self, s: [
        _record("BBB", "SELL"), _record("AAA", "BUY")])
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load",
                        lambda self: Shelf(ideas=[_idea("AAA", 455.0)]))
    monkeypatch.setattr("core.discovery.candidates.buy_candidates",
                        lambda portfolio, on, ideas, **k: ([], {}))
    monkeypatch.setattr(pipeline, "build_signals",
                        lambda h, *a, **k: _signals(h.symbol, **signals[h.symbol]))
    monkeypatch.setattr(pipeline, "session_close", lambda sym, d: (
        SessionClose(closes[sym], D, "agree"), D))
    monkeypatch.setattr(pipeline, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "n")
    monkeypatch.setattr(pipeline, "holding_identity_issue", lambda h, d: "")
    monkeypatch.setattr(pipeline, "symbol_identity_issue", lambda s, d: "")
    monkeypatch.setattr(pipeline, "resolve_identity",
                        lambda s, d: type("I", (), {"stamp": lambda self: {}})())
    monkeypatch.setattr("core.delivery.alerts.emit_alerts", lambda *a, **k: {"emitted": 0})
    monkeypatch.setattr("core.delivery.channels.deliver", lambda *a, **k: {"delivered": False})
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-10-23T11:00:00+00:00")
    import backend.shared.config.settings.loader as loader
    real_cfg = loader.cfg
    monkeypatch.setattr(loader, "cfg", lambda path, *a, **k: (
        mode if path == "advisor.exit_rule" else real_cfg(path, *a, **k)))
    return store


def _ledgers(store):
    folder = store._dir
    return {name: (folder / name).read_bytes() if (folder / name).exists() else b""
            for name in ("advice_ledger.jsonl", "transactions.jsonl")}


def _run(monkeypatch, tmp_path, mode):
    import core.portfolio.pipeline as pipeline
    store = _pipeline_world(monkeypatch, tmp_path / mode, mode)
    result = pipeline.run_post_review_pipeline(D)
    assert result["status"] == "completed" and result["advice"] == 4
    return store


def test_shadow_decisions_and_transactions_are_byte_identical_to_legacy(monkeypatch, tmp_path):
    legacy = _run(monkeypatch, tmp_path, "legacy")
    shadow = _run(monkeypatch, tmp_path, "shadow")
    evidence = _run(monkeypatch, tmp_path, "evidence")
    assert _ledgers(shadow) == _ledgers(legacy)
    # The portfolio too, but for the wall-clock time of its save.
    held = lambda s: s.load().model_dump(exclude={"updated_at"})
    assert held(shadow) == held(legacy)
    # The comparison can see a difference: under evidence the sales differ.
    sold = lambda s: sorted(t.symbol for t in s.load_transactions() if t.side == "SELL")
    assert sold(legacy) == sold(shadow) == ["AAA", "CCC"]
    assert sold(evidence) == ["BBB", "CCC"]
    assert _ledgers(evidence) != _ledgers(legacy)
    # legacy records nothing; shadow and evidence record both rules.
    assert legacy.load_exit_shadow() == []
    for store, mode in ((shadow, "shadow"), (evidence, "evidence")):
        rows = {r["symbol"]: r for r in store.load_exit_shadow()}
        assert sorted(rows) == ["AAA", "BBB", "CCC", "DDD"]
        assert {r["mode"] for r in rows.values()} == {mode}
        assert (rows["AAA"]["legacy_verdict"], rows["AAA"]["evidence_verdict"]) == ("EXIT", "HOLD")
        assert rows["AAA"]["legacy_triggers"] == ["thesis_break"]
        assert (rows["BBB"]["legacy_verdict"], rows["BBB"]["evidence_verdict"]) == ("HOLD", "EXIT")
        assert rows["BBB"]["case_broken_reasons"] == ["research verdict SELL (2026-10-22)"]
        assert rows["CCC"]["legacy_triggers"] == rows["CCC"]["evidence_triggers"] == ["stop_breach"]
        assert [s for s, r in sorted(rows.items()) if r["disagree"]] == ["AAA", "BBB"]
        assert rows["DDD"]["evidence"]["event_ids"] == []     # a positive event is not evidence
    advice = {a.symbol: a for a in evidence.load_advice()}
    assert advice["BBB"].triggers == ["case_broken"] and advice["AAA"].verdict == "HOLD"


def test_one_shadow_row_per_holding_per_review_day_however_often_it_runs(monkeypatch, tmp_path):
    import core.portfolio.pipeline as pipeline
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    for _ in range(3):
        pipeline.run_post_review_pipeline(D)
    rows = store.load_exit_shadow()
    assert sorted((r["date"], r["symbol"]) for r in rows) == [
        (D.isoformat(), s) for s in ("AAA", "BBB", "CCC", "DDD")]
    # The store refuses a repeat whatever its content; the first row wins.
    first = next(r for r in rows if r["symbol"] == "DDD")
    from backend.shared.schemas.portfolio import ExitShadowRow
    again = ExitShadowRow(**{**first, "evidence_verdict": "EXIT", "disagree": True})
    assert store.append_exit_shadow_once([again, again]) == 0
    assert next(r for r in store.load_exit_shadow() if r["symbol"] == "DDD") == first


def test_a_failing_evidence_read_never_changes_the_acting_decision(monkeypatch, tmp_path):
    import core.portfolio.pipeline as pipeline
    legacy = _run(monkeypatch, tmp_path, "legacy")
    store = _pipeline_world(monkeypatch, tmp_path / "broken", "shadow")

    def boom(self, holding, on):
        raise RuntimeError("evidence store down")
    monkeypatch.setattr(xs.EvidenceReader, "read", boom)
    pipeline.run_post_review_pipeline(D)
    assert _ledgers(store) == _ledgers(legacy)
    rows = store.load_exit_shadow()
    assert len(rows) == 4 and all(r["evidence"]["gaps"] == ["no evidence assembled"] for r in rows)


# -- Grading ---------------------------------------------------------------------------------

def _row(day: date, symbol="AAA", evidence_verdict="HOLD", legacy_verdict="EXIT",
         close=100.0, disagree=True, buy_date="2026-05-04", price_bar_date=""):
    """A stored row, as the pipeline writes it. Rows of one symbol are one
    holding (one decision) unless `buy_date` says it was bought again."""
    return {"date": day.isoformat(), "symbol": symbol, "close": close, "mode": "shadow",
            "buy_date": buy_date, "price_bar_date": price_bar_date,
            "legacy_verdict": legacy_verdict, "evidence_verdict": evidence_verdict,
            "disagree": disagree}


def test_grading_by_hand_and_only_from_prices_up_to_the_horizon():
    """Decided 1 Sep at ₹100, Nifty 1000. Ten sessions on (15 Sep): stock
    ₹95 (-5%), Nifty 990 (-1%), excess -4 points: keeping was wrong, so the
    evidence rule's HOLD is wrong and its EXIT right. Thirty sessions on
    (13 Oct) the stock is ₹110 (+10%) and the Nifty 1000 (0%): +10 points."""
    decided = date(2026, 9, 1)
    d10, d30 = trading_days_after(decided, 10), trading_days_after(decided, 30)
    stock = {d10: 95.0, d30: 110.0}
    nifty = {decided: 1000.0, d10: 990.0, d30: 1000.0}
    asked: list = []

    def stock_close(symbol, d):
        asked.append(("stock", symbol, d))
        return stock[d]

    def bench_close(d):
        asked.append(("nifty", d))
        return nifty[d]

    rows = [_row(decided, "AAA", "HOLD"), _row(decided, "BBB", "EXIT", "HOLD"),
            _row(decided, "CCC", "HOLD", "HOLD", disagree=False)]
    grades = xs.grade_disagreements(rows, as_of=d30, stock_close_on=stock_close,
                                    bench_close_on=bench_close)
    got = {(g["symbol"], g["horizon_td"]): (g["status"], g["excess_pct"], g["right"])
           for g in grades}
    assert got == {("AAA", 10): ("graded", -4.0, False), ("AAA", 30): ("graded", 10.0, True),
                   ("BBB", 10): ("graded", -4.0, True), ("BBB", 30): ("graded", 10.0, False)}
    stock_days = {d for kind, *_, d in asked if kind == "stock"}
    nifty_days = {d for kind, *_, d in asked if kind == "nifty"}
    assert stock_days == {d10, d30}                    # after the decision, never past the horizon
    assert nifty_days == {decided, d10, d30}

    # A day before the 30-session close the 30-session grade is pending, and
    # nothing at or after its day is read.
    asked.clear()
    early = xs.grade_disagreements(rows[:1], as_of=d30 - timedelta(days=1),
                                   stock_close_on=stock_close, bench_close_on=bench_close)
    assert [(g["horizon_td"], g["status"], g["right"]) for g in early] == [
        (10, "graded", False), (30, "pending", None)]
    assert asked and all(d < d30 for _kind, *_, d in asked)
    # A row decided after the look is not graded at all.
    assert xs.grade_disagreements([_row(d30)], as_of=d10, stock_close_on=stock_close,
                                  bench_close_on=bench_close) == []


def test_a_missing_price_is_ungraded_never_a_result():
    decided = date(2026, 9, 1)
    grades = xs.grade_disagreements(
        [_row(decided)], as_of=date(2026, 12, 1),
        stock_close_on=lambda s, d: (_ for _ in ()).throw(LookupError("no close")),
        bench_close_on=lambda d: 1000.0)
    assert [(g["status"], g["right"]) for g in grades] == [("ungraded", None)] * 2


# -- The switch gate ---------------------------------------------------------------------------

def _grades(n=16, right10=8, right30=8, symbols=8, span_days=60, ungraded10=0):
    """`n` matured disagreements over `symbols` stocks, review days spread
    over `span_days`; the evidence rule right on the first `right10` at 10
    sessions and the first `right30` at 30. `ungraded10` of the wrong ones at
    10 sessions have no grade instead."""
    out = []
    start = date(2026, 6, 1)
    for i in range(n):
        day = (start + timedelta(days=round(i * span_days / max(1, n - 1)))).isoformat()
        sym = f"S{i % symbols}"
        for h, right in ((10, i < right10), (30, i < right30)):
            status = "graded"
            if h == 10 and not right and i >= n - ungraded10:
                status = "ungraded"
            out.append({"date": day, "symbol": sym, "horizon_td": h, "status": status,
                        "right": right if status == "graded" else None,
                        "excess_pct": 0.0, "evidence_sold": False, "matures": day})
    return out


def test_the_gate_passes_at_exactly_half_at_both_horizons():
    look = xs.gate_look(_grades())
    assert look["status"] == xs.PASS and look["matured"] == 16
    assert look["right"] == {"10": 8, "30": 8} and look["span_days"] == 60
    assert xs.recommends(look, {"status": xs.PASS}) is True
    assert xs.recommends(look, None) is False
    assert xs.recommends(look, {"status": xs.FAIL}) is False
    assert xs.recommends(look, {"status": xs.NOT_ENOUGH}) is False


def test_a_pass_at_30_with_a_fail_at_10_does_not_recommend_nor_the_reverse():
    at30_only = xs.gate_look(_grades(right10=7, right30=9))
    at10_only = xs.gate_look(_grades(right10=9, right30=7))
    assert at30_only["status"] == at10_only["status"] == xs.FAIL
    assert at30_only["reasons"] == ["right on 7 of 16 at 10 sessions (needs 50%)"]
    assert at10_only["reasons"] == ["right on 7 of 16 at 30 sessions (needs 50%)"]
    for look in (at30_only, at10_only):
        assert xs.recommends(look, {"status": xs.PASS}) is False


def test_a_missing_grade_counts_against_the_evidence_rule():
    # 8 of 16 right at 10 sessions passes; with one of the right ones
    # replaced by a missing grade it reads 7 of 16 and fails.
    look = xs.gate_look(_grades(right10=7, ungraded10=1))
    assert look["status"] == xs.FAIL and look["right"]["10"] == 7


def test_too_few_too_close_together_or_one_stock_too_many_never_passes():
    few = xs.gate_look(_grades(n=14, right10=14, right30=14))
    assert few["status"] == xs.NOT_ENOUGH
    assert few["reasons"] == ["14 of the 15 decisions it needs have reached 30 sessions"]
    close = xs.gate_look(_grades(n=15, right10=15, right30=15, span_days=55))
    assert close["status"] == xs.NOT_ENOUGH
    assert close["reasons"] == ["they span 55 days of the 56 (8 weeks) it needs"]
    assert xs.gate_look(_grades(n=15, right10=15, right30=15, span_days=56))["status"] == xs.PASS
    # 5 of 16 from one stock is 31%; 5 of 17 is 29%.
    lopsided = _grades(n=16, right10=16, right30=16, symbols=16)
    for g in lopsided:
        if g["symbol"] in ("S1", "S2", "S3", "S4"):
            g["symbol"] = "S0"
    assert xs.gate_look(lopsided)["reasons"] == ["S0 is 5 of the 16 (more than 30%)"]
    seventeen = _grades(n=17, right10=17, right30=17, symbols=17)
    for g in seventeen:
        if g["symbol"] in ("S1", "S2", "S3", "S4"):
            g["symbol"] = "S0"
    assert xs.gate_look(seventeen)["status"] == xs.PASS
    # Exactly 30% (6 of 20) is not more than 30%; 7 of 20 is.
    for crowd, status in ((6, xs.PASS), (7, xs.FAIL)):
        twenty = _grades(n=20, right10=20, right30=20, symbols=20)
        for g in twenty:
            if g["symbol"] in {f"S{i}" for i in range(1, crowd)}:
                g["symbol"] = "S0"
        assert xs.gate_look(twenty)["status"] == status, crowd


def test_only_disagreements_past_30_sessions_count():
    grades = _grades(n=15, right10=15, right30=15)
    for g in grades[-2:]:                      # the last one is short of 30 sessions
        if g["horizon_td"] == 30:
            g.update(status="pending", right=None)
    look = xs.gate_look(grades)
    assert look["matured"] == 14 and look["status"] == xs.NOT_ENOUGH


# -- The weekly scorecard -----------------------------------------------------------------------

def _matured_rows():
    """16 decisions over 8 stocks (each stock held twice), 26 Jun to 24 Aug,
    every one an evidence EXIT the legacy rule held, decided at ₹100."""
    days = [date(2026, 6, 26) + timedelta(days=4 * i) for i in range(16)]
    return [_row(d if is_trading_day(d) else trading_days_after(d, 1), f"S{i % 8}", "EXIT",
                 "HOLD", buy_date=(d - timedelta(days=20)).isoformat())
            for i, d in enumerate(days)]


def test_the_scorecard_shows_the_tally_and_recommends_only_on_two_passing_weeks(tmp_path):
    from core.portfolio import results as R
    from core.portfolio.store import PortfolioStore

    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    assert store.load().holdings == []         # every graded stock was sold long ago
    late = date(2026, 11, 12)
    assert is_trading_day(late) and trading_days_after(late, 10) > date(2026, 11, 22)
    rows = _matured_rows()
    with open(tmp_path / "u1" / "exit_shadow.jsonl", "w", encoding="utf-8") as fh:
        for r in rows + [_row(late, "S9", "EXIT", "HOLD"),       # short of 10 sessions
                         _row(late, "S8", disagree=False),
                         _row(date(2026, 12, 10), "S7", "EXIT", "HOLD")]:   # after every look
            fh.write(json.dumps({**r, "user_id": "u1"}) + "\n")
    # Every sold stock then trailed the Nifty by 5 points: the evidence rule was right.
    kw = dict(store=store, audit_store=type("A", (), {"load_all": lambda self: []})(),
              close_on=lambda d: 1000.0, stock_close_on=lambda s, d: 95.0)

    first = R.weekly_scorecard("u1", date(2026, 11, 14), today=date(2026, 11, 14), **kw)
    block = first["exit_rule"]
    assert (block["rows"], block["decisions"], block["repeat_days"]) == (18, 17, 0)
    assert block["tally"] == [
        {"horizon_td": 10, "graded": 16, "right": 16, "ungraded": 0, "pending": 1},
        {"horizon_td": 30, "graded": 16, "right": 16, "ungraded": 0, "pending": 1}]
    assert block["gate"]["status"] == xs.PASS and block["recommend"] is False
    line = next(l["text"] for l in first["lines"] if l.get("label") == "Exit rule test")
    assert line == (
        "The price-path rule and the evidence rule disagreed on 17 decisions in 18 "
        "holding-days reviewed; at 10 sessions it was right on 16 of 16; at 30 sessions it "
        "was right on 16 of 16. 1 short of 10 sessions; 1 short of 30 sessions. "
        "Switch gate: passed this week; it must pass again next week.")

    second = R.weekly_scorecard("u1", date(2026, 11, 21), today=date(2026, 11, 21), **kw)
    assert second["exit_rule"]["recommend"] is True
    text = "\n".join(R.render_scorecard_text(second))
    assert "Exit rule test:" in text and "passed two weeks running" in text

    # A week with no stored look breaks the run.
    third = R.weekly_scorecard("u1", date(2026, 12, 5), today=date(2026, 12, 5), **kw)
    assert third["exit_rule"]["gate"]["status"] == xs.PASS
    assert third["exit_rule"]["recommend"] is False


def test_a_scorecard_without_shadow_rows_has_no_exit_line(tmp_path):
    from core.portfolio import results as R
    from core.portfolio.store import PortfolioStore

    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    row = R.weekly_scorecard("u1", date(2026, 11, 14), store=store,
                             audit_store=type("A", (), {"load_all": lambda self: []})(),
                             close_on=lambda d: 1000.0, stock_close_on=lambda s, d: 95.0,
                             today=date(2026, 11, 14))
    assert row["exit_rule"]["rows"] == 0 and row["exit_rule"]["gate"]["status"] == xs.NOT_ENOUGH
    assert not any(l.get("label") == "Exit rule test" for l in row["lines"])


# == Rework 1 (fresh review F1, F2, L1) ==========================================================
#
# F1: the invalidation level is set in the rupees of its deep dive's close. It is compared with
# the review day's close only in the same price basis: divided by every bonus or split that went
# ex after the dive, or not used at all (a named gap) when that basis cannot be established.
# F2: a holding (symbol and buy date) is one decision, on its first disagreeing day.

SPLIT_SEP = {"subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- "
                        "Per Share", "exDate": "10-Sep-2026"}


def _applied(*rows, symbol="AAA"):
    """The holding's applied actions, as the sync stores them: NSE rows parsed."""
    from core.portfolio.corp_actions import parse_action
    return [parse_action(dict(r, symbol=symbol)) for r in rows]


def _held(buy_date: str, *applied, price=500.0, symbol="AAA"):
    h = Holding(symbol=symbol, sector="automobile", qty=10, avg_buy_price=price,
                adj_avg_price=price, adj_qty=10, buy_date=buy_date)
    h.applied_actions = list(applied)
    return h


def test_a_split_before_the_buy_and_a_bonus_after_it_both_divide_the_level():
    """Dived 1 Sep with the level ₹900. A 10→2 face-value split (×5 shares) goes ex 10 Sep;
    bought 15 Sep; a 1:1 bonus goes ex 21 Oct, which the sync applied to the holding and NSE
    still lists, worded differently today (so under another key). By hand: 900 / 5 / 2 = ₹90.00. The
    bonus counts once, from the holding's record (45 if twice); the split is only in NSE's
    list (180 if it were missed)."""
    from core.portfolio.corp_actions import action_record
    relisted = {"subject": "Bonus 1 : 1 (record date 21-Oct-2026)", "exDate": "21-Oct-2026"}
    nse = action_record([DIVIDEND_AUG, SPLIT_SEP, relisted], "AAA")
    holding = _held("2026-09-15", *_applied(BONUS_OCT))
    assert nse.actions[-1].key != holding.applied_actions[0].key
    level, note, gap = xs.level_in_basis(900.0, date(2026, 9, 1), holding, D, nse)
    assert (round(level, 6), gap) == (90.0, "")
    assert note == ("900.00 at the dive, adjusted for the split ex 2026-09-10 (÷5), "
                    "the bonus ex 2026-10-21 (÷2)")
    # Without NSE's list the split between the dive and the buy cannot be ruled out.
    level, _note, gap = xs.level_in_basis(900.0, date(2026, 9, 1), holding, D, None)
    assert level == 0.0 and gap == ("a bonus or split between the dive (2026-09-01) and the "
                                    "buy (2026-09-15) cannot be ruled out: NSE's list read "
                                    "today is empty or was not read")


def test_a_dive_after_the_buy_needs_only_the_holdings_own_record():
    """Bought 1 Sep. A 1:1 bonus goes ex 7 Sep; the stock is dived 10 Sep at the new price
    (level ₹300); another 1:1 bonus goes ex 21 Oct. Only the second one changes the dive's
    basis: 300 / 2 = ₹150.00, and no NSE list is needed. A dividend changes nothing."""
    sep = {"subject": "Bonus 1:1", "exDate": "07-Sep-2026"}
    holding = _held("2026-09-01", *_applied(sep, BONUS_OCT, DIVIDEND_AUG | {"exDate": "05-Oct-2026"}))
    assert [a.kind for a in holding.applied_actions] == ["bonus", "bonus", "dividend"]
    assert xs.level_in_basis(300.0, date(2026, 9, 10), holding, D, None) == (
        150.0, "300.00 at the dive, adjusted for the bonus ex 2026-10-21 (÷2)", "")
    # A bonus that goes ex after the review day is not yet in its basis.
    later = _held("2026-09-01", *_applied({"subject": "Bonus 1:1", "exDate": "26-Oct-2026"}))
    assert xs.level_in_basis(300.0, date(2026, 9, 10), later, D, None) == (300.0, "", "")


def test_a_level_whose_basis_cannot_be_established_is_never_used():
    """Each case leaves the level unused, so a close far below it fires nothing; each has a
    neighbour one day or one row away that is established."""
    from core.portfolio.corp_actions import action_record
    dive, bought = date(2026, 9, 22), _held("2026-09-23")
    nse = lambda *rows: action_record(list(rows), "AAA")                # noqa: E731
    div_on = lambda day: {"subject": "Dividend - Rs 2 Per Share", "exDate": day}  # noqa: E731
    cases = {
        # NSE's list must reach back to the dive day: on it yes, the day after no.
        "reaches the dive day": (nse(div_on("22-Sep-2026")), True),
        "starts the day after": (nse(div_on("23-Sep-2026")), False),
        "empty list": (nse(), False),
        "not read": (None, False),
        # A bonus on the dive day itself: the dive's close may be either side of it.
        "bonus on the dive day": (nse(DIVIDEND_AUG, {"subject": "Bonus 1:1",
                                                     "exDate": "22-Sep-2026"}), False),
        "bonus the day before": (nse(DIVIDEND_AUG, {"subject": "Bonus 1:1",
                                                    "exDate": "21-Sep-2026"}), True),
        # A split or bonus row that cannot be parsed, from the dive day on.
        "unreadable bonus after": (nse(DIVIDEND_AUG, {"subject": "Bonus issue",
                                                      "exDate": "09-Oct-2026"}), False),
        "unreadable bonus on the dive day": (nse(DIVIDEND_AUG, {"subject": "Bonus issue",
                                                                "exDate": "22-Sep-2026"}), False),
        "unreadable bonus before": (nse(DIVIDEND_AUG, {"subject": "Bonus issue",
                                                       "exDate": "21-Sep-2026"}), True),
    }
    for name, (record, established) in cases.items():
        ev = xs.exit_evidence(bought, D, ideas=[_idea(level=455.0, dived=dive.isoformat())],
                              actions=record)
        assert ev.invalidation_level_at_dive == 455.0, name
        if established:
            assert (ev.invalidation_level, ev.gaps) == (455.0, []), name
            continue
        assert ev.invalidation_level == 0.0 and ev.invalidation_source == "", name
        assert len(ev.gaps) == 1 and ev.gaps[0].startswith("invalidation level 455.00 not used: ")
        assert case_broken_reasons(ev, 100.0) == [], name
    # The gap names the cause.
    assert xs.level_in_basis(455.0, dive, bought, D, nse(div_on("23-Sep-2026")))[2] == (
        "a bonus or split between the dive (2026-09-22) and the buy (2026-09-23) cannot be "
        "ruled out: NSE's list read today starts 2026-09-23")
    assert xs.level_in_basis(455.0, dive, bought, D, cases["bonus on the dive day"][0])[2] == (
        "a bonus went ex on the dive day, 2026-09-22, so the dive's close may be on either "
        "side of it")
    assert xs.level_in_basis(455.0, dive, bought, D, cases["unreadable bonus after"][0])[2] == (
        "NSE lists a split or bonus on 2026-10-09 that could not be read, so its price basis "
        "is unknown")
    # Dived on the buy day: the holding's record starts the day after, so NSE's list is needed.
    same_day = _held("2026-09-22")
    assert xs.level_in_basis(455.0, dive, same_day, D, None)[0] == 0.0
    assert xs.level_in_basis(455.0, dive, same_day, D, nse(DIVIDEND_AUG))[0] == 455.0


def test_nse_rows_become_a_record_and_the_sync_applies_exactly_as_before(tmp_path):
    """The record keeps the parsed bonus and split rows, the earliest ex-date of any row (an
    AGM counts: it shows how far back the list reaches) and the ex-dates of split or bonus
    rows that could not be parsed (one also read as a dividend). The sync applies only the
    bonus after the buy, as before."""
    from core.portfolio.corp_actions import action_record, sync_corp_actions
    from core.portfolio.store import PortfolioStore
    rows = [DIVIDEND_AUG, SPLIT_SEP, BONUS_OCT,
            {"subject": "Annual General Meeting", "exDate": "01-Aug-2026"},
            {"subject": "Bonus issue (ratio to be announced)", "exDate": "30-Oct-2026"},
            {"subject": "Dividend Rs 2 and Bonus", "exDate": "05-Nov-2026"},
            {"subject": "Bonus 1:2"}]                                  # no ex-date: not read
    record = action_record(rows, "AAA")
    assert [(a.kind, a.ex_date, a.ratio) for a in record.actions] == [
        ("split", "2026-09-10", 5.0), ("bonus", "2026-10-21", 2.0)]
    assert record.covers_from == "2026-08-01"
    assert record.unparsed == ("2026-10-30", "2026-11-05")
    assert action_record([], "AAA").covers_from == ""

    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.save(Portfolio(user_id="u1", holdings=[_held("2026-09-15")]))
    result = sync_corp_actions(store, D, fetch=lambda sym: rows)
    held = store.load().holdings[0]
    assert result["applied"] == 1 and (held.adj_avg_price, held.adj_qty) == (250.0, 20.0)
    assert result["records"] == {"AAA": record}

    def boom(sym):
        raise OSError("NSE down")
    assert sync_corp_actions(store, D, fetch=boom)["records"] == {}


def _world(monkeypatch, tmp_path, mode, holdings, closes, ideas=(), records=(), nse=None,
           autopilot=True):
    """The pipeline world above, re-pointed at `holdings` with the REAL corp-action sync
    fetching `nse` (symbol -> NSE rows). The loss is computed from the holding's own
    (adjusted) basis, as build_signals does."""
    import core.portfolio.pipeline as pipeline
    from core.portfolio.corp_actions import sync_corp_actions
    from core.portfolio.pricing import SessionClose
    store = _pipeline_world(monkeypatch, tmp_path, mode)
    store.save(Portfolio(user_id="u1", cash_deployable=10_000.0, capital_in=50_000.0,
                         autopilot=autopilot, holdings=holdings))
    monkeypatch.setattr(pipeline, "session_close",
                        lambda sym, d: (SessionClose(closes[sym], d, "agree"), d))
    monkeypatch.setattr(pipeline, "build_signals", lambda h, p, d, ps, cal, close, **k: _signals(
        h.symbol, close=close, pnl=(close / h.adj_avg_price - 1) * 100))
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load",
                        lambda self: Shelf(ideas=list(ideas)))
    monkeypatch.setattr(xs.EvidenceReader, "_score_records", lambda self, s: list(records))
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: sync_corp_actions(
        s, d, fetch=lambda sym: list((nse or {}).get(sym, []))))
    return store


EEE_SOURCE = ("shelf idea dived 2026-09-22, promoted; 455.00 at the dive, adjusted for the "
              "bonus ex 2026-10-21 (÷2)")


@pytest.mark.parametrize("mode", ["shadow", "evidence"])
def test_r1_a_bonus_after_the_buy_halves_the_level_and_a_2pct_fall_fires_nothing(
        monkeypatch, tmp_path, mode):
    """The review's R1, as an invariant, through the real sync, pipeline and autopilot. EEE is
    dived 22 Sep at about ₹500 (level ₹455) and bought 23 Sep at ₹500. A 1:1 bonus goes ex
    21 Oct; NSE's list reaches back to 14 Aug. On 23 Oct EEE closes at ₹245, ₹490 in the old
    shares: down 2%. By hand the level is 455 / 2 = ₹227.50, so nothing fires; at ₹225 (₹450
    in old shares, −10%, inside the 12% stop) the evidence rule's level is crossed."""
    import core.portfolio.pipeline as pipeline
    assert _bought(20) == "2026-09-23"
    for close, broken in ((245.0, False), (225.0, True)):
        store = _world(monkeypatch, tmp_path / f"{mode}-{close:.0f}", mode,
                       holdings=[_holding("EEE", 500.0, sessions=20)], closes={"EEE": close},
                       ideas=[_idea("EEE", 455.0, dived="2026-09-22")],
                       records=[_record("EEE", "BUY")],
                       nse={"EEE": [DIVIDEND_AUG, BONUS_OCT]})
        pipeline.run_post_review_pipeline(D)
        advice = {a.symbol: a for a in store.load_advice()}
        row = next(r for r in store.load_exit_shadow() if r["symbol"] == "EEE")
        # The sync ran first: the stop judged the close against the ₹250 basis.
        assert "stop_breach" not in advice["EEE"].triggers and row["legacy_verdict"] == "HOLD"
        assert (row["evidence"]["invalidation_level"], row["evidence"]["invalidation_level_at_dive"],
                row["evidence"]["invalidation_source"], row["evidence"]["gaps"]) == (
            227.5, 455.0, EEE_SOURCE, [])
        sold = [t.symbol for t in store.load_transactions() if t.side == "SELL"]
        if not broken:
            assert row["case_broken_reasons"] == [] and row["evidence_triggers"] == []
            assert row["disagree"] is False and advice["EEE"].verdict == "HOLD" and sold == []
            continue
        assert row["case_broken_reasons"] == [
            f"close 225.00 at or below the invalidation level 227.50 ({EEE_SOURCE})"]
        assert row["evidence_verdict"] == "EXIT" and row["disagree"] is True
        assert sold == (["EEE"] if mode == "evidence" else [])


def test_r1_as_reviewed_nse_listing_only_the_bonus_leaves_the_level_unused(monkeypatch, tmp_path):
    """The review's exact R1: NSE's list holds only the bonus row, so it does not reach back to
    the dive and a bonus or split between the dive and the buy cannot be ruled out. The level
    is not used: nothing fires, at ₹245 or at ₹225, in either mode."""
    import core.portfolio.pipeline as pipeline
    for mode in ("shadow", "evidence"):
        for close in (245.0, 225.0):
            store = _world(monkeypatch, tmp_path / f"{mode}-{close:.0f}", mode,
                           holdings=[_holding("EEE", 500.0, sessions=20)],
                           closes={"EEE": close},
                           ideas=[_idea("EEE", 455.0, dived="2026-09-22")],
                           records=[_record("EEE", "BUY")], nse={"EEE": [BONUS_OCT]})
            pipeline.run_post_review_pipeline(D)
            row = next(r for r in store.load_exit_shadow() if r["symbol"] == "EEE")
            assert store.load().holdings[0].adj_avg_price == 250.0        # the sync applied it
            assert row["case_broken_reasons"] == [] and row["disagree"] is False
            assert row["evidence"]["invalidation_level"] == 0.0
            assert row["evidence"]["gaps"] == [
                "invalidation level 455.00 not used: a bonus or split between the dive "
                "(2026-09-22) and the buy (2026-09-23) cannot be ruled out: NSE's list read "
                "today starts 2026-10-21"]
            assert [t for t in store.load_transactions() if t.side == "SELL"] == []


def test_r2_a_standing_sell_over_five_days_is_one_decision(monkeypatch, tmp_path):
    """The review's R2 through the real pipeline: BBB (bought 23 Sep) has an actionable SELL;
    the price-path rule holds it on 26-30 Oct. Five rows, all naming the same holding, and
    one decision, on 26 Oct; the other four are later days of it."""
    import core.portfolio.pipeline as pipeline
    days = [date(2026, 10, 26) + timedelta(days=i) for i in range(5)]
    store = _world(monkeypatch, tmp_path, "shadow", holdings=[_holding("BBB", 200.0, sessions=20)],
                   closes={"BBB": 196.0}, records=[_record("BBB", "SELL")])
    for d in days:
        pipeline.run_post_review_pipeline(d)
    rows = store.load_exit_shadow()
    assert [(r["date"], r["buy_date"], r["price_bar_date"], r["disagree"]) for r in rows] == [
        (d.isoformat(), "2026-09-23", d.isoformat(), True) for d in days]
    decisions, later = xs.first_disagreements(rows)
    assert [r["date"] for r in decisions] == ["2026-10-26"] and later == 4
    block = xs.scorecard_block(rows, as_of=date(2026, 11, 1), stock_close_on=None,
                               bench_close_on=lambda d: 1000.0)
    assert (block["rows"], block["decisions"], block["repeat_days"]) == (5, 1, 4)
    assert [t["pending"] for t in block["tally"]] == [1, 1]


def test_r2_four_five_day_episodes_are_four_decisions_and_the_gate_says_not_yet(tmp_path):
    """The review's R2 gate through the real weekly scorecard: four stocks, each sold by the
    evidence rule and kept by the price-path rule on five consecutive review days, the episodes
    three weeks apart (Jun-Aug). S0 and S1 then fell 5% with the Nifty flat (selling was right),
    S2 and S3 rose 5%. By hand: 4 decisions, 2 right at both horizons, span 63 days: not yet,
    4 of the 15, two weeks running."""
    from core.portfolio import results as R
    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    store.load()
    rows = []
    for i, start in enumerate([date(2026, 6, 1), date(2026, 6, 22), date(2026, 7, 13),
                               date(2026, 8, 3)]):
        d = start
        for _ in range(5):
            rows.append(_row(d, f"S{i}", "EXIT", "HOLD", buy_date="2026-05-04"))
            d = trading_days_after(d, 1)
    with open(tmp_path / "u1" / "exit_shadow.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "user_id": "u1"}) + "\n")
    price = {"S0": 95.0, "S1": 95.0, "S2": 105.0, "S3": 105.0}
    kw = dict(store=store, audit_store=type("A", (), {"load_all": lambda self: []})(),
              close_on=lambda d: 1000.0, stock_close_on=lambda s, d: price[s])
    for sunday in (date(2026, 11, 14), date(2026, 11, 21)):
        card = R.weekly_scorecard("u1", sunday, today=sunday, **kw)
        block, look = card["exit_rule"], card["exit_rule"]["gate"]
        assert (block["rows"], block["decisions"], block["repeat_days"]) == (20, 4, 16)
        assert (look["status"], look["matured"], look["right"], look["span_days"]) == (
            xs.NOT_ENOUGH, 4, {"10": 2, "30": 2}, 63)
        assert block["recommend"] is False
        line = next(l["text"] for l in card["lines"] if l.get("label") == "Exit rule test")
        assert line == (
            "The price-path rule and the evidence rule disagreed on 4 decisions in 20 "
            "holding-days reviewed (a holding counts once, on the first day the rules "
            "differed; 16 later days of the same disagreements are not counted); at 10 "
            "sessions it was right on 2 of 4; at 30 sessions it was right on 2 of 4. "
            "Switch gate: not yet (4 of the 15 decisions it needs have reached 30 sessions).")


def test_a_stock_bought_again_later_is_a_second_decision():
    """S0 bought 4 May disagrees on 1, 2 and 3 Jun: one decision. Sold, bought again on
    15 Jun, it disagrees on 22 Jun: a second decision."""
    rows = [_row(date(2026, 6, d), "S0", "EXIT", "HOLD", buy_date="2026-05-04") for d in (1, 2, 3)]
    rows.append(_row(date(2026, 6, 22), "S0", "EXIT", "HOLD", buy_date="2026-06-15"))
    decisions, later = xs.first_disagreements(rows)
    assert [(r["date"], r["buy_date"]) for r in decisions] == [
        ("2026-06-01", "2026-05-04"), ("2026-06-22", "2026-06-15")]
    assert later == 2
    grades = xs.grade_disagreements(rows, as_of=date(2026, 12, 31), stock_close_on=lambda s, d: 95.0,
                                    bench_close_on=lambda d: 1000.0)
    assert sorted({(g["date"], g["buy_date"]) for g in grades}) == [
        ("2026-06-01", "2026-05-04"), ("2026-06-22", "2026-06-15")]


def test_a_price_path_sale_that_repeats_is_one_decision(monkeypatch, tmp_path):
    """A portfolio without the autopilot: the price-path rule's EXIT on AAA (the ₹500
    example) is advice nobody executes, so AAA is still held the next days and the EXIT
    repeats; BBB's standing SELL repeats too. Through the real pipeline on 23, 26 and 27 Oct:
    12 rows, 2 decisions (AAA kept by the evidence rule, BBB sold by it), 4 later days."""
    import core.portfolio.pipeline as pipeline
    store = _pipeline_world(monkeypatch, tmp_path, "shadow")
    portfolio = store.load()
    portfolio.autopilot = False
    store.save(portfolio)
    for d in (D, date(2026, 10, 26), date(2026, 10, 27)):
        pipeline.run_post_review_pipeline(d)
    rows = store.load_exit_shadow()
    assert len(rows) == 12 and sum(r["disagree"] for r in rows) == 6
    decisions, later = xs.first_disagreements(rows)
    assert [(r["date"], r["symbol"], xs.sells(r["evidence_verdict"])) for r in decisions] == [
        ("2026-10-23", "AAA", False), ("2026-10-23", "BBB", True)]
    assert later == 4


def test_later_days_never_reach_the_gate_count_span_or_share():
    """All decisions right at both horizons. Later days of S0's holding never count:
    - 14 decisions and 10 later days of one of them: not enough (14 of 15); a 15th holding passes;
    - 15 decisions within 50 days and later days to day 70: the span is 50 days;
    - 15 decisions, 4 of them S0's (27%), with 6 later days: S0 is still 4 of 15, and it passes
      (counting the days, S0 would be 10 of 21, 48%)."""
    start = date(2026, 6, 1)

    def look(spec, later_days=()):
        rows = [_row(start + timedelta(days=offset), sym, "EXIT", "HOLD",
                     buy_date=f"2026-05-{n + 1:02d}") for n, (sym, offset) in enumerate(spec)]
        s0 = rows[0]
        rows += [{**s0, "date": (start + timedelta(days=o)).isoformat()} for o in later_days]
        block = xs.scorecard_block(rows, as_of=date(2026, 12, 31),
                                   stock_close_on=lambda s, d: 95.0, bench_close_on=lambda d: 1000.0)
        return block["gate"], block["repeat_days"]

    fourteen = [(f"S{i}", round(i * 60 / 13)) for i in range(14)]
    gate, later = look(fourteen, later_days=range(1, 11))
    assert (gate["status"], gate["matured"], later) == (xs.NOT_ENOUGH, 14, 10)
    gate, _ = look(fourteen + [("S14", 30)], later_days=range(1, 11))
    assert (gate["status"], gate["matured"]) == (xs.PASS, 15)

    fifty = [(f"S{i}", round(i * 50 / 14)) for i in range(15)]
    gate, later = look(fifty, later_days=(55, 60, 70))
    assert (gate["status"], gate["span_days"], later) == (xs.NOT_ENOUGH, 50, 3)

    crowd = [("S0" if i < 4 else f"S{i}", i * 4) for i in range(15)]
    gate, later = look(crowd, later_days=(1, 2, 3, 5, 6, 7))
    assert (gate["status"], gate["top_stock"], gate["top_stock_count"], later) == (
        xs.PASS, "S0", 4, 6)


def test_a_carried_forward_close_is_graded_from_its_own_session():
    """L1. Reviewed Wednesday 2 Sep with Tuesday 1 Sep's close carried forward (₹100). The
    Nifty is read on 1 Sep (1000), not 2 Sep (1010). Ten sessions on (17 Sep) the stock is ₹95
    (−5%) and the Nifty 990 (−1%): excess −4 points (from 2 Sep it would be −3.02)."""
    decided, bar = date(2026, 9, 2), date(2026, 9, 1)
    d10, d30 = trading_days_after(decided, 10), trading_days_after(decided, 30)
    nifty = {bar: 1000.0, decided: 1010.0, d10: 990.0, d30: 990.0}
    asked = []

    def bench(d):
        asked.append(d)
        return nifty[d]
    rows = [_row(decided, "AAA", "HOLD", price_bar_date=bar.isoformat())]
    grades = xs.grade_disagreements(rows, as_of=d30, stock_close_on=lambda s, d: 95.0,
                                    bench_close_on=bench)
    assert [(g["horizon_td"], g["priced"], g["excess_pct"]) for g in grades] == [
        (10, "2026-09-01", -4.0), (30, "2026-09-01", -4.0)]
    assert set(asked) == {bar, d10, d30}
    # A bar date after the review day is not a session the close could come from.
    odd = [_row(decided, "AAA", "HOLD", price_bar_date="2026-09-03")]
    assert {g["priced"] for g in xs.grade_disagreements(
        odd, as_of=d30, stock_close_on=lambda s, d: 95.0, bench_close_on=bench)} == {"2026-09-02"}
