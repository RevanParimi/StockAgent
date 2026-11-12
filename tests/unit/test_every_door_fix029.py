"""FIX-029 — every door to a buy reads the same facts: the day's regime, the
sale and the verdict.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test.

World (SA-049's `_pinned` and FIX-023's `_world`, both autouse): record mode;
deployment on, 80% invested in calm labels, 2 new positions a day, a new
position 80% of equity / 12; caps 10% of equity a stock and 30% a sector;
cash floor ₹10,000; no trading costs; the regime state in tmp; NSE's report
clears every symbol. A test that needs another clock sets it.

Independent invariants:
- M1, the day's regime: over every label, a holding's own entry of the day,
  an older one or none, and the day recorded, unrecorded or recorded
  unavailable, `decide` adds only when the day's label allows it: an older
  label never allows what today's recorded label refuses, today's calm
  recorded label frees what an older crisis label held, an own entry of the
  day is never overruled, and the crisis exit reads the same label.
- M2 and M4, the sale: over every (decided day, autopilot exit, hand exit,
  shelf or watchlist) in three weeks, the rule offers an idea exactly when an
  oracle written here says so: no exit on or after the day it was decided,
  and from the watchlist after an autopilot exit, an analysis on or after
  the first Saturday after the exit (found here by counting days).
- M3, issue time: the watchlist reads the newest analysis in the real score
  store run strictly before the review session's 15:30 IST close.
- L1: no door buys an idea its analysis does not rate BUY.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.unit.test_analysis_time_fix024 as f24
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_idea_supply_pr004 as pr004
from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Portfolio, TransactionRecord
from core.config import settings
from core.discovery import shelf as shelf_mod
from core.discovery.candidates import buy_candidates
from core.discovery.shelf import Sales, ledger_sales, saturday_after
from core.intelligence.regime import state
from core.intelligence.rl.nse_calendar import IST
from core.portfolio import autopilot as ap
from core.portfolio.advisor import AdvisorSignals, build_signals, decide, evaluate_switch_candidates
from tests.unit.test_deploy_idle_cash_sa049 import _pinned  # noqa: F401  (autouse)
from tests.unit.test_idea_supply_pr004 import shelf  # noqa: F401  (a fixture)
from tests.unit.test_regime_inputs_fix023 import _world  # noqa: F401  (autouse)

SAT_31, MON, TUE, WED, THU, FRI_6 = (date(2026, 10, 31), date(2026, 11, 2), date(2026, 11, 3),
                                     date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6))
SAT_7, MON_9, TUE_10 = date(2026, 11, 7), date(2026, 11, 9), date(2026, 11, 10)
LABELS = ("NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD", "RISK_OFF", "MACRO_CRISIS")
SEVERE = ("RISK_OFF", "MACRO_CRISIS")


def _sale(sym, day, stamp=None, qty_after=0.0, source="autopilot"):
    """A SELL of 10 at ₹1,000 dated `day` (the session it was booked at),
    stamped `stamp` (when the run decided it)."""
    return TransactionRecord(
        txn_id=f"s-{sym}-{day}-{source}", date=day, ts=stamp or f"{day}T11:00:00+00:00",
        user_id="u", symbol=sym, side="SELL", qty=10.0, price=1000.0, value=10_000.0,
        cash_before=0.0, cash_after=10_000.0, holding_qty_after=qty_after, realized_pnl=0.0,
        source=source, verdict="EXIT", advice_ref="r", triggers=[], note="exit_full")


def _watch_rules(monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", True)
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)


def _window():
    """W at ₹1,000 every calendar day from 12 Sep to 10 Nov."""
    return pr004._eod_window(["W"], days=60, end=TUE_10, close=1000.0)


def _watch_list(on, analysis_before, sales=None, source="user"):
    """The real list for review session `on`: the user's watchlist holds W."""
    return buy_candidates(pr004.portfolio(watch=[("W", source)]), on, [],
                          analysis_before=analysis_before, window=_window(),
                          listing=pr004.companies("W"), managed={}, sales=sales)


def _buy(run_at):
    """A reader that answers one BUY at 0.70 run at `run_at` (naive UTC)."""
    rec = pr004.record(run_at=run_at, score=0.70)
    return lambda sym, before: rec


# ---------------------------------------------------------------------------
# M1: the day's regime, whoever's review recorded it
# ---------------------------------------------------------------------------

