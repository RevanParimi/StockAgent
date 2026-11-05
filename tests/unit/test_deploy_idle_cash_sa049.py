"""SA-049 — put idle cash to work in normal markets.

Every expected figure is worked by hand in the test's docstring or comments
from the fixture's own numbers, never asked of the code under test. The
worked examples run without trading costs (SA-048's charges are pinned by
test_trading_costs_sa048.py); the property test runs on the configured rates.

Settings these examples assume (the owner's decisions of 12 Oct and 1 Nov):
target invested share 80% in NORMAL-like regimes, 50% in RISK_OFF, none in
MACRO_CRISIS; 2 new positions a day; at least 10 holdings, aim 12, at most
15; ₹10 L invested; so a new position asks for ₹10,00,000 / 12 = ₹83,333.33.
Caps: position 10%, sector 30% of total equity; cash floor ₹10,000.

Independent invariants:
- the card's acceptance fixtures (the 27 Sep shape, a crisis, target reached,
  no qualifying idea, SA-003 enforce and record, the same day twice, the
  switch off, the breadth floor and the D1/D2 decisions);
- a property test over random regimes, shelves and portfolios: nothing new in
  a crisis or without a regime, no cap breached, cash at or above its floor,
  at most N a day, never above the maximum holdings, and, at or above the
  holdings floor, the invested share never past the target by more than one
  position (below it, a case pins how far buying goes);
- issue time: the 16:30 run books at the close of the session it reviews, so
  an idea dived after that session (Saturday's dives on Monday's run, which
  reviews Friday) is neither deployed nor a SWITCH destination until a run
  reviews a session on or after the dive;
- the routed fixes: SA-050 R1 (whole shares at an exact boundary), SA-050 R2
  (a second switch into one stock), SA-051 R1 (a holding added during the
  run), FIX-016 (the benchmark once deployment is on), FIX-011 (generic
  sector keys, a surveillance check on every new position, and its report
  read through the real reader: any status but "A" refuses, the cache
  serves only its own day, nothing older than 7 days);
- the DEPOSIT route and the pipeline end to end.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.api.routes.portfolio_api as papi
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import Shelf, ShelfIdea
from backend.shared.schemas.portfolio import AdviceRecord, Holding, TransactionRecord
from core.config import settings
from core.portfolio import autopilot as ap
from core.portfolio import deployment, sizing
from core.portfolio import results as R
from core.portfolio.pricing import SessionClose
from core.portfolio.store import PortfolioStore

REAL_SURVEILLANCE_REPORT = ap.surveillance_report   # before conftest's stub is applied
D = date(2026, 7, 13)                       # a Monday
TODAY = date(2026, 7, 31)                   # the executor refuses a future review day
REPORT_DAY = "2026-07-10"
CONFIGURED_COSTS = dict(settings.PORTFOLIO_COSTS)
NO_COSTS = {**CONFIGURED_COSTS, "brokerage_pct": 0.0, "stt_pct": 0.0,
            "stamp_duty_buy_pct": 0.0, "exchange_fee_pct": 0.0, "sebi_fee_pct": 0.0,
            "dp_charge_inr": 0.0}
TARGETS = {"NORMAL": 80.0, "RISK_ON": 80.0, "MOMENTUM_EXTENDED": 80.0, "OVERSOLD": 80.0,
           "RISK_OFF": 50.0, "MACRO_CRISIS": 0.0}


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    """The owner's settings, deployment on, no trading costs, a frozen clock,
    no managed-ticker writes, NORMAL recorded for every day, and a
    surveillance report that clears every symbol listed in `CLEAR` (and any
    other symbol: see `_report`)."""
    for name, value in {
        "PORTFOLIO_COSTS": NO_COSTS, "ADVISOR_MAX_POSITION_PCT": 10.0,
        "ADVISOR_MAX_SECTOR_PCT": 30.0, "AUTOPILOT_MIN_CASH_FLOOR": 10_000.0,
        "AUTOPILOT_ENABLED": True, "AUTOPILOT_DEPLOY_IDLE_CASH": True,
        "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY": 2, "AUTOPILOT_DEPLOY_TARGET_PCT": dict(TARGETS),
        "PORTFOLIO_MIN_HOLDINGS": 10, "PORTFOLIO_TARGET_HOLDINGS": 12,
        "PORTFOLIO_MAX_HOLDINGS": 15, "PORTFOLIO_MIN_INVESTED_INR": 1_000_000.0,
        "PORTFOLIO_OVERRIDES": {}, "DECISION_GATE_MODE": "record",
    }.items():
        monkeypatch.setattr(settings, name, value)
    dg._warned.clear()
    monkeypatch.setattr(ap, "_today_ist", lambda: TODAY)
    monkeypatch.setattr(ap, "promote_symbol", lambda *a, **k: {"status": "ok"})
    _regime(monkeypatch, "NORMAL")
    _report(monkeypatch)


def _regime(monkeypatch, label):
    monkeypatch.setattr(deployment, "recorded_regime", lambda on: label)


def _report(monkeypatch, measures=None, status=None, unlisted=(), dark=False):
    """NSE's report as of REPORT_DAY: every symbol active and under no
    measure, but for `measures` {symbol: [..]}, `status` {symbol: "S"} and
    `unlisted`; `dark` = no report at all."""
    measures, status = measures or {}, status or {}

    class Report(dict):
        def get(self, key, default=None):
            if key in unlisted:
                return None
            return {"status": status.get(key, "A"), "measures": list(measures.get(key, []))}

    reads = []

    def read(session):
        reads.append(session)
        return (None, None) if dark else (Report(), REPORT_DAY)
    monkeypatch.setattr(ap, "surveillance_report", read)
    return reads


def _h(sym, qty, price, sector):
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _store(tmp_path, holdings, cash, name="u", capital_in=1_000_000.0):
    s = PortfolioStore(user_id=name, base_dir=str(tmp_path / "pf"))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, capital_in, True
    s.save(p)
    return s


def _idea(sym, price, conviction=0.8, sector="pharma", gate="actionable", dived="2026-07-08",
          lo=None, hi=None, inval=None, **kw):
    """An idea whose band holds `price`: 96-104% of it, invalidation at 90%."""
    return ShelfIdea(symbol=sym, sector=sector, added="2026-07-01", dived=dived,
                     conviction=conviction, data_gate=gate,
                     entry_low=round(price * 0.96, 2) if lo is None else lo,
                     entry_high=round(price * 1.04, 2) if hi is None else hi,
                     invalidation_level=round(price * 0.90, 2) if inval is None else inval,
                     thesis=f"why {sym}", **kw)


def _prices(monkeypatch, prices, bars=None):
    """The executor's close for each symbol, dated the session asked (or
    `bars[sym]`, a stale bar); a symbol not in `prices` has no close."""
    bars = bars or {}

    def quote(sym, d):
        if sym not in prices:
            raise LookupError(f"no close for {sym}")
        return SessionClose(prices[sym], bars.get(sym, d), "agree"), d
    monkeypatch.setattr(ap, "session_close", quote)


def _run(store, ideas, closes, on=D, advice=(), report=None):
    out = {} if report is None else report
    txns = ap.execute_advice(store, store.load(), list(advice), closes, on,
                             sector_lookup={i.symbol: i.sector for i in ideas},
                             shelf_index={i.symbol: i for i in ideas}, report=out)
    return txns, out.get("deployment")


def _buys(txns):
    return [(t.symbol, t.qty, t.price) for t in txns if t.side == "BUY"]


def _equity(store, marks):
    p = store.load()
    return sum(h.adj_qty * marks.get(h.symbol, h.adj_avg_price) for h in p.holdings) \
        + p.cash_deployable


def _outcomes(record):
    return {o["symbol"]: (o["outcome"], o["why"]) for o in record["ideas"]}


# ---------------------------------------------------------------------------
# The card's acceptance fixtures
# ---------------------------------------------------------------------------

def _sep27(tmp_path, monkeypatch):
    """The 27 Sep shape: AAA 1,000 × ₹100 and BBB 900 × ₹100 (₹1,90,000)
    and ₹8,10,000 cash: equity ₹10,00,000, 81% cash, 2 holdings.
    Three qualifying ideas: P1 (0.90, ₹500, pharma), P2 (0.80, ₹250,
    chemicals), P3 (0.70, ₹1,000, capgoods)."""
    s = _store(tmp_path, [_h("AAA", 1000, 100.0, "it_sector"), _h("BBB", 900, 100.0, "fmcg")],
               cash=810_000.0)
    ideas = [_idea("P1", 500.0, 0.9, "pharma"), _idea("P2", 250.0, 0.8, "chemicals"),
             _idea("P3", 1000.0, 0.7, "capgoods")]
    _prices(monkeypatch, {"P1": 500.0, "P2": 250.0, "P3": 1000.0})
    return s, ideas


def test_the_27_sep_shape_buys_two_today_and_the_third_tomorrow(tmp_path, monkeypatch):
    """Target: 80% of ₹10 L is ₹8 L; the ₹10 L floor raises it to ₹10 L, but
    only ₹9,90,000 sits above the ₹10,000 cash floor, so the target is
    ₹9,90,000 (99.0%) and the invested floor is recorded unreachable.
    Each position asks for ₹83,333.33:
      P1 floor(83,333.33 / 500) = 166 shares = ₹83,000 (8.3% of equity);
      P2 floor(83,333.33 / 250) = 333 shares = ₹83,250 (8.3%).
    Then 2 new positions, the daily limit; P3 qualifies and waits.
    Invested ₹1,90,000 (19.0%) → ₹2,73,000 (27.3%) → ₹3,56,250 (35.6%);
    cash ₹8,10,000 − 83,000 − 83,250 = ₹6,43,750.
    Next day P1 and P2 are held; P3: floor(83,333.33 / 1,000) = 83 shares
    = ₹83,000, invested ₹4,39,250 (43.9%), cash ₹5,60,750."""
    s, ideas = _sep27(tmp_path, monkeypatch)
    marks = {"AAA": 100.0, "BBB": 100.0}
    txns, rec = _run(s, ideas, dict(marks))

    assert _buys(txns) == [("P1", 166.0, 500.0), ("P2", 333.0, 250.0)]
    assert txns[0].note == ("deploy_idle_cash: discovery idea, conviction 0.90; regime NORMAL, "
                            "target 99.0% invested (₹9,90,000); invested 19.0% before, "
                            "27.3% after")
    assert txns[1].note.endswith("invested 27.3% before, 35.6% after")
    assert all(t.verdict == "DEPLOY" and t.source == "autopilot" for t in txns)
    assert txns[0].reason == "why P1"
    p = s.load()
    assert p.cash_deployable == 643_750.0
    for t in txns:
        assert t.qty * t.price / 1_000_000 <= 0.10
    assert (rec["regime"], rec["target_share_pct"], rec["target_inr"], rec["target_pct"]) == \
        ("NORMAL", 80.0, 990_000.0, 99.0)
    assert (rec["invested_before_pct"], rec["invested_after_pct"]) == (19.0, 35.6)
    assert (rec["holdings_before"], rec["holdings_after"], rec["bought"]) == (2, 4, ["P1", "P2"])
    assert rec["reasons"] == [
        "2 new positions today, the daily limit of 2",
        "invested floor unreachable: equity ₹10,00,000 is below the ₹10,00,000 floor plus "
        "the ₹10,000 cash floor",
        "holdings floor unreachable: 3 qualifying ideas, 4 holdings against at least 10",
        "1 idea qualifying but not bought today",
    ]
    assert _outcomes(rec)["P3"] == (
        "waiting", "qualifies; not bought: 2 new positions today, the daily limit of 2")

    day2 = D + timedelta(days=1)
    txns2, rec2 = _run(s, ideas, {**marks, "P1": 500.0, "P2": 250.0}, on=day2)
    assert _buys(txns2) == [("P3", 83.0, 1000.0)]
    assert txns2[0].note.endswith("invested 35.6% before, 43.9% after")
    assert s.load().cash_deployable == 560_750.0
    assert _outcomes(rec2)["P1"] == ("held", "already held")
    assert rec2["bought"] == ["P3"]


def test_in_a_crisis_nothing_new_is_bought_and_an_exit_still_sells(tmp_path, monkeypatch):
    s, ideas = _sep27(tmp_path, monkeypatch)
    _regime(monkeypatch, "MACRO_CRISIS")
    reads = _report(monkeypatch)
    exit_bbb = AdviceRecord(date=D.isoformat(), user_id="u", symbol="BBB", verdict="EXIT",
                            close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                            rationale_hash="xb")
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0}, advice=[exit_bbb])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "BBB")]
    assert rec["reasons"] == ["market regime MACRO_CRISIS: no new positions, cash held on purpose"]
    assert rec["bought"] == [] and rec["ideas"] == []
    assert reads == []                     # nothing was evaluated, so NSE was not read


def test_with_no_regime_recorded_for_the_day_nothing_is_bought(tmp_path, monkeypatch):
    s, ideas = _sep27(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path / "pred"))  # no state file
    _regime(monkeypatch, None)
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert txns == []
    assert rec["reasons"] == [f"no market regime recorded for {D.isoformat()}; no new positions"]


def test_target_reached_buys_nothing_and_says_so(tmp_path, monkeypatch):
    """RISK_OFF: target 50% of ₹10 L = ₹5 L. AAA 5,500 × ₹100 = ₹5,50,000
    is 55.0% invested, so nothing is bought."""
    s = _store(tmp_path, [_h("AAA", 5500, 100.0, "it_sector")], cash=450_000.0)
    _regime(monkeypatch, "RISK_OFF")
    _prices(monkeypatch, {"P1": 500.0})
    txns, rec = _run(s, [_idea("P1", 500.0)], {"AAA": 100.0})
    assert txns == []
    assert rec["reasons"] == ["regime RISK_OFF, target reached: 55.0% invested against a "
                              "target of 50.0% (₹5,00,000)"]


def test_no_qualifying_idea_records_each_ideas_reason(tmp_path, monkeypatch):
    """Enforce mode. AAA (held) 1,000 × ₹100; cash ₹9,00,000. One idea per
    reason; BUSY is in pharma, where PHX already holds ₹3,00,000 = 30%."""
    monkeypatch.setattr(settings, "DECISION_GATE_MODE", "enforce")
    s = _store(tmp_path, [_h("AAA", 1000, 100.0, "it_sector"),
                          _h("PHX", 3000, 100.0, "pharma")], cash=600_000.0)
    s.append_transaction(TransactionRecord(
        txn_id="sold", date="2026-07-10", ts="2026-07-10T10:00:00+00:00", user_id="u",
        symbol="SOLD", side="SELL", qty=10, price=100.0, value=1000.0, cash_before=599_000.0,
        cash_after=600_000.0, holding_qty_after=0.0, verdict="EXIT"))
    ideas = [
        _idea("AAA", 100.0, 0.99, "it_sector"),
        _idea("HIGH", 120.0, 0.95, "chemicals", lo=95.0, hi=105.0, inval=85.0),
        _idea("LOW", 80.0, 0.94, "metals", lo=95.0, hi=105.0, inval=85.0),
        _idea("ABST", 100.0, 0.93, "infra", gate="abstain"),
        _idea("STALE", 100.0, 0.92, "telecom"),
        _idea("WATCHED", 100.0, 0.91, "media"),
        _idea("NOPRICE", 100.0, 0.90, "retail"),
        _idea("HUGE", 200_000.0, 0.89, "defence"),
        _idea("BUSY", 500.0, 0.88, "pharma"),
        _idea("SOLD", 100.0, 0.87, "fmcg", dived="2026-07-08"),
    ]
    _prices(monkeypatch, {"AAA": 100.0, "HIGH": 120.0, "LOW": 80.0, "ABST": 100.0,
                          "STALE": 100.0, "WATCHED": 100.0, "HUGE": 200_000.0, "BUSY": 500.0,
                          "SOLD": 100.0},
            bars={"STALE": date(2026, 7, 10)})
    _report(monkeypatch, measures={"WATCHED": ["LT-ASM"]})
    txns, rec = _run(s, ideas, {"AAA": 100.0, "PHX": 100.0})
    assert txns == []
    got = _outcomes(rec)
    assert got == {
        "AAA": ("held", "already held"),
        "HIGH": ("band", "14.3% above entry band (₹95–₹105); needs a fresh deep dive"),
        "LOW": ("invalidated", "at or below its invalidation level ₹85; the idea's case no "
                               "longer holds"),
        "ABST": ("gate", "withheld by the data gate: its deep dive's data gate is abstain "
                         "(not verified as actionable)"),
        "STALE": ("gate", "withheld by the data gate: its close is from bar 2026-07-10, not "
                          "the review session"),
        "WATCHED": ("surveillance", "under LT-ASM in NSE's surveillance report of 2026-07-10"),
        "NOPRICE": ("price", "no close for the review session"),
        "HUGE": ("size", "₹83,333 of a new position's budget is less than one share at "
                         "₹200,000"),
        "BUSY": ("size", "the 30% cap on pharma leaves room for less than one share at ₹500"),
        "SOLD": ("sold", "sold on 2026-07-10, after its deep dive of 2026-07-08; waits for a "
                         "new deep dive"),
    }
    assert rec["reasons"][0] == "no further qualifying idea"
    assert "2 ideas withheld by the data gate" in rec["reasons"]
    assert "1 idea above entry band" in rec["reasons"]
    assert "holdings floor unreachable: 0 qualifying ideas, 2 holdings against at least 10" \
        in rec["reasons"]


@pytest.mark.parametrize("mode", ["enforce", "record"])
def test_sa003_an_abstained_idea_is_never_bought_in_enforce(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(settings, "DECISION_GATE_MODE", mode)
    s = _store(tmp_path, [], cash=1_200_000.0)
    _prices(monkeypatch, {"ABST": 1000.0, "UNV": 1000.0}, bars={"UNV": date(2026, 7, 10)})
    ideas = [_idea("ABST", 1000.0, 0.9, "infra", gate="abstain"),
             _idea("UNV", 1000.0, 0.8, "telecom", gate="")]
    txns, rec = _run(s, ideas, {})
    if mode == "enforce":
        assert txns == []
        assert {o["outcome"] for o in rec["ideas"]} == {"gate"}
    else:
        assert _buys(txns) == [("ABST", 83.0, 1000.0), ("UNV", 83.0, 1000.0)]
        assert txns[0].note.endswith("record mode: the data gate would withhold it: its deep "
                                     "dive's data gate is abstain (not verified as actionable)")
        assert txns[1].note.endswith(
            "record mode: the data gate would withhold it: its deep dive's data gate is "
            "unknown (not verified as actionable); its close is from bar 2026-07-10, not "
            "the review session")


def test_the_same_review_date_twice_buys_nothing_twice(tmp_path, monkeypatch):
    s, ideas = _sep27(tmp_path, monkeypatch)
    first, _ = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    again, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert len(first) == 2 and again == [] and rec is None
    assert [t.symbol for t in s.load_transactions() if t.side == "BUY"] == ["P1", "P2"]


def test_switch_off_is_the_old_executor(tmp_path, monkeypatch):
    """With the switch off, the deployment step never runs (it would raise),
    the regime is never read, no record is made, and the same day's trades
    are those of a run with no candidates at all: the EXIT and the SWITCH."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(deployment, "recorded_regime",
                        lambda on: (_ for _ in ()).throw(AssertionError("regime read")))
    monkeypatch.setattr(ap, "_deploy_idle_cash",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("deployed")))
    advice = [
        AdviceRecord(date=D.isoformat(), user_id="u", symbol="BBB", verdict="EXIT",
                     close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0, rationale_hash="x"),
        AdviceRecord(date=D.isoformat(), user_id="u", symbol="AAA", verdict="SWITCH",
                     close=100.0, unrealised_pnl_pct=-13.0, stop_pct=12.0,
                     switch_candidate="P1", rationale_hash="s"),
    ]
    runs = []
    for name, with_ideas in (("a", True), ("b", False)):
        s, ideas = _sep27(tmp_path / name, monkeypatch)
        txns, rec = _run(s, ideas if with_ideas else [ideas[0]],
                         {"AAA": 100.0, "BBB": 100.0}, advice=advice)
        assert rec is None
        p = s.load()
        runs.append(([(t.side, t.symbol, t.qty, t.price, t.note) for t in txns],
                     p.cash_deployable, sorted((h.symbol, h.adj_qty) for h in p.holdings)))
    assert runs[0] == runs[1]
    assert [r[:2] for r in runs[0][0]] == [("SELL", "AAA"), ("SELL", "BBB"), ("BUY", "P1")]


