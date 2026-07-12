"""Audit Wave 1 (AUD-001) — cross-process file locking for portfolio RMW."""
import multiprocessing as mp

from backend.shared.schemas.portfolio import Holding
from core.portfolio.store import PortfolioStore


def _h(sym="MARUTI", qty=10.0):
    return Holding(symbol=sym, sector="automobile", qty=qty, avg_buy_price=100.0,
                   adj_avg_price=100.0, adj_qty=qty, buy_date="2026-07-01")


def test_locked_is_reentrant(tmp_path):
    s = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    with s.locked():
        with s.locked():            # same instance: must not deadlock
            s.add_holding(_h())     # internal lock: must not deadlock
    assert s.load().holdings[0].symbol == "MARUTI"


def _worker(base_dir: str, n: int) -> None:
    s = PortfolioStore(user_id="u1", base_dir=base_dir)
    for i in range(n):
        s.add_holding(_h(sym=f"SYM{i}", qty=1.0))


def test_cross_process_add_holding_is_atomic(tmp_path):
    procs = [mp.Process(target=_worker, args=(str(tmp_path), 20)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    p = PortfolioStore(user_id="u1", base_dir=str(tmp_path)).load()
    # 2 procs × 20 adds of qty 1 across SYM0..SYM19 → each symbol merged to qty 2
    assert {h.symbol: h.qty for h in p.holdings} == {f"SYM{i}": 2.0 for i in range(20)}