def _log_store(entries, unavailable=""):
    """A VerdictStore stand-in: no envelope, and a feedback log of
    (date, label) entries, each a correct direction (7-day accuracy 1.0); the
    last one's day recorded unavailable with `unavailable` when given."""
    log = SimpleNamespace(entries=[
        SimpleNamespace(date=d, regime_label=label,
                        regime_unavailable=unavailable if k == len(entries) - 1 else "",
                        direction_correct=True, thesis_review=None)
        for k, (d, label) in enumerate(entries)])
    return SimpleNamespace(cycle_id_for=lambda d: "H_2026-11", load_envelope=lambda c: None,
                           load_feedback_log=lambda c: log)


def _market(kind, label=""):
    """The market-wide state for WED: recorded `label`, never recorded, or
    recorded unavailable (an established NORMAL on Tuesday, then a dark Wednesday)."""
    Path(settings.PREDICTION_DATA_DIR, "_regime_state.json").unlink(missing_ok=True)
    if kind == "recorded":
        state.update_sticky_regime(label, WED.isoformat())
    elif kind == "unavailable":
        state.update_sticky_regime("NORMAL", TUE.isoformat())
        state.record_unavailable_day(WED.isoformat(), "India VIX did not answer", "")


def _signals(entries, envelope, unavailable=""):
    holding = story._h("H", 100, 100.0, "pharma")
    portfolio = Portfolio(user_id="u", holdings=[holding], cash_deployable=900_000.0)
    sig = build_signals(holding, portfolio, WED, _log_store(entries, unavailable), {},
                        close=100.0)
    # Where ADD (UP) or the crisis exit (DOWN) would fire on a calm or a crisis
    # label: a 5% position (cap 10%), 7-day accuracy 0.70 (floor 0.60).
    return holding, sig.model_copy(update={
        "envelope_direction": envelope, "position_weight_pct": 5.0,
        "direction_accuracy_7d": 0.70, "price_fresh": True, "forecast_gate": "actionable"})


def test_m1_every_label_with_or_without_an_entry_of_its_own():
    """104 shapes: an own entry of Wednesday, an older one (Tuesday) or none,
    each with every label, against Wednesday recorded with every label, never
    recorded, or recorded unavailable."""
    owns = ([("today", lab) for lab in LABELS] + [("older", lab) for lab in LABELS]
            + [("none", "")])
    markets = [("recorded", lab) for lab in LABELS] + [("unrecorded", ""), ("unavailable", "")]
    seen = 0
    for when, own in owns:
        entries = {"today": [(TUE.isoformat(), "NORMAL"), (WED.isoformat(), own)],
                   "older": [(TUE.isoformat(), own)], "none": []}[when]
        for kind, recorded in markets:
            _market(kind, recorded)
            # The label the day reads, by the card: the holding's own entry of
            # the day; else the day's recorded label; else nothing is known.
            if when == "today":
                day_label, known = own, True
            elif kind == "recorded":
                day_label, known = recorded, True
            else:
                day_label, known = (own if when == "older" else "NORMAL"), False
            holding, up = _signals(entries, "UP")
            rec = decide(up, holding, "balanced")
            should_add = known and day_label not in SEVERE
            assert (rec.verdict == "ADD") == should_add, (when, own, kind, recorded, rec)
            if when != "today" and kind == "recorded":
                # never what today's label refuses; always what it frees
                assert (rec.verdict == "ADD") == (recorded not in SEVERE)
            if not known:
                assert rec.notes == (["REGIME_UNAVAILABLE"] if day_label not in SEVERE else [])
                why = ("market regime unavailable for 2026-11-04: India VIX did not answer"
                       if kind == "unavailable" else "no market regime recorded for 2026-11-04")
                assert up.regime_unavailable == why
            _, down = _signals(entries, "DOWN")
            crisis = "crisis_regime_bearish" in decide(down, holding, "balanced").triggers
            assert crisis == (day_label == "MACRO_CRISIS"), (when, own, kind, recorded)
            seen += 1
    assert seen == 13 * 8


def test_m1_todays_calm_label_frees_what_an_older_crisis_label_held():
    """The holding's own review last ran on Tuesday, in a MACRO_CRISIS. Today,
    Wednesday, another ticker's review recorded NORMAL: the ADD fires, and the
    narrative reads NORMAL, the day's label."""
    _market("recorded", "NORMAL")
    holding, sig = _signals([(TUE.isoformat(), "MACRO_CRISIS")], "UP")
    assert (sig.regime_label, sig.regime_unavailable) == ("NORMAL", "")
    assert decide(sig, holding, "balanced").verdict == "ADD"