def test_a_failing_deployment_never_costs_the_days_sells(tmp_path, monkeypatch):
    """The deployment step raises half-way (after it bought on its copy): the
    EXIT of BBB is still saved, nothing is bought, the cash is the sale's,
    and the record and the digest text say what failed."""
    from core.portfolio.digest_text import render_digest_text
    s, ideas = _sep27(tmp_path, monkeypatch)
    real = ap._deploy_idle_cash

    def half_way(portfolio, *a, **k):
        real(portfolio, *a, **k)               # buys P1 and P2 on the copy
        raise RuntimeError("boom")
    monkeypatch.setattr(ap, "_deploy_idle_cash", half_way)
    exit_bbb = AdviceRecord(date=D.isoformat(), user_id="u", symbol="BBB", verdict="EXIT",
                            close=100.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                            rationale_hash="xb")
    closes = {"AAA": 100.0, "BBB": 100.0}
    txns, rec = _run(s, ideas, closes, advice=[exit_bbb])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "BBB")]
    assert [(t.side, t.symbol) for t in s.load_transactions()] == [("SELL", "BBB")]
    p = s.load()
    assert (p.cash_deployable, [h.symbol for h in p.holdings]) == (900_000.0, ["AAA"])
    assert "P1" not in closes and p.last_autopilot_run == D.isoformat()
    assert rec["error"] == "deployment failed: boom" and rec["bought"] == []
    assert "Idle cash: nothing bought; deployment failed: boom" in render_digest_text(
        {"date": D.isoformat(), "deployment": rec})


def test_an_unreadable_surveillance_report_means_no_report(monkeypatch):
    import services.data.fetchers.surveillance as fetcher
    monkeypatch.setattr(fetcher, "surveillance_list",
                        lambda session: (_ for _ in ()).throw(OSError("disk")))
    assert REAL_SURVEILLANCE_REPORT(D) == (None, None)
    assert sizing.surveillance_issue("P1", REAL_SURVEILLANCE_REPORT(D)) == \
        "NSE's surveillance report is unavailable (none from the last 7 days)"


def test_the_switch_is_off_in_the_shipped_config():
    from backend.shared.config.settings.loader import cfg
    assert cfg("autopilot.deploy_idle_cash") is False
    assert cfg("portfolio.overrides") == {}
    assert {k: float(v) for k, v in cfg("autopilot.deploy_target_invested_pct").items()} \
        == TARGETS
    assert (cfg("autopilot.deploy_max_new_per_day"), cfg("portfolio.min_holdings"),
            cfg("portfolio.target_holdings"), cfg("portfolio.max_holdings"),
            cfg("portfolio.min_invested_inr")) == (2, 10, 12, 15, 1_000_000)


# ---------------------------------------------------------------------------
# The breadth floor and the 12 Oct decisions
# ---------------------------------------------------------------------------

def _ideas_at_1000(n, conviction=0.9):
    """n ideas at ₹1,000, each in its own sector, convictions descending."""
    return [_idea(f"I{k:02d}", 1000.0, round(conviction - k * 0.01, 2), f"sector{k:02d}")
            for k in range(n)]


def _one_day(s, ideas, on, held_marks):
    marks = {**held_marks, **{h.symbol: 1000.0 for h in s.load().holdings
                              if h.symbol.startswith("I")}}
    return _run(s, ideas, marks, on=on)


def test_d1_two_lakh_deposit_then_twelve_holdings_within_six_days(tmp_path, monkeypatch):
    """The 27 Sep holdings (₹1,90,000) with ₹8,10,000 cash; the owner deposits
    ₹2,00,000 through the real route: equity ₹12,00,000, cash ₹10,10,000.
    Target max(80% × 12 L, 10 L) = ₹10,00,000. Each buy: 83 × ₹1,000 = ₹83,000.
    Two a day: holdings 4, 6, 8, 10, 12 after five days; invested
    1,90,000 + 10 × 83,000 = ₹10,20,000 (85.0%), at least ₹10 L. Day six:
    target reached. Cash ₹10,10,000 − 8,30,000 = ₹1,80,000."""
    _app_store(tmp_path, monkeypatch)
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = [_h("AAA", 1000, 100.0, "it_sector"), _h("BBB", 900, 100.0, "fmcg")]
    p.cash_deployable, p.capital_in, p.autopilot = 810_000.0, 1_000_000.0, True
    s.save(p)
    client = _client(tmp_path, monkeypatch)
    r = client.post("/portfolio/deposit", json={"amount": 200_000, "reference": "rollout"})
    assert r.status_code == 200, r.text
    assert (s.load().cash_deployable, s.load().capital_in) == (1_010_000.0, 1_200_000.0)

    ideas = _ideas_at_1000(12)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    held = {"AAA": 100.0, "BBB": 100.0}
    counts = []
    for day in _weekdays(D, 6):
        txns, rec = _one_day(s, ideas, day, held)
        assert all(t.qty == 83.0 and t.value == 83_000.0 for t in txns)
        counts.append(len(s.load().holdings))
    assert counts == [4, 6, 8, 10, 12, 12]
    assert rec["reasons"][0] == ("regime NORMAL, target reached: 85.0% invested against a "
                                 "target of 83.3% (₹10,00,000)")
    marks = {**held, **{i.symbol: 1000.0 for i in ideas}}
    assert sizing.holdings_value(s.load(), marks) == 1_020_000.0
    assert s.load().cash_deployable == 180_000.0
    assert sizing.weights(s.load(), marks).position_pct["I00"] == pytest.approx(83_000 / 12_000)


def test_d2_fourteen_ideas_stop_at_twelve_holdings(tmp_path, monkeypatch):
    """₹12 L cash, 14 ideas, no daily limit in the way (N = 20): 12 buys of
    83 × ₹1,000 = ₹83,000, invested ₹9,96,000 = 83.0%. Twelve held and the
    regime's 80% (₹9,60,000) met: target reached; two wait."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 20)
    s = _store(tmp_path, [], cash=1_200_000.0)
    ideas = _ideas_at_1000(14)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {})
    assert _buys(txns) == [(f"I{k:02d}", 83.0, 1000.0) for k in range(12)]
    assert rec["reasons"][0] == ("regime NORMAL, target reached: 12 holdings, the target of "
                                 "12, with 83.0% invested")
    assert [o["outcome"] for o in rec["ideas"]][-2:] == ["waiting", "waiting"]
    assert s.load().cash_deployable == 204_000.0


def test_d2_never_more_than_fifteen_holdings(tmp_path, monkeypatch):
    """₹30 L cash, 16 ideas, N = 20: the target is 80% = ₹24 L, so buying
    goes past 12 holdings, and stops at the maximum: 15 × ₹83,000 = ₹12,45,000."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 20)
    s = _store(tmp_path, [], cash=3_000_000.0)
    ideas = _ideas_at_1000(16)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {})
    assert len(txns) == 15 and len(s.load().holdings) == 15
    assert rec["reasons"][0] == "15 holdings, the maximum of 15"
    assert _outcomes(rec)["I15"][0] == "waiting"


def test_below_the_holdings_floor_a_position_opens_past_the_target(tmp_path, monkeypatch):
    """NORMAL, ₹12 L: 9 holdings of 115 × ₹1,000 (₹1,15,000 each, three to a
    sector: ₹3,45,000 = 28.75%), ₹10,35,000 invested (86.25%), ₹1,65,000
    cash. Target max(80% × 12 L, 10 L) = ₹10,00,000, already met; but 9 < 10
    holdings, so one position opens: 83 × ₹1,000 = ₹83,000, invested
    ₹11,18,000 = 93.2% (₹1,18,000 past the target, more than one ₹83,333
    position). At 10 holdings the floor is met and invested is past the
    target, so the second idea waits."""
    s = _store(tmp_path, [_h(f"H{k}", 115, 1000.0, ("banking", "power", "metals")[k % 3])
                          for k in range(9)], cash=165_000.0)
    ideas = _ideas_at_1000(2)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {f"H{k}": 1000.0 for k in range(9)})
    assert _buys(txns) == [("I00", 83.0, 1000.0)]
    assert (rec["target_inr"], rec["invested_before_pct"], rec["invested_after_pct"]) == \
        (1_000_000.0, 86.2, 93.2)
    assert _outcomes(rec)["I01"][0] == "waiting"
    assert s.load().cash_deployable == 82_000.0


def test_only_six_qualifying_ideas_buys_six_and_records_the_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 10)
    s = _store(tmp_path, [], cash=1_200_000.0)
    ideas = _ideas_at_1000(6)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {})
    assert len(txns) == 6
    assert rec["reasons"][:2] == [
        "no further qualifying idea",
        "holdings floor unreachable: 6 qualifying ideas, 6 holdings against at least 10"]


def test_risk_off_relaxes_the_floor_to_half(tmp_path, monkeypatch):
    """RISK_OFF from all cash (₹12 L): target 50% = ₹6 L; no holdings floor.
    83,000 a buy: 7 buys = ₹5,81,000 is still below, the 8th makes
    ₹6,64,000 (55.3%), past the target by less than one position."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 20)
    _regime(monkeypatch, "RISK_OFF")
    s = _store(tmp_path, [], cash=1_200_000.0)
    ideas = _ideas_at_1000(20)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {})
    assert len(txns) == 8
    assert rec["reasons"][0] == ("regime RISK_OFF, target reached: 55.3% invested against a "
                                 "target of 50.0% (₹6,00,000)")
    assert rec["min_holdings"] == 0


def test_the_floor_and_holdings_come_from_config_with_no_code_change(tmp_path, monkeypatch):
    """min 5, target 6, max 8, ₹6 L: a position asks for ₹1,00,000 = 100
    shares at ₹1,000 (8.3% of ₹12 L). The regime's 80% (₹9,60,000) is never
    met inside 8 holdings, so it stops at the maximum: ₹8,00,000 invested."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 20)
    for name, value in (("PORTFOLIO_MIN_HOLDINGS", 5), ("PORTFOLIO_TARGET_HOLDINGS", 6),
                        ("PORTFOLIO_MAX_HOLDINGS", 8), ("PORTFOLIO_MIN_INVESTED_INR", 600_000.0)):
        monkeypatch.setattr(settings, name, value)
    s = _store(tmp_path, [], cash=1_200_000.0)
    ideas = _ideas_at_1000(10)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    txns, rec = _run(s, ideas, {})
    assert [t.qty for t in txns] == [100.0] * 8
    assert rec["reasons"][0] == "8 holdings, the maximum of 8"


