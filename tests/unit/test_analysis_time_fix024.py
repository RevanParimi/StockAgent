"""FIX-024 — a buy waits for an analysis made before its close; an unknown
regime adds nothing.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test.

Fixture rules (pinned by FIX-023's autouse world, imported below): record
mode; deployment on, 80% in calm labels, 2 new positions a day, 80% of equity
over 12 positions, so one asks for ₹80,000 of ₹12 L; a watchlist band is 97-102% of the
close it is set from; NSE's 15:30 IST close.

Independent invariants:
- issue time (M1), in hours: a close prices a buy only when it is struck
  after the idea was decided. A watchlist analysis keeps its own time; a deep
  dive keeps only its day and so counts as made after that day's close. The
  candidate list, a SWITCH leg, deployment and the shadow's switch test
  agree, checked over every half hour of a week against the definition
  written here (15:30 IST of the bar's day, strictly after the decision);
- a watchlist band comes from the last close the analysis could have read;
- L1: through the real daily review, the feedback log and the advisor, a day
  whose regime the live inputs did not establish holds an ADD the kept label
  would allow, in either gate mode, and the record names the day and why;
  the crisis exit still reads the kept label; an established day ADDs;
- L2: a state written fresh is established for its own day, so a later dark
  review that day neither marks it nor moves it;
- a manual run of a session that has not closed is refused
  (tests/unit/test_portfolio_api.py).
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

import core.intelligence.rl.workflows.daily_review as dr
import core.portfolio.pipeline as pipeline
import tests.unit.test_deploy_idle_cash_sa049 as story
import tests.unit.test_idea_supply_pr004 as pr004
import tests.unit.test_regime_inputs_fix023 as f23
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.portfolio import AdviceRecord, Portfolio, WatchlistItem
from core.config import settings
from core.discovery import candidates as cands_mod
from core.discovery.shelf import close_before_dive
from core.intelligence.regime import state
from core.intelligence.regime.detector import RegimeDetector
from core.intelligence.rl.nse_calendar import IST
from core.portfolio import autopilot as ap
from core.portfolio import deployment
from core.portfolio import exit_shadow as xs
from core.portfolio.advisor import AdvisorSignals, build_signals, decide
from core.portfolio.narrator import fallback_narrative
from core.portfolio.pricing import SessionClose
from tests.unit.test_regime_inputs_fix023 import _world  # noqa: F401  (autouse)

FRI, SAT, MON = date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 2)
TUE, WED = date(2026, 11, 3), date(2026, 11, 4)
REAL_DETECT = RegimeDetector.detect


# ---------------------------------------------------------------------------
# A watchlist analysis and the closes around it
# ---------------------------------------------------------------------------

# Run times are naive UTC, as the score history keeps them: IST is UTC+5:30.
MON_2000_IST = "2026-11-02T14:30:00"      # after Monday's 15:30 close
MON_1100_IST = "2026-11-02T05:30:00"      # before it
CLOSES = {FRI: 500.0, MON: 505.0, TUE: 510.0}


def _window(closes=CLOSES):
    """The EOD store's rows for W: 20 sessions at ₹500 up to Thu 29 Oct, then
    `closes` (Fri ₹500, Mon ₹505, Tue ₹510)."""
    from services.data.stores.eod_store import COLUMNS
    days = f23._sessions(date(2026, 10, 29), 20)
    rows = [(d, 500.0) for d in days] + sorted(closes.items())
    return pd.DataFrame([{"symbol": "W", "series": "EQ", "date": d.isoformat(),
                          "prev_close": c, "open": c, "high": c * 1.02, "low": c * 0.98,
                          "close": c, "volume": 1.0, "traded_value_cr": 10.0,
                          "delivery_qty": 1.0, "delivery_pct": 50.0} for d, c in rows],
                        columns=COLUMNS)


def _watch_rules(monkeypatch):
    monkeypatch.setattr(settings, "DISCOVERY_STALE_DAYS", 60)
    monkeypatch.setattr(settings, "DISCOVERY_WATCHLIST_BUYS", True)
    monkeypatch.setattr(settings, "DISCOVERY_MIN_CONVICTION", 0.55)


def _offered(on, run_at, holdings=()):
    """buy_candidates for review session `on`, the user's watchlist BUY of W
    at 0.80 run at `run_at`."""
    rec = pr004.record(run_at=run_at)
    return cands_mod.buy_candidates(pr004.portfolio(watch=[("W", "user")], holdings=holdings),
                                    on, [], latest_analysis=lambda s: rec, window=_window(),
                                    listing=pr004.companies("W"), managed={})


def _w_idea(run_at):
    """W's candidate as the watchlist lane builds it, whatever the session."""
    out, excluded = _offered(WED, run_at)
    assert excluded == {}
    return out[0]


