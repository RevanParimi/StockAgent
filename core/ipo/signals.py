"""PI Prospect P2 — the capture ledger (design §5 P2).

One row per (IPO, refresh pass) recording what NSE reported at that moment.
Perishable by nature: the bid ladder of an issue that closed last Tuesday is
not retrievable in its intermediate states, so a pass that is not captured is
gone for good.

Deliberately dumb, exactly like the P1 spine: captured facts only, no ratio,
delta or index anywhere in the file. Everything derived lives in velocity.py
and is recomputed on read, so a change to the maths never requires rewriting
history.

APPEND-ONLY, with one exception. `prune()` is the only writer that rewrites
the file, it is bounded by age, and its no-op case is asserted in the tests —
because the one way to lose this data is a rewrite path that misbehaves.

`append()` applies TWO independent dedup rules, either of which can veto a
write:

  1. Hour dedup — same (symbol, hour) already stored. A manual re-run of the
     refresh inside one window must not double-count demand.
  2. Content dedup — the newest already-stored row for this symbol carries
     identical `combined`/`nse_only`/`cutoff_share` to the incoming snapshot.
     An issue that has CLOSED but not yet LISTED keeps its bid ladder on the
     NSE cache row, and NSE keeps such issues in its feed for days. Without
     this rule a daily refresh would append byte-identical rows for days,
     and a later "change since last reading" derivation would compute a
     meaningless 0.0 forever instead of recognising there simply was no new
     reading.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IpoSignalSnapshot(BaseModel):
    symbol: str
    captured_at: str                    # ISO-8601, UTC
    state: str = "unknown"              # core.ipo.calendar.issue_state output
    issue_start: str = ""
    issue_end: str = ""

    # Both ladders, named for what they are. `combined` is all-exchange and is
    # the figure the market quotes; `nse_only` under-reports. See spec §11.4.
    combined: dict[str, float | None] = Field(default_factory=dict)
    nse_only: dict[str, float | None] = Field(default_factory=dict)
    cutoff_share: float | None = None

    # Populated only when a dedicated Serper key exists (Task 8). None here
    # means "not collected", never "no premium".
    gmp: float | None = None
    gmp_pct: float | None = None
    gmp_sources: int = 0
    news_volume: int | None = None


def _as_utc(stamp: str) -> datetime | None:
    """Naive timestamps are read as UTC rather than rejected — an unparseable
    row must not be able to stall a prune or crash a read."""
    try:
        dt = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class IpoSignalStore:
    """JSONL at <base_dir>/ipo_signals.jsonl."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or "data/ipo")
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "ipo_signals.jsonl"

    @staticmethod
    def _key(snap: IpoSignalSnapshot) -> tuple[str, str]:
        # Hour resolution: the refresh runs twice a day, so two rows inside one
        # hour means the job was re-run by hand, not that demand moved.
        return (snap.symbol, snap.captured_at[:13])

    def append(self, snap: IpoSignalSnapshot) -> bool:
        """True if written, False on either dedup rule (see module docstring):
        same (symbol, hour) already stored, or the newest already-stored row
        for this symbol carries identical combined/nse_only/cutoff_share."""
        rows = self.load_all()
        if self._key(snap) in {self._key(r) for r in rows}:
            return False
        symbol_rows = [r for r in rows if r.symbol == snap.symbol]
        if symbol_rows:
            newest = symbol_rows[-1]
            if (newest.combined == snap.combined
                    and newest.nse_only == snap.nse_only
                    and newest.cutoff_share == snap.cutoff_share):
                return False
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(snap.model_dump_json() + "\n")
        return True

    def load_all(self) -> list[IpoSignalSnapshot]:
        if not self.path.exists():
            return []
        out: list[IpoSignalSnapshot] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(IpoSignalSnapshot(**json.loads(line)))
            except Exception:
                continue            # a corrupt line must never break a read
        return out

    def load_symbol(self, symbol: str) -> list[IpoSignalSnapshot]:
        rows = [r for r in self.load_all() if r.symbol == symbol]
        return sorted(rows, key=lambda r: r.captured_at)

    def prune(self, older_than_days: int, now: datetime | None = None) -> int:
        """Drop rows older than the retention window. Returns rows removed.

        Rewrites via .tmp + replace(); a row whose timestamp will not parse is
        KEPT, because deleting data we cannot date is the worse error.

        older_than_days <= 0 is a no-op, not "prune everything". 0 is the
        near-universal config convention for "disabled", and a caller setting
        it to mean that must not have the entire ledger wiped out from under
        them: cutoff = now - 0 days = now would empty `keep` outright, and a
        negative value is worse still. This runs twice daily in production
        immediately after capture, so silently destroying the ledger here is
        the single worst thing this function could do.
        """
        if older_than_days <= 0:
            return 0
        rows = self.load_all()
        if not rows:
            return 0
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=older_than_days)
        keep = [r for r in rows
                if (_as_utc(r.captured_at) or now) >= cutoff]
        removed = len(rows) - len(keep)
        if removed == 0:
            return 0
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(r.model_dump_json() + "\n" for r in keep),
                       encoding="utf-8")
        tmp.replace(self.path)
        logger.info("[ipo_signals] pruned %d row(s) older than %dd",
                    removed, older_than_days)
        return removed
