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
    applied, _ = apply_actions_to_holding(h, [bonus], TODAY)
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
    assert apply_actions_to_holding(h, [bonus], TODAY)[0] == 1
    assert apply_actions_to_holding(h, [bonus], TODAY)[0] == 0
    assert h.adj_qty == 20   # not 40


def test_action_before_buy_date_not_applied():
    h = _holding()   # bought 2026-01-05
    old = parse_action({"subject": "Bonus 1:1", "exDate": "10-Jun-2025"})
    assert apply_actions_to_holding(h, [old], TODAY)[0] == 0


def test_future_ex_date_not_applied():
    h = _holding()
    future = parse_action({"subject": "Bonus 1:1", "exDate": "10-Aug-2026"})
    assert apply_actions_to_holding(h, [future], TODAY)[0] == 0


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
    applied, _ = apply_actions_to_holding(h, [bonus, div], TODAY)
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


# ---------------------------------------------------------------------------
# Audit Wave 1 — AUD-045 (dividends are real cash) / AUD-046 (percent guard)
# ---------------------------------------------------------------------------

def _cash_store(tmp_path, cash=5000.0):
    store = PortfolioStore(user_id="u3", base_dir=str(tmp_path))
    store.add_holding(_holding())
    p = store.load()
    p.cash_deployable, p.capital_in, p.autopilot = cash, 15000.0, True
    store.save(p)
    return store


def test_dividend_sync_credits_cash_and_writes_div_txn(tmp_path):
    """AUD-045: with cash accounting on, an applied dividend credits
    cash_deployable and appends one DIV ledger row."""
    store = _cash_store(tmp_path)

    def fetch(symbol):
        return [{"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"}]

    result = sync_corp_actions(store, TODAY, fetch=fetch)
    assert result["applied"] == 1
    p = store.load()
    assert p.cash_deployable == pytest.approx(5000.0 + 80.0)
    divs = [t for t in store.load_transactions() if t.side == "DIV"]
    assert len(divs) == 1
    t = divs[0]
    assert t.value == pytest.approx(80.0) and t.qty == 0.0
    assert t.realized_pnl == 0.0
    assert t.cash_after - t.cash_before == pytest.approx(80.0)
    assert t.date == "2026-06-10"          # ex-date, not sync date


def test_dividend_sync_idempotent_no_double_credit(tmp_path):
    store = _cash_store(tmp_path)

    def fetch(symbol):
        return [{"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"}]

    sync_corp_actions(store, TODAY, fetch=fetch)
    sync_corp_actions(store, TODAY, fetch=fetch)   # re-sync, same action key
    p = store.load()
    assert p.cash_deployable == pytest.approx(5080.0)   # credited ONCE
    assert len([t for t in store.load_transactions() if t.side == "DIV"]) == 1


def test_dividend_without_cash_accounting_tracks_metric_only(tmp_path):
    store = PortfolioStore(user_id="u4", base_dir=str(tmp_path))
    store.add_holding(_holding())                  # cash_deployable stays None

    def fetch(symbol):
        return [{"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jun-2026"}]

    sync_corp_actions(store, TODAY, fetch=fetch)
    p = store.load()
    assert p.cash_deployable is None
    assert p.holdings[0].dividends_received == pytest.approx(80.0)
    assert not [t for t in store.load_transactions() if t.side == "DIV"]


def test_percent_dividend_skipped_with_warning():
    """AUD-046: percent-of-face-value rows must not book ₹/share amounts."""
    assert parse_action({"subject": "Dividend 150%", "exDate": "10-Jun-2026"}) is None
    assert parse_action({"subject": "Dividend - 150 % of face value",
                         "exDate": "10-Jun-2026"}) is None
    # ₹-per-share formats still parse
    a = parse_action({"subject": "Interim Dividend - Rs 2.50 Per Share",
                      "exDate": "10-Jun-2026"})
    assert a is not None and a.dividend_per_share == 2.50