def test_m1_an_older_dark_day_does_not_hold_a_day_another_review_recorded():
    """The holding's last entry is Tuesday's, a day India VIX did not answer
    (NORMAL kept). Wednesday, another ticker's review recorded NORMAL: the
    older day's reason goes with its label, and the ADD fires. With Wednesday
    not recorded, the reason is Wednesday's own and the ADD is held."""
    _market("recorded", "NORMAL")
    holding, sig = _signals([(TUE.isoformat(), "NORMAL")], "UP",
                            unavailable="India VIX did not answer")
    assert (sig.regime_label, sig.regime_unavailable) == ("NORMAL", "")
    assert decide(sig, holding, "balanced").verdict == "ADD"
    _market("unrecorded")
    holding, sig = _signals([(TUE.isoformat(), "NORMAL")], "UP",
                            unavailable="India VIX did not answer")
    assert sig.regime_unavailable == "no market regime recorded for 2026-11-04"
    rec = decide(sig, holding, "balanced")
    assert (rec.verdict, rec.notes) == ("HOLD", ["REGIME_UNAVAILABLE"])


@pytest.mark.parametrize("today", ["RISK_OFF", "MACRO_CRISIS"])
def test_m1_rv3_no_entry_of_its_own_on_a_recorded_bad_day_adds_nothing(tmp_path, monkeypatch,
                                                                        today):
    """RV3 through the real daily review: the holding's own review wrote
    nothing today, its older entry says NORMAL, and another ticker's review
    recorded RISK_OFF or MACRO_CRISIS. ADD refuses both."""
    holding, day, sig = f24._next_day_signals(
        tmp_path, monkeypatch, mark=lambda d: state.update_sticky_regime(today, d))
    assert state.label_recorded_for(day) == today
    assert sig.regime_label == today
    assert decide(sig, holding, "balanced").verdict != "ADD"


# ---------------------------------------------------------------------------
# M3: the newest analysis before the close, from the real score store
# ---------------------------------------------------------------------------

def _score_db(tmp_path):
    from services.data.stores.score_store import ScoreStore
    return ScoreStore(db_path=str(tmp_path / "scores.db"))


def _analyse(store, run_at, verdict="BUY", score=0.70):
    """One row as the daily review's re-run writes it (run_at naive UTC)."""
    with sqlite3.connect(str(store._db_path)) as conn:
        conn.execute(
            "INSERT INTO score_history (ticker, company_name, run_at, final_score, verdict, "
            "agent_scores, investment_thesis, conviction_drivers, top_risks, report_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("W", "W Ltd", run_at, score, verdict, "{}", f"case of {run_at}", "[]", "[]",
             json.dumps({"decision_gate": {"status": "actionable"}})))


def test_m3_rv12_a_daily_reviewed_watchlist_buy_is_offered_every_day(tmp_path, monkeypatch):
    """W is on the user's own watchlist and in the daily review: the 16:30 job
    on day J reviews the session before and re-runs W's analysis at 16:35 IST
    (11:05 UTC) on J, a BUY at 0.70. Then the list for that session is built.

    By hand, the newest analysis before the session's 15:30 close is the one
    of the trading day before the session, at 16:35:
      session Fri 30 Oct (job Mon 2 Nov): Thu 29 Oct's;
      Mon 2 Nov (job Tue): Fri 30 Oct's; Tue (job Wed): Mon's;
      Wed (job Thu): Tue's; Thu 5 Nov (job Fri): Wed's.
    W is offered on every one; before FIX-029 it was offered on none."""
    _watch_rules(monkeypatch)
    scores = _score_db(tmp_path)
    _analyse(scores, "2026-10-29T11:05:00")          # Thursday's job (review of Wed 28 Oct)
    _analyse(scores, "2026-10-30T11:05:00")          # Friday's job (review of Thu 29 Oct)
    days = [date(2026, 10, 30), MON, TUE, WED, THU, FRI_6]
    for session, job in zip(days, days[1:]):
        _analyse(scores, f"{job.isoformat()}T11:05:00")       # the job's own re-run
        offered, excluded = _watch_list(session, scores.get_latest_before)
        assert excluded == {}, (session, excluded)
        before = days[days.index(session) - 1] if session != days[0] else date(2026, 10, 29)
        assert [(i.symbol, i.dived, i.analysed_at) for i in offered] == \
            [("W", before.isoformat(), f"{before.isoformat()}T16:35:00+05:30")], session


