"""Move the long notes of accepted (done) stories out of STATE.json, word for word.

AGENTS.md, "Continuing the active PI", step 5 (owner, 19 Nov 2026): when a story is
accepted, STATE.json keeps its card and the rest of its entry moves to
STATE-tasks-archive.json under its id. The card is what a session needs to pick the next
story and see what is still open: identity and status, dependencies, links (receipts,
manifests, commits, revisions, origin and routed findings), owner decisions and the
production verification, which stays until it passes.

Only done tasks change; every other byte of STATE.json is kept as it is. The script checks
itself before writing: each task's card plus its archived fields equals the original entry.

    python scripts/docs/archive_done_tasks.py          # move, then verify
    python scripts/docs/archive_done_tasks.py --check  # report what would move; write nothing
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PI_DIR = ROOT / "docs/planning/PI-2026-09"
STATE = PI_DIR / "STATE.json"
ARCHIVE = PI_DIR / "STATE-tasks-archive.json"
ARCHIVE_REF = "docs/planning/PI-2026-09/STATE-tasks-archive.json"
POINTER = "archived_detail"

CARD_FIELDS = {
    "id", "title", "story", "sprint", "points", "priority", "scope", "status",
    "depends_on", "blocked_reason", "lane", "review_lane", "branch",
    "origin", "evidence", "manifest", "commit", "commits", "committed",
    "production_verification", "production_probe", "deployment", "rollout",
    "docs", "documentation", POINTER,
}
CARD_PREFIXES = ("routed", "owner_")
CARD_SUFFIXES = (
    "_receipt", "_receipts", "_receipt_2", "_manifest", "_commit", "_revision",
    "_sha256", "_baseline", "_evidence", "follow_ups", "followups",
)

ARCHIVE_ABOUT = (
    "Archive of STATE.json task entries (PI-2026-09). When a story is accepted (done), the "
    "fields outside its card move here word for word, never rewritten, under its id; the card "
    "in STATE.json points here with 'archived_detail'. Written by "
    "scripts/docs/archive_done_tasks.py (AGENTS.md, step 5)."
)


def is_card_field(name: str) -> bool:
    return name in CARD_FIELDS or name.startswith(CARD_PREFIXES) or name.endswith(CARD_SUFFIXES)


def task_spans(raw: str) -> list[tuple[int, int, dict]]:
    """Return (start, end, task) for each element of the top-level "tasks" array."""
    decoder = json.JSONDecoder()
    key = raw.index('\n  "tasks": [')
    pos = raw.index("[", key) + 1
    spans = []
    while True:
        while raw[pos] in " \t\r\n,":
            pos += 1
        if raw[pos] == "]":
            return spans
        task, end = decoder.raw_decode(raw, pos)
        spans.append((pos, end, task))
        pos = end


def render_card(card: dict) -> str:
    fields = ",\n".join(
        f"      {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
        for k, v in card.items()
    )
    return "{\n" + fields + "\n    }"


def split_task(task: dict) -> tuple[dict, dict]:
    card = {k: v for k, v in task.items() if is_card_field(k)}
    moved = {k: v for k, v in task.items() if not is_card_field(k)}
    if moved:
        card[POINTER] = ARCHIVE_REF
    return card, moved


def load_archive() -> dict:
    if ARCHIVE.exists():
        return json.loads(ARCHIVE.read_text(encoding="utf-8"))
    return {"about": ARCHIVE_ABOUT, "tasks": []}


def archived_fields(archive: dict, task_id: str) -> dict:
    """Every field already archived for a task, across its entries."""
    merged: dict = {}
    for entry in archive["tasks"]:
        if entry["id"] == task_id:
            merged.update(entry["fields"])
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()

    raw = STATE.read_text(encoding="utf-8")
    before = json.loads(raw)
    archive = load_archive()
    today = dt.date.today().isoformat()

    pieces, cursor, moved_now = [], 0, {}
    for start, end, task in task_spans(raw):
        if task.get("status") != "done":
            continue
        card, moved = split_task(task)
        if not moved:
            continue
        overlap = set(moved) & set(archived_fields(archive, task["id"]))
        if overlap:
            print(f"{task['id']}: {sorted(overlap)} already archived; resolve by hand", file=sys.stderr)
            return 1
        pieces += [raw[cursor:start], render_card(card)]
        cursor = end
        archive["tasks"].append({"id": task["id"], "moved": today, "fields": moved})
        moved_now[task["id"]] = moved
    new_raw = "".join(pieces) + raw[cursor:]

    after = json.loads(new_raw)
    errors = verify(before, after, moved_now)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(json.dumps({
        "moved_tasks": len(moved_now),
        "ids": list(moved_now),
        "state_bytes": [len(raw.encode()), len(new_raw.encode())],
        "written": not args.check,
    }, indent=2))
    if not args.check and moved_now:
        STATE.write_text(new_raw, encoding="utf-8")
        ARCHIVE.write_text(json.dumps(archive, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def verify(before: dict, after: dict, moved_now: dict[str, dict]) -> list[str]:
    errors = []
    if {k: v for k, v in before.items() if k != "tasks"} != {k: v for k, v in after.items() if k != "tasks"}:
        errors.append("a top-level field other than tasks changed")
    old, new = before["tasks"], after["tasks"]
    if [t["id"] for t in old] != [t["id"] for t in new]:
        errors.append("task ids or their order changed")
        return errors
    for o, n in zip(old, new):
        if o["id"] in moved_now:
            rebuilt = {k: v for k, v in n.items() if k != POINTER}
            rebuilt.update(moved_now[o["id"]])
            if POINTER in o:
                rebuilt[POINTER] = o[POINTER]
            if rebuilt != o:
                errors.append(f"{o['id']}: card plus archive differs from the original entry")
        elif o != n:
            errors.append(f"{o['id']}: changed without being archived")
        for field in ("status", "depends_on", "production_verification", "scope", "title"):
            if o.get(field) != n.get(field):
                errors.append(f"{o['id']}: {field} changed")
    return errors

if __name__ == "__main__":
    sys.exit(main())
