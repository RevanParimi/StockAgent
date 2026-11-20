"""Every deep dive as it was issued, kept for good (PR-017).

The shelf refreshes an idea in place when it is re-dived (`ShelfStore.
apply_redives`: the conviction, verdict and band are overwritten), and the
dive memo (`dives.json`) keeps only each stock's latest dive for
DISCOVERY_REDIVE_AFTER_DAYS. Neither can say what a dive said on its day once a
later one followed, and a dive that was not shelved leaves no record after a
month. The auditor grades every dive at the conviction it was issued with
(`core/audit/idea_lanes.py`), so that record is kept here:

    {DISCOVERY_DATA_DIR}/dives.jsonl, append-only, two kinds of row:

- `"row": "dive"`, one per dive: reference `dive:<dive date>|<symbol>`, the
  conviction, verdict, graph, sector key, close, composite, data gate, entry
  band and invalidation level as the dive returned them, and whether it was a
  re-dive of a shelf idea (`kind`: "redive" | "new");
- `"row": "run"`, one per discovery run that made dives: its day, the screen
  file it read (`screen_date`) and the symbols it dived. The screen lane counts
  a screen candidate as "not dived" only against a run row.

A row is never rewritten. When one reference is written twice (a second run on
the same day), the first row is the one graded (`dive_rows`).

**Recorded at the dive** (`recorded: "at_dive"`) from the first discovery run
after this module was deployed. **Seeded once** (`recorded: "backfill"`), on
the first write, from what the older files kept of each dive as issued:

- the dive memo: every stock's latest dive of the last month (date,
  conviction, verdict, data gate), shelved or not;
- `shelf_events.jsonl`: an `added` event's conviction (the dive that shelved
  the idea) and a `redived` event's new conviction (a re-dive that kept it),
  with the day read in IST from the event's time; the verdict is the memo's
  for the same stock and day, else "" (not recorded);
- the graph and sector of the stock's shelf idea where it is still in
  `shelf.json`, else "" (unknown). A backfill row has no close or band.

A backfilled day gets a run row only when the memo covered it: on or after
the newest memo date less DISCOVERY_REDIVE_AFTER_DAYS. Before that the memo
was pruned, so a dive that was not shelved may be missing, and the screen lane
cannot tell which of that day's candidates were dived.

Example: ABC shelved on 3 Oct at 0.62 (an `added` event), re-dived on 7 Nov at
0.80 (`redived`, "conviction 0.62 -> 0.80"). The seed writes two rows,
`dive:2026-10-03|ABC` at 0.62 and `dive:2026-11-07|ABC` at 0.80; the 3 Oct dive
is graded at 0.62 whatever followed.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from core.config import settings
from core.intelligence.rl.nse_calendar import IST

logger = logging.getLogger(__name__)

AT_DIVE, BACKFILL = "at_dive", "backfill"
SCREEN_LOOKBACK_DAYS = 7          # a run reads the newest screen file within this many days
_ADDED = re.compile(r"conviction=([0-9.]+)")
_REDIVED = re.compile(r"conviction [0-9.]+ -> ([0-9.]+)")


def dive_ref(dive_date: str, symbol: str) -> str:
    return f"dive:{dive_date}|{symbol}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ist_day(ts: str) -> str:
    """The IST calendar day of a UTC ISO timestamp; "" when unreadable."""
    try:
        at = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(IST).date().isoformat()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _dive_row(d, *, kind: str, screen_date: str, at: str) -> dict:
    return {
        "row": "dive", "ref": dive_ref(d.dive_date, d.symbol), "symbol": d.symbol,
        "dive_date": d.dive_date, "conviction": round(float(d.conviction), 4),
        "verdict": str(d.verdict), "graph": d.graph, "sector": d.sector,
        "close": float(d.close), "composite": float(d.composite),
        "data_gate": d.data_gate, "entry_low": float(d.entry_low),
        "entry_high": float(d.entry_high), "invalidation_level": float(d.invalidation_level),
        "market_sector": d.market_sector, "industry": d.industry,
        "kind": kind, "screen_date": screen_date, "recorded": AT_DIVE, "source": "",
        "logged_at": at,
    }


class DiveRecord:
    """The append-only dives.jsonl in the discovery data folder."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or settings.DISCOVERY_DATA_DIR)
        self.path = self._dir / "dives.jsonl"

    # -- reading -------------------------------------------------------------

    def load(self) -> list[dict]:
        return _read_jsonl(self.path)

    def dive_rows(self) -> list[dict]:
        """One row per reference, the first written: what the dive said on
        its day. A dive recorded at the dive wins over a seeded one."""
        first: dict[str, dict] = {}
        for row in self.load():
            if row.get("row") != "dive" or not row.get("ref"):
                continue
            held = first.get(row["ref"])
            if held is None or (held.get("recorded") != AT_DIVE
                                and row.get("recorded") == AT_DIVE):
                first[row["ref"]] = row
        return list(first.values())

    def run_rows(self) -> list[dict]:
        return [r for r in self.load() if r.get("row") == "run" and r.get("run_date")]

    # -- writing -------------------------------------------------------------

    def append_run(self, dives: Iterable, *, on: date, screen_date: str = "",
                   redives: Iterable[str] = ()) -> int:
        """Append one row per dive and one run row. Seeds the file first when
        it does not exist yet (`seed_rows`), so call it BEFORE the run's
        `record_dives` updates the memo and before the shelf writes the
        run's events. Returns the rows written; never raises."""
        dives = list(dives)
        if not dives:
            return 0
        redived = set(redives)
        at = _now()
        rows: list[dict] = []
        try:
            if not self.path.exists():
                rows.extend(self.seed_rows(on=on))
        except Exception as exc:
            logger.warning("[dive_record] seed failed (non-fatal; nothing seeded): %s", exc)
            rows = []
        for d in dives:
            rows.append(_dive_row(d, kind="redive" if d.symbol in redived else "new",
                                  screen_date=screen_date, at=at))
        rows.append({"row": "run", "run_date": on.isoformat(), "screen_date": screen_date,
                     "dives": len(dives), "symbols": sorted({d.symbol for d in dives}),
                     "recorded": AT_DIVE, "logged_at": at})
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, sort_keys=True) + "\n")
        except OSError as exc:
            logger.warning("[dive_record] write failed (non-fatal): %s", exc)
            return 0
        return len(rows)

    # -- the one-time seed -----------------------------------------------------

    def seed_rows(self, *, on: date) -> list[dict]:
        """The backfill rows the first write adds (module docstring). Reads
        the memo, the shelf events and the shelf; writes nothing."""
        memo = self._load_json(self._dir / "dives.json")
        memo = memo if isinstance(memo, dict) else {}
        shelf = self._load_json(self._dir / "shelf.json")
        ideas = {}
        for idea in (shelf.get("ideas") or []) if isinstance(shelf, dict) else []:
            if isinstance(idea, dict) and idea.get("symbol"):
                ideas[str(idea["symbol"])] = idea      # the latest record of the stock
        found: dict[str, dict] = {}

        def put(symbol: str, day: str, conviction, verdict: str, gate: str, source: str):
            if not symbol or not day:
                return
            try:
                conv = round(float(conviction), 4)
                date.fromisoformat(day)
            except (TypeError, ValueError):
                return
            ref = dive_ref(day, symbol)
            if ref in found:
                return
            idea = ideas.get(symbol) or {}
            found[ref] = {
                "row": "dive", "ref": ref, "symbol": symbol, "dive_date": day,
                "conviction": conv, "verdict": verdict, "graph": idea.get("graph", ""),
                "sector": idea.get("sector", ""), "close": None, "composite": None,
                "data_gate": gate, "kind": "", "screen_date": "",
                "recorded": BACKFILL, "source": source, "logged_at": _now(),
            }

        for symbol, rec in sorted(memo.items()):
            if isinstance(rec, dict):
                put(str(symbol), str(rec.get("date") or ""), rec.get("conviction"),
                    str(rec.get("verdict") or ""), str(rec.get("data_gate") or ""), "memo")
        memo_day = {(str(s), str(r.get("date"))): r for s, r in memo.items()
                    if isinstance(r, dict)}
        for event in _read_jsonl(self._dir / "shelf_events.jsonl"):
            kind = event.get("event")
            pattern = _ADDED if kind == "added" else _REDIVED if kind == "redived" else None
            if pattern is None:
                continue
            hit = pattern.search(str(event.get("detail") or ""))
            day = _ist_day(event.get("ts"))
            symbol = str(event.get("symbol") or "")
            if not hit or not day:
                continue
            same = memo_day.get((symbol, day)) or {}
            put(symbol, day, hit.group(1), str(same.get("verdict") or ""),
                str(same.get("data_gate") or ""), f"shelf_event:{kind}")

        rows = sorted(found.values(), key=lambda r: (r["dive_date"], r["symbol"]))
        rows += self._seed_runs(rows, memo, on)
        return rows

    def _seed_runs(self, rows: list[dict], memo: dict, on: date) -> list[dict]:
        days = [str(r.get("date")) for r in memo.values()
                if isinstance(r, dict) and r.get("date")]
        if not days:
            return []
        newest = max(days)
        try:
            covered = (date.fromisoformat(newest)
                       - timedelta(days=max(0, int(settings.DISCOVERY_REDIVE_AFTER_DAYS)))
                       ).isoformat()
        except (TypeError, ValueError):
            return []
        by_day: dict[str, set[str]] = {}
        for r in rows:
            if covered <= r["dive_date"] <= newest:
                by_day.setdefault(r["dive_date"], set()).add(r["symbol"])
        screens = self._screen_dates()
        at = _now()
        return [{"row": "run", "run_date": day, "screen_date": _screen_for(day, screens),
                 "dives": len(symbols), "symbols": sorted(symbols),
                 "recorded": BACKFILL, "logged_at": at}
                for day, symbols in sorted(by_day.items())]

    def _screen_dates(self) -> list[str]:
        folder = self._dir / "screens"
        if not folder.exists():
            return []
        return sorted(p.name[: -len("_screen.json")] for p in folder.glob("*_screen.json"))

    @staticmethod
    def _load_json(path: Path):
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("[dive_record] %s unreadable: %s", path.name, exc)
            return {}


def _screen_for(day: str, screen_dates: list[str]) -> str:
    """The newest screen file dated on or before `day`, within the lookback."""
    try:
        floor = (date.fromisoformat(day) - timedelta(days=SCREEN_LOOKBACK_DAYS)).isoformat()
    except ValueError:
        return ""
    hits = [s for s in screen_dates if floor <= s <= day]
    return max(hits) if hits else ""


def preview(base_dir: str | None = None, on: date | None = None) -> dict:
    """What the first write would seed, without writing (read-only)."""
    record = DiveRecord(base_dir)
    rows = record.seed_rows(on=on or date.today())
    dives = [r for r in rows if r["row"] == "dive"]
    runs = [r for r in rows if r["row"] == "run"]
    return {"file_exists": record.path.exists(), "dives": len(dives),
            "with_verdict": sum(1 for r in dives if r["verdict"]),
            "by_source": {s: sum(1 for r in dives if r["source"] == s)
                          for s in sorted({r["source"] for r in dives})},
            "first_day": min((r["dive_date"] for r in dives), default=None),
            "runs_complete": [r["run_date"] for r in runs]}


if __name__ == "__main__":       # python -m core.discovery.dive_record
    print(json.dumps(preview(), indent=1))
