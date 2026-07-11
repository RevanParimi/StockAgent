"""Autopilot executor — sell side (spec §4)."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.autopilot import execute_advice, make_txn_id
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)          # a Monday (trading day)


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


def _advice(sym="MARUTI", verdict="HOLD", close=110.0, confidence=0.5,
            switch_candidate=""):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym,
                        verdict=verdict, close=close, unrealised_pnl_pct=10.0,
                        stop_pct=8.0, confidence=confidence,
                        switch_candidate=switch_candidate,
                        rationale_hash="feedbeef")


def test_gating_off_no_writes(tmp_path):
    s = _store(tmp_path, [_h()], autopilot=False)
    before = (tmp_path / "t1" / "portfolio.json").read_bytes()
    txns = execute_advice(s, s.load(), [_advice(verdict="EXIT")], {"MARUTI": 110.0}, D)
    assert txns == []
    assert (tmp_path / "t1" / "portfolio.json").read_bytes() == before
    assert not (tmp_path / "t1" / "transactions.jsonl").exists()


def test_exit_sells_all_credits_cash_moves_to_watchlist(tmp_path):
    s = _store(tmp_path, [_h()], cash=1000.0)
    txns = execute_advice(s, s.load(), [_advice(verdict="EXIT")], {"MARUTI": 110.0}, D)
    assert len(txns) == 1
    t = txns[0]
    assert t.side == "SELL" and t.qty == 10 and t.price == 110.0
    assert t.realized_pnl == pytest.approx(100.0)
    assert t.cash_after == pytest.approx(1000.0 + 1100.0)
    p = s.load()
    assert p.holdings == []
    assert p.cash_deployable == pytest.approx(2100.0)
    assert any(w.symbol == "MARUTI" and w.source == "autopilot" for w in p.watchlist)
    assert p.last_autopilot_run == D.isoformat()
    assert [x.txn_id for x in s.load_transactions()] == [t.txn_id]


def test_trim_sells_25pct_floored_min_1(tmp_path):
    s = _store(tmp_path, [_h(qty=10)])
    txns = execute_advice(s, s.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns[0].qty == 2                     # floor(10*0.25)=2
    assert s.load().holdings[0].adj_qty == pytest.approx(8.0)
    s2 = _store(tmp_path.parent / "b", [_h(qty=3)])
    txns2 = execute_advice(s2, s2.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns2[0].qty == 1                    # max(1, floor(0.75))


def test_trim_to_zero_when_under_one_share_would_remain(tmp_path):
    s = _store(tmp_path, [_h(qty=1)])
    txns = execute_advice(s, s.load(), [_advice(verdict="TRIM")], {"MARUTI": 110.0}, D)
    assert txns[0].qty == 1 and txns[0].note == "trim_to_zero"
    assert s.load().holdings == []


def test_idempotent_same_day_rerun_no_double_trades(tmp_path):
    s = _store(tmp_path, [_h()])
    advice = [_advice(verdict="TRIM")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    txns2 = execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    assert txns2 == []
    assert len(s.load_transactions()) == 1


def test_txn_id_dedupe_survives_missing_run_marker(tmp_path):
    s = _store(tmp_path, [_h()])
    advice = [_advice(verdict="TRIM")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    p = s.load(); p.last_autopilot_run = ""; s.save(p)   # simulate crash pre-save
    txns2 = execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    assert txns2 == []                                    # ledger id blocks replay


def test_stale_review_date_replay_is_blocked(tmp_path):
    """C1: a re-run for a PAST review_date (e.g. a manually retried
    POST /portfolio/run-advisor?review_date=<past>) must not execute stale
    trades against the CURRENT portfolio nor regress the run marker. Only
    an equality check (old behaviour) would miss this — day < last_run
    must also be blocked."""
    s = _store(tmp_path, [_h()])
    advice = [_advice(verdict="TRIM")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)   # stamps last_autopilot_run=D
    assert s.load().last_autopilot_run == D.isoformat()
    stale = date(2026, 7, 10)                                   # before D
    before = (tmp_path / "t1" / "portfolio.json").read_bytes()
    txns2 = execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, stale)
    assert txns2 == []
    assert (tmp_path / "t1" / "portfolio.json").read_bytes() == before
    assert s.load().last_autopilot_run == D.isoformat()          # marker not regressed
    assert len(s.load_transactions()) == 1                       # no new txns appended


def test_hold_and_unknown_symbol_do_nothing(tmp_path):
    s = _store(tmp_path, [_h()])
    txns = execute_advice(
        s, s.load(),
        [_advice(verdict="HOLD"), _advice(sym="GHOST", verdict="EXIT")],
        {"MARUTI": 110.0}, D)
    assert txns == []
    p = s.load()
    assert len(p.holdings) == 1
    assert p.last_autopilot_run == D.isoformat()   # zero-trade run still stamps marker
    assert s.load_transactions() == []
