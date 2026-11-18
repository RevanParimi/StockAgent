"""PR-005: an investment case for each holding bought before cases existed.

Run once, as an owner-approved step. Each holding without a case gets one
built from the latest inputs (the newest actionable analysis, the shelf idea
decided before now, the dossier's dated guidance, the company's events),
marked `written: after_purchase` so nobody mistakes it for the original
reason. Its invalidation price follows the same rule as a case written at
purchase: the shelf idea's level in the buy day's rupees, used only inside
the window of the stop and the noise line on the buy day.

    python -B scripts/backfill_cases.py            # dry run: which holdings would get one
    python -B scripts/backfill_cases.py --apply    # write them (one model call each)

A holding with a case is left alone, so a second run writes nothing. Prints
per user the symbol, its buy date and what happened; no case text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the cases (default: dry run)")
    args = parser.parse_args(argv)

    from core.discovery.shelf import ShelfStore
    from core.portfolio.cases import backfill
    from core.portfolio.store import PortfolioStore, active_user_ids

    ideas = list(ShelfStore().load().ideas)
    total = 0
    for user_id in active_user_ids():
        portfolio = PortfolioStore(user_id=user_id).load()
        rows = backfill(user_id, portfolio, ideas=ideas, apply=args.apply)
        print(f"{user_id}: {len(rows)} holding(s)")
        for row in rows:
            print(f"  {row['symbol']:<14} bought {row['opened_on']}  {row['action']}")
        total += len(rows)
    print(f"{'applied' if args.apply else 'dry run'}: {total} holding(s) read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