def test_an_analysis_after_the_close_waits_for_the_next_sessions_review(monkeypatch):
    """RV5: W analysed Mon 2 Nov 20:00 IST, after Monday's 15:30 close.
    Tuesday's run reviews Monday: not offered, the reason names both times.
    Wednesday's run reviews Tuesday: offered, its band from Monday's close
    (₹505, the last close the analysis could read): 97% = 489.85, 102% =
    515.1."""
    _watch_rules(monkeypatch)
    out, excluded = _offered(MON, MON_2000_IST)
    assert out == [] and excluded == {"W": (
        "analysis of 2026-11-02 20:00 IST is after the close of 2026-11-02; waits for a "
        "review of a later session")}
    out, excluded = _offered(TUE, MON_2000_IST)
    assert excluded == {}
    idea = out[0]
    assert (idea.dived, idea.analysed_at) == ("2026-11-02", "2026-11-02T20:00:00+05:30")
    assert (idea.close_at_add, idea.entry_low, idea.entry_high) == (505.0, 489.85, 515.1)


def test_an_analysis_before_the_close_is_offered_for_that_close(monkeypatch):
    """W analysed Mon 2 Nov 11:00 IST: offered for Monday's close (Tuesday's
    run), its band from Friday's close (₹500, the last one struck before
    11:00 Monday): 485.0-510.0, not Monday's ₹505 (489.85-515.1). Monday's
    run reviews Friday, whose close is before the analysis."""
    _watch_rules(monkeypatch)
    out, excluded = _offered(MON, MON_1100_IST)
    assert excluded == {}
    assert [(i.close_at_add, i.entry_low, i.entry_high) for i in out] == [(500.0, 485.0, 510.0)]
    out, excluded = _offered(FRI, MON_1100_IST)
    assert out == [] and excluded == {"W": (
        "close of 2026-10-30 is before the analysis of 2026-11-02 11:00 IST; waits for a "
        "review of a later session")}


def test_a_watchlist_analysis_with_no_close_before_it_is_not_offered(monkeypatch):
    """Only Monday's bar is stored and the analysis ran at 11:00 Monday:
    there is no close it could have read."""
    _watch_rules(monkeypatch)
    rec = pr004.record(run_at=MON_1100_IST)
    window = _window({MON: 505.0})
    window = window[pd.to_datetime(window["date"]).dt.date == MON]
    out, excluded = cands_mod.buy_candidates(
        pr004.portfolio(watch=[("W", "user")]), MON, [], latest_analysis=lambda s: rec,
        window=window, listing=pr004.companies("W"), managed={})
    assert out == [] and excluded == {"W": "no close before the analysis of 2026-11-02 11:00 IST"}


# ---------------------------------------------------------------------------
# Every buy lane: a SWITCH leg, deployment, the shadow's switch test
# ---------------------------------------------------------------------------