def test_a_portfolio_override_switches_and_sizes_one_portfolio(tmp_path, monkeypatch):
    """Global switch off; portfolio u opts in with min 2, target 4, max 5 and
    ₹4 L: ₹1,00,000 a position, 5 bought. Portfolio v has no override and
    buys nothing; portfolio w opts out while the global switch is on."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", 20)
    monkeypatch.setattr(settings, "PORTFOLIO_OVERRIDES", {
        "u": {"deploy_idle_cash": True, "min_holdings": 2, "target_holdings": 4,
              "max_holdings": 5, "min_invested_inr": 400_000},
        "w": {"deploy_idle_cash": False}})
    ideas = _ideas_at_1000(10)
    _prices(monkeypatch, {i.symbol: 1000.0 for i in ideas})
    u = _store(tmp_path, [], cash=1_200_000.0, name="u")
    txns, rec = _run(u, ideas, {})
    assert [t.qty for t in txns] == [100.0] * 5 and rec["reasons"][0] == \
        "5 holdings, the maximum of 5"
    v = _store(tmp_path, [], cash=1_200_000.0, name="v")
    assert _run(v, ideas, {}) == ([], None)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", True)
    w = _store(tmp_path, [], cash=1_200_000.0, name="w")
    assert _run(w, ideas, {}) == ([], None)
    assert deployment.active(v.load()) and not deployment.active(w.load())


# ---------------------------------------------------------------------------
# Churn, surveillance and the sector key
# ---------------------------------------------------------------------------

def test_a_stock_sold_today_or_since_its_dive_is_not_bought_back(tmp_path, monkeypatch):
    """P1 is held and EXITs today; its idea was dived on 8 Jul, before the
    sale, so it is not re-bought. OLD was sold on 6 Jul and re-dived on
    10 Jul: a new deep dive after the sale, so it may be bought."""
    s = _store(tmp_path, [_h("P1", 100, 500.0, "pharma")], cash=900_000.0)
    s.append_transaction(TransactionRecord(
        txn_id="old", date="2026-07-06", ts="2026-07-06T10:00:00+00:00", user_id="u",
        symbol="OLD", side="SELL", qty=1, price=1000.0, value=1000.0, cash_before=899_000.0,
        cash_after=900_000.0, holding_qty_after=0.0, verdict="EXIT"))
    ideas = [_idea("P1", 500.0, 0.9, "pharma"), _idea("OLD", 1000.0, 0.8, "metals",
                                                       dived="2026-07-10")]
    _prices(monkeypatch, {"P1": 500.0, "OLD": 1000.0})
    exit_p1 = AdviceRecord(date=D.isoformat(), user_id="u", symbol="P1", verdict="EXIT",
                           close=500.0, unrealised_pnl_pct=0.0, stop_pct=12.0,
                           rationale_hash="e1")
    txns, rec = _run(s, ideas, {"P1": 500.0}, advice=[exit_p1])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "P1"), ("BUY", "OLD")]
    assert _outcomes(rec)["P1"] == ("sold", "sold on 2026-07-13, after its deep dive of "
                                            "2026-07-08; waits for a new deep dive")


def test_without_a_surveillance_report_no_position_opens(tmp_path, monkeypatch):
    s, ideas = _sep27(tmp_path, monkeypatch)
    _report(monkeypatch, dark=True)
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert txns == []
    assert set(_outcomes(rec).values()) == {(
        "surveillance", "NSE's surveillance report is unavailable (none from the last 7 days)")}


def test_an_unlisted_or_suspended_stock_is_not_bought(tmp_path, monkeypatch):
    s, ideas = _sep27(tmp_path, monkeypatch)
    _report(monkeypatch, status={"P1": "S"}, unlisted=("P2",))
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert _buys(txns) == [("P3", 83.0, 1000.0)]
    assert _outcomes(rec)["P1"] == ("surveillance", "status S, not active, in NSE's "
                                                    "surveillance report of 2026-07-10")
    assert _outcomes(rec)["P2"] == ("surveillance",
                                    "not listed in NSE's surveillance report of 2026-07-10")


def test_a_switch_into_a_stock_under_short_term_asm_sells_and_keeps_the_cash(tmp_path,
                                                                         monkeypatch):
    """A new listing (an IPO idea) under short-term ASM: the SWITCH sells
    AAA (1,000 × ₹100 = ₹1,00,000) and its buy leg is skipped, as when the
    switch is off. The report is read once for the run."""
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    reads = _report(monkeypatch, measures={"NEWIPO": ["ST-ASM"]})
    s = _store(tmp_path, [_h("AAA", 1000, 120.0, "it_sector")], cash=100_000.0)
    _prices(monkeypatch, {"NEWIPO": 300.0})
    switch = AdviceRecord(date=D.isoformat(), user_id="u", symbol="AAA", verdict="SWITCH",
                          close=100.0, unrealised_pnl_pct=-16.7, stop_pct=12.0,
                          switch_candidate="NEWIPO", rationale_hash="s1")
    txns, _ = _run(s, [_idea("NEWIPO", 300.0)], {"AAA": 100.0}, advice=[switch])
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "AAA")]
    assert txns[0].note == ("exit_full; buy leg skipped: NEWIPO: under ST-ASM in NSE's "
                            "surveillance report of 2026-07-10; ₹1,00,000 stays in cash")
    assert reads == [D]


def test_the_shadow_rows_switch_test_agrees_with_the_executor_on_surveillance():
    from core.portfolio import exit_shadow as xs
    idea = _idea("NEWIPO", 300.0)
    quote = SessionClose(300.0, D, "agree")
    assert xs.switch_buy_lands(quote, D, idea) is True
    watched = sizing.surveillance_issue("NEWIPO", ({"NEWIPO": {"status": "A",
                                                              "measures": ["ST-ASM"]}}, "x"))
    assert xs.switch_buy_lands(quote, D, idea, surveillance_issue=watched) is False


def test_a_generic_idea_is_offered_under_its_classifications_key():
    """Shelved as "generic" before infer_sector read Yahoo's classification;
    the stored classification maps it, so SA-050's sector cap counts it with
    the drug makers. One with no classification stays generic; a real key
    is kept."""
    from core.discovery.candidates import buy_candidates, shelf_sector
    pharma = _idea("GENX", 100.0, sector="generic", market_sector="Healthcare",
                   industry="Drug Manufacturers - Specialty & Generic")
    bare = _idea("BARE", 100.0, sector="generic")
    real = _idea("REAL", 100.0, sector="chemicals", market_sector="Healthcare")
    assert [shelf_sector(i) for i in (pharma, bare, real)] == ["pharma", "generic", "chemicals"]
    portfolio = SimpleNamespace(holdings=[], watchlist=[])
    out, _ = buy_candidates(portfolio, D, [pharma, bare, real], managed={})
    assert [(i.symbol, i.sector) for i in out] == [("GENX", "pharma"), ("BARE", "generic"),
                                                   ("REAL", "chemicals")]


def test_a_sale_on_the_day_of_the_latest_dive_waits_for_a_newer_dive(tmp_path, monkeypatch):
    """SAMEDAY was sold on 10 Jul and dived on 10 Jul: the dive may have
    seen the stock before the sale or after it, so it waits for a newer one."""
    s = _store(tmp_path, [], cash=1_200_000.0)
    s.append_transaction(TransactionRecord(
        txn_id="sd", date="2026-07-10", ts="2026-07-10T10:00:00+00:00", user_id="u",
        symbol="SAMEDAY", side="SELL", qty=1, price=1000.0, value=1000.0,
        cash_before=1_199_000.0, cash_after=1_200_000.0, holding_qty_after=0.0, verdict="EXIT"))
    _prices(monkeypatch, {"SAMEDAY": 1000.0})
    txns, rec = _run(s, [_idea("SAMEDAY", 1000.0, dived="2026-07-10")], {})
    assert txns == []
    assert _outcomes(rec)["SAMEDAY"] == ("sold", "sold on 2026-07-10, after its deep dive of "
                                                 "2026-07-10; waits for a new deep dive")


# ---------------------------------------------------------------------------
# Issue time: the 16:30 run books at the close of the session it reviews
# ---------------------------------------------------------------------------

THU = date(2026, 10, 29)
FRI, SAT, MON, TUE = (date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 2),
                      date(2026, 11, 3))


def _first_dived(sym, price, day, conviction=0.9, sector="pharma"):
    """An idea Saturday's discovery run first screened and dived on `day`
    (`added`, `source_screen_date` and `dived` are that day)."""
    return _idea(sym, price, conviction, sector, dived=day.isoformat()).model_copy(
        update={"added": day.isoformat(), "source_screen_date": day.isoformat()})


def test_an_idea_dived_after_the_review_session_is_not_offered(monkeypatch):
    """Monday 2 Nov's 16:30 run reviews Friday 30 Oct. NEWX (first dived
    Sat 31 Oct) and OLDX (on the shelf since 3 Oct, re-dived Sat 31 Oct)
    carry what Saturday's dives read, so neither is offered for Friday's
    close. FIX-024: nor is FRIX, dived on Friday itself, since a deep dive
    keeps only its day and so counts as made after that day's 15:30 close.
    With re-dives off the bound still holds. Tuesday's run, reviewing
    Monday, offers all three."""
    from core.discovery.candidates import buy_candidates
    from core.intelligence.rl.nse_calendar import trading_days_ago
    assert trading_days_ago(MON, 1) == FRI and trading_days_ago(TUE, 1) == MON
    new, fri = _first_dived("NEWX", 100.0, SAT), _first_dived("FRIX", 100.0, FRI)
    old = _first_dived("OLDX", 100.0, date(2026, 10, 3)).model_copy(
        update={"dived": SAT.isoformat()})
    portfolio = SimpleNamespace(holdings=[], watchlist=[])
    why = ("close of 2026-10-30 is before the deep dive of 2026-10-31; waits for a "
           "review of a later session")
    same_day = ("deep dive of 2026-10-30 has no time, so it counts as made after that day's "
                "close; waits for a review of a later session")
    for redive_days in (30, 0):
        monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", redive_days)
        out, excluded = buy_candidates(portfolio, FRI, [new, old, fri], managed={})
        assert out == [], redive_days
        assert excluded == {"NEWX": why, "OLDX": why, "FRIX": same_day}, redive_days
        out, excluded = buy_candidates(portfolio, MON, [new, old, fri], managed={})
        assert [i.symbol for i in out] == ["NEWX", "OLDX", "FRIX"] and excluded == {}


def test_mondays_run_waits_for_a_saturday_dive_and_tuesdays_buys_it_at_mondays_close(
        tmp_path, monkeypatch, caplog):
    """₹12 L all cash; NEWX first dived on Sat 31 Oct at ₹1,000. Monday's run
    (review Fri 30 Oct) buys nothing and logs why NEWX was not offered.
    Tuesday's run (review Mon 2 Nov) buys floor(₹83,333.33 / ₹1,000) = 83
    shares = ₹83,000, dated Monday, at Monday's close."""
    import logging
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    store, _ = _pipeline_world(tmp_path, monkeypatch, [], 1_200_000.0,
                               [_first_dived("NEWX", 1000.0, SAT)], {"NEWX": 1000.0})
    caplog.set_level(logging.INFO, logger="core.portfolio.pipeline")
    pipeline.run_post_review_pipeline(FRI)
    assert [t for t in store.load_transactions() if t.side == "BUY"] == []
    assert ("'NEWX': 'close of 2026-10-30 is before the deep dive of 2026-10-31; "
            "waits for a review of a later session'") in caplog.text
    pipeline.run_post_review_pipeline(MON)
    assert [(t.date, t.symbol, t.qty, t.price, t.verdict) for t in store.load_transactions()
            if t.side == "BUY"] == [("2026-11-02", "NEWX", 83.0, 1000.0, "DEPLOY")]


