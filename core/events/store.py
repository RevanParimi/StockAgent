"""
The company-event store: market facts, with no user in them.

    data/events/<SYMBOL>.jsonl   one CompanyEvent per line, append-only;
                                 an id (the source item's identity) is stored once
    data/events/state.json       the day's news-query count, and the items the
                                 classifier judged not about the company (kept
                                 events.seen_days days, so they are not asked again)
    data/events/runs.jsonl       one line per feed run: what it used and stored

Nothing here records who holds or watches a stock. Writes take one file lock
(`.lock`); the feed is the only writer and the route only reads. A reader
skips a line it cannot parse, such as a line still being written.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from filelock import FileLock

from backend.shared.schemas.events import CompanyEvent
from core.config import settings
from core.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

# NSE symbols: letters, digits, "&", "-" and "_" (M&M, BAJAJ-AUTO). The symbol
# names a file, so nothing else is accepted.
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&_\-]{0,24}$")


def valid_symbol(symbol) -> bool:
    return isinstance(symbol, str) and bool(_SYMBOL.match(symbol))


class EventStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._dir = Path(base_dir or settings.EVENTS_DATA_DIR)
        self._lock = FileLock(str(self._dir / ".lock"), timeout=60)

    @property
    def base_dir(self) -> Path:
        return self._dir

    def path(self, symbol: str) -> Path:
        if not valid_symbol(symbol):
            raise ValueError(f"not a stock symbol: {symbol!r}")
        return self._dir / f"{symbol}.jsonl"

    # -- events --------------------------------------------------------------

    def load(self, symbol: str) -> list[CompanyEvent]:
        path = self.path(symbol)
        if not path.exists():
            return []
        events, bad = [], 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    events.append(CompanyEvent(**json.loads(line)))
                except (ValueError, TypeError) as exc:
                    bad += 1
                    logger.debug("[events] %s: unreadable line skipped: %s", path.name, exc)
        if bad:
            logger.warning("[events] %s: %d unreadable line(s) skipped", path.name, bad)
        return events

    def known_ids(self, symbol: str) -> set[str]:
        return {e.id for e in self.load(symbol)}

    def append_new(self, symbol: str, events: list[CompanyEvent]) -> list[CompanyEvent]:
        """Append the events whose id is not stored yet; returns those appended."""
        if not events:
            return []
        path = self.path(symbol)
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            known = self.known_ids(symbol)
            new: list[CompanyEvent] = []
            for event in events:
                if event.symbol != symbol:
                    raise ValueError(f"event for {event.symbol} offered to {symbol}'s file")
                if event.id in known:
                    continue
                known.add(event.id)
                new.append(event)
            if new:
                with open(path, "a", encoding="utf-8", newline="\n") as fh:
                    for event in new:
                        fh.write(event.model_dump_json() + "\n")
        return new

    def read(self, symbol: str, since: date | None = None, limit: int = 100) -> list[CompanyEvent]:
        """Newest first. With `since`, only events published on or after that
        IST day; an event without a publication time is never among them."""
        events = self.load(symbol)
        if since is not None:
            day = since.isoformat()
            events = [e for e in events if e.published_day() and e.published_day() >= day]
        events.sort(key=lambda e: (e.published_at is not None, e.published_at or ""), reverse=True)
        return events[:max(0, limit)]

    # -- state ---------------------------------------------------------------

    def load_state(self) -> dict:
        path = self._dir / "state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            logger.warning("[events] %s unreadable, starting empty: %s", path, exc)
            data = {}
        if not isinstance(data, dict):
            data = {}
        queries = data.get("queries") if isinstance(data.get("queries"), dict) else {}
        seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
        return {"queries": {"day": str(queries.get("day") or ""), "used": int(queries.get("used") or 0)},
                "seen": {s: dict(v) for s, v in seen.items() if isinstance(v, dict)}}

    def save_state(self, state: dict, today: date, keep_days: int) -> None:
        """Write the state, dropping seen items older than `keep_days`."""
        cutoff = (today - timedelta(days=max(0, keep_days))).isoformat()
        seen = {}
        for symbol, ids in (state.get("seen") or {}).items():
            kept = {sid: day for sid, day in ids.items() if str(day) >= cutoff}
            if kept:
                seen[symbol] = kept
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            atomic_write_json(self._dir / "state.json",
                              {"queries": state.get("queries") or {}, "seen": seen},
                              indent=1, sort_keys=True)

    def append_run(self, record: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(self._dir / "runs.jsonl", "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def load_runs(self, limit: int = 50) -> list[dict]:
        path = self._dir / "runs.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows
