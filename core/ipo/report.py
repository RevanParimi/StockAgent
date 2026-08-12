"""PI Prospect P1 — what actually predicted what (design section 5, P1).

This module measures; it does not model. Its output is the evidence the P3
weights must answer to, and the honest caveats travel WITH the numbers so a
reader cannot pick up the hit-rate without also picking up its limits.
"""
from __future__ import annotations

from statistics import mean

from core.ipo.history import IpoRecord

_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("hot (>=10x)", 10.0, float("inf")),
    ("warm (2-10x)", 2.0, 10.0),
    ("cold (<2x)", float("-inf"), 2.0),
)


def _bucket(total_x: float) -> str:
    for name, low, high in _BUCKETS:
        if low <= total_x < high:
            return name
    return _BUCKETS[-1][0]


def summarise(rows: list[IpoRecord]) -> dict:
    graded = [r for r in rows if r.outcomes.get("1") is not None]
    buckets: dict[str, dict] = {name: {"n": 0, "listing": [], "held_252": []}
                                for name, _lo, _hi in _BUCKETS}
    missing = 0
    for r in graded:
        if r.total_x is None:
            missing += 1
            continue                # dark-signal: excluded, never zeroed
        b = buckets[_bucket(r.total_x)]
        b["n"] += 1
        b["listing"].append(r.outcomes["1"])
        if r.outcomes.get("252") is not None:
            b["held_252"].append(r.outcomes["252"])

    by_subscription = {
        name: {
            "n": b["n"],
            "mean_listing_pct": round(mean(b["listing"]), 4) if b["listing"] else None,
            "positive_listing_rate": (
                round(sum(1 for x in b["listing"] if x > 0) / len(b["listing"]), 4)
                if b["listing"] else None),
            "n_matured_252": len(b["held_252"]),
            "mean_252_pct": round(mean(b["held_252"]), 4) if b["held_252"] else None,
        }
        for name, b in buckets.items()
    }
    return {
        "total": len(rows),
        "graded": len(graded),
        "missing_subscription": missing,
        "by_subscription": by_subscription,
    }


# Below this, a bucket mean is noise dressed as a finding. The protection has
# to live HERE rather than in a general caveat at the bottom: a reader skimming
# a table sees "n=8, mean +47.44%" with the same visual weight as "n=118", and
# the most seductive number in this dataset is exactly the one with the
# smallest sample.
_MIN_N_TO_REPORT = 10


def _mean_or_floor(value: float | None, n: int, prefix: str = "mean ") -> str:
    """Render a mean, or refuse to when the sample cannot carry it."""
    if value is None:
        return ""
    if n < _MIN_N_TO_REPORT:
        return f"{prefix}n/a (n<{_MIN_N_TO_REPORT})"
    return f"{prefix}{value:+.2f}%"


def render_report(summary: dict) -> str:
    if not summary.get("graded"):
        return "IPO historical spine — no rows with a listing-day outcome yet."

    lines = [
        f"IPO historical spine — {summary['graded']} of {summary['total']} rows graded",
        "",
        "Listing-day return vs ISSUE PRICE, bucketed by total subscription:",
    ]
    for name, b in summary["by_subscription"].items():
        if not b["n"]:
            lines.append(f"  {name:14} n=0")
            continue
        lines.append(
            f"  {name:14} n={b['n']:<4} {_mean_or_floor(b['mean_listing_pct'], b['n'])}  "
            f"positive {b['positive_listing_rate']:.0%}  "
            f"(252td: n={b['n_matured_252']}"
            f"{_mean_or_floor(b['mean_252_pct'], b['n_matured_252'], prefix=', mean ')})"
        )
    lines += [
        "",
        "READ WITH CARE:",
        f"  - {summary['missing_subscription']} graded rows had no subscription "
        "figure and are excluded, not counted as zero.",
        "  - Buckets are small. Treat these as directional, not significant; the "
        "auditor's 2026-08-07 Wilson episode is the precedent for what happens "
        "when a narrow interval gets over-read.",
        "  - GMP and RHP financials are NOT in this dataset. Grey-market archives "
        "and prospectus PDFs are not retrievable retroactively at scale, so those "
        "weights can only be validated forward from launch (spec section 5, P1).",
    ]
    return "\n".join(lines)
