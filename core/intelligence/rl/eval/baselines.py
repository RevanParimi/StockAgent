"""
core/intelligence/rl/eval/baselines.py
=======================================
Naive baseline accuracy functions for the Monthly Scorecard + Baseline Duel
(spec 2026-06-12, section 3).

Pure functions over a month's ordered `FeedbackEntry` list:
  - take plain Python lists of `FeedbackEntry` (from `core.schemas.feedback`),
  - return `float | None`,
  - perform no I/O and read no global/mutable state.

Computed at scorecard time and backfillable for any past month — unlike the
control lane, naive baselines need no LLM call and can be applied
retroactively to historical feedback logs.

Direction semantics
--------------------
All three functions compare against `entry.actual_direction` — the same
3-way (UP | DOWN | FLAT) classification `classify_direction` already wrote
onto each `FeedbackEntry` at review time. None of these functions re-derive
direction from raw prices.
"""
from __future__ import annotations

from core.schemas.feedback import FeedbackEntry


def persistence_accuracy(entries: list[FeedbackEntry]) -> float | None:
    """
    Naive "persistence" baseline: predict day D's direction = day D-1's
    realized `actual_direction`. The first day has no prior day to persist
    from, so it is skipped.

    Returns `None` if fewer than 2 entries (no predictable days).
    """
    if len(entries) < 2:
        return None
    hits = 0
    total = 0
    for prev, curr in zip(entries, entries[1:]):
        total += 1
        if prev.actual_direction == curr.actual_direction:
            hits += 1
    return hits / total


def always_up_accuracy(entries: list[FeedbackEntry]) -> float | None:
    """
    Naive "always predict UP" baseline.

    Returns `None` for an empty list.
    """
    if not entries:
        return None
    hits = sum(1 for e in entries if e.actual_direction == "UP")
    return hits / len(entries)


def always_down_accuracy(entries: list[FeedbackEntry]) -> float | None:
    """
    Naive "always predict DOWN" baseline.

    Returns `None` for an empty list.
    """
    if not entries:
        return None
    hits = sum(1 for e in entries if e.actual_direction == "DOWN")
    return hits / len(entries)
