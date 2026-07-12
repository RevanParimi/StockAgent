# tests/unit/test_autopilot_isolation.py
"""Autopilot must never touch RL paper-lane or PredictionStore paths
(spec §8 isolation invariant, mirrors Phase B paper isolation)."""
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)

import pytest


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Wave 1 (AUD-044): executor date guards compare against IST-today;
    freeze it so these tests are calendar-independent."""
    import core.portfolio.autopilot as _ap
    monkeypatch.setattr(_ap, "_today_ist", lambda: D)


def test_executor_writes_stay_inside_user_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                     # any stray relative write lands here
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path / "portfolio"))
    p = s.load()
    p.holdings = [Holding(symbol="MARUTI", sector="automobile", qty=10,
                          avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                          buy_date="2026-06-01")]
    p.cash_deployable, p.capital_in, p.autopilot = 50000.0, 100000.0, True
    s.save(p)
    advice = [AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                           verdict="TRIM", close=110.0, unrealised_pnl_pct=10.0,
                           stop_pct=8.0, rationale_hash="abc")]
    execute_advice(s, s.load(), advice, {"MARUTI": 110.0}, D)
    created = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert created == {"portfolio"}                 # nothing outside the user store
    assert not (tmp_path / "data").exists()         # no data/rl/paper, no predictions


@patch("core.portfolio.autopilot.promote_symbol", return_value={"status": "ok"})
@patch("core.portfolio.autopilot.close_on", return_value=200.0)
def test_executor_buy_paths_stay_inside_user_dir(mock_close, mock_promote,
                                                 tmp_path, monkeypatch):
    """ADD + SWITCH buy legs must also write only inside the user store.
    The SWITCH promotion side-effect (data/managed_tickers.json via
    promote_symbol) is DESIGNED behavior, so it is mocked — the invariant
    covers every other write the buy paths make."""
    monkeypatch.chdir(tmp_path)                     # any stray relative write lands here
    s = PortfolioStore(user_id="t1", base_dir=str(tmp_path / "portfolio"))
    p = s.load()
    p.holdings = [
        Holding(symbol="MARUTI", sector="automobile", qty=10,
                avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=10,
                buy_date="2026-06-01"),
        Holding(symbol="TATAMOTORS", sector="automobile", qty=100,
                avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=100,
                buy_date="2026-06-01"),
    ]
    p.cash_deployable, p.capital_in, p.autopilot = 50000.0, 100000.0, True
    s.save(p)
    advice = [
        AdviceRecord(date=D.isoformat(), user_id="t1", symbol="MARUTI",
                     verdict="ADD", close=110.0, unrealised_pnl_pct=10.0,
                     stop_pct=8.0, confidence=0.8, rationale_hash="add1"),
        AdviceRecord(date=D.isoformat(), user_id="t1", symbol="TATAMOTORS",
                     verdict="SWITCH", close=110.0, unrealised_pnl_pct=-9.0,
                     stop_pct=8.0, confidence=0.4, switch_candidate="LODHA",
                     rationale_hash="sw1"),
    ]
    txns = execute_advice(s, s.load(), advice,
                          {"MARUTI": 110.0, "TATAMOTORS": 110.0}, D,
                          sector_lookup={"LODHA": "realty"})
    buys = [t for t in txns if t.side == "BUY"]
    assert {t.symbol for t in buys} == {"LODHA", "MARUTI"}  # both buy paths really ran
    mock_promote.assert_called_once_with("LODHA", "realty", origin="held")
    created = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert created == {"portfolio"}                 # nothing outside the user store
    assert not (tmp_path / "data").exists()         # no data/rl/paper, no predictions
