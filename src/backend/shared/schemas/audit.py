"""Verification layer — the graded-outcome row (design 2026-08-07 section 4.2).

One row per (ref, horizon_td). Written append-only to
data/portfolio/<user_id>/advice_outcomes.jsonl. The source ledgers are never
rewritten: grading is derived data and derived data must not be able to
corrupt what the user was actually told.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lane = Literal["advice", "alert", "shelf", "switch"]


class AuditOutcome(BaseModel):
    ref: str                       # "<issued_on>|<symbol>|<hash-or-kind>"
    lane: Lane
    user_id: str
    symbol: str
    verdict: str = ""              # "" for shelf rows — they are not calls
    triggers: list[str] = Field(default_factory=list)
    issued_on: str                 # ISO date the call was made
    horizon_td: int                # 10 | 30 | 60 trading days
    graded_on: str                 # ISO date the horizon matured

    entry_close: float
    exit_close: float
    return_pct: float              # (exit/entry - 1) * 100

    bench_entry: float
    bench_exit: float
    bench_pct: float
    excess_pct: float              # return_pct - bench_pct

    correct: bool | None           # None for shelf rows (never scored)
    graded_at: str                 # UTC ISO timestamp the grade was taken

    # Optional, present only where they apply (design section 4.2). Both have
    # writers — see core/audit/outcomes.py. No declared-but-unwritten fields:
    # that is the outcome_*td failure this whole layer exists to correct.
    switch_excess_pct: float | None = None   # SWITCH rows with a priceable candidate
    conviction: float | None = None          # shelf rows only

    # Switch lane only (2026-08-20). Both written by grade_switch_lane — no
    # declared-but-unwritten fields, which is the outcome_*td failure this
    # whole layer exists to correct.
    candidate: str = ""            # the destination symbol
    miss_class: str = ""           # attribution bucket; "" when not a miss

    def key(self) -> tuple[str, int]:
        return (self.ref, self.horizon_td)
