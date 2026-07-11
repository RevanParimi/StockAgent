"""Autopilot executor — SWITCH two-leg + value history (spec §3.3/§4)."""
from datetime import date
from unittest.mock import patch

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice, record_value_point
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)


def _store(tmp_path, holdings, cash=20000.0):
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in, p.autopilot = holdings, cash, 100000.0, True
    s.save(p)
    return s


def _h(sym="TATAMOTORS", qty=10.0, price=100.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-06-01")


def _switch(sym="TATAMOTORS", cand="LODHA", close=110.0):
    return AdviceRecord(date=D.isoformat(), user_id="t1", symbol=sym,
                        verdict="SWITCH", close=close, unrealised_pnl_pct=-9.0,
                        stop_pct=8.0, confidence=0.4, switch_candidate=cand,
                        triggers=["stop_breach", "switch_candidate_available"],
                        rationale_hash="5w17c4")


@patch("core.portfolio.autopilot.promote_symbol", return_value={"status": "ok"})
@patch("core.portfolio.autopilot.close_on", return_value=200.0)
def test_switch_sells_then_buys_candidate(mock_close, mock_promote, tmp_path):
    s = _store(tmp_path, [_h()], cash=20000.0)
    txns = execute_advice(s, s.load(), [_switch()], {"TATAMOTORS": 110.0}, D,
                          sector_lookup={"LODHA": "realty"})
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "TATAMOTORS"), ("BUY", "LODHA")]
    buy = txns[1]
    # proceeds 1100, cash 20000+1100=21100, floor 10000 -> budget min(1100, 11100)=1100 -> 5 shares
    assert buy.qty == 5 and buy.price == 200.0
    p = s.load()
    lodha = next(h for h in p.holdings if h.symbol == "LODHA")
    assert lodha.sector == "realty" and lodha.buy_date == D.isoformat()
    mock_close.assert_called_once()
    mock_promote.assert_called_once_with("LODHA", "realty", origin="held")


@patch("core.portfolio.autopilot.close_on", side_effect=Exception("no price"))
def test_switch_buy_skipped_when_candidate_unpriceable(mock_close, tmp_path):
    s = _store(tmp_path, [_h()], cash=20000.0)
    txns = execute_advice(s, s.load(), [_switch()], {"TATAMOTORS": 110.0}, D)
    assert [(t.side, t.symbol) for t in txns] == [("SELL", "TATAMOTORS")]
    assert not any(h.symbol == "LODHA" for h in s.load().holdings)


def test_record_value_point_appends_and_computes_day_change(tmp_path):
    s = _store(tmp_path, [_h(qty=10, price=100.0)], cash=1000.0)
    s.append_value_point({"date": "2026-07-10", "market_value": 1000.0,
                          "cash": 1000.0, "total_equity": 2000.0,
                          "capital_in": 100000.0, "day_change_pct": None})
    pt = record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D)
    assert pt["market_value"] == pytest.approx(1100.0)
    assert pt["total_equity"] == pytest.approx(2100.0)
    assert pt["day_change_pct"] == pytest.approx(5.0)
    # idempotent: same day again -> None, no extra line
    assert record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D) is None
    assert len(s.load_value_history()) == 2


def test_record_value_point_skips_stale_review_date(tmp_path):
    """C1: a replayed point for a review_date older than the last recorded
    history point must be dropped, not just an exact-date duplicate — else
    a stale-date replay appends an out-of-order value point."""
    s = _store(tmp_path, [_h(qty=10, price=100.0)], cash=1000.0)
    s.append_value_point({"date": "2026-07-13", "market_value": 1100.0,
                          "cash": 1000.0, "total_equity": 2100.0,
                          "capital_in": 100000.0, "day_change_pct": None})
    before = s.load_value_history()
    stale = date(2026, 7, 10)                       # before the last recorded point
    pt = record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, stale)
    assert pt is None
    assert s.load_value_history() == before          # nothing appended


def test_record_value_point_skips_without_cash_accounting(tmp_path):
    s = PortfolioStore(user_id="t2", base_dir=str(tmp_path))
    p = s.load(); p.holdings = [_h()]; s.save(p)      # cash_deployable None
    assert record_value_point(s, s.load(), {"TATAMOTORS": 110.0}, D) is None
    assert s.load_value_history() == []