def test_a_switch_leg_waits_for_a_close_after_the_analysis(tmp_path, monkeypatch):
    """Record mode, deployment off. AAA (1,000 × ₹100) is switched into W,
    analysed Mon 20:00 IST. At Monday's close (₹505) AAA is sold and W is
    not bought: the ₹1,00,000 stays in cash, said on the SELL. At Tuesday's
    close W is bought: floor(₹1,00,000 / ₹505) = 198 shares. The shadow's
    switch test agrees on both."""
    _watch_rules(monkeypatch)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    w = _w_idea(MON_2000_IST)
    story._prices(monkeypatch, {"W": 505.0})
    monkeypatch.setattr(ap, "_today_ist", lambda: WED)

    def switch(day):
        return AdviceRecord(date=day.isoformat(), user_id="u", symbol="AAA", verdict="SWITCH",
                            close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                            switch_candidate="W", rationale_hash=f"s{day}")
    s = story._store(tmp_path, [story._h("AAA", 1000, 100.0, "it_sector")], cash=900_000.0)
    txns, _ = story._run(s, [w], {"AAA": 100.0}, on=MON, advice=[switch(MON)])
    assert [(t.side, t.symbol, t.qty) for t in txns] == [("SELL", "AAA", 1000.0)]
    assert ap.switch_skip_reason(txns[0].note) == (
        "W: analysis of 2026-11-02 20:00 IST is after the close of 2026-11-02; ₹1,00,000 "
        "stays in cash")
    s2 = story._store(tmp_path, [story._h("AAA", 1000, 100.0, "it_sector")], cash=900_000.0,
                      name="u2")
    txns, _ = story._run(s2, [w], {"AAA": 100.0}, on=TUE, advice=[switch(TUE)])
    assert [(t.side, t.symbol, t.qty, t.date) for t in txns] == \
        [("SELL", "AAA", 1000.0, "2026-11-03"), ("BUY", "W", 198.0, "2026-11-03")]
    assert xs.switch_buy_lands(SessionClose(505.0, MON, "agree"), MON, w) is False
    assert xs.switch_buy_lands(SessionClose(505.0, TUE, "agree"), TUE, w) is True


def _watch_pipeline(tmp_path, monkeypatch, run_at, holdings=(), cash=1_200_000.0, prices=None):
    """The real pipeline over a user with ₹12 L cash (or `holdings` and `cash`)
    and the watchlist BUY of W (₹505 at every close asked, or `prices`), its
    readers faked; the day's regime NORMAL."""
    _watch_rules(monkeypatch)
    store, _ = story._pipeline_world(tmp_path, monkeypatch, list(holdings), cash, [],
                                     prices or {"W": 505.0})
    p = store.load()
    p.watchlist = [WatchlistItem(symbol="W", sector="pharma", added="2026-10-01", source="user")]
    store.save(p)
    rec = pr004.record(run_at=run_at)
    import services.data.fetchers.bhavcopy as bhavcopy
    import services.data.stores.eod_store as eod_store
    import services.data.stores.score_store as score_store
    monkeypatch.setattr(score_store, "ScoreStore",
                        lambda: SimpleNamespace(get_latest=lambda sym: rec))
    monkeypatch.setattr(eod_store, "EodStore",
                        lambda: SimpleNamespace(load_window=lambda end, sessions: _window()))
    monkeypatch.setattr(bhavcopy, "load_listing", lambda: pr004.companies("W"))
    return store


def _buys(store):
    return [(t.date, t.symbol, t.qty, t.price, t.verdict) for t in store.load_transactions()
            if t.side == "BUY"]


def test_deployment_waits_for_the_session_after_an_evening_analysis(tmp_path, monkeypatch):
    """RV5 through the real pipeline and deployment. Tuesday's run (review
    Mon 2 Nov) buys nothing: W is not offered. Wednesday's run (review Tue 3
    Nov) buys floor(₹80,000 / ₹505) = 158 shares, dated Tuesday."""
    store = _watch_pipeline(tmp_path, monkeypatch, MON_2000_IST)
    for review, run_day in ((MON, TUE), (TUE, WED)):
        monkeypatch.setattr(ap, "_today_ist", lambda d=run_day: d)
        state.update_sticky_regime("NORMAL", review.isoformat())
        pipeline.run_post_review_pipeline(review)
        if review == MON:
            assert _buys(store) == []
    assert _buys(store) == [("2026-11-03", "W", 158.0, 505.0, "DEPLOY")]


