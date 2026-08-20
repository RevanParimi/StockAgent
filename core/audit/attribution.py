"""Why a switch decision was wrong — as a distribution, never a per-call verdict.

Order is the design. `unpredictable` is tested first so a genuine shock is
never filed as a knowledge gap; `technical` before `knowledge` so a call made
blind is never blamed on the model's reasoning. Getting the order wrong does
not raise — it produces a plausible, confident, wrong fix list, which is the
expensive failure here.

A row with no evidence on file is `unknown_evidence` and sits OUTSIDE the
denominator. Guessing would make the pre-instrumentation backlog look like a
model problem, which is exactly the mistake this module exists to prevent.
"""
from __future__ import annotations

# reforecast_reason values that mean "something arrived that nothing could
# have anticipated" (core/portfolio/advisor.py reads the same set).
SHOCK_REASONS = frozenset({"external_shock", "preopen_shock"})

BUCKETS = ("unpredictable", "technical", "knowledge", "research",
           "unknown_evidence")


def classify_miss(row, *, news_index: dict, had_shock: bool = False,
                  atr_breach: bool = False, below_chance: bool = False) -> str:
    """One bucket for one wrong decision; "" when the row was not a miss.

    `row.correct is not False` rather than `is True` on purpose: a row that was
    never scored (None) is not a miss either, and must not be classified.
    """
    if row.correct is not False:
        return ""
    if had_shock or atr_breach:
        return "unpredictable"
    seen = news_index.get((row.symbol, row.issued_on))
    if seen is None:
        return "unknown_evidence"
    if seen is False:
        return "technical"
    if below_chance:
        return "research"
    return "knowledge"


def attribution_distribution(rows, *, news_index: dict,
                             shocked_refs: set | None = None,
                             below_chance_reasons: set | None = None) -> dict:
    """Counts per bucket, plus `n_classified`.

    `n_classified` is the denominator any percentage must use: it deliberately
    excludes `unknown_evidence`, so "40% knowledge gaps" never quietly means
    "40% of the rows we happened to have evidence for, presented as all rows".
    """
    shocked_refs = shocked_refs or set()
    below_chance_reasons = below_chance_reasons or set()
    out = {b: 0 for b in BUCKETS}
    for row in rows:
        reason = row.triggers[1] if len(row.triggers) > 1 else ""
        bucket = classify_miss(
            row, news_index=news_index,
            had_shock=row.ref in shocked_refs,
            below_chance=reason in below_chance_reasons)
        if bucket:
            out[bucket] += 1
    out["n_classified"] = sum(out[b] for b in BUCKETS
                              if b != "unknown_evidence")
    return out
