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


from backend.shared.schemas.portfolio import AdviceRecord, Holding, Portfolio
from core.portfolio.autopilot import _execute_buys, _execute_sells


def _holding(**over):
    h = dict(symbol="SUZLON", sector="renewable_energy", qty=100.0,
             avg_buy_price=50.0, adj_avg_price=50.0, adj_qty=100.0,
             buy_date="2026-07-01")
    h.update(over)
    return Holding(**h)


def _advice(**over):
    a = dict(date="2026-07-20", user_id="primary", symbol="SUZLON",
             verdict="EXIT", close=55.0, unrealised_pnl_pct=10.0,
             stop_pct=8.0, triggers=["stop_breach"],
             narrative="The stop was breached while the forecast points down.",
             rationale_hash="deadbeef")
    a.update(over)
    return AdviceRecord(**a)


def _portfolio(holdings):
    return Portfolio(user_id="primary", holdings=holdings,
                     cash_deployable=10_000.0, capital_in=100_000.0,
                     autopilot=True)


def test_sell_txn_carries_cost_basis_pnl_pct_and_reason():
    pf = _portfolio([_holding()])
    txns, _ = _execute_sells(pf, [_advice()], {"SUZLON": 55.0}, set())
    assert len(txns) == 1
    t = txns[0]
    assert t.cost_basis == 50.0
    # realized = (55-50)*100 = 500 ; pnl_pct = 500 / (50*100) * 100 = 10.0
    assert t.pnl_pct == 10.0
    assert t.reason == "The stop was breached while the forecast points down."


def test_buy_txn_carries_reason_but_no_cost_basis(monkeypatch):
    import core.portfolio.autopilot as ap
    monkeypatch.setattr(ap, "_last_add_date", lambda store, symbol: None)
    from datetime import date
    # For the ADD tranche to actually fire (and produce a BUY txn), SUZLON must
    # sit under the position-weight cap and the portfolio must hold cash above
    # the min-cash floor — otherwise the tranche budget is zeroed before _txn
    # runs. A dominant second holding dilutes SUZLON's weight; the raised cash
    # clears the floor. None of this touches what we assert (reason / no basis).
    pf = _portfolio([_holding(qty=10.0, adj_qty=10.0),
                     _holding(symbol="BIGCO", sector="it", qty=1000.0,
                              adj_qty=1000.0, avg_buy_price=100.0,
                              adj_avg_price=100.0)])
    pf.cash_deployable = 60_000.0
    rec = _advice(verdict="ADD", triggers=["add_bullish_healthy"],
                  narrative="Envelope bullish and regime supportive.",
                  confidence=0.9)
    txns = _execute_buys(pf, [rec], {"SUZLON": 55.0}, set(), [],
                         date(2026, 7, 20), store=None, sector_lookup=None)
    assert len(txns) == 1
    assert txns[0].reason == "Envelope bullish and regime supportive."
    assert txns[0].cost_basis is None
    assert txns[0].pnl_pct is None