def test_deployment_buys_a_morning_analysis_at_that_days_close(tmp_path, monkeypatch):
    """W analysed Mon 11:00 IST, its band ₹485-510 from Friday's ₹500:
    Tuesday's run (review Monday) buys 158 × ₹505, dated Monday."""
    store = _watch_pipeline(tmp_path, monkeypatch, MON_1100_IST)
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    state.update_sticky_regime("NORMAL", MON.isoformat())
    pipeline.run_post_review_pipeline(MON)
    assert _buys(store) == [("2026-11-02", "W", 158.0, 505.0, "DEPLOY")]


def test_deployment_refuses_an_idea_decided_after_its_close_even_if_offered(tmp_path,
                                                                           monkeypatch):
    """The executor's own check, not only the candidate list's: handed W
    (analysed Mon 20:00 IST) for Monday's session, deployment opens nothing
    and names both times."""
    _watch_rules(monkeypatch)
    w = _w_idea(MON_2000_IST)
    story._prices(monkeypatch, {"W": 505.0})
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: "NORMAL")
    s = story._store(tmp_path, [], cash=1_200_000.0)
    txns, record = story._run(s, [w], {}, on=MON)
    assert txns == []
    assert story._outcomes(record)["W"] == (
        "before_dive", "analysis of 2026-11-02 20:00 IST is after the close of 2026-11-02")


def test_a_deep_dive_dated_a_trading_day_counts_as_made_after_its_close(tmp_path,
                                                                        monkeypatch):
    """The owner's manual discovery run on Mon 2 Nov dives MANX (no time is
    kept). Monday's review does not offer it; Tuesday's does. With Tuesday's
    bar missing, the close carried from Monday is not after the dive: no
    buy, in record mode as in enforce. A Saturday dive is offered on Monday
    (SA-049's tests)."""
    manx = f23._idea("MANX", 1000.0, 0.95, "pharma", MON)
    portfolio = SimpleNamespace(holdings=[], watchlist=[])
    out, excluded = cands_mod.buy_candidates(portfolio, MON, [manx], managed={})
    assert out == [] and excluded == {"MANX": (
        "deep dive of 2026-11-02 has no time, so it counts as made after that day's close; "
        "waits for a review of a later session")}
    out, excluded = cands_mod.buy_candidates(portfolio, TUE, [manx], managed={})
    assert [i.symbol for i in out] == ["MANX"] and excluded == {}
    story._prices(monkeypatch, {"MANX": 1000.0}, bars={"MANX": MON})
    monkeypatch.setattr(ap, "_today_ist", lambda: WED)
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: "NORMAL")
    s = story._store(tmp_path, [], cash=1_200_000.0)
    txns, record = story._run(s, [manx], {}, on=TUE)
    assert txns == []
    assert story._outcomes(record)["MANX"] == (
        "before_dive", "deep dive of 2026-11-02 has no time, so it counts as made after that "
        "day's close")


def _struck_after(bar: date, decided: datetime) -> bool:
    """The definition, written here: NSE's close is struck at 15:30 IST on
    the bar's day, and it must come strictly after the decision."""
    return datetime.combine(bar, time(15, 30), IST) > decided


