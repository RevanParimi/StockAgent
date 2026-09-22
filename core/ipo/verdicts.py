"""PI Prospect P3 — the verdict store (plan 2026-09-21 / IPO-3d).

JSONL at `data/ipo/ipo_verdicts.jsonl`, keyed `(symbol, close_date)`. It is a
WRITE-ONLY store in the product sense: nothing outside the tests and the
watchdog may read it until `IPO-5b` passes its gate. A verdict that no one can
see is the whole point of Sprint 3 — the model has to earn its surface on
forward rows, and this file is where those rows accrue.

Why the close date is part of the key. Close dates get extended, and the
extension is not a correction — it is a new book, a new final demand, a new
verdict. So an extended issue writes a SECOND row rather than overwriting the
first, and when the forward hit-rate is computed both attempts are visible.
Keying on the symbol alone would silently discard the earlier read.

What a row carries, and why it is more than the verdict. Every anchor in this
PI is provisional: `demand` is fitted on one regime, and every Substance
anchor is UNFITTED outright. The day an anchor moves, the question asked of
these rows is "what would this verdict have been under the new anchors?" —
which is answerable only if the raw FEATURES were kept, not just the indices
they produced. So each row stores the whole `HypeReading` and
`SubstanceReading` beside the verdict. The anchors in force are deliberately
NOT copied in: they live in `config.yaml`, which is version-controlled and
dated at the block, and duplicating them per row would create a second source
of truth that drifts.

Append-only, with the one content-dedup rule this codebase already uses on the
capture ledger (`signals.py`): a re-run that reproduces the stored row exactly
does not write a second copy. Anything that changed — the book moved, research
finally corroborated, or the issue crossed from `open` to `closed` and the lean
became admissible evidence — is a genuinely new reading and is appended.
Readers take the newest row per key.

`prune()` is the only writer that rewrites the file, and it goes through
`guard_lossless_rewrite` for the reason that module documents: read tolerance
plus a rewrite equals silent permanent deletion.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from core.ipo.hype import HypeReading
from core.ipo.ledger import guard_lossless_rewrite
from core.ipo.substance import SubstanceReading
from core.ipo.verdict import IpoVerdict

logger = logging.getLogger(__name__)

_WHAT = "IPO verdict store (the forward rows the IPO-5b visibility gate is measured on)"


class IpoVerdictRecord(BaseModel):
    """One decision, with everything needed to replay it under new anchors."""
    written_at: str = ""                 # ISO-8601 UTC, when the row was stored
    verdict: IpoVerdict = Field(default_factory=IpoVerdict)
    hype: HypeReading = Field(default_factory=HypeReading)
    substance: SubstanceReading = Field(default_factory=SubstanceReading)

    @property
    def key(self) -> tuple[str, str]:
        return (self.verdict.symbol, self.verdict.close_date)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_utc(stamp: str) -> datetime | None:
    """Naive timestamps read as UTC rather than rejected — an undateable row
    must not stall a prune (same rule as signals.py)."""
    try:
        dt = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _same_reading(a: IpoVerdictRecord, b: IpoVerdictRecord) -> bool:
    """Everything but the write time.

    Deliberately wider than the verdict alone. Two runs can reach the same
    lean over different evidence — research that finally corroborated a peer
    P/E leaves S dark and the verdict unchanged while the FEATURES behind it
    improve — and the features are the half of the row that makes a later
    replay possible. Comparing only the verdict would silently drop the better
    row. Duplicates are not a counting hazard either way: the gate reads one
    row per key via `latest()`, not every row in the file.
    """
    return a.model_dump(exclude={"written_at"}) == b.model_dump(exclude={"written_at"})


class IpoVerdictStore:
    """JSONL at <base_dir>/ipo_verdicts.jsonl."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or "data/ipo")
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "ipo_verdicts.jsonl"

    def append(self, verdict: IpoVerdict, hype: HypeReading | None = None,
               substance: SubstanceReading | None = None, *,
               written_at: str | None = None) -> bool:
        """Store one decision. True if written, False on the content-dedup rule.

        A verdict carrying no symbol is refused: an unkeyed row cannot be found
        again, and the gate would count it against nothing.
        """
        if not verdict.symbol:
            logger.warning("[ipo_verdicts] refusing a verdict with no symbol")
            return False
        record = IpoVerdictRecord(written_at=written_at or _now_iso(), verdict=verdict,
                                  hype=hype or HypeReading(),
                                  substance=substance or SubstanceReading())
        newest = self.latest(verdict.symbol, verdict.close_date)
        if newest is not None and _same_reading(newest, record):
            return False
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        return True

    def _read_rows(self) -> tuple[list[IpoVerdictRecord], int]:
        """(parsed rows, non-blank line count) from ONE read, so prune's guard
        cannot be fooled by a write landing between two reads."""
        if not self.path.exists():
            return [], 0
        lines = [ln for ln in (raw.strip() for raw in
                               self.path.read_text(encoding="utf-8").splitlines())
                 if ln]
        out: list[IpoVerdictRecord] = []
        for line in lines:
            try:
                out.append(IpoVerdictRecord(**json.loads(line)))
            except Exception:
                continue            # a corrupt line must never break a read
        return out, len(lines)

    def load_all(self) -> list[IpoVerdictRecord]:
        return self._read_rows()[0]

    def load_key(self, symbol: str, close_date: str) -> list[IpoVerdictRecord]:
        """Every row for one (symbol, close_date), oldest first by write time."""
        return sorted((r for r in self.load_all() if r.key == (symbol, close_date)),
                      key=lambda r: r.written_at)

    def latest(self, symbol: str, close_date: str) -> IpoVerdictRecord | None:
        rows = self.load_key(symbol, close_date)
        return rows[-1] if rows else None

    def prune(self, older_than_days: int, now: datetime | None = None) -> int:
        """Drop rows written before the retention window. Returns rows removed.

        Same three rules as the capture ledger, for the same reasons:
        `older_than_days <= 0` is a no-op rather than "prune everything" (0 is
        this codebase's convention for disabled); a row whose timestamp will
        not parse is KEPT, because deleting data we cannot date is the worse
        error; and the rewrite is refused outright if any line failed to parse.
        """
        if older_than_days <= 0:
            return 0
        rows, lines = self._read_rows()
        guard_lossless_rewrite(self.path, len(rows), lines, what=_WHAT)
        if not rows:
            return 0
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=older_than_days)
        keep = [r for r in rows if (_as_utc(r.written_at) or now) >= cutoff]
        removed = len(rows) - len(keep)
        if removed == 0:
            return 0
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(r.model_dump_json() + "\n" for r in keep),
                       encoding="utf-8")
        tmp.replace(self.path)
        logger.info("[ipo_verdicts] pruned %d row(s) older than %dd",
                    removed, older_than_days)
        return removed
