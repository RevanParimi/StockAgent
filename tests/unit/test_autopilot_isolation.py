# tests/unit/test_autopilot_isolation.py
"""Autopilot must never touch RL paper-lane or PredictionStore paths
(spec §8 isolation invariant, mirrors Phase B paper isolation)."""
from datetime import date
from pathlib import Path

from backend.shared.schemas.portfolio import AdviceRecord, Holding
from core.portfolio.autopilot import execute_advice
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 13)


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