def test_m3_an_older_buy_counts_for_its_close_and_a_later_sell_from_the_next(tmp_path,
                                                                             monkeypatch):
    """Mon 2 Nov 16:35 IST: BUY; Tue 3 Nov 16:35 IST: SELL (the page shows the
    SELL from then on). The list for Tuesday's close (Wednesday's run) reads
    the newest analysis before 15:30 on Tuesday: Monday's BUY, so W is offered
    with Monday's case. The SELL counts from Wednesday's close (Thursday's
    run): not offered. Reading the SELL for Tuesday's close would use what was
    learnt after the price the buy is booked at (FIX-031 I-1, decided)."""
    _watch_rules(monkeypatch)
    scores = _score_db(tmp_path)
    _analyse(scores, "2026-11-02T11:05:00", "BUY")
    _analyse(scores, "2026-11-03T11:05:00", "SELL")
    _analyse(scores, "2026-11-04T11:05:00", "SELL")
    offered, excluded = _watch_list(TUE, scores.get_latest_before)
    assert excluded == {} and [(i.dived, i.thesis) for i in offered] == \
        [("2026-11-02", "case of 2026-11-02T11:05:00")]
    offered, excluded = _watch_list(WED, scores.get_latest_before)
    assert offered == [] and excluded == {"W": "latest analysis is SELL"}


def test_m3_the_bound_is_strictly_before_the_close(tmp_path):
    """15:30 IST on Mon 2 Nov is 10:00:00 UTC. A run a microsecond before is the
    answer; one at the close or after is not. A naive bound is UTC."""
    scores = _score_db(tmp_path)
    for stamp in ("2026-11-02T09:59:59.999999", "2026-11-02T10:00:00",
                  "2026-11-02T10:00:00.000001"):
        _analyse(scores, stamp)
    close = datetime(2026, 11, 2, 15, 30, tzinfo=IST)
    assert scores.get_latest_before("w", close)["run_at"] == "2026-11-02T09:59:59.999999"
    assert scores.get_latest_before("W", datetime(2026, 11, 2, 10, 0))["run_at"] == \
        "2026-11-02T09:59:59.999999"
    assert scores.get_latest_before("W", datetime(2026, 11, 2, 9, 0)) is None
    assert scores.get_latest_before("OTHER", close) is None


# ---------------------------------------------------------------------------
# The sale (M2, M4): one rule, an oracle over three weeks
# ---------------------------------------------------------------------------

def _first_saturday_after(day):
    d = day + timedelta(days=1)
    while d.strftime("%A") != "Saturday":
        d += timedelta(days=1)
    return d


def test_saturday_after_counts_to_the_next_saturday():
    for k in range(21):
        day = date(2026, 10, 26) + timedelta(days=k)
        assert saturday_after(day) == _first_saturday_after(day), day


def test_the_sale_rule_over_three_weeks_against_an_oracle():
    """Every decided day (a dive's, or a watchlist analysis's IST day), an
    autopilot exit, a later or earlier hand exit, or none, shelf or watchlist.
    Oracle: not offered when any exit is on or after the decided day; and from
    the watchlist after an autopilot exit, not before the first Saturday
    after that exit."""
    days = [date(2026, 10, 26) + timedelta(days=k) for k in range(21)]
    checked = 0
    for decided in days:
        for auto in [None, *days]:
            for hand in [None, *days]:
                for watch in (False, True):
                    idea = ShelfIdea(symbol="X", sector="pharma", added=decided.isoformat(),
                                     dived=decided.isoformat(), conviction=0.7, verdict="BUY",
                                     source="watchlist" if watch else "discovery")
                    exits = [d for d in (auto, hand) if d is not None]
                    sales = Sales(last={"X": max(exits)} if exits else {},
                                  by_autopilot={"X": auto} if auto else {})
                    blocked = any(d >= decided for d in exits) or (
                        watch and auto is not None and decided < _first_saturday_after(auto))
                    assert (sales.wait(idea) == "") == (not blocked), (decided, auto, hand, watch)
                    checked += 1
    assert checked == 21 * 22 * 22 * 2


def test_ledger_sales_reads_exits_on_the_day_they_were_decided():
    """A 16:30 IST run on Tue 3 Nov sells X at Monday's close (dated Mon, stamped
    Tue): Tuesday's. A trim that leaves shares is no exit. A hand sale keeps
    its date. A BUY is no sale. The later of two exits wins."""
    txns = [_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00"),
            _sale("T", "2026-11-02", qty_after=5.0),
            _sale("H", "2026-10-30", stamp="2026-11-06T11:00:00+00:00", source="manual"),
            _sale("X", "2026-10-20"),
            _sale("H", "2026-10-29")]
    buy = txns[0].model_copy(update={"side": "BUY", "symbol": "B", "txn_id": "b"})
    got = ledger_sales([*txns, buy])
    assert got.last == {"X": TUE, "H": date(2026, 10, 30)}
    assert got.by_autopilot == {"X": TUE, "H": date(2026, 10, 29)}