def test_a_saturday_dive_is_no_switch_destination_on_mondays_run(tmp_path, monkeypatch):
    """The advisor chooses a SWITCH destination from the same candidates:
    for the held AAA, Monday's run (review Friday) offers only THUX, dived
    Thursday (FIX-024: a dive dated Friday would count as made after Friday's
    close); Tuesday's run (review Monday) offers NEWX, dived Saturday, too.
    Deployment is off here, so the advisor is the only buyer."""
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(settings, "DISCOVERY_REDIVE_AFTER_DAYS", 30)
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    monkeypatch.setattr(ap, "_today_ist", lambda: TUE)
    ideas = [_first_dived("NEWX", 100.0, SAT, 0.95), _first_dived("THUX", 100.0, THU, 0.9,
                                                                   "metals")]
    _pipeline_world(tmp_path, monkeypatch, [_h("AAA", 1000, 100.0, "it_sector")], 900_000.0,
                    ideas, {"AAA": 100.0, "NEWX": 100.0, "THUX": 100.0})
    offered: dict = {}
    real = pipeline.gated_decide

    def spy(*args, **kwargs):
        offered.setdefault(run[0], set()).add(tuple(i.symbol for i in kwargs["shelf_ideas"]))
        return real(*args, **kwargs)
    monkeypatch.setattr(pipeline, "gated_decide", spy)
    for run in ([FRI], [MON]):
        pipeline.run_post_review_pipeline(run[0])
    assert offered == {FRI: {("THUX",)}, MON: {("NEWX", "THUX")}}


# ---------------------------------------------------------------------------
# FIX-011's report through the real reader (the card's routed tests)
# ---------------------------------------------------------------------------

def _archive(monkeypatch, tmp_path, files=None, cached=None):
    """The real `surveillance_report` -> `surveillance_list` over NSE's
    archive answered by FIX-011's fake (`files` {name: csv}; None: NSE
    unreachable) and a cache file written by hand (`cached` (as_of,
    {symbol: status})). Returns the fake client, or None."""
    import json
    import services.data.fetchers.surveillance as surv
    from tests.unit.test_surveillance_sector_fix011 import _FakeNSE
    monkeypatch.setattr(ap, "surveillance_report", REAL_SURVEILLANCE_REPORT)
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "discovery"))
    monkeypatch.setattr(surv.time, "sleep", lambda s: None)
    client = None if files is None else _FakeNSE(files)

    def make():
        if client is None:
            raise ConnectionError("nseindia.com unreachable")
        return client
    monkeypatch.setattr(surv, "_make_nse_client", make)
    if cached is not None:
        (tmp_path / "discovery").mkdir(parents=True, exist_ok=True)
        as_of, statuses = cached
        (tmp_path / "discovery" / "surveillance.json").write_text(json.dumps(
            {"as_of": as_of, "securities": {sym: {"status": st, "measures": []}
                                            for sym, st in statuses.items()}}),
            encoding="utf-8")
    return client


def _csv(**rows):
    """NSE's report text: {symbol: (status, short-term ASM stage)}."""
    from tests.unit.test_surveillance_sector_fix011 import _report as report, _row as row
    return report(*(row(sym, status=st, st=stage) for sym, (st, stage) in rows.items()))


def test_any_status_but_active_in_the_report_refuses(tmp_path, monkeypatch):
    """13 Jul's report lists P1 with status "I" (not one NSE is known to use:
    anything but "A" refuses), P2 suspended ("S") and P3 active. Only P3 is
    bought: 83 × ₹1,000."""
    s, ideas = _sep27(tmp_path, monkeypatch)
    _archive(monkeypatch, tmp_path, {"REG1_IND130726.csv": _csv(
        P1=("I", "100"), P2=("S", "100"), P3=("A", "100"))})
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert _buys(txns) == [("P3", 83.0, 1000.0)]
    assert _outcomes(rec)["P1"] == ("surveillance", "status I, not active, in NSE's "
                                                    "surveillance report of 2026-07-13")
    assert _outcomes(rec)["P2"][1].startswith("status S, not active")


def test_the_cached_report_serves_only_its_own_day(tmp_path, monkeypatch):
    """The cache holds Friday 10 Jul's report, P1 active and clear. NSE has
    published Monday 13 Jul's, with P1 under short-term ASM stage 1. Monday's
    buys read Monday's report: P1 is refused, P2 and P3 are bought."""
    s, ideas = _sep27(tmp_path, monkeypatch)
    client = _archive(monkeypatch, tmp_path,
                      {"REG1_IND130726.csv": _csv(P1=("A", "1"), P2=("A", "100"),
                                                  P3=("A", "100"))},
                      cached=("2026-07-10", {"P1": "A", "P2": "A", "P3": "A"}))
    txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0})
    assert client.asked == ["REG1_IND130726.csv"]
    assert _buys(txns) == [("P2", 333.0, 250.0), ("P3", 83.0, 1000.0)]
    assert _outcomes(rec)["P1"] == ("surveillance", "under ST-ASM in NSE's surveillance "
                                                    "report of 2026-07-13")


def test_a_report_older_than_seven_days_opens_no_position(tmp_path, monkeypatch):
    """NSE cannot be reached; the cache holds Monday 6 Jul's report, all
    clear. For Monday 13 Jul it is 7 days old and serves: P1 and P2 are
    bought. For Tuesday 14 Jul it is 8 days old: nothing opens."""
    for name, on, bought in (("mon", D, ["P1", "P2"]), ("tue", date(2026, 7, 14), [])):
        s, ideas = _sep27(tmp_path / name, monkeypatch)
        _archive(monkeypatch, tmp_path / name, None,
                 cached=("2026-07-06", {"P1": "A", "P2": "A", "P3": "A"}))
        txns, rec = _run(s, ideas, {"AAA": 100.0, "BBB": 100.0}, on=on)
        assert [t.symbol for t in txns] == bought, name
    assert set(_outcomes(rec).values()) == {(
        "surveillance", "NSE's surveillance report is unavailable (none from the last 7 days)")}


# ---------------------------------------------------------------------------
# The property test
# ---------------------------------------------------------------------------

REGIMES = [None, "NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD", "RISK_OFF",
           "MACRO_CRISIS"]
SECTORS = ["banking", "pharma", "power", "it_sector", "metals", "fmcg"]


def test_property_random_days_keep_every_rule(tmp_path, monkeypatch):
    """400 seeded random portfolios, shelves and regimes, at the configured
    trading costs. After each run, by this test's own arithmetic at the run's
    marks:
      - no BUY with no regime or in MACRO_CRISIS; at most N BUYs; never more
        than the maximum holdings (unless already above it); no BUY of a
        held stock;
      - every BUY at most 10% of total equity after it, its sector at most
        30%, its price inside its idea's band, and cash at or above the floor;
      - from at or above the holdings floor in force, invested never passes
        the target (from the run's start) by more than one position;
      - every idea not bought has a reason, and a day that ends below the
        target with idle cash says why.
    The counters prove the cases were exercised."""
    monkeypatch.setattr(settings, "PORTFOLIO_COSTS", CONFIGURED_COSTS)
    floor = 10_000.0
    seen = {"buys": 0, "crisis_or_none": 0, "target_stops": 0, "limit_stops": 0,
            "max_stops": 0, "capped": 0}
    for seed in range(400):
        rng = random.Random(seed)
        regime = rng.choice(REGIMES)
        _regime(monkeypatch, regime)
        n_max = rng.randint(0, 4)
        monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_MAX_NEW_PER_DAY", n_max)
        holdings, marks = [], {}
        for i in range(rng.choice([0, 1, 2, 5, 9, 11, 14, 16])):
            cost = round(rng.uniform(50, 3000), 2)
            h = _h(f"H{i}", float(rng.randint(1, 400)), cost, rng.choice(SECTORS))
            holdings.append(h)
            marks[h.symbol] = round(cost * rng.uniform(0.6, 1.5), 2)
        cash = round(rng.uniform(0, 2_500_000), 2)
        prices, ideas = {}, []
        for k in range(rng.randint(0, 20)):
            sym = f"C{k}"
            prices[sym] = round(rng.uniform(20, 120_000), 2)
            lo, hi = prices[sym] * rng.uniform(0.85, 1.0), prices[sym] * rng.uniform(0.9, 1.2)
            ideas.append(_idea(sym, prices[sym], round(rng.random(), 2), rng.choice(SECTORS),
                               gate=rng.choice(["actionable"] * 4 + ["abstain", ""]),
                               lo=round(lo, 2), hi=round(hi, 2),
                               inval=round(lo * rng.uniform(0.8, 1.0), 2)))
        _prices(monkeypatch, prices)
        s = _store(tmp_path, holdings, cash, name=f"p{seed}")
        before = s.load()
        b = deployment.breadth(before.user_id)
        eq0 = sizing.total_equity(before, marks)
        inv0 = sizing.holdings_value(before, marks)
        t = deployment.target(regime, eq0, b, floor)
        txns, rec = _run(s, ideas, dict(marks))
        after = s.load()
        run_marks = {**marks, **prices}
        buys = [x for x in txns if x.side == "BUY"]
        if regime in (None, "MACRO_CRISIS"):
            seen["crisis_or_none"] += 1
            assert not buys, seed
        assert len(buys) <= n_max, seed
        assert len(after.holdings) <= max(b.max_holdings, len(before.holdings)), seed
        eq_after = sizing.total_equity(after, run_marks)
        idea_of = {i.symbol: i for i in ideas}
        sector_of = {h.symbol: h.sector for h in after.holdings}
        for x in buys:
            assert x.symbol not in {h.symbol for h in before.holdings}, seed
            pos = sum(h.adj_qty * run_marks[h.symbol] for h in after.holdings
                      if h.symbol == x.symbol)
            sec = sum(h.adj_qty * run_marks.get(h.symbol, h.adj_avg_price)
                      for h in after.holdings if h.sector == sector_of[x.symbol])
            assert pos <= 0.10 * eq_after + 1e-6, (seed, x.symbol)
            assert sec <= 0.30 * eq_after + 1e-6, (seed, x.symbol)
            i = idea_of[x.symbol]
            assert i.invalidation_level < x.price <= i.entry_high, seed
            assert x.qty * x.price <= b.position_inr + 1e-6, seed
            seen["capped"] += "capped by" in x.note
        if buys:
            assert after.cash_deployable >= floor - 0.005, seed
            inv_after = sizing.holdings_value(after, run_marks)
            if len(before.holdings) >= t.min_holdings:
                assert inv_after <= max(t.invested_inr, inv0) + b.position_inr + 1e-6, seed
        seen["buys"] += len(buys)
        if rec is not None:
            assert rec["reasons"], seed
            for o in rec["ideas"]:
                assert o["outcome"] and o["why"], (seed, o)
            first = rec["reasons"][0]
            seen["target_stops"] += "target reached" in first
            seen["limit_stops"] += "daily limit" in first
            seen["max_stops"] += "the maximum of" in first
    assert seen["buys"] > 150 and seen["crisis_or_none"] > 60, seen
    assert seen["target_stops"] > 10 and seen["limit_stops"] > 20 and seen["max_stops"] > 5, seen
    assert seen["capped"] > 5, seen


