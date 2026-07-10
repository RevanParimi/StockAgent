"""Compass Phase C — weekly review: allocation, laggards, scoreboard (spec §7)."""
from datetime import date

import pandas as pd

import core.delivery.weekly as wk
from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.store import PortfolioStore


def _store(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    p = store.load()
    p.holdings = [
        Holding(symbol="WINCO", sector="it_sector", qty=10, avg_buy_price=100.0,
                adj_avg_price=100.0, adj_qty=10, buy_date="2026-03-02"),
        Holding(symbol="LAGCO", sector="automobile", qty=10, avg_buy_price=200.0,
                adj_avg_price=200.0, adj_qty=10, buy_date="2026-03-02"),
    ]
    store.save(p)
    # 20-day-old EXIT advice at close 100; latest close 80 -> correct call
    store.append_advice(AdviceRecord(
        date="2026-06-15", user_id="u1", symbol="LAGCO", verdict="EXIT",
        close=100.0, unrealised_pnl_pct=-10.0, stop_pct=12.0))
    return store


def _closes():
    return {"WINCO": 130.0, "LAGCO": 80.0}


def test_build_weekly_sections(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "Weekly headline.")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)

    alloc = {a["sector"]: a["weight_pct"] for a in review["allocation"]}
    assert abs(alloc["it_sector"] - 61.90) < 0.1      # 1300 / 2100 (market value)
    assert abs(alloc["automobile"] - 38.10) < 0.1     # 800 / 2100
    # both above the 30% warn threshold; allocation is sorted by weight desc
    assert review["concentration_flags"] == ["it_sector", "automobile"]
    assert review["laggards"][0]["symbol"] == "LAGCO"
    assert review["laggards"][0]["pnl_pct"] == -60.0
    sb = review["scoreboard"]
    assert sb["counts"]["EXIT"] == 1
    assert sb["checked"] == 1 and sb["correct"] == 1  # price fell after EXIT
    assert review["headline"] == "Weekly headline."
    text = wk.render_weekly_text(review)
    assert "LAGCO" in text and "Weekly headline." in text


def test_switch_candidates_only_underweight_sectors(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())

    class _Idea:
        def __init__(self, symbol, sector, conviction):
            self.symbol, self.sector, self.conviction = symbol, sector, conviction
            self.status, self.thesis = "active", "t"
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [
        _Idea("PHARMCO", "pharma", 0.8),          # 0% weight -> underweight, offered
        _Idea("ITCO", "it_sector", 0.9),          # largest sector (61.9%) -> not offered
    ])
    review = wk.build_weekly_review("u1", date(2026, 7, 5), store=store)
    assert [c["symbol"] for c in review["switch_candidates"]] == ["PHARMCO"]


def test_run_weekly_saves_and_delivers(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setattr(wk, "list_user_ids", lambda: ["u1"])
    monkeypatch.setattr(wk.settings, "PORTFOLIO_DATA_DIR", str(tmp_path))
    _store(tmp_path)
    monkeypatch.setattr(wk, "_narrate_weekly", lambda r: "h")
    monkeypatch.setattr(wk, "_latest_closes", lambda symbols, on: _closes())
    monkeypatch.setattr(wk, "_active_shelf_ideas", lambda: [])
    with patch.object(wk, "deliver", return_value={"delivered": True}) as m:
        out = wk.run_weekly_review(on=date(2026, 7, 5))
    assert out["status"] == "completed" and m.call_count == 1
    saved = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load_latest_weekly()
    assert saved and saved["kind"] == "weekly_review"
