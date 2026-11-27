"""
scripts/lenses/coverage_report.py — which Yahoo industries the general path's dives had,
and how many of them the committed lenses cover (PR-032). Read-only.

The card's rule for the first lenses: write them until at least 80% of the last
8 weeks' general-path deep dives are covered. This read says whether the
committed set does, and names the industries still without a lens, most dives
first. It writes nothing.

    railway ssh "cd /app && python -B scripts/lenses/coverage_report.py"

**Which dives**, deduplicated by (symbol, day), dived in the last `--weeks` (8):

- `dives.jsonl` dive rows (PR-017), with their own graph and Yahoo industry;
- `shelf_events.jsonl` "added" and "redived" events, dated in IST;
- the dive memo `dives.json` (each stock's latest dive of the last month).

**The graph** is the row's, else the stock's shelf idea's; a dive whose graph
is unknown is counted apart, never as general-path. **The industry** is the
row's, else the shelf idea's, else the peers step's cached profile
(`data/peer_profiles.json`, the label the bundle itself reads); none of them
is "no label".
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TARGET = 0.80
_IST = timedelta(hours=5, minutes=30)


def _jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ist_day(ts: str) -> str:
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is not None:
        when = when.astimezone(timezone(_IST))
    return when.date().isoformat()


def gather(base_dir: Path, today: date, weeks: int = 8,
           profiles_path: Path | None = None) -> list[dict]:
    """The dives of the last `weeks` weeks: {symbol, dive_date, graph,
    industry, source}, one per (symbol, day)."""
    since = (today - timedelta(weeks=weeks)).isoformat()
    shelf = _json(base_dir / "shelf.json") or {}
    ideas = {}
    for idea in (shelf.get("ideas") or []) if isinstance(shelf, dict) else []:
        if isinstance(idea, dict) and idea.get("symbol"):
            ideas[str(idea["symbol"]).upper()] = idea
    profiles = {}
    raw_profiles = _json(profiles_path) if profiles_path else None
    if isinstance(raw_profiles, dict) and isinstance(raw_profiles.get("profiles"), dict):
        profiles = raw_profiles["profiles"]

    found: dict[tuple[str, str], dict] = {}

    def add(symbol, day, graph, industry, source):
        symbol = str(symbol or "").strip().upper()
        day = str(day or "")[:10]
        if not symbol or not day or day < since or day > today.isoformat():
            return
        key = (symbol, day)
        if key in found:
            row = found[key]
            row["graph"] = row["graph"] or str(graph or "")
            row["industry"] = row["industry"] or str(industry or "")
            return
        found[key] = {"symbol": symbol, "dive_date": day, "graph": str(graph or ""),
                      "industry": str(industry or "").strip(), "source": source}

    for row in _jsonl(base_dir / "dives.jsonl"):
        if row.get("row") == "dive":
            add(row.get("symbol"), row.get("dive_date"), row.get("graph"),
                row.get("industry"), "dives.jsonl")
    for event in _jsonl(base_dir / "shelf_events.jsonl"):
        if event.get("event") in ("added", "redived"):
            add(event.get("symbol"), _ist_day(event.get("ts", "")), "", "", "shelf_events")
    memo = _json(base_dir / "dives.json")
    if isinstance(memo, dict):
        for symbol, rec in memo.items():
            if isinstance(rec, dict):
                add(symbol, rec.get("date"), "", "", "dives.json")

    for row in found.values():
        idea = ideas.get(row["symbol"]) or {}
        row["graph"] = row["graph"] or str(idea.get("graph") or "")
        if not row["industry"]:
            row["industry"] = str(idea.get("industry") or "").strip()
        if not row["industry"]:
            profile = profiles.get(f"{row['symbol']}.NS") or {}
            row["industry"] = str(profile.get("industry") or "").strip()
    return sorted(found.values(), key=lambda r: (r["dive_date"], r["symbol"]))


def report(dives: list[dict], lens_set) -> dict:
    """Coverage of the general-path dives by `lens_set` (lenses.LensSet)."""
    general = [d for d in dives if d.get("graph") == "generic"]
    labels = Counter(d["industry"] or "" for d in general)
    by_label = []
    covered = 0
    for label, n in sorted(labels.items(), key=lambda kv: (-kv[1], kv[0])):
        choice = lens_set.lens_for(label)
        by_label.append({"industry": label or "(no label)", "dives": n, "lens": choice.record})
        if choice.kind == "lens":
            covered += n
    with_label = sum(n for label, n in labels.items() if label)
    share = covered / len(general) if general else None
    return {
        "dives": len(dives), "general_path": len(general),
        "graph_unknown": sum(1 for d in dives if not d.get("graph")),
        "native": sum(1 for d in dives if d.get("graph") == "native"),
        "with_label": with_label, "covered": covered, "share": share,
        "passes": share is not None and share >= TARGET,
        "by_label": by_label,
    }


def render(rep: dict, since: str, weeks: int) -> str:
    lines = [f"PR-032 lens coverage: general-path deep dives since {since} ({weeks} weeks)",
             f"dives {rep['dives']}: general path {rep['general_path']}, sector paths "
             f"{rep['native']}, graph unknown {rep['graph_unknown']} (not counted)"]
    if not rep["general_path"]:
        lines.append("no general-path dives: nothing to judge")
        return "\n".join(lines)
    share = rep["share"]
    lines.append(f"covered by a lens: {rep['covered']} of {rep['general_path']} "
                 f"({share:.0%}); with a Yahoo label {rep['with_label']}; "
                 f"target {TARGET:.0%}: {'met' if rep['passes'] else 'NOT met'}"
                 + ("" if rep["general_path"] >= 30 else " (under 30 dives: too few to judge)"))
    lines.append("industry | dives | lens")
    for row in rep["by_label"]:
        lines.append(f"{row['industry']} | {row['dives']} | {row['lens']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from core.config import settings
    from services.data.context.lenses import load_lenses
    from services.data.context.peers import PROFILE_PATH

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--weeks", type=int, default=8)
    ap.add_argument("--base-dir", default=None, help="the discovery data folder")
    ap.add_argument("--today", default=None, help="ISO date; default today")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON too")
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    base = Path(args.base_dir or settings.DISCOVERY_DATA_DIR)
    dives = gather(base, today, args.weeks, profiles_path=PROFILE_PATH)
    rep = report(dives, load_lenses())
    print(render(rep, (today - timedelta(weeks=args.weeks)).isoformat(), args.weeks))
    if args.json:
        print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