# ---------------------------------------------------------------------------
# Routed fixes: SA-050 R1 and R2
# ---------------------------------------------------------------------------

def test_r1_a_budget_of_exactly_36_shares_buys_36():
    """144 × ₹6,358.80 × 25% = ₹2,28,916.80 = 36 × ₹6,358.80 exactly. In
    floating point 36 × 6358.8 is 228916.80000000002, more than the budget, so
    the old guard (`qty × price > budget`: one share less) bought 35."""
    budget = 144 * 6358.80 * 25 / 100
    assert 36 * 6358.8 > budget                          # the old guard's trigger
    assert sizing.whole_shares(budget, 6_358.80) == 36.0
    assert sizing.whole_shares(228_916.80, 6_358.80) == 36.0
    p = SimpleNamespace(holdings=[_h("BIG", 144, 6358.80, "x")], cash_deployable=20_000_000.0)
    size = sizing.size_buy(p, {"BIG": 6358.80}, symbol="BIG", sector="x", price=6358.80,
                           wanted=144 * 6358.80 * 25 / 100, floor_cash=10_000.0)
    assert (size.qty, size.binding) == (36.0, "")


def test_r1_whole_shares_counts_exact_multiples_and_never_overspends():
    rng = random.Random(49)
    for _ in range(5000):
        price = round(rng.uniform(0.05, 90_000), 2)
        k = rng.randint(0, 3000)
        assert sizing.whole_shares(round(k * price, 2), price) == k
        budget = rng.uniform(0, 5_000_000)
        q = sizing.whole_shares(budget, price)
        assert q * price <= budget + 1e-6 and (q + 1) * price > budget - 0.01
    assert sizing.whole_shares(1000.0, 330.155) == 3.0      # more than two decimals


def test_r1_an_add_of_a_whole_tranche_buys_every_share(tmp_path, monkeypatch):
    s = _store(tmp_path, [_h("BIG", 144, 6358.80, "x")], cash=20_000_000.0)
    add = AdviceRecord(date=D.isoformat(), user_id="u", symbol="BIG", verdict="ADD",
                       close=6358.80, unrealised_pnl_pct=0.0, stop_pct=12.0,
                       confidence=0.7, triggers=["add_bullish_healthy"], rationale_hash="a")
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    txns, _ = _run(s, [], {"BIG": 6358.80}, advice=[add])
    assert _buys(txns) == [("BIG", 36.0, 6358.80)]


def test_r2_a_second_switch_into_the_same_stock_alerts_when_its_leg_is_skipped():
    """Two SWITCHes into NEW on one day: the first leg lands, the second is
    stopped by the position cap. The old match (any BUY of NEW) stayed
    silent; each leg is now matched to its own SELL by the shared advice."""
    import core.portfolio.pipeline as pl
    from backend.shared.schemas.portfolio import Portfolio
    recs = [AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym, verdict="SWITCH",
                         close=100.0, unrealised_pnl_pct=-13.0, stop_pct=12.0,
                         switch_candidate="NEW", rationale_hash=f"h{sym}")
            for sym in ("AAA", "BBB")]

    def txn(side, sym, ref, note=""):
        return TransactionRecord(txn_id=f"{side}{sym}", date=D.isoformat(),
                                 ts="2026-07-13T11:00:00+00:00", user_id="t1", symbol=sym,
                                 side=side, qty=10, price=100.0, value=1000.0, cash_before=0.0,
                                 cash_after=0.0, holding_qty_after=0.0, advice_ref=ref,
                                 note=note)
    ref_a, ref_b = f"{D}|AAA|hAAA", f"{D}|BBB|hBBB"
    txns = [txn("SELL", "AAA", ref_a, "exit_full"),
            txn("SELL", "BBB", ref_b, "exit_full; buy leg skipped: NEW: the 10% position cap "
                                      "leaves room for less than one share at ₹100; ₹1,000 "
                                      "stays in cash"),
            txn("BUY", "NEW", ref_a)]
    portfolio = Portfolio(user_id="t1", holdings=[_h("AAA", 10, 100.0, "x"),
                                                  _h("BBB", 10, 100.0, "x")])
    with patch.object(pl, "active_user_ids", return_value=["t1"]), \
         patch.object(pl, "PortfolioStore") as MockStore, \
         patch.object(pl, "sync_corp_actions"), \
         patch.object(pl, "refresh_events_calendar", return_value={}), \
         patch.object(pl, "session_close", return_value=(SessionClose(100.0, D, "agree"), D)), \
         patch.object(pl, "get_price_history", side_effect=Exception("skip")), \
         patch.object(pl, "build_signals"), \
         patch.object(pl, "gated_decide", side_effect=lambda signals, holding, *a, **k: (
             next(r for r in recs if r.symbol == holding.symbol), None)), \
         patch.object(pl, "narrate", return_value="n"), \
         patch("core.portfolio.autopilot.execute_advice", return_value=txns), \
         patch("core.portfolio.autopilot.record_value_point", return_value=None), \
         patch.object(pl, "is_trading_day", return_value=True), \
         patch("core.delivery.alerts.emit_alerts", return_value={"emitted": 0}) as emit, \
         patch("core.delivery.channels.deliver", return_value={"delivered": False}):
        MockStore.return_value.load.return_value = portfolio
        pl.run_post_review_pipeline(D)
    skipped = [e for e in emit.call_args.args[0] if e.kind == "switch_buy_skipped"]
    assert [(e.symbol, e.message) for e in skipped] == [(
        "NEW", "SWITCH BBB→NEW: sold but the buy leg was skipped: NEW: the 10% position cap "
               "leaves room for less than one share at ₹100; ₹1,000 stays in cash")]


# ---------------------------------------------------------------------------
# The regime the deployment reads
# ---------------------------------------------------------------------------

