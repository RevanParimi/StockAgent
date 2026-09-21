"""PI Prospect P3 — the Hype side (design §3, plan 2026-09-21 Sprint 3 / IPO-3a).

Two readings come out of here, kept apart on purpose:

  demand  — the FITTED short-horizon reading. `qib_x >= total_x > retail_x`,
            anchored on the P1 spine's p10/p50/p90 (188 graded listings,
            2024-05 → 2026-08). This is the one number with measured evidence
            behind it: on the spine the composite's top tercile listed
            positive 95% of the time, the bottom tercile 33% (IPO-1 read).
  froth   — H proper, the §3 Hype features that have NO return evidence and
            are not claimed to: retail ×, retail-to-QIB skew, cut-off share,
            GMP (dark until IPO-0c wires it). Skew and cut-off enter as
            modifiers "unweighted for return until P2 rows mature" (IPO-1).
            Their anchors are read off the same spine where a feature exists
            there, and stated as unfitted where it does not.

Both are pure functions over captured facts. Nothing here is written back to
the ledger; a change of anchor never requires rewriting history (same rule as
velocity.py). The LLM is nowhere in this file.

Dark-signal rule: a feature that was not captured is None, is listed in
`dark`, and the weights are renormalised over the features present. An index
that would rest on less than `ipo.index_min_coverage` of its weight is None,
not a confident number built on one leg.

OFS share is CAPTURED here so a reader sees it and NEVER SCORED — §3 marks it
UNVALIDATED after three measurements (2026-08-15, 08-18, 09-21).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Mapping

from pydantic import BaseModel, Field

from core.ipo.signals import IpoSignalSnapshot
from core.ipo.velocity import demand_delta, final_demand_snapshot

logger = logging.getLogger(__name__)

# Everything score-relevant, in the order the reading renders it. Features
# outside the two weight tables are captured for the record, never scored.
DEMAND_FEATURES: tuple[str, ...] = ("qib_x", "total_x", "retail_x")
FROTH_FEATURES: tuple[str, ...] = ("retail_x", "retail_qib_skew", "cutoff_share", "gmp_pct")
CAPTURED_ONLY: tuple[str, ...] = ("nii_x", "fii_x", "dom_fi_x", "mutual_fund_x",
                                  "demand_delta", "issue_size_cr", "ofs_share",
                                  "news_volume")


class HypeReading(BaseModel):
    symbol: str = ""
    as_of: str = ""                                   # captured_at of the snapshot scored
    state: str = ""                                   # calendar state at that snapshot
    features: dict[str, float | None] = Field(default_factory=dict)
    components: dict[str, float | None] = Field(default_factory=dict)  # 0..1 per scored feature
    demand: float | None = None                       # 0..100, fitted (IPO-1)
    demand_coverage: float = 0.0                      # share of demand weight present
    froth: float | None = None                        # 0..100, H — unfitted
    froth_coverage: float = 0.0
    dark: list[str] = Field(default_factory=list)     # scored features that were None


# ─────────────────────────── configuration ───────────────────────────────

def _settings() -> Any:
    from core.config import settings
    return settings


def _weights(name: str) -> dict[str, float]:
    raw = getattr(_settings(), name, None) or {}
    out: dict[str, float] = {}
    for key, val in raw.items():
        try:
            w = float(val)
        except (TypeError, ValueError):
            continue
        if w > 0:
            out[str(key)] = w
    return out


def _anchors(name: str) -> dict[str, tuple[float, float, float]]:
    raw = getattr(_settings(), name, None) or {}
    out: dict[str, tuple[float, float, float]] = {}
    for key, val in raw.items():
        try:
            lo, mid, hi = (float(v) for v in val)
        except (TypeError, ValueError):
            continue
        if 0 < lo < mid < hi:
            out[str(key)] = (lo, mid, hi)
    return out


# ─────────────────────────── feature gathering ────────────────────────────

def _f(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def hype_features(snaps: list[IpoSignalSnapshot], row: Mapping[str, Any] | None = None,
                  ) -> tuple[dict[str, float | None], IpoSignalSnapshot | None]:
    """Raw features for one issue → (features, snapshot they came from).

    The demand legs come from the LAST snapshot carrying a total — the
    completed demand picture (velocity.final_demand_snapshot). `row` is the
    NSE cache record for anything the ledger does not hold (issue size, OFS
    share when the offer parse read it). Every absent value is None.
    """
    snap = final_demand_snapshot(snaps)
    combined = snap.combined if snap else {}
    row = row or {}
    feats: dict[str, float | None] = {
        "total_x": _f(combined.get("total")),
        "qib_x": _f(combined.get("qib")),
        "retail_x": _f(combined.get("retail")),
        "nii_x": _f(combined.get("nii")),
        "fii_x": _f(combined.get("fii")),
        "dom_fi_x": _f(combined.get("dom_fi")),
        "mutual_fund_x": _f(combined.get("mutual_fund")),
        "cutoff_share": _f(snap.cutoff_share) if snap else None,
        "gmp_pct": _f(snap.gmp_pct) if snap else None,
        "news_volume": _f(snap.news_volume) if snap else None,
        "demand_delta": demand_delta(snaps),
        "issue_size_cr": _f(row.get("issue_size_cr")),
        "ofs_share": _f(row.get("ofs_share")),
    }
    qib, retail = feats["qib_x"], feats["retail_x"]
    # Retail leading institutions is the distribution tell (§3). A QIB book
    # at exactly 0.0 is a real reading with an undefined ratio, not an
    # infinite one — leave the skew dark rather than invent a number.
    feats["retail_qib_skew"] = (retail / qib) if (qib and retail is not None) else None
    return feats, snap


# ─────────────────────────── scoring ─────────────────────────────────────

def score_feature(x: float | None, anchors: tuple[float, float, float]) -> float | None:
    """Piecewise-linear on a log scale through (p10→0, p50→0.5, p90→1), clipped.

    Log because every input is a ratio (×, share, premium) whose spine
    distribution is heavy-tailed — 1.8× to 207× for the QIB book. A value at
    or below zero is below any positive anchor and scores 0.0, which keeps a
    genuine 0.00 total (NSE reports them) a real, bottom reading rather than
    an absent one.
    """
    if x is None:
        return None
    if x <= 0:
        return 0.0
    lo, mid, hi = (math.log(a) for a in anchors)
    lx = math.log(x)
    if lx <= mid:
        t = 0.5 * (lx - lo) / (mid - lo)
    else:
        t = 0.5 + 0.5 * (lx - mid) / (hi - mid)
    return max(0.0, min(1.0, t))


def score_index(features: Mapping[str, float | None], weights: Mapping[str, float],
                anchors: Mapping[str, tuple[float, float, float]], *, min_coverage: float,
                ) -> tuple[float | None, float, dict[str, float | None]]:
    """(index 0..100 | None, coverage, components).

    Weights renormalise over the features actually present. Coverage is the
    share of total weight those features carry; below `min_coverage` the
    index is None — a number built on one leg out of four is not an index.
    A feature with a weight but no anchors is treated as dark: it cannot be
    scored, and silently scoring it on someone else's anchors would be worse.
    """
    components: dict[str, float | None] = {}
    num = den = total = 0.0
    for name, w in weights.items():
        total += w
        comp = score_feature(features.get(name), anchors[name]) if name in anchors else None
        components[name] = comp
        if comp is None:
            continue
        num += w * comp
        den += w
    coverage = (den / total) if total > 0 else 0.0
    if den <= 0 or coverage < min_coverage:
        return None, coverage, components
    return round(100.0 * num / den, 1), round(coverage, 3), components


def read_hype(snaps: list[IpoSignalSnapshot], row: Mapping[str, Any] | None = None,
              symbol: str = "") -> HypeReading:
    """The Hype side of one issue from its captured facts. Never raises —
    the deep dive that calls this must not die on a malformed ledger row."""
    try:
        feats, snap = hype_features(snaps, row)
        s = _settings()
        min_cov = float(getattr(s, "IPO_INDEX_MIN_COVERAGE", 0.5))
        demand, d_cov, d_comp = score_index(
            feats, _weights("IPO_DEMAND_WEIGHTS"), _anchors("IPO_DEMAND_ANCHORS"),
            min_coverage=min_cov)
        froth, f_cov, f_comp = score_index(
            feats, _weights("IPO_HYPE_WEIGHTS"), _anchors("IPO_HYPE_ANCHORS"),
            min_coverage=min_cov)
        components = {**d_comp, **f_comp}
        dark = sorted(k for k, v in components.items() if v is None)
        return HypeReading(
            symbol=symbol or (snap.symbol if snap else "") or str((row or {}).get("symbol", "")),
            as_of=snap.captured_at if snap else "",
            state=snap.state if snap else "",
            features=feats, components=components,
            demand=demand, demand_coverage=d_cov,
            froth=froth, froth_coverage=f_cov,
            dark=dark,
        )
    except Exception as exc:
        logger.warning("[ipo_hype] reading failed (non-fatal): %s", exc)
        return HypeReading(symbol=symbol, dark=list(DEMAND_FEATURES) + list(FROTH_FEATURES))