def test_every_lane_uses_one_rule_over_every_half_hour_of_a_week(monkeypatch):
    """Analyses every 30 minutes from Fri 30 Oct 00:00 to Tue 3 Nov 23:30 IST
    (240 times), against bars Fri, Mon, Tue and Wed: the candidate list (for
    review session = bar), close_before_dive and the shadow's switch test
    each admit the close exactly when the definition above does. For a deep
    dive dated each of those days, the close is admitted exactly when the
    bar's day is later."""
    _watch_rules(monkeypatch)
    bars = (FRI, MON, TUE, WED)
    start = datetime.combine(FRI, time(0, 0), IST)
    checked = 0
    for k in range(240):
        at = start + timedelta(minutes=30 * k)
        run_at = (at - timedelta(hours=5, minutes=30)).replace(tzinfo=None).isoformat()
        idea = _w_idea(run_at) if _struck_after(WED, at) else None
        for bar in bars:
            expected = _struck_after(bar, at)
            out, excluded = _offered(bar, run_at)
            assert bool(out) == expected, (at, bar, excluded)
            if idea is not None:
                assert (close_before_dive(bar, idea) == "") == expected, (at, bar)
                lands = xs.switch_buy_lands(SessionClose(500.0, bar, "agree"), bar, idea)
                assert lands == expected, (at, bar)
            checked += 1
    assert checked == 960
    for dived in (FRI, SAT, MON, TUE):
        idea = f23._idea("X", 100.0, 0.9, "pharma", dived)
        for bar in bars:
            assert (close_before_dive(bar, idea) == "") == (bar > dived), (dived, bar)


# ---------------------------------------------------------------------------
# L1: an unknown regime adds nothing
# ---------------------------------------------------------------------------

def _full_review(monkeypatch, tmp_path, established_today=False, **yahoo):
    """The real daily review of today for TESTSHOCK (the shock-path seams:
    no LLM, no network), with the real regime detector over a fake Yahoo,
    after yesterday's review recorded NORMAL (and, with `established_today`,
    an earlier ticker's review established today NORMAL). Returns the
    prediction store, the review's feedback entry and the seam module."""
    from tests.unit.intelligence.rl import test_shock_path as sp
    sp._setup_store(tmp_path)
    sp._patch_common(dr, monkeypatch, tmp_path, actual_close=100.1)
    from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
    monkeypatch.setattr(FeedbackAgent, "run",
                        lambda self, fb_input, ledger: sp._fb_output("magnitude"))
    monkeypatch.setattr(dr.RegimeDetector, "detect", REAL_DETECT)
    monkeypatch.setattr(dr, "regenerate_envelope", lambda **kw: None)
    state.update_sticky_regime("NORMAL", (sp.REVIEW_DATE - timedelta(days=1)).isoformat())
    if established_today:
        state.update_sticky_regime("NORMAL", sp.DATE_STR)
    f23._yahoo(monkeypatch, **yahoo)
    summary = dr.run_daily_review(sp.TICKER, sp.REVIEW_DATE, sector=sp.SECTOR)
    assert summary["status"] == "completed", summary
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    ps = PredictionStore(sp.TICKER, sector=sp.SECTOR, base_dir=tmp_path)
    log = ps.load_feedback_log(ps.cycle_id_for(sp.REVIEW_DATE))
    return ps, log.entries[-1], sp


def _add_ready(ps, sp):
    """The advisor's signals from the review's own artifacts, then set where
    ADD would fire: an UP envelope, 7-day accuracy 0.70 (floor 0.60), a 5%
    position (cap 10%), the session's close and an actionable forecast."""
    holding = story._h(sp.TICKER, 100, 100.0, sp.SECTOR)
    portfolio = Portfolio(user_id="u", holdings=[holding], cash_deployable=90_000.0)
    sig = build_signals(holding, portfolio, sp.REVIEW_DATE, ps, {}, close=100.0)
    return holding, sig.model_copy(update={
        "envelope_direction": "UP", "direction_accuracy_7d": 0.70, "position_weight_pct": 5.0,
        "price_fresh": True, "forecast_gate": "actionable"})


