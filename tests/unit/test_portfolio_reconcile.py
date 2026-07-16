"""Audit Wave 1 (AUD-006) — ledger-replay reconciler, detect + alert only."""
from datetime import datetime, timezone

import pytest

import core.portfolio.reconcile as rec
from backend.shared.schemas.portfolio import AppliedCorpAction, Holding, TransactionRecord
from core.portfolio.store import PortfolioStore


@pytest.fixture(autouse=True)
def _alert_spy(monkeypatch):
    sent = []
    monkeypatch.setattr(rec, "_alert", lambda user_id, issues: sent.append(issues))
    yield sent


def _txn(tid, side, sym, qty, price, cash_before, cash_after, source="autopilot"):
    return TransactionRecord(
        txn_id=tid, date="2026-07-10", ts=datetime.now(timezone.utc).isoformat(),
        user_id="u1", symbol=sym, side=side, qty=qty, price=price,
        value=round(qty * price, 2) if side != "DIV" else round(cash_after - cash_before, 2),
        cash_before=cash_before, cash_after=cash_after,
        holding_qty_after=qty, source=source)


def _store(tmp_path, holdings, cash):
    s = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    p = s.load()
    p.holdings, p.cash_deployable, p.capital_in = holdings, cash, 10000.0
    s.save(p)
    return s


def _h(sym, qty, price=100.0, actions=()):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=price,
                   adj_avg_price=price, adj_qty=qty, buy_date="2026-07-01",
                   applied_actions=list(actions))


def test_clean_ledger_is_clean(tmp_path, _alert_spy):
    s = _store(tmp_path, [_h("MARUTI", 10)], cash=9000.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    result = rec.reconcile(s)
    assert result["status"] == "clean"
    assert _alert_spy == []


def test_cash_drift_detected_and_alerted(tmp_path, _alert_spy):
    s = _store(tmp_path, [_h("MARUTI", 10)], cash=9500.0)   # 500 unexplained
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    result = rec.reconcile(s)
    assert result["status"] == "drift"
    assert any("cash" in i.lower() for i in result["issues"])
    assert len(_alert_spy) == 1


def test_chain_gap_detected(tmp_path, _alert_spy):
    """The AUD-001 lost-update signature: txn N+1's cash_before doesn't match
    txn N's cash_after."""
    s = _store(tmp_path, [_h("MARUTI", 20)], cash=8000.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    s.append_transaction(_txn("t2", "BUY", "MARUTI", 10, 100.0, 9500.0, 8500.0))  # gap!
    result = rec.reconcile(s)
    assert result["status"] == "drift"
    assert any("chain" in i.lower() for i in result["issues"])


def test_qty_mismatch_detected(tmp_path, _alert_spy):
    s = _store(tmp_path, [_h("MARUTI", 7)], cash=9000.0)    # ledger says 10
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    result = rec.reconcile(s)
    assert result["status"] == "drift"
    assert any("MARUTI" in i for i in result["issues"])


def test_corp_action_adjusted_symbol_is_unverifiable_not_drift(tmp_path, _alert_spy):
    bonus = AppliedCorpAction(key="k", ex_date="2026-07-05", kind="bonus",
                              desc="Bonus 1:1", ratio=2.0, applied_on="2026-07-06")
    s = _store(tmp_path, [_h("MARUTI", 20, actions=[bonus])], cash=9000.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    result = rec.reconcile(s)
    assert result["status"] == "clean"                       # skipped, not drift
    assert "MARUTI" in result.get("unverifiable", [])
    assert _alert_spy == []


def test_div_rows_replay_into_cash(tmp_path, _alert_spy):
    s = _store(tmp_path, [_h("MARUTI", 10)], cash=9080.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    s.append_transaction(_txn("t2", "DIV", "MARUTI", 0.0, 8.0, 9000.0, 9080.0))
    result = rec.reconcile(s)
    assert result["status"] == "clean"


def test_no_cash_accounting_skips(tmp_path, _alert_spy):
    s = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    s.add_holding(_h("MARUTI", 10))
    assert rec.reconcile(s)["status"] == "skipped"


def test_clean_pass_logs_info(tmp_path, _alert_spy, caplog):
    """AUD-090a: a clean pass must leave a log line — silence previously meant
    either 'clean' or 'never ran'."""
    import logging
    s = _store(tmp_path, [_h("MARUTI", 10)], cash=9000.0)
    s.append_transaction(_txn("t1", "BUY", "MARUTI", 10, 100.0, 10000.0, 9000.0))
    with caplog.at_level(logging.INFO, logger="core.portfolio.reconcile"):
        assert rec.reconcile(s)["status"] == "clean"
    assert any("clean" in r.message for r in caplog.records)
