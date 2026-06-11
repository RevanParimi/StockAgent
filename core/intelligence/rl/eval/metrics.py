"""
core/intelligence/rl/eval/metrics.py
=====================================
PURE metric functions for the RL Evaluation Harness (Component 1).

Every function in this module:
  - takes plain Python lists of `FeedbackEntry` (from
    `core.schemas.feedback`) or `MatchedRecord` (defined here) as input,
  - returns a `float` or `dict`,
  - performs **no I/O** and reads no global/mutable state.

`MatchedRecord` is the join of a `FeedbackEntry` (realized outcome) with the
corresponding `DailyForecast` (stated confidence + Monte Carlo band) for the
same date. The harness is responsible for producing this join; metrics.py
never touches `PredictionStore` or the filesystem.

Direction semantics
--------------------
`direction_accuracy` and `mae_pct` reuse the realized-direction fields that
`core.intelligence.rl.agents.feedback_agent.classify_direction` already wrote
onto each `FeedbackEntry` at review time (`direction_correct`,
`actual_direction`, both derived from `RL_FLAT_THRESHOLD_PCT`). This module
does not re-derive direction from raw prices — it trusts the system's own
recorded classification, which is exactly what "reuse classify_direction
semantics" means in practice.
"""
from __future__ import annotations

from typing import NamedTuple

from core.schemas.feedback import FeedbackEntry


class MatchedRecord(NamedTuple):
    """
    One date's realized outcome joined with its stated forecast.

    Produced by the harness when pairing `FeedbackEntry` (actuals) with the
    `DailyForecast` row (predictions) for the same `date`.
    """
    date: str
    confidence: float                  # DailyForecast.confidence, 0.0-1.0
    direction_correct: bool            # FeedbackEntry.direction_correct
    actual_close: float                # FeedbackEntry.actual_close
    price_lower: float | None = None   # DailyForecast.price_lower (P10)
    price_upper: float | None = None   # DailyForecast.price_upper (P90)


# ---------------------------------------------------------------------------
# direction_accuracy
# ---------------------------------------------------------------------------

def direction_accuracy(entries: list[FeedbackEntry]) -> float:
    """
    Fraction of entries where `direction_correct` is True.

    `direction_correct` is set at review time via `classify_direction` /
    `RL_FLAT_THRESHOLD_PCT`, so this is the system's own UP/DOWN/FLAT hit rate.

    Returns 0.0 for an empty list.
    """
    if not entries:
        return 0.0
    hits = sum(1 for e in entries if e.direction_correct)
    return hits / len(entries)


# ---------------------------------------------------------------------------
# brier_score
# ---------------------------------------------------------------------------

def brier_score(records: list[MatchedRecord]) -> float:
    """
    Mean squared error between stated `confidence` and the binary realized
    outcome (1.0 if `direction_correct`, else 0.0).

    Lower is better; 0.0 = perfectly calibrated and correct every time.
    Returns 0.0 for an empty list.
    """
    if not records:
        return 0.0
    total = 0.0
    for r in records:
        outcome = 1.0 if r.direction_correct else 0.0
        total += (r.confidence - outcome) ** 2
    return total / len(records)


# ---------------------------------------------------------------------------
# reliability_table
# ---------------------------------------------------------------------------

def reliability_table(records: list[MatchedRecord]) -> dict[str, dict[str, float | int]]:
    """
    Bucket records by confidence decile and report the realized hit rate
    per bucket.

    Buckets are half-open `[d/10, (d+1)/10)` for d in 0..8, plus a closed
    top bucket `[0.9, 1.0]` so confidence == 1.0 is included.

    Returns `{"<lo>-<hi>": {"n": int, "hit_rate": float, "avg_confidence": float}}`
    for buckets that contain at least one record. Empty dict for an empty list.
    """
    if not records:
        return {}

    buckets: dict[str, list[MatchedRecord]] = {}
    for r in records:
        key = _decile_bucket(r.confidence)
        buckets.setdefault(key, []).append(r)

    table: dict[str, dict[str, float | int]] = {}
    for key, recs in buckets.items():
        n = len(recs)
        hits = sum(1 for r in recs if r.direction_correct)
        table[key] = {
            "n": n,
            "hit_rate": hits / n,
            "avg_confidence": sum(r.confidence for r in recs) / n,
        }
    return table


def _decile_bucket(confidence: float) -> str:
    """Return the bucket label for a confidence value in [0, 1]."""
    c = min(max(confidence, 0.0), 1.0)
    if c >= 0.9:
        return "0.9-1.0"
    lo = int(c * 10) / 10
    hi = round(lo + 0.1, 1)
    return f"{lo:.1f}-{hi:.1f}"


# ---------------------------------------------------------------------------
# band_coverage
# ---------------------------------------------------------------------------

def band_coverage(records: list[MatchedRecord]) -> float:
    """
    Fraction of records where `actual_close` falls within
    `[price_lower, price_upper]` (the P10/P90 Monte Carlo band).

    Records with `price_lower is None` or `price_upper is None` (MC
    unavailable for that day) are excluded from both numerator and
    denominator. Returns 0.0 if no record has a usable band.
    """
    usable = [r for r in records if r.price_lower is not None and r.price_upper is not None]
    if not usable:
        return 0.0
    inside = sum(1 for r in usable if r.price_lower <= r.actual_close <= r.price_upper)
    return inside / len(usable)


# ---------------------------------------------------------------------------
# mae_pct
# ---------------------------------------------------------------------------

def mae_pct(entries: list[FeedbackEntry]) -> float:
    """
    Mean absolute value of `price_error_pct` across entries.

    Returns 0.0 for an empty list.
    """
    if not entries:
        return 0.0
    return sum(abs(e.price_error_pct) for e in entries) / len(entries)