@pytest.mark.parametrize("mode", ["record", "enforce"])
def test_a_dark_day_holds_add_and_names_the_day_and_why(tmp_path, monkeypatch, mode):
    """RV6: NORMAL recorded yesterday; today India VIX is dark and the Nifty
    fell 3.0% in five sessions, so the label could be NORMAL or MACRO_CRISIS.
    The review keeps NORMAL and its feedback entry says why; the advisor
    holds the ADD the kept NORMAL would allow, in either gate mode, and the
    record and its narrative name the day and 'India VIX did not answer'.
    (The mode is set after the review, which enforce would gate on its own
    fixture's forecast rows.)"""
    end = date.today()
    ps, entry, sp = _full_review(monkeypatch, tmp_path, vix=None,
                                 nifty=f23._nifty_falling(end), **f23._calm_globals(end))
    monkeypatch.setattr(settings, "DECISION_GATE_MODE", mode)
    dg._warned.clear()
    assert (entry.regime_label, entry.regime_unavailable) == ("NORMAL", "India VIX did not answer")
    holding, sig = _add_ready(ps, sp)
    why = f"market regime unavailable for {sp.DATE_STR}: India VIX did not answer"
    assert (sig.regime_label, sig.regime_unavailable) == ("NORMAL", why)
    rec, _ = pipeline.gated_decide(sig, holding, "balanced", shelf_ideas=[], sector_weights={},
                                   held_symbols={sp.TICKER}, candidate_fresh={})
    assert (rec.verdict, rec.triggers, rec.notes) == ("HOLD", [], ["REGIME_UNAVAILABLE"])
    assert rec.regime_unavailable == why and rec.data_gate is None
    assert f"an add was withheld: {why}" in fallback_narrative(rec)


def test_an_established_day_adds_as_before(tmp_path, monkeypatch):
    """The control: India VIX answers 15.0 and the Nifty is flat: NORMAL is
    established, the entry carries no reason, and the same signals ADD."""
    end = date.today()
    ps, entry, sp = _full_review(monkeypatch, tmp_path, vix=f23._flat(15.0, end),
                                 nifty=f23._flat(24_000.0, end), **f23._calm_globals(end))
    assert (entry.regime_label, entry.regime_unavailable) == ("NORMAL", "")
    holding, sig = _add_ready(ps, sp)
    assert sig.regime_unavailable == ""
    rec = decide(sig, holding, "balanced")
    assert (rec.verdict, rec.triggers, rec.regime_unavailable, rec.notes) == \
        ("ADD", ["add_bullish_healthy"], "", [])


# ---------------------------------------------------------------------------
# FIX-025 (routed from this story's review: L2, T3)
# ---------------------------------------------------------------------------

def _next_day_signals(tmp_path, monkeypatch, *, mark=None):
    """A holding reviewed on the established day, with no entry of its own for
    the next: its failed or skipped review wrote nothing. `mark` runs on the
    next day's market-wide state. The signals are set where ADD would fire."""
    end = date.today()
    ps, entry, sp = _full_review(monkeypatch, tmp_path, vix=f23._flat(15.0, end),
                                 nifty=f23._flat(24_000.0, end), **f23._calm_globals(end))
    assert entry.regime_unavailable == ""
    next_day = sp.REVIEW_DATE + timedelta(days=1)
    if mark:
        mark(next_day.isoformat())
    holding = story._h(sp.TICKER, 100, 100.0, sp.SECTOR)
    portfolio = Portfolio(user_id="u", holdings=[holding], cash_deployable=90_000.0)
    sig = build_signals(holding, portfolio, next_day, ps, {}, close=100.0)
    return holding, next_day.isoformat(), sig.model_copy(update={
        "envelope_direction": "UP", "direction_accuracy_7d": 0.70, "position_weight_pct": 5.0,
        "price_fresh": True, "forecast_gate": "actionable"})


def test_no_entry_of_its_own_on_a_dark_day_holds_the_add(tmp_path, monkeypatch):
    """The review's L2: the older entry is established, but the market-wide
    state marks today unavailable, so the ADD is held and says so."""
    holding, day, sig = _next_day_signals(
        tmp_path, monkeypatch,
        mark=lambda d: state.record_unavailable_day(d, "India VIX did not answer", ""))
    assert sig.regime_unavailable == f"market regime unavailable for {day}: India VIX did not answer"
    rec = decide(sig, holding, "balanced")
    assert (rec.verdict, rec.notes) == ("HOLD", ["REGIME_UNAVAILABLE"])
    assert rec.regime_unavailable == sig.regime_unavailable