# -- M2: a shelf idea the sale overruled, at every door -----------------------

def _x_and_z():
    """X, pharma, conviction 0.80, and Z, fmcg, 0.75, both dived Sat 31 Oct at
    ₹1,000: bands 960-1,040, invalidation 900."""
    return (story._idea("X", 1000.0, 0.80, "pharma", dived=SAT_31.isoformat()),
            story._idea("Z", 1000.0, 0.75, "fmcg", dived=SAT_31.isoformat()))


SOLD_X = "sold on 2026-11-03, after its deep dive of 2026-10-31; waits for a new deep dive"


def test_m2_rv5_a_hand_made_switch_into_a_stock_sold_the_day_before_is_not_bought(tmp_path,
                                                                                   monkeypatch):
    """RV5: Tuesday 3 Nov's run sold X (stamped 16:30 IST Tue). Wednesday's run
    reviews Tuesday: Y (100 × ₹1,000) is switched into X by an advice made by
    hand, not from the list. The SWITCH leg reads the ledger: no buy, and the
    ₹1,00,000 stays in cash, said on the SELL."""
    monkeypatch.setattr(ap, "_today_ist", lambda: THU)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-04T11:00:00+00:00")
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = story._store(tmp_path, [story._h("Y", 100, 1000.0, "it_sector")], cash=800_000.0)
    s.append_transaction(_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00"))
    x, _ = _x_and_z()
    story._prices(monkeypatch, {"X": 1000.0})
    switch = AdviceRecord(date=TUE.isoformat(), user_id="u", symbol="Y", verdict="SWITCH",
                          close=1000.0, unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x",
                          switch_candidate="X")
    txns, _ = story._run(s, [x], {"Y": 1000.0}, on=TUE, advice=[switch])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "Y")]
    assert ap.switch_skip_reason(txns[0].note) == f"X: {SOLD_X}; ₹1,00,000 stays in cash"
    assert s.load().cash_deployable == 900_000.0


