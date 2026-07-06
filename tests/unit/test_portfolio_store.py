"""Compass Phase A — per-user portfolio store: CRUD, ledger, CSV import."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import AdviceRecord, Holding, WatchlistItem
from core.portfolio.store import PortfolioStore, import_csv, list_user_ids


def _holding(symbol="MARUTI", qty=10, price=12000.0) -> Holding:
    return Holding(
        symbol=symbol, sector="automobile", qty=qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=qty, buy_date="2026-01-05",
    )


@pytest.fixture
def store(tmp_path):
    return PortfolioStore(user_id="testuser", base_dir=str(tmp_path))


def test_load_empty_portfolio(store):
    p = store.load()
    assert p.user_id == "testuser"
    assert p.holdings == [] and p.watchlist == []


def test_add_and_reload_holding(store, tmp_path):
    store.add_holding(_holding())
    p = PortfolioStore(user_id="testuser", base_dir=str(tmp_path)).load()
    assert len(p.holdings) == 1
    assert p.holdings[0].symbol == "MARUTI"
    assert p.updated_at != ""


def test_add_same_symbol_merges_weighted_avg(store):
    store.add_holding(_holding(qty=10, price=100.0))
    p = store.add_holding(_holding(qty=10, price=200.0))
    h = p.holdings[0]
    assert len(p.holdings) == 1
    assert h.qty == 20 and h.adj_qty == 20
    assert h.avg_buy_price == pytest.approx(150.0)
    assert h.adj_avg_price == pytest.approx(150.0)


def test_add_holding_rejects_bad_input(store):
    with pytest.raises(ValueError):
        store.add_holding(_holding(qty=0))
    with pytest.raises(ValueError):
        store.add_holding(_holding(price=-5))


def test_remove_holding(store):
    store.add_holding(_holding())
    assert store.remove_holding("MARUTI") is True
    assert store.remove_holding("MARUTI") is False
    assert store.load().holdings == []


def test_watchlist_dedupe(store):
    w = WatchlistItem(symbol="TCS", sector="it_sector", added="2026-07-06")
    store.add_watchlist(w)
    p = store.add_watchlist(w)
    assert len(p.watchlist) == 1
    assert store.remove_watchlist("TCS") is True


def test_advice_ledger_append_only(store):
    rec = AdviceRecord(
        date="2026-07-06", user_id="testuser", symbol="MARUTI",
        verdict="HOLD", close=13000.0, unrealised_pnl_pct=8.3, stop_pct=10.0,
    )
    store.append_advice(rec)
    store.append_advice(rec.model_copy(update={"date": "2026-07-07"}))
    records = store.load_advice()
    assert [r.date for r in records] == ["2026-07-06", "2026-07-07"]


def test_digest_roundtrip(store):
    assert store.load_latest_digest() is None
    store.save_digest({"date": "2026-07-06", "holdings": []})
    store.save_digest({"date": "2026-07-07", "holdings": []})
    assert store.load_latest_digest()["date"] == "2026-07-07"


def test_import_csv_with_and_without_price(tmp_path):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,10,12000,2026-01-05\n"
        "TCS,it_sector,5,,2026-02-10\n"
    )
    result = import_csv(
        csv_text, user_id="testuser", base_dir=str(tmp_path),
        price_lookup=lambda sym, d: 4000.0,
    )
    assert result["imported"] == 2 and result["errors"] == []
    p = PortfolioStore(user_id="testuser", base_dir=str(tmp_path)).load()
    tcs = next(h for h in p.holdings if h.symbol == "TCS")
    assert tcs.avg_buy_price == 4000.0 and tcs.adj_avg_price == 4000.0


def test_import_csv_reports_row_errors(tmp_path):
    csv_text = (
        "symbol,sector,qty,avg_buy_price,buy_date\n"
        "MARUTI,automobile,notanumber,12000,2026-01-05\n"
    )
    result = import_csv(csv_text, user_id="testuser", base_dir=str(tmp_path))
    assert result["imported"] == 0
    assert len(result["errors"]) == 1


def test_list_user_ids(tmp_path):
    PortfolioStore(user_id="alpha", base_dir=str(tmp_path)).add_holding(_holding())
    PortfolioStore(user_id="beta", base_dir=str(tmp_path)).add_holding(_holding())
    assert sorted(list_user_ids(base_dir=str(tmp_path))) == ["alpha", "beta"]


def test_add_lowercase_symbol_normalized_and_removable(store):
    store.add_holding(_holding(symbol="maruti"))
    p = store.load()
    assert p.holdings[0].symbol == "MARUTI"
    assert store.remove_holding("maruti") is True


def test_watchlist_dedupes_across_case(store):
    store.add_watchlist(WatchlistItem(symbol="tcs", added="2026-07-06"))
    p = store.add_watchlist(WatchlistItem(symbol="TCS", added="2026-07-06"))
    assert len(p.watchlist) == 1
    assert p.watchlist[0].symbol == "TCS"


def test_load_latest_digest_does_not_create_dir(tmp_path):
    s = PortfolioStore(user_id="fresh", base_dir=str(tmp_path))
    assert s.load_latest_digest() is None
    assert not (tmp_path / "fresh" / "digests").exists()