def test_no_entry_of_its_own_and_no_regime_recorded_holds_the_add(tmp_path, monkeypatch):
    """No other review recorded the day at all: nothing says the market is calm."""
    holding, day, sig = _next_day_signals(tmp_path, monkeypatch)
    assert sig.regime_unavailable == f"no market regime recorded for {day}"
    assert decide(sig, holding, "balanced").verdict == "HOLD"


def test_no_entry_of_its_own_on_an_established_day_still_adds(tmp_path, monkeypatch):
    """The control: another ticker's review established today, so the holding's
    older entry costs it nothing."""
    holding, _, sig = _next_day_signals(
        tmp_path, monkeypatch, mark=lambda d: state.update_sticky_regime("NORMAL", d))
    assert sig.regime_unavailable == ""
    rec = decide(sig, holding, "balanced")
    assert (rec.verdict, rec.notes) == ("ADD", [])


def test_an_entry_of_its_own_for_the_day_never_asks_the_market_wide_record(tmp_path, monkeypatch):
    """The holding's own established entry for the day decides: the market-wide
    state is not read (here it would answer "no label"), and the ADD fires."""
    end = date.today()
    ps, entry, sp = _full_review(monkeypatch, tmp_path, vix=f23._flat(15.0, end),
                                 nifty=f23._flat(24_000.0, end), **f23._calm_globals(end))
    assert entry.date == sp.DATE_STR
    asked: list = []
    monkeypatch.setattr(state, "label_recorded_for", lambda day: asked.append(day))
    holding, sig = _add_ready(ps, sp)
    assert asked == [] and sig.regime_unavailable == ""
    assert decide(sig, holding, "balanced").verdict == "ADD"


def _stop_breach(tmp_path, monkeypatch, run_at, folder):
    """AAA 1,000 × ₹100 now ₹70 (−30%, past any ATR stop), ₹9,00,000 cash,
    deployment off, so only a SWITCH can buy; W the only idea."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    return _watch_pipeline(tmp_path / folder, monkeypatch, run_at,
                           holdings=[story._h("AAA", 1000, 100.0, "it_sector")], cash=900_000.0,
                           prices={"AAA": 70.0, "W": 505.0})


def _review(store, monkeypatch, session, run_day):
    monkeypatch.setattr(ap, "_today_ist", lambda d=run_day: d)
    state.update_sticky_regime("NORMAL", session.isoformat())
    pipeline.run_post_review_pipeline(session)
    return {r.symbol: (r.verdict, r.switch_candidate) for r in store.load_advice()}


def test_a_real_switch_buys_a_morning_analysis_at_that_days_close(tmp_path, monkeypatch):
    """The review's T3, with no hand-made advice: a real stop breach, the real
    decide and the real executor. W analysed Mon 11:00 IST: Monday's close was
    struck after it. The ₹70,000 of AAA's sale buys floor(70,000 / 505) = 138
    shares of W, dated Monday."""
    store = _stop_breach(tmp_path, monkeypatch, MON_1100_IST, "morning")
    assert _review(store, monkeypatch, MON, TUE) == {"AAA": ("SWITCH", "W")}
    assert _buys(store) == [("2026-11-02", "W", 138.0, 505.0, "SWITCH")]


def test_a_real_switch_waits_for_the_close_after_an_evening_analysis(tmp_path, monkeypatch):
    """W analysed Mon 20:00 IST. Monday's review offers it no longer: a plain EXIT.
    In a fresh copy, Tuesday's review offers it: the SWITCH buys 138 at Tuesday's
    close, dated Tuesday."""
    store = _stop_breach(tmp_path, monkeypatch, MON_2000_IST, "monday")
    assert _review(store, monkeypatch, MON, TUE) == {"AAA": ("EXIT", "")}
    assert _buys(store) == []
    store = _stop_breach(tmp_path, monkeypatch, MON_2000_IST, "tuesday")
    assert _review(store, monkeypatch, TUE, WED) == {"AAA": ("SWITCH", "W")}
    assert _buys(store) == [("2026-11-03", "W", 138.0, 505.0, "SWITCH")]


def test_a_dark_day_after_a_day_already_established_keeps_that_days_label(tmp_path,
                                                                          monkeypatch):
    """A first ticker established today NORMAL; this review then finds India
    VIX dark. Today's label is established, so the entry carries no reason
    and ADD is not held."""
    end = date.today()
    ps, entry, sp = _full_review(monkeypatch, tmp_path, established_today=True, vix=None,
                                 nifty=f23._nifty_falling(end), **f23._calm_globals(end))
    assert state.label_recorded_for(sp.DATE_STR) == "NORMAL"
    assert (entry.regime_label, entry.regime_unavailable) == ("NORMAL", "")
    holding, sig = _add_ready(ps, sp)
    assert decide(sig, holding, "balanced").verdict == "ADD"


def test_the_crisis_exit_still_reads_the_kept_label():
    """Decision F24-D3: a crisis entered before a run of dark days stays, and
    with a DOWN envelope the crisis exit sells; a sale is never blocked by a
    missing input. The record still says the day's regime was not known."""
    why = "market regime unavailable for 2026-10-30: India VIX did not answer"
    holding = story._h("H", 100, 100.0, "pharma")
    sig = AdvisorSignals(symbol="H", sector="pharma", close=100.0, atr_stop_pct=12.0,
                         unrealised_pnl_pct=0.0, holding_age_days=40,
                         regime_label="MACRO_CRISIS", regime_unavailable=why,
                         envelope_direction="DOWN")
    rec = decide(sig, holding, "balanced")
    assert (rec.verdict, rec.triggers, rec.notes, rec.regime_unavailable) == \
        ("EXIT", ["crisis_regime_bearish"], [], why)


