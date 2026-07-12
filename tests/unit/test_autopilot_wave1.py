"""Audit Wave 1 — executor fixes (AUD-001 fresh reload, AUD-003 price basis,
AUD-004 sell price guard, AUD-044 future-date refusal)."""
from datetime import date

import pytest

import core.portfolio.autopilot as ap
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice, record_value_point
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)          # a Monday (trading day)


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Executor date guards compare against IST-today; freeze it to D so the
    suite is calendar-independent."""
    monkeypatch.setattr(ap, "_today_ist", lambda: D)


def _store(tmp_path, holdings, cash=50000.0, autopilot=True):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings = holdings
    p.cash_deployable = cash
    p.capital_in = 100000.0
    p.autopilot = autopilot
    s.save(p)
    return s


def _h(sym="MARUTI", qty=10.0, price=100.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _advice(sym="MARUTI", verdict="EXIT", close=110.0, switch_candidate=""):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym,
                        verdict=verdict, close=close, unrealised_pnl_pct=10.0,
                        stop_pct=8.0, confidence=0.5,
                        switch_candidate=switch_candidate,
                        rationale_hash="feedbeef")


def test_execute_advice_refuses_future_date(tmp_path):
    """AUD-044: a future review_date must not trade and must NOT stamp the marker."""
    s = _store(tmp_path, [_h()])
    future = date(2026, 12, 31)
    txns = execute_advice(s, s.load(), [_advice()], {"MARUTI": 110.0}, future)
    assert txns == []
    p = s.load()
    assert p.last_autopilot_run == ""            # marker untouched → not bricked
    assert p.holdings and p.holdings[0].symbol == "MARUTI"


def test_execute_advice_uses_fresh_portfolio(tmp_path):
    """AUD-001: executor must act on the CURRENT stored portfolio, not the
    stale object loaded before the (minutes-long) advisor phase."""
    s = _store(tmp_path, [_h()])
    stale = s.load()                             # snapshot before "advisor phase"
    s.remove_holding("MARUTI")                   # user deletes mid-run
    txns = execute_advice(s, stale, [_advice()], {"MARUTI": 110.0}, D)
    assert txns == []                            # nothing to sell in fresh state
    p = s.load()
    assert p.holdings == []                      # user's delete NOT reverted
    assert p.cash_deployable == pytest.approx(50000.0)   # no phantom sale credit


def test_sell_skipped_on_nonpositive_price(tmp_path):
    """AUD-004: a 0/negative resolved price must never wipe a position for ₹0."""
    s = _store(tmp_path, [_h()])
    txns = execute_advice(s, s.load(), [_advice(close=0.0)], {}, D)
    assert txns == []
    assert s.load().holdings[0].adj_qty == 10.0


def test_executed_price_lands_in_closes(tmp_path):
    """AUD-003: every executed price joins `closes` → one price basis per run."""
    s = _store(tmp_path, [_h()])
    closes = {}                                  # advisor failed to price MARUTI
    execute_advice(s, s.load(), [_advice(close=110.0)], closes, D)
    assert closes["MARUTI"] == 110.0


def test_record_value_point_skips_future_date(tmp_path):
    s = _store(tmp_path, [_h()])
    pt = record_value_point(s, s.load(), {"MARUTI": 110.0}, date(2026, 12, 31))
    assert pt is None
    assert not (tmp_path / "t1" / "value_history.jsonl").exists()
