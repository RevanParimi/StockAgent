"""
Compass Autopilot — one-time portfolio seeding (spec §5).

Seeds the managed tickers as equal-weight virtual holdings and turns
autopilot on for the user. Idempotent: refuses to run when the user already
has holdings or transactions.

Prod (Railway):  railway ssh "python scripts/seed_autopilot.py --user primary --pot 1000000"
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Repo root + src/ on sys.path (mirrors pyproject pythonpath = [".", "src"])
_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.shared.schemas.portfolio import Holding, TransactionRecord   # noqa: E402
from core.portfolio.autopilot import make_txn_id, record_value_point      # noqa: E402
from core.portfolio.pricing import close_on                               # noqa: E402
from core.portfolio.store import PortfolioStore                           # noqa: E402

logger = logging.getLogger(__name__)


def seed(user_id: str, pot: float, base_dir: str | None = None,
         tickers: list[dict] | None = None, price_lookup=None,
         on: date | None = None) -> dict:
    on = on or date.today()
    price_lookup = price_lookup or close_on
    if tickers is None:
        from services.api.log_buffer import get_active_tickers_with_sector
        tickers = get_active_tickers_with_sector()
    if not tickers:
        raise SystemExit("no managed tickers found — aborting")

    store = PortfolioStore(user_id=user_id, base_dir=base_dir)
    p = store.load()
    if p.holdings or store.load_transactions(limit=1):
        raise SystemExit(
            f"user {user_id} already has holdings/transactions — refusing to seed")

    budget = pot / len(tickers)
    day = on.isoformat()
    seeded, skipped, spent = 0, [], 0.0
    for t in tickers:
        sym = t["sym"].strip().upper()
        sector = (t.get("sector") or "generic").strip().lower()
        try:
            price = float(price_lookup(sym, on))
        except Exception as exc:
            logger.warning("[seed] %s skipped: no price (%s)", sym, exc)
            skipped.append(sym)
            continue
        qty = float(math.floor(budget / price))
        if qty < 1:
            logger.warning("[seed] %s skipped: budget %.2f < 1 share @ %.2f",
                           sym, budget, price)
            skipped.append(sym)
            continue
        p.holdings.append(Holding(
            symbol=sym, sector=sector, qty=qty, avg_buy_price=price,
            adj_avg_price=price, adj_qty=qty, buy_date=day))
        value = round(qty * price, 2)
        cash_before = round(pot - spent, 2)
        spent += value
        store.append_transaction(TransactionRecord(
            txn_id=make_txn_id(user_id, day, sym, "BUY", "seed"),
            date=day, ts=datetime.now(timezone.utc).isoformat(),
            user_id=user_id, symbol=sym, side="BUY", qty=qty, price=price,
            value=value, cash_before=cash_before,
            cash_after=round(pot - spent, 2), holding_qty_after=qty,
            source="seed", note=f"seed {len(tickers)} tickers @ ₹{budget:,.0f} each"))
        seeded += 1

    p.capital_in = float(pot)
    p.cash_deployable = round(pot - spent, 2)
    p.autopilot = True
    store.save(p)
    closes = {h.symbol: h.adj_avg_price for h in p.holdings}
    record_value_point(store, p, closes, on)
    return {"seeded": seeded, "skipped": skipped,
            "cash": p.cash_deployable, "capital_in": p.capital_in}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Seed the autopilot virtual portfolio")
    ap.add_argument("--user", default="primary")
    ap.add_argument("--pot", type=float, default=1_000_000.0)
    ap.add_argument("--base-dir", default=None)
    args = ap.parse_args()
    result = seed(args.user, args.pot, base_dir=args.base_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
