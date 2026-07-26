"""Autopilot pipeline integration — execution hook + digest trades (spec §4)."""
from datetime import date

import pytest
from unittest.mock import patch

from backend.shared.schemas.portfolio import (
    AdviceRecord, Holding, Portfolio, TransactionRecord,
)
from core.portfolio.digest import build_digest

D = date(2026, 7, 13)

@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Wave 1 (AUD-044): executor date guards compare against IST-today;
    freeze it so these tests are calendar-independent."""
    import core.portfolio.autopilot as _ap
    monkeypatch.setattr(_ap, "_today_ist", lambda: D)



def _portfolio():
    return Portfolio(user_id="t1", holdings=[
        Holding(symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=100.0,
                adj_avg_price=100.0, adj_qty=10, buy_date="2026-06-01")])


def _advice():
    return [AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                         verdict="HOLD", close=110.0, unrealised_pnl_pct=10.0,
                         stop_pct=8.0)]


def _txn():
    return TransactionRecord(
        txn_id="x1", date=D.isoformat(), ts="2026-07-13T12:00:00+00:00",
        user_id="t1", symbol="MARUTI", side="SELL", qty=2, price=110.0,
        value=220.0, cash_before=0.0, cash_after=220.0, holding_qty_after=8,
        realized_pnl=20.0, verdict="TRIM")


def _switch_advice_with_skipped_buy():
    """SWITCH verdict whose sell leg executed but whose buy leg (LODHA) did
    not — mirrors an unpriceable candidate or budget < 1 share (spec §4)."""
    return [AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                         verdict="SWITCH", close=110.0, unrealised_pnl_pct=-9.0,
                         stop_pct=8.0, switch_candidate="lodha")]


def _switch_sell_only_txn():
    return TransactionRecord(
        txn_id="x2", date=D.isoformat(), ts="2026-07-13T12:00:00+00:00",
        user_id="t1", symbol="MARUTI", side="SELL", qty=10, price=110.0,
        value=1100.0, cash_before=0.0, cash_after=1100.0, holding_qty_after=0,
        realized_pnl=100.0, verdict="SWITCH")


def test_digest_includes_trades_when_passed():
    d = build_digest("t1", D, _advice(), _portfolio(), {"MARUTI": 110.0},
                     transactions=[_txn()])
    assert len(d["trades"]) == 1
    assert d["trades"][0]["side"] == "SELL"


def test_digest_backward_compatible_without_trades():
    d = build_digest("t1", D, _advice(), _portfolio(), {"MARUTI": 110.0})
    assert d["trades"] == []


def test_pipeline_calls_executor_and_value_recorder():
    """The pipeline must call execute_advice + record_value_point per user."""
    import core.portfolio.pipeline as pl
    with patch.object(pl, "active_user_ids", return_value=["t1"]), \
         patch.object(pl, "PortfolioStore") as MockStore, \
         patch.object(pl, "sync_corp_actions"), \
         patch.object(pl, "refresh_events_calendar", return_value={}), \
         patch.object(pl, "close_on", return_value=110.0), \
         patch.object(pl, "get_price_history", side_effect=Exception("skip")), \
         patch.object(pl, "build_signals"), \
         patch.object(pl, "decide", return_value=_advice()[0]), \
         patch.object(pl, "narrate", return_value="n"), \
         patch("core.portfolio.autopilot.execute_advice", return_value=[_txn()]) as mock_exec, \
         patch("core.portfolio.autopilot.record_value_point", return_value=None) as mock_rvp, \
         patch.object(pl, "is_trading_day", return_value=True):
        store = MockStore.return_value
        store.load.return_value = _portfolio()
        result = pl.run_post_review_pipeline(D)
    assert result["status"] == "completed"
    assert mock_exec.call_count == 1
    assert mock_rvp.call_count == 1


def test_pipeline_emits_switch_buy_skipped_alert():
    """I2 (spec §4): when a SWITCH sell executes but the buy leg is skipped
    (unpriceable candidate / budget < 1 share / dedupe), the pipeline must
    surface a switch_buy_skipped alert — otherwise the user sees a SELL
    alert and silence while a position quietly became cash."""
    import core.portfolio.pipeline as pl
    with patch.object(pl, "active_user_ids", return_value=["t1"]), \
         patch.object(pl, "PortfolioStore") as MockStore, \
         patch.object(pl, "sync_corp_actions"), \
         patch.object(pl, "refresh_events_calendar", return_value={}), \
         patch.object(pl, "close_on", return_value=110.0), \
         patch.object(pl, "get_price_history", side_effect=Exception("skip")), \
         patch.object(pl, "build_signals"), \
         patch.object(pl, "decide", return_value=_switch_advice_with_skipped_buy()[0]), \
         patch.object(pl, "narrate", return_value="n"), \
         patch("core.portfolio.autopilot.execute_advice",
               return_value=[_switch_sell_only_txn()]), \
         patch("core.portfolio.autopilot.record_value_point", return_value=None), \
         patch.object(pl, "is_trading_day", return_value=True), \
         patch("core.delivery.alerts.emit_alerts", return_value={"emitted": 0}) as mock_emit, \
         patch("core.delivery.channels.deliver", return_value={"delivered": False}):
        store = MockStore.return_value
        store.load.return_value = _portfolio()
        result = pl.run_post_review_pipeline(D)
    assert result["status"] == "completed"
    assert mock_emit.call_count == 1
    events = mock_emit.call_args.args[0]
    skipped = [e for e in events if e.kind == "switch_buy_skipped"]
    assert len(skipped) == 1
    assert skipped[0].symbol == "LODHA"
    assert "MARUTI" in skipped[0].message and "LODHA" in skipped[0].message
    assert skipped[0].severity == "warning"
