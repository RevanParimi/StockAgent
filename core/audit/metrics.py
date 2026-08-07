"""Pure metrics over graded outcome rows. Lists in, numbers out, no I/O.

Every function reports its own `n` and returns None rather than a number when
there is nothing to compute — a fresh install must read INSUFFICIENT_DATA,
never "0% hit rate".

wilson_interval and sign_test_p are reused from the Learning Evidence report
rather than reimplemented: two auditors must not disagree about what a
confidence interval is.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from backend.shared.schemas.audit import AuditOutcome
from core.intelligence.rl.eval.learning_evidence import sign_test_p, wilson_interval


class Rate(NamedTuple):
    n: int
    value: float | None          # None when n == 0
    lo: float | None             # Wilson 95% lower bound
    hi: float | None             # Wilson 95% upper bound


_EMPTY = Rate(0, None, None, None)


def _scored(
    rows: Iterable[AuditOutcome],
    horizon: int | None = None,
    verdict: str | None = None,
) -> list[AuditOutcome]:
    """Rows that carry a real True/False. Shelf rows (correct=None) are
    excluded everywhere — they were never calls."""
    out = []
    for r in rows:
        if r.correct is None:
            continue
        if horizon is not None and r.horizon_td != horizon:
            continue
        if verdict is not None and r.verdict.strip().upper() != verdict.strip().upper():
            continue
        out.append(r)
    return out


def hit_rate(
    rows: Iterable[AuditOutcome],
    horizon: int | None = None,
    verdict: str | None = None,
) -> Rate:
    scored = _scored(rows, horizon, verdict)
    if not scored:
        return _EMPTY
    hits = sum(1 for r in scored if r.correct)
    lo, hi = wilson_interval(hits, len(scored))
    return Rate(len(scored), hits / len(scored), round(lo, 4), round(hi, 4))


def per_trigger_precision(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> dict[str, Rate]:
    """Hit-rate grouped by advisor trigger. A row with two triggers counts
    under both — the question is "when this rule fires, how often is the call
    right?", per rule."""
    buckets: dict[str, list[AuditOutcome]] = {}
    for r in _scored(rows, horizon):
        for trigger in r.triggers:
            t = (trigger or "").strip()
            if t:
                buckets.setdefault(t, []).append(r)
    return {t: hit_rate(rs) for t, rs in sorted(buckets.items())}


def coin_flip_p(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> float | None:
    """Exact two-sided sign test of the hit-rate against 50%."""
    scored = _scored(rows, horizon)
    if not scored:
        return None
    hits = sum(1 for r in scored if r.correct)
    return sign_test_p(hits, len(scored))


def mean_excess(
    rows: Iterable[AuditOutcome], horizon: int | None = None
) -> float | None:
    """Average excess return in percentage points. Includes shelf rows: they
    have no verdict but they do have a return."""
    vals = [r.excess_pct for r in rows
            if horizon is None or r.horizon_td == horizon]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)
