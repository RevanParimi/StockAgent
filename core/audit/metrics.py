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


def conviction_calibration(
    rows: Iterable[AuditOutcome], horizon: int = 30, buckets: int = 5
) -> list[dict]:
    """Shelf ideas bucketed by conviction against realized excess return.

    The question nothing has ever asked: does a 0.9-conviction idea actually
    beat a 0.4-conviction idea? A flat curve means conviction carries no
    information and the discovery floor is arbitrary.

    Buckets span [0, 1] evenly; empty buckets are omitted.
    """
    scored = [r for r in rows
              if r.lane == "shelf" and r.conviction is not None
              and r.horizon_td == horizon]
    if not scored or buckets <= 0:
        return []

    width = 1.0 / buckets
    grouped: dict[int, list[AuditOutcome]] = {}
    for r in scored:
        idx = min(int(max(0.0, min(1.0, r.conviction)) / width), buckets - 1)
        grouped.setdefault(idx, []).append(r)

    out: list[dict] = []
    for idx in sorted(grouped):
        rs = grouped[idx]
        out.append({
            "lo": round(idx * width, 4),
            "hi": round((idx + 1) * width, 4),
            "n": len(rs),
            "mean_excess": round(sum(r.excess_pct for r in rs) / len(rs), 4),
        })
    return out


def calibration_spread(buckets: list[dict]) -> float | None:
    """Top populated bucket's mean excess minus the bottom's. None below two
    populated buckets — a single bucket says nothing about ordering."""
    if len(buckets) < 2:
        return None
    return round(buckets[-1]["mean_excess"] - buckets[0]["mean_excess"], 4)


def portfolio_vs_benchmark(history: list[dict], bench_pct: float) -> dict:
    """Equity-curve return vs the index over the same span.

    `history` is value_history.jsonl rows, ascending by date, each carrying
    "market_value". Needs at least two points to describe a change.
    """
    points = [h for h in history if isinstance(h.get("market_value"), (int, float))]
    if len(points) < 2:
        return {"portfolio_pct": None, "bench_pct": bench_pct,
                "excess_pct": None, "n": len(points)}
    first = float(points[0]["market_value"])
    last = float(points[-1]["market_value"])
    if first <= 0:
        return {"portfolio_pct": None, "bench_pct": bench_pct,
                "excess_pct": None, "n": len(points)}
    portfolio_pct = round((last / first - 1.0) * 100.0, 4)
    return {
        "portfolio_pct": portfolio_pct,
        "bench_pct": bench_pct,
        "excess_pct": round(portfolio_pct - bench_pct, 4),
        "n": len(points),
    }