# ---------------------------------------------------------------------------
# L2: a fresh state is established for its own day
# ---------------------------------------------------------------------------

def test_a_fresh_state_keeps_its_day_against_a_later_dark_review(tmp_path, monkeypatch):
    """RV3: no state file. Friday's first review answers NORMAL (VIX 15, the
    Nifty flat) and writes a fresh state; the second finds India VIX empty
    (VIX above 22 alone would make it RISK_OFF). Friday stays NORMAL: not
    marked, still recorded, and deployment buys on it."""
    path = tmp_path / "pred" / "_regime_state.json"
    assert not path.exists()
    f23._yahoo(monkeypatch, vix=f23._flat(15.0), nifty=f23._flat(24_000.0), **f23._calm_globals())
    f23._review(FRI)
    assert "_last_update" not in json.loads(path.read_text(encoding="utf-8"))
    f23._yahoo(monkeypatch, vix=None, nifty=f23._flat(24_000.0), **f23._calm_globals())
    assert RegimeDetector().detect(FRI, "pharma").unavailable == "India VIX did not answer"
    f23._review(FRI, ticker="TICK2")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert (saved["label"], saved["since"], saved["calm_streak"]) == ("NORMAL", "2026-10-30", 0)
    assert "_unavailable" not in saved
    assert state.label_recorded_for(FRI.isoformat()) == "NORMAL"
    txns, rec = f23._deploy_on(tmp_path, monkeypatch)
    assert rec["regime"] == "NORMAL" and len(txns) == 2


def test_a_fresh_state_counts_one_calm_day_per_day():
    """The same rule in update_sticky_regime: a fresh RISK_OFF on Friday, then
    a second NORMAL detection that Friday, is not a calm day (Friday's label
    is the first established one); Monday's NORMAL is calm day 1 of 3."""
    state.update_sticky_regime("RISK_OFF", FRI.isoformat())
    again = state.update_sticky_regime("NORMAL", FRI.isoformat())
    assert (again.label, again.calm_streak) == ("RISK_OFF", 0)
    monday = state.update_sticky_regime("NORMAL", MON.isoformat())
    assert (monday.label, monday.calm_streak) == ("RISK_OFF", 1)
