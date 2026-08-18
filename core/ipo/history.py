"""PI Prospect P1 — the historical spine (design section 5, P1).

One row per mainboard IPO: what was knowable BEFORE listing joined to what
actually happened after. This is the file that decides whether any later
scoring model is evidence or astrology, so it is deliberately dumb — a JSONL
of facts, rebuildable from NSE plus the bhavcopy parquet at any time, with no
derived score anywhere in it.

Outcome horizons are TRADING DAYS, keyed as strings because JSON object keys
are strings: "1" (listing day), "5", "21", "63", "126", "252".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from core.ipo.ledger import guard_lossless_rewrite

logger = logging.getLogger(__name__)

# Named in the refusal message so the operator knows which file to look at.
_WHAT = "IPO history spine (the only copy, ~200 throttled NSE calls to rebuild)"

HORIZONS_TD: tuple[int, ...] = (1, 5, 21, 63, 126, 252)


class IpoRecord(BaseModel):
    symbol: str
    company: str = ""
    listing_date: str = ""             # ISO
    issue_price: float | None = None

    # Pre-listing knowables. None means genuinely unavailable — never 0.
    total_x: float | None = None
    qib_x: float | None = None
    retail_x: float | None = None
    # Promoters cashing out vs fresh capital in. 0.0 is a real reading
    # (pure fresh issue); None means the split could not be read.
    ofs_share: float | None = None

    # Realised curves, percent vs ISSUE PRICE, keyed by trading-day horizon.
    outcomes: dict[str, float] = Field(default_factory=dict)
    # Same horizons, percent vs ^NSEI over the identical calendar dates.
    excess: dict[str, float] = Field(default_factory=dict)

    listing_open: float | None = None
    listing_close: float | None = None
    sessions_available: int = 0


class IpoHistoryStore:
    """JSONL at <base_dir>/ipo_history.jsonl."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or "data/ipo")
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._dir / "ipo_history.jsonl"

    def append(self, rec: IpoRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(rec.model_dump_json() + "\n")

    def _read_rows(self) -> tuple[list[IpoRecord], int]:
        """(parsed rows, non-blank line count) from ONE read of the file.

        The rewrite guard compares these two numbers, and deriving them from
        two separate reads would let a write land in between and report a
        phantom mismatch.
        """
        if not self.path.exists():
            return [], 0
        lines = [ln for ln in (raw.strip() for raw in
                               self.path.read_text(encoding="utf-8").splitlines())
                 if ln]
        out: list[IpoRecord] = []
        for line in lines:
            try:
                out.append(IpoRecord(**json.loads(line)))
            except Exception:
                continue            # a corrupt line must never break a backfill
        return out, len(lines)

    def load_all(self) -> list[IpoRecord]:
        return self._read_rows()[0]

    def existing_symbols(self) -> set[str]:
        return {r.symbol for r in self.load_all()}

    def upsert(self, rec: IpoRecord) -> None:
        """Replace any row for this symbol. Rewrites the file — acceptable at
        a few hundred rows, and keeps the reader trivially correct."""
        parsed, lines = self._read_rows()
        guard_lossless_rewrite(self.path, len(parsed), lines, what=_WHAT)
        rows = {r.symbol: r for r in parsed}
        rows[rec.symbol] = rec
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "".join(r.model_dump_json() + "\n" for r in rows.values()),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def upsert_many(self, recs: list[IpoRecord]) -> int:
        """Replace rows for these symbols in ONE rewrite. Returns rows written.

        upsert() rewrites the whole file per row, which is O(n²) IO at ~206
        rows and the root cause of the OneDrive lock _upsert_with_retry works
        around (§9b). An enrichment pass touching every row must not do that.
        """
        parsed, lines = self._read_rows()
        guard_lossless_rewrite(self.path, len(parsed), lines, what=_WHAT)
        rows = {r.symbol: r for r in parsed}
        for rec in recs:
            rows[rec.symbol] = rec
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(r.model_dump_json() + "\n" for r in rows.values()),
                       encoding="utf-8")
        tmp.replace(self.path)
        return len(recs)
