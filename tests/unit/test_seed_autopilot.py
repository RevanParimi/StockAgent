"""Autopilot seed script (spec §5)."""
from datetime import date

import pytest

from core.portfolio.store import PortfolioStore
from scripts.seed_autopilot import seed

D = date(2026, 7, 13)


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Wave 1 (AUD-044): value-point future guard compares against IST-today;
    freeze it so these tests are calendar-independent."""
    import core.portfolio.autopilot as _ap
    monkeypatch.setattr(_ap, "_today_ist", lambda: D)
TICKERS = [{"sym": "AAA", "sector": "automobile"},
           {"sym": "BBB", "sector": "banking"},
           {"sym": "CCC", "sector": "it"},
           {"sym": "DDD", "sector": "pharma"}]
PRICES = {"AAA": 250.0, "BBB": 100.0, "CCC": 999999.0, "DDD": 40.0}


def _lookup(sym, on):
    if sym == "CCC":
        raise RuntimeError("no price")
    return PRICES[sym]


def test_seed_equal_weight_whole_shares(tmp_path):
    res = seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
               price_lookup=_lookup, on=D)
    # budget 25000 each: AAA 100 sh, BBB 250 sh, CCC skipped, DDD 625 sh
    assert res["seeded"] == 3 and res["skipped"] == ["CCC"]
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path))
    p = s.load()
    assert {h.symbol: h.adj_qty for h in p.holdings} == {"AAA": 100, "BBB": 250, "DDD": 625}
    assert p.capital_in == 100000.0
    assert p.autopilot is True
    spent = 100 * 250.0 + 250 * 100.0 + 625 * 40.0
    assert p.cash_deployable == pytest.approx(100000.0 - spent)
    txns = s.load_transactions()
    assert len(txns) == 3 and all(t.source == "seed" and t.side == "BUY" for t in txns)
    hist = s.load_value_history()
    assert len(hist) == 1 and hist[0]["total_equity"] == pytest.approx(100000.0)


def test_seed_refuses_non_empty_portfolio(tmp_path):
    seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
         price_lookup=_lookup, on=D)
    with pytest.raises(SystemExit):
        seed("t1", 100000.0, base_dir=str(tmp_path), tickers=TICKERS,
             price_lookup=_lookup, on=D)
