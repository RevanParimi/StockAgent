"""Verification layer — the graded-outcome row (design 2026-08-07 section 4.2).

One row per (ref, horizon_td). Written append-only to
data/portfolio/<user_id>/advice_outcomes.jsonl. The source ledgers are never
rewritten: grading is derived data and derived data must not be able to
corrupt what the user was actually told.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lane = Literal["advice", "alert", "shelf", "switch", "ipo", "dive", "screen", "bare"]

# PR-017: the lanes that grade research ideas rather than advice. Their rows
# carry the fields below marked "idea lanes"; core/audit/report.py keeps them
# out of every advice block, so they cannot move the advice verdict.
IDEA_LANES: tuple[str, ...] = ("dive", "screen", "bare")
# Written only on idea-lane rows; left out of every other row's line, so the
# advice, alert, shelf, switch and ipo rows keep the shape they had.
IDEA_FIELDS: tuple[str, ...] = ("graph", "reference_close", "entry_on", "basis", "composite")


class AuditOutcome(BaseModel):
    ref: str                       # "<issued_on>|<symbol>|<hash-or-kind>"
    lane: Lane
    user_id: str
    symbol: str
    verdict: str = ""              # "" for shelf rows — they are not calls
    triggers: list[str] = Field(default_factory=list)
    # ISO date the call was made (on dive and bare rows the dive's run day, on
    # screen rows the screen's run day). On ipo rows this is the verdict date (T-1 or
    # the close day), which is BEFORE the listing the return is measured from
    # — the two cannot be the same date, because the only price a subscriber
    # can transact at is fixed before the tape exists.
    issued_on: str
    # 10 | 30 | 60 td; 1/5/21/63/126/252 on ipo rows; 10/30/60/90/180 on idea
    # rows (audit.idea_horizons_td), counted from the call's day.
    horizon_td: int
    graded_on: str                 # ISO date the horizon matured

    # The price the return is measured from. A market close on `issued_on` for
    # every lane EXCEPT ipo, where it is the ISSUE PRICE — what the subscriber
    # actually paid — and the horizon is counted in trading days from listing,
    # horizon 1 being the listing day itself. Stated here rather than left to
    # be inferred from a writer: an IPO's defining number is the move from what
    # was paid to what the market said it was worth, and anchoring an ipo row
    # on a close would throw exactly that away (core/ipo/outcomes.py).
    # On the idea lanes (dive, screen, bare) it is the OPEN of the first
    # session after the call's day (`entry_on`), the first price anyone could
    # act at; the call's own close is kept beside it (`reference_close`), and
    # `exit_close` is the horizon close in the entry open's price basis.
    entry_close: float
    exit_close: float
    return_pct: float              # (exit/entry - 1) * 100

    bench_entry: float
    bench_exit: float
    bench_pct: float
    excess_pct: float              # return_pct - bench_pct

    correct: bool | None           # None for shelf and idea rows (never scored)
    graded_at: str                 # UTC ISO timestamp the grade was taken

    # Optional, present only where they apply (design section 4.2). Both have
    # writers — see core/audit/outcomes.py. No declared-but-unwritten fields:
    # that is the outcome_*td failure this whole layer exists to correct.
    switch_excess_pct: float | None = None   # SWITCH rows with a priceable candidate
    conviction: float | None = None          # shelf rows; dive and bare rows, as issued

    # Switch lane only (2026-08-20). Both written by grade_switch_lane — no
    # declared-but-unwritten fields, which is the outcome_*td failure this
    # whole layer exists to correct.
    candidate: str = ""            # the destination symbol
    miss_class: str = ""           # attribution bucket; "" when not a miss

    # Idea lanes only (PR-017), all written by core/audit/idea_lanes.py.
    graph: str = ""                          # dive and bare rows: "native" | "generic" | "" unknown
    reference_close: float | None = None     # the close the call read (the dive's, the screen's)
    entry_on: str = ""                       # ISO session whose open is entry_close
    basis: str = ""                          # ratios applied to the horizon close; "" none
    composite: float | None = None           # screen rows: the screen's composite rank

    def key(self) -> tuple[str, int]:
        return (self.ref, self.horizon_td)