def test_m2_rv5b_the_list_drops_the_sold_idea_and_the_switch_takes_the_next_best(tmp_path,
                                                                                 monkeypatch):
    """RV5b through the real list, decide and executor. Y (it_sector, 1,000 at
    ₹100, now ₹70, −30%) breaches its stop. Equity 70,000 + 8,00,000 = 8,70,000,
    so it_sector is 8.05% and pharma and fmcg 0%. Unfiltered, decide names X
    (0.80 beats Z's 0.75; both beat confidence 0.30 by 0.15). The list with the
    ledger drops X, so the SWITCH goes to Z, and the executor buys
    floor(70,000 / 1,000) = 70 shares of Z."""
    monkeypatch.setattr(ap, "_today_ist", lambda: THU)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-04T11:00:00+00:00")
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = story._store(tmp_path, [story._h("Y", 1000, 100.0, "it_sector")], cash=800_000.0)
    s.append_transaction(_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00"))
    x, z = _x_and_z()
    offered, excluded = buy_candidates(s.load(), TUE, [x, z], managed={},
                                       sales=ledger_sales(s.load_transactions()))
    assert [i.symbol for i in offered] == ["Z"] and excluded == {"X": SOLD_X}
    sig = AdvisorSignals(symbol="Y", sector="it_sector", close=70.0, atr_stop_pct=12.0,
                         unrealised_pnl_pct=-30.0, holding_age_days=40, confidence=0.3)
    weights = {"it_sector": 8.05, "pharma": 0.0, "fmcg": 0.0}
    holding = s.load().holdings[0]
    control = decide(sig, holding, "balanced", shelf_ideas=[x, z], sector_weights=weights,
                     held_symbols={"Y"})
    assert (control.verdict, control.switch_candidate) == ("SWITCH", "X")
    rec = decide(sig, holding, "balanced", shelf_ideas=offered, sector_weights=weights,
                 held_symbols={"Y"})
    assert (rec.verdict, rec.switch_candidate) == ("SWITCH", "Z")
    _, rows = evaluate_switch_candidates(sig, offered, weights, {"Y"})
    assert [(r["candidate"], r["decision"]) for r in rows] == [("Z", "taken")]
    rec.user_id, rec.date = "u", TUE.isoformat()
    story._prices(monkeypatch, {"Z": 1000.0})
    txns, _ = story._run(s, offered, {"Y": 70.0}, on=TUE, advice=[rec])
    assert [(t.side, t.symbol, t.qty) for t in txns] == [("SELL", "Y", 1000.0),
                                                         ("BUY", "Z", 70.0)]


def _breach_pipeline(tmp_path, monkeypatch, with_sale):
    """The real pipeline for Tuesday 3 Nov, run on Wednesday: Y as above, X and
    Z on the shelf, deployment off; the ledger holds X's sale or not."""
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(ap, "_today_ist", lambda: WED)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-04T11:00:00+00:00")
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    store, _ = story._pipeline_world(tmp_path, monkeypatch,
                                     [story._h("Y", 1000, 100.0, "it_sector")], 800_000.0,
                                     list(_x_and_z()), {"Y": 70.0, "X": 1000.0, "Z": 1000.0})
    if with_sale:
        store.append_transaction(_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00"))
    state.update_sticky_regime("NORMAL", TUE.isoformat())
    pipeline.run_post_review_pipeline(TUE)
    advice = {r.symbol: (r.verdict, r.switch_candidate) for r in store.load_advice()}
    buys = [(t.date, t.symbol, t.qty, t.price) for t in store.load_transactions()
            if t.side == "BUY"]
    return advice, buys


def test_m2_the_pipeline_passes_the_ledger_so_a_real_switch_skips_the_sold_stock(tmp_path,
                                                                                 monkeypatch):
    """The same day twice through the real pipeline. Without X's sale in the
    ledger the stop breach switches into X (70 shares). With it, into Z."""
    assert _breach_pipeline(tmp_path / "control", monkeypatch, False) == (
        {"Y": ("SWITCH", "X")}, [("2026-11-03", "X", 70.0, 1000.0)])
    assert _breach_pipeline(tmp_path / "sold", monkeypatch, True) == (
        {"Y": ("SWITCH", "Z")}, [("2026-11-03", "Z", 70.0, 1000.0)])


def test_m2_a_hand_sale_blocks_as_deployment_did_and_an_older_one_does_not():
    """X dived Sat 31 Oct. Sold by hand on Mon 2 Nov: not offered. Sold by
    hand on Fri 30 Oct, before the dive: offered."""
    x, _ = _x_and_z()
    pf = SimpleNamespace(holdings=[], watchlist=[])
    after = ledger_sales([_sale("X", "2026-11-02", source="manual")])
    offered, excluded = buy_candidates(pf, TUE, [x], managed={}, sales=after)
    assert offered == [] and excluded == {"X": (
        "sold on 2026-11-02, after its deep dive of 2026-10-31; waits for a new deep dive")}
    before = ledger_sales([_sale("X", "2026-10-30", source="manual")])
    offered, excluded = buy_candidates(pf, TUE, [x], managed={}, sales=before)
    assert [i.symbol for i in offered] == ["X"] and excluded == {}


def test_m2_the_first_run_that_may_use_the_new_dive_offers_it():
    """The autopilot sold X on Tue 3 Nov; Sat 7 Nov re-dived it. Monday 9 Nov's
    run reviews Friday 6 Nov: the dive is after that close (FIX-024). Tuesday
    10 Nov's run reviews Monday 9 Nov: offered."""
    redived = story._idea("X", 1000.0, 0.80, "pharma", dived=SAT_7.isoformat())
    sales = ledger_sales([_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00")])
    pf = SimpleNamespace(holdings=[], watchlist=[])
    offered, excluded = buy_candidates(pf, FRI_6, [redived], managed={}, sales=sales)
    assert offered == [] and excluded == {"X": (
        "close of 2026-11-06 is before the deep dive of 2026-11-07; waits for a review of a "
        "later session")}
    offered, excluded = buy_candidates(pf, MON_9, [redived], managed={}, sales=sales)
    assert [i.symbol for i in offered] == ["X"] and excluded == {}


def test_m2_a_held_stock_is_left_to_each_doors_own_held_check():
    """X is held again (bought back by hand) and its last exit came after its
    dive. The list still carries it, so the switch evaluation's row says
    "already_held", as before FIX-029."""
    x, z = _x_and_z()
    held = Portfolio(user_id="u", holdings=[story._h("X", 5, 1000.0, "pharma")],
                     cash_deployable=0.0)
    sales = ledger_sales([_sale("X", "2026-11-02", stamp="2026-11-03T11:00:00+00:00")])
    offered, excluded = buy_candidates(held, TUE, [x, z], managed={}, sales=sales)
    assert [i.symbol for i in offered] == ["X", "Z"] and excluded == {}
    sig = AdvisorSignals(symbol="Y", sector="it_sector", close=70.0, atr_stop_pct=12.0,
                         unrealised_pnl_pct=-30.0, holding_age_days=40, confidence=0.3)
    _, rows = evaluate_switch_candidates(sig, offered, {"it_sector": 8.0}, {"X", "Y"})
    assert {r["candidate"]: r["reason"] for r in rows} == {"X": "already_held", "Z": ""}


# -- M4, Option A: an own-watchlist stock the autopilot sold -------------------

AUTO_SOLD_W = ("sold by the autopilot on 2026-11-03; from the watchlist only an analysis made "
               "on or after Saturday 2026-11-07 counts (this one is of 2026-11-04)")


def test_m4_rv4_an_own_watchlist_stock_waits_for_the_saturday_after_its_sale(tmp_path,
                                                                             monkeypatch):
    """RV4: W is on the user's own watchlist (source "user") and held. Tuesday
    3 Nov's job sells it at Monday's close, stamped 17:00 IST Tuesday. Wednesday
    16:35 IST: a BUY. Friday's job reviews Thursday: that analysis is before
    Thursday's close and newer than the sale. By Option A it does not count
    until Saturday 7 Nov: the list drops it, and so does deployment when
    handed it directly."""
    _watch_rules(monkeypatch)
    monkeypatch.setattr(ap, "_today_ist", lambda: FRI_6)
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-03T11:30:00+00:00")
    s = story._store(tmp_path, [story._h("W", 100, 1000.0, "pharma")], cash=1_100_000.0)
    p = s.load()
    from backend.shared.schemas.portfolio import WatchlistItem
    p.watchlist = [WatchlistItem(symbol="W", sector="pharma", added="2026-10-01")]
    s.save(p)
    story._prices(monkeypatch, {"W": 1000.0})
    sell = AdviceRecord(date=MON.isoformat(), user_id="u", symbol="W", verdict="EXIT", close=1000.0,
                        unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x")
    txns, _ = story._run(s, [], {"W": 1000.0}, on=MON, advice=[sell])
    assert [t.side for t in txns] == ["SELL"]
    wed_1635 = "2026-11-04T11:05:00"
    sales = ledger_sales(s.load_transactions())
    assert sales.by_autopilot == {"W": TUE}
    offered, excluded = buy_candidates(s.load(), THU, [], analysis_before=_buy(wed_1635),
                                       window=_window(), listing=pr004.companies("W"),
                                       managed={}, sales=sales)
    assert offered == [] and excluded == {"W": AUTO_SOLD_W}
    # The deployment door, handed the candidate without the list's sales.
    unfiltered, _ = buy_candidates(s.load(), THU, [], analysis_before=_buy(wed_1635),
                                   window=_window(), listing=pr004.companies("W"), managed={})
    monkeypatch.setattr(ap, "_now_iso", lambda: "2026-11-06T11:30:00+00:00")
    txns, record = story._run(s, unfiltered, {}, on=THU)
    assert txns == [] and story._outcomes(record)["W"] == ("sold", AUTO_SOLD_W)


@pytest.mark.parametrize("run_at, session, offered", [
    ("2026-11-06T11:05:00", MON_9, False),     # Fri 6 Nov 16:35 IST: before Sat 7 Nov
    ("2026-11-09T05:30:00", MON_9, True),      # Mon 9 Nov 11:00 IST: on or after it
])
def test_m4_an_analysis_on_or_after_that_saturday_counts(monkeypatch, run_at, session, offered):
    _watch_rules(monkeypatch)
    sales = ledger_sales([_sale("W", "2026-11-02", stamp="2026-11-03T11:30:00+00:00")])
    out, excluded = _watch_list(session, _buy(run_at), sales)
    assert ([i.symbol for i in out] == ["W"]) == offered, excluded


def test_m4_after_a_hand_sale_any_later_analysis_counts():
    """A hand sale on Tue 3 Nov: Wednesday 11:00 IST's analysis counts for
    Wednesday's close; Tuesday 11:00 IST's, made the day of the sale, does not."""
    sales = ledger_sales([_sale("W", "2026-11-03", source="manual")])
    with pytest.MonkeyPatch.context() as mp:
        _watch_rules(mp)
        out, excluded = _watch_list(WED, _buy("2026-11-04T05:30:00"), sales)
        assert [i.symbol for i in out] == ["W"] and excluded == {}
        out, excluded = _watch_list(TUE, _buy("2026-11-03T05:30:00"), sales)
        assert out == [] and excluded == {"W": (
            "sold on 2026-11-03, after its analysis of 2026-11-03; waits for a new analysis")}


# ---------------------------------------------------------------------------
# L1: the analysis must rate the idea a BUY
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verdict", ["NEUTRAL", "SELL"])
def test_l1_rv6_deployment_never_buys_an_idea_not_rated_buy(tmp_path, monkeypatch, verdict):
    """RV6: ₹10 L cash, one idea at conviction 0.70 whose verdict is NEUTRAL or
    SELL, handed straight to deployment. Not bought; the record says why."""
    s = story._store(tmp_path, [], cash=1_000_000.0)
    idea = story._idea("N", 1000.0, 0.70, "pharma", verdict=verdict)
    story._prices(monkeypatch, {"N": 1000.0})
    txns, record = story._run(s, [idea], {})
    assert txns == []
    assert story._outcomes(record)["N"] == ("verdict",
                                            f"its deep dive rates it {verdict}, not a BUY")
    assert "1 idea not rated a BUY by the analysis" in record["reasons"]


def test_l1_the_list_and_a_switch_leg_refuse_it_too(tmp_path, monkeypatch):
    """The list leaves out N (NEUTRAL) and the empty-verdict E; a hand-made
    SWITCH into N sells Y and keeps ₹1,00,000 in cash."""
    n = story._idea("N", 1000.0, 0.70, "pharma", verdict="NEUTRAL")
    e = story._idea("E", 1000.0, 0.70, "fmcg", verdict="")
    pf = SimpleNamespace(holdings=[], watchlist=[])
    offered, excluded = buy_candidates(pf, story.D, [n, e], managed={})
    assert offered == [] and excluded == {
        "N": "its deep dive rates it NEUTRAL, not a BUY",
        "E": "its deep dive stored no verdict; waits for its re-dive"}
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    s = story._store(tmp_path, [story._h("Y", 100, 1000.0, "it_sector")], cash=800_000.0)
    story._prices(monkeypatch, {"N": 1000.0})
    switch = AdviceRecord(date=story.D.isoformat(), user_id="u", symbol="Y", verdict="SWITCH",
                          close=1000.0, unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x",
                          switch_candidate="N")
    txns, _ = story._run(s, [n], {"Y": 1000.0}, advice=[switch])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "Y")]
    assert ap.switch_skip_reason(txns[0].note) == \
        "N: its deep dive rates it NEUTRAL, not a BUY; ₹1,00,000 stays in cash"


def test_l1_rv7_a_re_dive_that_is_no_longer_a_buy_leaves_the_shelf(shelf):
    """D4: "If it is still a BUY, it can be bought again ... If not, the idea
    leaves the shelf". The re-dive of Sat 31 Oct is NEUTRAL at 0.70."""
    shelf.save(Shelf(ideas=[pr004._idea("BACK", "2026-10-24")]))
    dive = pr004.dive("BACK", 0.70, on=SAT_31.isoformat(), close=1000.0)
    out = shelf.apply_redives([dive.model_copy(update={"verdict": "NEUTRAL"})], on=SAT_31)
    assert out["dropped"] == {"BACK": "re-dive 2026-10-31: its deep dive rates it NEUTRAL, not a BUY"}
    assert [i.status for i in shelf.load().ideas] == ["dropped"]


def test_l1_a_new_dive_not_rated_buy_is_not_shelved(shelf):
    """A dive at 0.70 rated NEUTRAL takes no slot; the BUY beside it does."""
    dives = [pr004.dive("NEUT", 0.70, on=SAT_31.isoformat()).model_copy(update={"verdict": "NEUTRAL"}),
             pr004.dive("GOOD", 0.65, on=SAT_31.isoformat())]
    out = shelf.apply_deep_dives(dives, on=SAT_31)
    assert (out["added"], out["not_buy"], out["skipped"]) == (["GOOD"], ["NEUT"], ["NEUT"])
    assert [i.symbol for i in shelf.load().ideas] == ["GOOD"]


def test_l1_an_idea_with_no_stored_verdict_is_re_dived_before_the_stale_ones(shelf):
    """On Sat 31 Oct: E (no verdict, dived 24 Oct) is fresh but unverified, so
    it is due before S (a BUY dived 20 Sep, 41 days ago, stale). F (a BUY dived
    24 Oct) is not due."""
    shelf.save(Shelf(ideas=[pr004._idea("S", "2026-09-20", verdict="BUY"),
                            pr004._idea("E", "2026-10-24", verdict=""),
                            pr004._idea("F", "2026-10-24", verdict="BUY")]))
    assert [i.symbol for i in shelf.redive_due(SAT_31)] == ["E", "S"]
