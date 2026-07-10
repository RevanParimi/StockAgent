"""Compass Autopilot — store ledger tests (spec §3.2/§3.3)."""
import pytest

from backend.shared.schemas.portfolio import Holding, TransactionRecord
from core.portfolio.store import PortfolioStore


def _store(tmp_path):
    return PortfolioStore(user_id="t1", base_dir=str(tmp_path))


def _txn(i=0, side="BUY"):
    return TransactionRecord(
        txn_id=f"id{i}", date="2026-07-11", ts="2026-07-11T12:00:00+00:00",
        user_id="t1", symbol="MARUTI", side=side, qty=1, price=100.0,
        value=100.0, cash_before=1000.0, cash_after=900.0, holding_qty_after=1,
    )


def test_transactions_append_and_tail_load(tmp_path):
    s = _store(tmp_path)
    assert s.load_transactions() == []
    for i in range(5):
        s.append_transaction(_txn(i))
    got = s.load_transactions(limit=3)
    assert [t.txn_id for t in got] == ["id2", "id3", "id4"]   # tail, file order


def test_transactions_tolerate_bad_lines(tmp_path):
    s = _store(tmp_path)
    s.append_transaction(_txn(1))
    (tmp_path / "t1" / "transactions.jsonl").open("a", encoding="utf-8").write("{broken\n")
    s.append_transaction(_txn(2))
    assert [t.txn_id for t in s.load_transactions()] == ["id1", "id2"]


def test_value_history_roundtrip(tmp_path):
    s = _store(tmp_path)
    assert s.load_value_history() == []
    s.append_value_point({"date": "2026-07-11", "total_equity": 100.0})
    s.append_value_point({"date": "2026-07-12", "total_equity": 101.0})
    hist = s.load_value_history(limit=1)
    assert hist == [{"date": "2026-07-12", "total_equity": 101.0}]


def test_reduce_holding_partial_and_full(tmp_path):
    s = _store(tmp_path)
    s.add_holding(Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-07-01"))
    realized, removed = s.reduce_holding("MARUTI", 4, 110.0)
    assert realized == pytest.approx(40.0) and removed is False
    assert s.load().holdings[0].adj_qty == pytest.approx(6.0)
    realized, removed = s.reduce_holding("MARUTI", 6, 90.0)
    assert realized == pytest.approx(-60.0) and removed is True
    assert s.load().holdings == []
    with pytest.raises(ValueError):
        s.reduce_holding("NOPE", 1, 100.0)
