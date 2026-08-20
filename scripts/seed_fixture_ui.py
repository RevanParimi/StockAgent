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


# Alerts tab fixtures (2026-08-20). Deliberately mixed: two rows carrying the
# structured card fields and one legacy row with `message` only, because the
# renderer has to keep both readable — every alert already in the sent-log
# predates the fields and must not regress to a wall of text.
_ALERTS = [
    {"date": "2026-08-19", "kind": "watchdog_ipo_signals_accruing_resolved",
     "symbol": "", "severity": "info", "user_id": "primary", "delivered": True,
     "title": "IPO capture ledger is accruing snapshots",
     "headline": "Now satisfied — closing.",
     "status": "Capture ledger has snapshots for all 4 open issue(s).",
     "next_step": "",
     "docs": "docs/superpowers/specs/2026-08-11-ipo-intelligence-design.md",
     "message": "[watchdog] IPO capture ledger is accruing snapshots\n\n"
                "Now satisfied — closing.\n\n"
                "Status: Capture ledger has snapshots for all 4 open issue(s)."},
    {"date": "2026-08-19", "kind": "watchdog_atlas_c11_cutover_info",
     "symbol": "", "severity": "info", "user_id": "primary", "delivered": True,
     "title": "Atlas C11 live cutover",
     "headline": "Comes due on 2026-08-22 (3 day(s) away).",
     "status": "ETL already run and VALIDATED by the watchdog at "
               "2026-08-15T06:30:00+05:30. Ready to flip — the flag is still off.",
     "next_step": "Set atlas.enabled: true in config.yaml and push (Railway NOT "
                  "needed — the env var is only an override and prod does not "
                  "set it).\n\nThen watch the next trading day: 16:30 autopilot "
                  "and 08:50 brief must fan out to exactly ['primary'], with no "
                  "SQLITE_BUSY. Rollback is the same edit in reverse.",
     "docs": "docs/superpowers/plans/2026-07-26-atlas-user-data-program.md",
     "message": "[watchdog] Atlas C11 live cutover\n\nComes due on 2026-08-22."},
    {"date": "2026-08-18", "kind": "advisor_exit", "symbol": "TATAMOTORS",
     "severity": "critical", "user_id": "primary", "delivered": True,
     "message": "Stop breached on the JLR demand warning.\n"
                "Unrealised -8.7% against a 6.0% ATR stop.\n"
                "Thesis review: broken."},
]


def _seed_alerts(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in _ALERTS:
            fh.write(json.dumps(rec) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".uidev-data")
    ap.add_argument("--with-alerts", action="store_true",
                    help="also OVERWRITE the configured delivery sent-log with "
                         "alert fixtures (delivery.data_dir is not env-"
                         "overridable, so this writes where the server reads)")
    args = ap.parse_args()

    from core.portfolio.store import PortfolioStore
    store = PortfolioStore(user_id="primary", base_dir=args.data_dir)
    store.save_brief(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    store.save_digest(_DIGEST)
    store.save_weekly(_WEEKLY)
    print(f"[seed] brief + digest + weekly written under {args.data_dir}")

    if args.with_alerts:
        from core.config import settings
        target = Path(settings.DELIVERY_DATA_DIR) / "alerts_sent.jsonl"
        _seed_alerts(target)
        print(f"[seed] {len(_ALERTS)} alert fixture(s) written to {target}")


if __name__ == "__main__":
    main()
