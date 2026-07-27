"""Piece A (spec 2026-07-27): transparency fields on TransactionRecord and
their population by the autopilot executor."""
from backend.shared.schemas.portfolio import TransactionRecord


def _base_row(**over):
    row = dict(
        txn_id="abc123", date="2026-07-20", ts="2026-07-20T11:05:00+00:00",
        user_id="primary", symbol="SUZLON", side="SELL", qty=10.0, price=55.0,
        value=550.0, cash_before=100.0, cash_after=650.0,
        holding_qty_after=0.0, realized_pnl=50.0,
    )
    row.update(over)
    return row


def test_old_ledger_row_without_new_fields_still_parses():
    t = TransactionRecord(**_base_row())
    assert t.cost_basis is None
    assert t.pnl_pct is None
    assert t.reason == ""


def test_new_fields_round_trip():
    t = TransactionRecord(**_base_row(cost_basis=50.0, pnl_pct=10.0,
                                      reason="stop was breached"))
    dumped = t.model_dump()
    assert dumped["cost_basis"] == 50.0
    assert dumped["pnl_pct"] == 10.0
    assert dumped["reason"] == "stop was breached"
    assert TransactionRecord(**dumped) == t
