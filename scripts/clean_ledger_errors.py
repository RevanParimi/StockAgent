"""
scripts/clean_ledger_errors.py
==============================
One-off cleanup for the 2026-07 garbage-learning incident: error strings
("Parse error: Expecting value…", "LLM unavailable: …") were ingested into
LearningLedger miss counters as if they were market factors.

Removes every miss_counter key (and matching miss_events entries) that fails
the same slug validation FeedbackAgent now enforces at ingestion
(feedback_agent.VALID_MISS_FACTOR_RE). Writes a .bak backup next to each
modified ledger.

Usage:
    python scripts/clean_ledger_errors.py            # dry run (default)
    python scripts/clean_ledger_errors.py --apply    # actually rewrite files

Run locally against data/predictions, or on the Railway volume via
`railway run python scripts/clean_ledger_errors.py --apply`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Repo root + src/ on sys.path (mirrors pyproject pythonpath = [".", "src"])
_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.config import settings                                   # noqa: E402
from core.intelligence.rl.agents.feedback_agent import (            # noqa: E402
    VALID_MISS_FACTOR_RE,
)


def clean_ledger_file(path: Path, apply: bool) -> tuple[int, int]:
    """Return (bad_counter_keys_removed, bad_miss_events_removed)."""
    data = json.loads(path.read_text(encoding="utf-8"))

    counter = data.get("miss_counter") or {}
    bad_keys = [k for k in counter if not VALID_MISS_FACTOR_RE.fullmatch(k)]

    events = data.get("miss_events") or {}
    bad_event_keys = [k for k in events if not VALID_MISS_FACTOR_RE.fullmatch(k)]

    if not bad_keys and not bad_event_keys:
        return 0, 0

    for k in bad_keys:
        print(f"    - miss_counter[{k!r}] = {counter[k]}")
    for k in bad_event_keys:
        print(f"    - miss_events[{k!r}] ({len(events[k])} events)")

    if apply:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        for k in bad_keys:
            del counter[k]
        for k in bad_event_keys:
            del events[k]
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return len(bad_keys), len(bad_event_keys)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="rewrite files (default is dry run)")
    ap.add_argument("--data-dir", default=settings.PREDICTION_DATA_DIR,
                    help="prediction data root (default: %(default)s)")
    args = ap.parse_args()

    root = Path(args.data_dir)
    if not root.exists():
        print(f"No prediction data dir at {root} — nothing to do.")
        return 0

    ledgers = sorted(root.rglob("*learning_ledger.json"))
    if not ledgers:
        print(f"No ledger files under {root}.")
        return 0

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] scanning {len(ledgers)} ledger file(s) under {root}\n")

    total_keys = total_events = touched = 0
    for path in ledgers:
        print(f"  {path}")
        nk, ne = clean_ledger_file(path, args.apply)
        if nk or ne:
            touched += 1
        total_keys += nk
        total_events += ne

    verb = "removed" if args.apply else "would remove"
    print(f"\n{mode}: {verb} {total_keys} poisoned counter key(s) and "
          f"{total_events} poisoned event list(s) across {touched} file(s).")
    if not args.apply and (total_keys or total_events):
        print("Re-run with --apply to write changes (backups saved as *.bak).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
