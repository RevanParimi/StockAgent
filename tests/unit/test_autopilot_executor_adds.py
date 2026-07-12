"""Autopilot executor — ADD sizing, caps, cooldown (spec §4)."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio, TransactionRecord
from core.portfolio.autopilot import execute_advice, make_txn_id
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)

@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Wave 1 (AUD-044): executor date guards compare against IST-today;
    freeze it so these tests are calendar-independent."""
    import core.portfolio.autopilot as _ap
    monkeypatch.setattr(_ap, "_today_ist", lambda: D)




def _store(tmp_path, holdings, cash=100000.0):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, 500000.0, True
    s.save(p)
    return s


def _h(sym="MARUTI", qty=10.0, price=100.0, sector="automobile"):
    return Holding(symbol=sym, sector=sector, qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _add(sym="MARUTI", close=100.0, confidence=0.6):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym, verdict="ADD",
                        close=close, unrealised_pnl_pct=5.0, stop_pct=8.0,
                        confidence=confidence, rationale_hash="c0ffee")


def test_add_buys_25pct_of_position_whole_shares(tmp_path):
    # big portfolio so the 10% weight cap doesn't bind: MARUTI is 1k of 401k
    others = [_h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, [_h(qty=10, price=100.0)] + others, cash=100000.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)], {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert len(txns) == 1
    t = txns[0]
    assert t.side == "BUY" and t.qty == 2        # floor(0.25*1000/100)=2
    p = s.load()
    maruti = next(h for h in p.holdings if h.symbol == "MARUTI")
    assert maruti.adj_qty == pytest.approx(12.0)
    assert maruti.adj_avg_price == pytest.approx(100.0)
    assert p.cash_deployable == pytest.approx(100000.0 - 200.0)


def test_add_respects_cash_floor(tmp_path):
    # padding keeps MARUTI far below the 10% weight cap so only cash binds
    holdings = [_h(qty=100, price=100.0),
                _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=10100.0)
    # tranche = 2500 but only 100 above the 10k floor -> qty 1
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert len(txns) == 1 and txns[0].qty == 1
    assert s.load().cash_deployable == pytest.approx(10000.0)


def test_add_skipped_when_floor_leaves_under_one_share(tmp_path):
    holdings = [_h(qty=100, price=100.0),
                _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=10050.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert txns == []


def test_add_respects_position_weight_cap(tmp_path):
    # MARUTI 5000 of 50000 total = 10% already at ADVISOR_MAX_POSITION_PCT cap
    holdings = [_h(qty=50, price=100.0),
                _h(sym="OTHER", qty=450, price=100.0, sector="banking")]
    s = _store(tmp_path, holdings, cash=100000.0)
    txns = execute_advice(s, s.load(), [_add(close=100.0)],
                          {"MARUTI": 100.0, "OTHER": 100.0}, D)
    assert txns == []


def test_add_cooldown_blocks_repeat_within_5_trading_days(tmp_path):
    s = _store(tmp_path, [_h(qty=100, price=100.0),
                          _h(sym="PADDING", qty=100.0, price=4000.0, sector="banking")])
    prior = TransactionRecord(
        txn_id="prior1", date=date(2026, 7, 9).isoformat(),   # Thu, 2 TD before Mon 13th
        ts="2026-07-09T12:00:00+00:00", user_id="t1", symbol="MARUTI",
        side="BUY", qty=1, price=100.0, value=100.0, cash_before=0, cash_after=0,
        holding_qty_after=1, source="autopilot", verdict="ADD")
    s.append_transaction(prior)
    txns = execute_advice(s, s.load(), [_add()], {"MARUTI": 100.0, "PADDING": 4000.0}, D)
    assert txns == []


def test_buys_ordered_by_confidence_when_cash_constrained(tmp_path):
    holdings = [_h(sym="AAA", qty=100, price=100.0),
                _h(sym="BBB", qty=100, price=100.0, sector="banking"),
                _h(sym="PADDING", qty=200.0, price=4000.0, sector="pharma")]
    s = _store(tmp_path, holdings, cash=12000.0)   # only 2000 above floor
    advice = [_add(sym="AAA", confidence=0.5), _add(sym="BBB", confidence=0.9)]
    txns = execute_advice(s, s.load(), advice,
                          {"AAA": 100.0, "BBB": 100.0, "PADDING": 4000.0}, D)
    # BBB (higher confidence) fills its 20-share tranche... capped by cash to 20
    assert [t.symbol for t in txns] == ["BBB"]
    assert txns[0].qty == 20                       # floor(2000/100)
