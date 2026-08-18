"""Shared integrity rule for the two PI Prospect JSONL ledgers.

Both stores skip unparseable lines on read, so one bad line can never break a
backfill or a morning brief. Every rewrite path then wrote back only what
parsed — which turned that read tolerance into PERMANENT DELETION, silently,
and up to 9 times per `enrich_ofs` run against a 209-row spine that is
gitignored, is the only copy, and costs ~200 throttled NSE calls to rebuild.

The decision, and why this file exists rather than a patch at each call site:

  * A rewrite REFUSES when it cannot account for every non-blank line in the
    file. Refusing is recoverable — the operator still holds every byte.
    Rewriting is not.
  * Reads keep their tolerance. A corrupt line must not break a read.
  * Append-only writes keep working. They cannot drop a line, so a corrupt
    ledger must not stop the twice-daily capture from landing.

The count compared is PARSED ROWS vs NON-BLANK LINES, never the size of a
symbol-keyed dict: the spine legitimately holds repeated symbols before a
dedup, so comparing the deduped mapping would refuse every ordinary upsert.
"""
from __future__ import annotations

from pathlib import Path


class LedgerIntegrityError(RuntimeError):
    """A rewrite was refused because the file holds lines we cannot parse.

    Deliberately not a subclass of PermissionError: `scripts/ipo_backfill.py`
    retries PermissionError five times for a OneDrive lock race, and a refusal
    is not transient — it must surface on the first attempt.
    """


def guard_lossless_rewrite(path: Path, parsed: int, lines: int, *,
                           what: str) -> None:
    """Raise unless every non-blank line in `path` was parsed.

    `parsed` and `lines` must come from ONE read of the file — deriving them
    from two reads lets a write land in between and reports a phantom mismatch.
    """
    if parsed == lines:
        return
    raise LedgerIntegrityError(
        f"refusing to rewrite {path}: parsed {parsed} of {lines} non-blank "
        f"line(s), so the rewrite would permanently delete "
        f"{lines - parsed} unparseable line(s) from the {what}. Nothing was "
        f"written. Move the bad line(s) out of the file (keep a copy) and "
        f"re-run — reads and appends keep working in the meantime."
    )