def test_the_regime_counts_only_for_the_day_the_review_recorded_it(tmp_path, monkeypatch):
    from core.intelligence.regime import state
    monkeypatch.setattr(settings, "PREDICTION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "RL_REGIME_STICKY_ENABLED", True)
    monkeypatch.setattr(settings, "RL_REGIME_CALM_DAYS", 3)
    assert state.label_recorded_for("2026-07-13") is None          # no file
    state.update_sticky_regime("RISK_OFF", "2026-07-13")           # fresh: no marker yet
    assert state.label_recorded_for("2026-07-13") == "RISK_OFF"
    assert state.label_recorded_for("2026-07-14") is None          # stale for the next day
    state.update_sticky_regime("NORMAL", "2026-07-14")             # calm 1 of 3: still sticky
    assert state.label_recorded_for("2026-07-14") == "RISK_OFF"
    assert state.label_recorded_for("2026-07-13") is None          # written for a later day
    (tmp_path / "_regime_state.json").write_text("{not json", encoding="utf-8")
    assert state.label_recorded_for("2026-07-14") is None


# ---------------------------------------------------------------------------
# The DEPOSIT (D1)
# ---------------------------------------------------------------------------

class _Nifty:
    def preload(self, start, end):
        return True

    def close_on(self, d):
        return 100.0


def _app_store(tmp_path, monkeypatch):
    monkeypatch.setattr(papi.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(papi, "_deposit_day", lambda: D)


def _client(tmp_path, monkeypatch):
    _app_store(tmp_path, monkeypatch)
    monkeypatch.setattr(papi, "promote_symbol", lambda *a, **k: {"status": "test"})
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 100.0)
    monkeypatch.setattr(papi, "_benchmark", _Nifty)
    monkeypatch.setattr(papi, "_stock_closes", lambda: (lambda symbol, d: 100.0))
    app = FastAPI()
    app.include_router(papi.router)
    return TestClient(app)


def _seeded(tmp_path, cash=810_000.0):
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = [_h("AAA", 1000, 100.0, "it_sector"), _h("BBB", 900, 100.0, "fmcg")]
    p.cash_deployable, p.capital_in, p.autopilot = cash, 1_000_000.0, True
    s.save(p)
    for sym, qty, before in (("AAA", 1000, 1_000_000.0), ("BBB", 900, 900_000.0)):
        s.append_transaction(TransactionRecord(
            txn_id=f"seed-{sym}", date="2026-07-01", ts="2026-07-01T05:00:00+00:00",
            user_id="primary", symbol=sym, side="BUY", qty=qty, price=100.0,
            value=qty * 100.0, cash_before=before, cash_after=before - qty * 100.0,
            holding_qty_after=qty, source="seed"))
    return s


def test_a_deposit_raises_cash_and_capital_in_once(tmp_path, monkeypatch):
    from core.portfolio.reconcile import reconcile
    client = _client(tmp_path, monkeypatch)
    s = _seeded(tmp_path)
    body = {"amount": 200_000, "reference": "SA-049 rollout"}
    r = client.post("/portfolio/deposit", json=body)
    assert r.status_code == 200 and r.json()["duplicate"] is False
    p = s.load()
    assert (p.cash_deployable, p.capital_in) == (1_010_000.0, 1_200_000.0)
    deposits = [t for t in s.load_transactions() if t.side == "DEPOSIT"]
    assert [(t.date, t.symbol, t.qty, t.value, t.cash_before, t.cash_after, t.source)
            for t in deposits] == [("2026-07-13", "CASH", 0.0, 200_000.0, 810_000.0,
                                    1_010_000.0, "manual")]
    again = client.post("/portfolio/deposit", json=body)
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert len([t for t in s.load_transactions() if t.side == "DEPOSIT"]) == 1
    assert (s.load().cash_deployable, s.load().capital_in) == (1_010_000.0, 1_200_000.0)
    assert reconcile(s)["status"] == "clean"
    # The ledger view shows it with no trading costs; realized P&L is untouched.
    rows = client.get("/portfolio/transactions").json()["transactions"]
    assert [(x["side"], x["costs"]) for x in rows if x["side"] == "DEPOSIT"] == [("DEPOSIT", None)]
    assert client.get("/portfolio/performance").json()["realized_pnl"] == 0.0


def test_a_second_deposit_of_another_amount_with_the_same_reference_is_written(tmp_path,
                                                                              monkeypatch):
    """Idempotent on (date, amount, reference): ₹2,00,000 "rollout", then
    ₹50,000 "rollout" the same day is a second deposit, not a retry. Cash
    ₹8,10,000 + 2,00,000 + 50,000 = ₹10,60,000; capital in ₹12,50,000."""
    client = _client(tmp_path, monkeypatch)
    s = _seeded(tmp_path)
    first = client.post("/portfolio/deposit", json={"amount": 200_000, "reference": "rollout"})
    second = client.post("/portfolio/deposit", json={"amount": 50_000, "reference": "rollout"})
    assert (first.json()["duplicate"], second.json()["duplicate"]) == (False, False)
    assert [t.value for t in s.load_transactions() if t.side == "DEPOSIT"] == [200_000.0,
                                                                              50_000.0]
    assert (s.load().cash_deployable, s.load().capital_in) == (1_060_000.0, 1_250_000.0)


def test_only_the_owner_or_the_machine_key_may_deposit(tmp_path, monkeypatch):
    import services.api.auth as auth
    client = _client(tmp_path, monkeypatch)
    s = _seeded(tmp_path)

    async def member(authorization=None):
        return {"user_id": "m1", "role": "member"}
    monkeypatch.setattr(auth, "get_current_user", member)
    body = {"amount": 1000, "reference": "x"}
    assert client.post("/portfolio/deposit", json=body).status_code == 403
    assert s.load().cash_deployable == 810_000.0
    monkeypatch.setenv("SCHEDULER_KEY", "k")
    ok = client.post("/portfolio/deposit", json=body, headers={"X-Scheduler-Key": "k"})
    assert ok.status_code == 200 and s.load().cash_deployable == 811_000.0
    for bad in ({"amount": 0, "reference": "x"}, {"amount": -5, "reference": "x"},
                {"amount": 10, "reference": ""}, {"amount": 10, "reference": "   "}):
        assert client.post("/portfolio/deposit", json=bad,
                           headers={"X-Scheduler-Key": "k"}).status_code == 422, bad


def test_a_deposit_needs_cash_accounting(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    s.save(s.load())
    r = client.post("/portfolio/deposit", json={"amount": 1000, "reference": "x"})
    assert r.status_code == 409 and s.load_transactions() == []


def test_the_nifty_comparison_buys_the_deposit_at_that_days_close(tmp_path, monkeypatch):
    """₹10 L on 10 Jul (Nifty 100): 10,000 units. ₹2 L deposited on 13 Jul,
    before that day's valuation (Nifty 125): 1,600 units. On 13 Jul the Nifty
    side is 11,600 × 125 = ₹14,50,000. The portfolio side holds the cash:
    its return over the day is 0, not +20%.
    This world dates the valuation on the deposit day. In production the
    16:30 run on day T writes the point for the session it reviews (T's
    previous session), so a deposit made before that run is bought at the
    previous session's close: the units follow the point's date."""
    client = _client(tmp_path, monkeypatch)
    s = _seeded(tmp_path)
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    marks = {"AAA": 100.0, "BBB": 100.0}
    ap.record_value_point(s, s.load(), marks, date(2026, 7, 10))
    client.post("/portfolio/deposit", json={"amount": 200_000, "reference": "rollout"})
    ap.record_value_point(s, s.load(), marks, D)
    pts = s.load_value_history()
    flows = R.capital_flows(pts, s.load_transactions())
    assert flows == [R.Flow(date(2026, 7, 10), 1_000_000.0), R.Flow(D, 200_000.0)]
    nifty = {date(2026, 7, 10): 100.0, D: 125.0}
    assert R.nifty_equivalent(flows, nifty.__getitem__, D) == pytest.approx(1_450_000.0)
    week = R.vs_nifty(pts, nifty.__getitem__, end=D, start=D, flows=flows)
    assert week["portfolio_pct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# SA-051 R1: a holding added while the 16:30 run is under way
# ---------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
FRIDAYS = ["2026-01-30", "2026-02-06", "2026-02-13", "2026-02-20", "2026-02-27", "2026-03-06"]
NIFTY = {date(2026, 1, 30): 100.0, date(2026, 2, 6): 100.0, date(2026, 2, 13): 102.0,
         date(2026, 2, 20): 105.0, date(2026, 2, 27): 107.0, date(2026, 3, 6): 110.0}


def _mid_run_timeline(tmp_path, monkeypatch, *, acme_found: bool):
    """The SA-051 review's RV3: ₹10 L on 30 Jan, ₹9,90,000 cash and 100 BASE
    at ₹100 (flat). On Fri 20 Feb the REAL pipeline runs; while it narrates
    BASE (16:35) the owner adds 1,000 ACME through the real route (bought in
    2025, priced by the route at ₹50; worth ₹150 from 20 Feb). The value
    point (16:40) is the real writer's. With `acme_found` the run finds
    ACME's close; otherwise it has none that day. Other Fridays' points are
    written at 17:00 with ACME at ₹150."""
    import core.discovery.shelf as shelf_mod
    import core.portfolio.pipeline as pl
    clock = {"now": datetime(2026, 1, 1, tzinfo=IST)}

    class FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"].astimezone(tz) if tz else clock["now"].replace(tzinfo=None)

    def at(day, hhmm):
        clock["now"] = datetime.fromisoformat(f"{day}T{hhmm}:00+05:30")
    monkeypatch.setattr(papi, "datetime", FrozenDT)
    monkeypatch.setattr(ap, "_now_iso", lambda: clock["now"].astimezone(timezone.utc).isoformat())
    monkeypatch.setattr(ap, "_today_ist", lambda: clock["now"].astimezone(IST).date())
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(papi, "close_on", lambda sym, d: 50.0)
    s = PortfolioStore(user_id="primary", base_dir=str(tmp_path))
    p = s.load()
    p.cash_deployable, p.capital_in, p.autopilot = 990_000.0, 1_000_000.0, True
    p.holdings = [_h("BASE", 100, 100.0, "pharma")]
    s.save(p)
    s.append_transaction(TransactionRecord(
        txn_id="seed-base", date="2026-01-30", ts="2026-01-30T05:00:00+00:00",
        user_id="primary", symbol="BASE", side="BUY", qty=100, price=100.0, value=10_000.0,
        cash_before=1_000_000.0, cash_after=990_000.0, holding_qty_after=100, source="seed"))

    def add_during_narration(rec, signals):
        at("2026-02-20", "16:35")
        r = client.post("/portfolio/holdings", json={"symbol": "ACME", "sector": "pharma",
                                                     "qty": 1000, "buy_date": "2025-02-03"})
        assert r.status_code == 200, r.text
        at("2026-02-20", "16:40")
        return "n"

    closes = {"BASE": 100.0, **({"ACME": 150.0} if acme_found else {})}
    day = date(2026, 2, 20)
    advice = AdviceRecord(date=day.isoformat(), user_id="primary", symbol="BASE",
                          verdict="HOLD", close=100.0, unrealised_pnl_pct=0.0, stop_pct=8.0)
    shelf = MagicMock()
    shelf.return_value.load.return_value.ideas = []
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    for name, value in {
        "is_trading_day": lambda d: True,
        "active_user_ids": lambda: ["primary"],
        "PortfolioStore": lambda user_id: PortfolioStore(user_id=user_id, base_dir=str(tmp_path)),
        "sync_corp_actions": lambda *a, **k: None,
        "session_close": lambda sym, d: (SessionClose(closes[sym], d, "agree"), d),
        "_switch_eval_enabled": lambda: False,
        "refresh_events_calendar": lambda syms: {},
        "get_price_history": MagicMock(side_effect=Exception("skip")),
        "VerdictStore": MagicMock(),
        "build_signals": MagicMock(),
        "holding_identity_issue": lambda *a: None,
        "gated_decide": lambda *a, **k: (advice, None),
        "narrate": add_during_narration,
        "build_digest": MagicMock(side_effect=Exception("skip")),
    }.items():
        monkeypatch.setattr(pl, name, value)
    monkeypatch.setattr(shelf_mod, "ShelfStore", shelf)
    monkeypatch.setattr("core.portfolio.autopilot.execute_advice", lambda *a, **k: [])
    monkeypatch.setattr("core.delivery.channels.deliver", lambda *a, **k: None)
    monkeypatch.setattr("core.delivery.alerts.emit_alerts", lambda *a, **k: None)
    for d in FRIDAYS:
        if d == "2026-02-20":
            at(d, "16:30")
            pl.run_post_review_pipeline(day)
            continue
        at(d, "17:00")
        marks = {h.symbol: {"BASE": 100.0, "ACME": 150.0}[h.symbol] for h in s.load().holdings}
        ap.record_value_point(s, s.load(), marks, date.fromisoformat(d))
    return s


def _week(s, sunday):
    on = date.fromisoformat(sunday)
    return R.weekly_scorecard("primary", on, store=s, close_on=NIFTY.__getitem__,
                              stock_close_on=lambda sym, d: {"ACME": 150.0}[sym],
                              today=on)["vs_nifty"]["week"]


def test_sa051_r1_an_add_during_the_run_is_valued_at_its_close(tmp_path, monkeypatch):
    """The run fetches ACME's close before the point: 9,90,000 + 10,000 +
    1,000 × 150 = ₹11,50,000, as capital_flows values the arrival (₹1,50,000
    in). Week of 16-22 Feb: (11,50,000 − 10,00,000 − 1,50,000) / 11,50,000
    = 0.0% (it read −8.70%) against the Nifty's +2.56%; the next week
    (11,50,000 − 11,50,000) = 0.0% (it read +9.52%) against +1.90%."""
    s = _mid_run_timeline(tmp_path, monkeypatch, acme_found=True)
    feb20 = next(p for p in s.load_value_history() if p["date"] == "2026-02-20")
    assert (feb20["total_equity"], "at_cost" in feb20) == (1_150_000.0, False)
    w08, w09 = _week(s, "2026-02-22"), _week(s, "2026-03-01")
    assert (w08["portfolio_pct"], w08["nifty_pct"]) == (0.0, 2.56)
    assert (w09["portfolio_pct"], w09["nifty_pct"]) == (0.0, 1.9)


def test_sa051_r1_an_add_with_no_close_reads_could_not_check_not_a_gain(tmp_path, monkeypatch):
    """No close for ACME on 20 Feb: the point marks it at its ₹50 cost and
    says so (at_cost). The week holding that point and the week whose point
    first values ACME at ₹150 are unavailable: the ₹1,00,000 jump is never
    read as a gain. The week after is known again: flat against +2.80%."""
    s = _mid_run_timeline(tmp_path, monkeypatch, acme_found=False)
    feb20 = next(p for p in s.load_value_history() if p["date"] == "2026-02-20")
    assert (feb20["total_equity"], feb20["at_cost"]) == (1_050_000.0, ["ACME"])
    w08, w09, w10 = _week(s, "2026-02-22"), _week(s, "2026-03-01"), _week(s, "2026-03-08")
    assert (w08["available"], w09["available"]) == (False, False)
    assert "no close for ACME" in w08["reason"]
    assert (w10["portfolio_pct"], w10["nifty_pct"]) == (0.0, 2.8)


# ---------------------------------------------------------------------------
# FIX-016: the benchmark once deployment is on
# ---------------------------------------------------------------------------

def test_fix016_a_decision_before_and_after_deployment_each_keep_their_benchmark(
        monkeypatch, tmp_path):
    """PR-009's pipeline world: AAA is sold by the price-path rule and kept by
    the evidence rule, a plain EXIT. With deployment off its row says cash;
    with it on for the portfolio, the proceeds are reinvested, so nifty.
    Graded at the same prices (stock −3%, Nifty −5%): against cash the kept
    stock lost 3 (wrong, −3.0); against the Nifty it beat it by 2 (right,
    +2.0)."""
    import core.portfolio.pipeline as pipeline
    from core.portfolio import exit_shadow as xs
    from tests.unit.test_exit_evidence_pr009 import D as REVIEW, _nse, _no_actions, \
        _pipeline_world
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    off = _pipeline_world(monkeypatch, tmp_path / "off", "shadow")
    pipeline.run_post_review_pipeline(REVIEW)
    monkeypatch.setattr(settings, "PORTFOLIO_OVERRIDES", {"u1": {"deploy_idle_cash": True}})
    on = _pipeline_world(monkeypatch, tmp_path / "on", "shadow")
    pipeline.run_post_review_pipeline(REVIEW)
    row_off = next(r for r in off.load_exit_shadow() if r["symbol"] == "AAA")
    row_on = next(r for r in on.load_exit_shadow() if r["symbol"] == "AAA")
    assert (row_off["benchmark"], row_on["benchmark"]) == ("cash", "nifty")
    rows = [row_off, {**row_on, "symbol": "AAA_ON"}]
    decided = date.fromisoformat(row_off["date"])
    grades = xs.grade_disagreements(
        rows, as_of=date(2026, 12, 31), stock_quote_on=_nse(row_off["close"] * 0.97),
        corp_actions=_no_actions, bench_close_on=lambda d: 1000.0 if d == decided else 950.0)
    got = {(g["symbol"], g["horizon_td"]): (g["benchmark"], g["right"], g["result_pct"])
           for g in grades}
    for h in (10, 30):
        assert got[("AAA", h)] == ("cash", False, -3.0)
        assert got[("AAA_ON", h)] == ("nifty", True, 2.0)


# ---------------------------------------------------------------------------
# The pipeline end to end
# ---------------------------------------------------------------------------

class _NoArtifacts:
    def __init__(self, *a, **k):
        pass

    def cycle_id_for(self, d):
        return "X_2026-07"

    def load_envelope(self, cid):
        return None

    def load_feedback_log(self, cid):
        return None


def _pipeline_world(tmp_path, monkeypatch, holdings, cash, ideas, prices):
    import core.delivery.alerts as alerts_mod
    import core.delivery.channels as channels_mod
    import core.portfolio.pipeline as pipeline
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    store = _store(tmp_path, holdings, cash=cash)
    quote = lambda sym, d: (SessionClose(prices[sym], d, "agree"), d)  # noqa: E731
    monkeypatch.setattr(pipeline, "session_close", quote)
    monkeypatch.setattr(ap, "session_close", quote)
    monkeypatch.setattr(pipeline.settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "pf"))
    monkeypatch.setattr(pipeline, "is_trading_day", lambda d: True)
    monkeypatch.setattr(pipeline, "sync_corp_actions", lambda s, d: {"applied": 0})
    monkeypatch.setattr(pipeline, "refresh_events_calendar", lambda syms: {"events": {}})
    monkeypatch.setattr(pipeline, "get_price_history", lambda t, years=1: None)
    monkeypatch.setattr(pipeline, "narrate", lambda rec, sig: "n")
    monkeypatch.setattr(pipeline, "VerdictStore", _NoArtifacts)
    monkeypatch.setattr("core.discovery.shelf.ShelfStore.load", lambda self: Shelf(ideas=ideas))
    monkeypatch.setattr("core.discovery.candidates._managed_sectors", lambda: {})
    emitted = []
    monkeypatch.setattr(alerts_mod, "emit_alerts",
                        lambda events, **k: emitted.extend(events) or {"emitted": 0})
    monkeypatch.setattr(channels_mod, "deliver", lambda *a, **k: {"delivered": False})
    return store, emitted


def test_the_27_sep_shape_through_the_pipeline(tmp_path, monkeypatch):
    """The real advisor holds AAA and BBB (at cost, no forecasts); the real
    candidates offer P1-P3 (dived 8 Jul, fresh); the run buys P1 and P2 as in
    the executor test, records the value point and puts the record in the
    digest, whose text names the buys."""
    import core.portfolio.pipeline as pipeline
    from core.portfolio.digest_text import render_digest_text
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    ideas = [_idea("P1", 500.0, 0.9, "pharma"), _idea("P2", 250.0, 0.8, "chemicals"),
             _idea("P3", 1000.0, 0.7, "capgoods")]
    store, emitted = _pipeline_world(
        tmp_path, monkeypatch, [_h("AAA", 1000, 100.0, "it_sector"),
                                _h("BBB", 900, 100.0, "fmcg")], 810_000.0, ideas,
        {"AAA": 100.0, "BBB": 100.0, "P1": 500.0, "P2": 250.0, "P3": 1000.0})
    result = pipeline.run_post_review_pipeline(D)
    assert result["status"] == "completed"
    txns = store.load_transactions()
    assert _buys(txns) == [("P1", 166.0, 500.0), ("P2", 333.0, 250.0)]
    digest = store.load_latest_digest()
    assert digest["deployment"]["bought"] == ["P1", "P2"]
    assert digest["deployment"]["reasons"][0] == "2 new positions today, the daily limit of 2"
    assert "Idle cash: bought P1, P2; invested 19.0% → 35.6% against a target of 99.0% " \
           "(NORMAL)." in render_digest_text(digest)
    point = store.load_value_history()[-1]
    assert (point["date"], point["total_equity"], point["cash"]) == \
        (D.isoformat(), 1_000_000.0, 643_750.0)
    assert sorted(e.symbol for e in emitted if e.kind == "autopilot_trade") == ["P1", "P2"]


def test_a_portfolio_with_no_holdings_still_deploys(tmp_path, monkeypatch):
    """All cash (₹12 L): the pipeline used to skip a portfolio with no
    holdings. Two buys of 83 × ₹1,000."""
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(ap, "_today_ist", lambda: D)
    ideas = _ideas_at_1000(3)
    store, _ = _pipeline_world(tmp_path, monkeypatch, [], 1_200_000.0, ideas,
                               {i.symbol: 1000.0 for i in ideas})
    pipeline.run_post_review_pipeline(D)
    assert _buys(store.load_transactions()) == [("I00", 83.0, 1000.0), ("I01", 83.0, 1000.0)]
    assert store.load_value_history()[-1]["market_value"] == 166_000.0


def test_with_the_switch_off_a_portfolio_with_no_holdings_is_skipped(tmp_path, monkeypatch):
    import core.portfolio.pipeline as pipeline
    monkeypatch.setattr(settings, "AUTOPILOT_DEPLOY_IDLE_CASH", False)
    ideas = _ideas_at_1000(3)
    store, _ = _pipeline_world(tmp_path, monkeypatch, [], 1_200_000.0, ideas,
                               {i.symbol: 1000.0 for i in ideas})
    pipeline.run_post_review_pipeline(D)
    assert store.load_transactions() == [] and store.load_value_history() == []
    assert store.load_latest_digest() is None
