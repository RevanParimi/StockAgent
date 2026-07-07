"""Compass Phase A — corp-action adjustment (BLOCKER-grade invariant).

A 1:1 bonus must NOT look like a −50% crash: adj price halves, adj qty
doubles, P&L unchanged.
"""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import Holding
from core.portfolio.corp_actions import (
    apply_actions_to_holding,
    parse_action,
    sync_corp_actions,
)
from core.portfolio.store import PortfolioStore

TODAY = date(2026, 7, 6)


def _holding(price=1000.0, qty=10) -> Holding:
    return Holding(
        symbol="ACME", sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


def test_parse_bonus():
    a = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    assert a is not None and a.kind == "bonus" and a.ratio == 2.0


def test_parse_split():
    a = parse_action({
        "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
        "exDate": "10-Jun-2026",
    })
    assert a is not None and a.kind == "split" and a.ratio == 5.0


def test_parse_dividend():
    a = parse_action({"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"})
    assert a is not None and a.kind == "dividend" and a.dividend_per_share == 8.0


def test_parse_ignores_agm():
    assert parse_action({"subject": "Annual General Meeting", "exDate": "10-Jun-2026"}) is None


def test_bonus_preserves_pnl():
    h = _holding(price=1000.0, qty=10)
    bonus = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    applied = apply_actions_to_holding(h, [bonus], TODAY)
    assert applied == 1
    assert h.adj_avg_price == pytest.approx(500.0)
    assert h.adj_qty == 20
    assert h.avg_buy_price == 1000.0 and h.qty == 10      # raw fields untouched
    # Post-bonus close ~500 => P&L ~0%, NOT -50%
    assert abs(h.unrealised_pnl_pct(500.0)) < 1e-9


def test_dividend_credits_cash():
    h = _holding(price=1000.0, qty=10)
    div = parse_action({"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"})
    apply_actions_to_holding(h, [div], TODAY)
    assert h.dividends_received == pytest.approx(80.0)    # 10 shares × ₹8


def test_idempotent_second_apply_is_noop():
    h = _holding()
    bonus = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    assert apply_actions_to_holding(h, [bonus], TODAY) == 1
    assert apply_actions_to_holding(h, [bonus], TODAY) == 0
    assert h.adj_qty == 20   # not 40


def test_action_before_buy_date_not_applied():
    h = _holding()   # bought 2026-01-05
    old = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2025"})
    assert apply_actions_to_holding(h, [old], TODAY) == 0


def test_future_ex_date_not_applied():
    h = _holding()
    future = parse_action({"subject": "Bonus 1:1", "exDate": "10-Aug-2026"})
    assert apply_actions_to_holding(h, [future], TODAY) == 0


def test_sync_never_raises_and_saves(tmp_path):
    store = PortfolioStore(user_id="u", base_dir=str(tmp_path))
    store.add_holding(_holding())

    def fake_fetch(symbol):
        return [{"subject": "Bonus 1:1", "exDate": "10-Jun-2026"}]

    result = sync_corp_actions(store, TODAY, fetch=fake_fetch)
    assert result["applied"] == 1
    reloaded = store.load().holdings[0]
    assert reloaded.adj_qty == 20

    def boom(symbol):
        raise RuntimeError("network down")
    assert sync_corp_actions(store, TODAY, fetch=boom)["applied"] == 0


def test_parse_bonus_issue_phrasing():
    a = parse_action({"subject": "Bonus Issue 1:1", "exDate": "10-Jun-2026"})
    assert a is not None and a.kind == "bonus" and a.ratio == 2.0


def test_actions_apply_in_ex_date_order_regardless_of_feed_order():
    h = _holding(price=1000.0, qty=10)
    bonus = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2026"})
    div = parse_action({"subject": "Dividend - Rs 8 Per Share", "exDate": "01-Jun-2026"})
    # Feed newest-first: bonus before dividend. Dividend ex-date is EARLIER,
    # so it must credit on the pre-bonus quantity (10 × 8 = 80, not 160).
    applied = apply_actions_to_holding(h, [bonus, div], TODAY)
    assert applied == 2
    assert h.dividends_received == pytest.approx(80.0)
    assert h.adj_qty == 20


def test_sync_survives_save_failure(tmp_path, monkeypatch):
    store = PortfolioStore(user_id="u2", base_dir=str(tmp_path))
    store.add_holding(_holding())

    def fake_fetch(symbol):
        return [{"subject": "Bonus 1:1", "exDate": "10-Jun-2026"}]

    def boom_save(portfolio):
        raise RuntimeError("disk full")
    monkeypatch.setattr(store, "save", boom_save)
    result = sync_corp_actions(store, TODAY, fetch=fake_fetch)
    assert result["applied"] == 0 and result.get("save_failed") is True
