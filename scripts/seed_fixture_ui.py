"""Seed a data dir with fixture brief/digest/weekly for local UI work.

Writes SAVED artefacts only — nothing is rebuilt, so no LLM or Serper call is
made (spec 2026-07-31 D8; the Serper counter is under validation). Usage:

    python scripts/seed_fixture_ui.py --data-dir .uidev-data
    PORTFOLIO_DATA_DIR=.uidev-data python -m uvicorn services.api.server:app --port 8001
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root + src/ on sys.path (mirrors pyproject pythonpath = [".", "src"];
# needed because this script is invoked directly, not via pytest).
_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_FIXTURE = _ROOT / "tests" / "fixtures" / "ui_brief_fixture.json"

_DIGEST = {
    "date": "2026-07-30", "user_id": "primary",
    "portfolio_value": 482300.0, "cost_basis": 453200.0, "total_pnl_pct": 6.4,
    "holdings": [
        {"symbol": "MARUTI", "verdict": "TRIM", "close": 12840.0, "pnl_pct": 4.2,
         "reason": "Thesis weakened — margin guidance cut twice.", "notes": []},
        {"symbol": "TATAMOTORS", "verdict": "EXIT", "close": 642.0, "pnl_pct": -8.7,
         "reason": "Stop breached on the JLR demand warning.", "notes": []},
        {"symbol": "M&M", "verdict": "HOLD", "close": 3120.0, "pnl_pct": 21.3,
         "reason": "Thesis intact.", "notes": []},
    ],
    "escalations": ["TATAMOTORS"],
}

_WEEKLY = {
    "date": "2026-07-27", "user_id": "primary",
    "headline": "Concentration crept up in autos; one laggard is close to a switch.",
    "allocation": [{"sector": "AUTOMOBILE", "weight_pct": 64.2},
                   {"sector": "BFSI", "weight_pct": 35.8}],
    "concentration_flags": ["AUTOMOBILE"],
    "laggards": [{"symbol": "TATAMOTORS", "pnl_pct": -8.7}],
    "switch_candidates": [{"sector": "AUTOMOBILE", "symbol": "BAJAJ-AUTO", "conviction": 0.72}],
    "switch_suggestions": [{"symbol": "TATAMOTORS", "switch_candidate": "BAJAJ-AUTO"}],
    "scoreboard": {"checked": 12, "correct": 8},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".uidev-data")
    args = ap.parse_args()

    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id="primary", base_dir=args.data_dir)
    store.save_brief(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    store.save_digest(_DIGEST)
    store.save_weekly(_WEEKLY)
    print(f"[seed] brief + digest + weekly written under {args.data_dir}")


if __name__ == "__main__":
    main()
