"""PI Prospect P3 — the Substance side (design §3, plan 2026-09-21 Sprint 3 / IPO-3b).

S answers "is there a business" from two provenance classes that never mix:

  browsed   — the corroborated `IpoSubstance` from extract.py: PAT and revenue
              series, issue P/E against peers. Every number here already
              passed the ≥2-domain gate; this module only ever reads
              `value`, never a `reported` string.
  official  — the P2 ledger snapshot: the QIB book and the mutual-fund
              sub-row of it. The one Substance leg with a fitted anchor is
              `qib_x` (same spine percentiles as hype.demand).

**Nothing here is fitted except `qib_x`.** The P1 spine has no Substance
column — no PAT, no revenue, no valuation — so every other anchor in
`ipo.substance_anchors` is labelled UNFITTED in config.yaml and the reading
carries `fitted=False` so verdict.py and the narrator cannot present S with
the confidence `demand` has earned. Weights are equal until evidence says
otherwise (IPO-1: "no weight on historical evidence — none exists").

Scoring reuses hype.score_index verbatim: one primitive, two indices.

What is captured and NOT scored, and why:
  promoter / parent_track  — free text, status `reported`; turning it into
                             0/0.5/1 is a judgement, and the LLM never decides.
  fii_x / dom_fi_x         — sub-row multiples whose denominator NSE does not
                             state (dom_fi 245,600 shares bid reads 0.42× against
                             a 2,325,145-share QIB book in the recorded payload,
                             so it is not "share of QIB"). A true sticky-vs-
                             flipper share needs shares-bid in the ledger — a
                             P2 follow-up, not a guess here.
  ebitda_margin, red_flags, anchor_names, use_of_proceeds — rendered by the
                             narrator (IPO-4b), not weighed.
  ofs_share                — UNVALIDATED (spec §3). Never scored anywhere.
"""
from __future__ import annotations

import logging
import re
import statistics
from typing import Any, Mapping

from pydantic import BaseModel, Field

from core.ipo.extract import IpoSubstance, Sourced
from core.ipo.hype import score_index
from core.ipo.signals import IpoSignalSnapshot
from core.ipo.velocity import final_demand_snapshot

logger = logging.getLogger(__name__)

BROWSED_FEATURES: tuple[str, ...] = ("pat_growth", "revenue_growth", "peer_pe_discount")
OFFICIAL_FEATURES: tuple[str, ...] = ("qib_x", "mutual_fund_x")
SUBSTANCE_FEATURES: tuple[str, ...] = BROWSED_FEATURES + OFFICIAL_FEATURES

_FY_NUM = re.compile(r"(\d{4})")


class SubstanceReading(BaseModel):
    symbol: str = ""
    as_of: str = ""                                   # ledger snapshot captured_at, if any
    features: dict[str, float | None] = Field(default_factory=dict)
    components: dict[str, float | None] = Field(default_factory=dict)
    index: float | None = None                        # S, 0..100
    coverage: float = 0.0
    fitted: bool = False                              # ALWAYS False until a Substance column exists
    dark: list[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)      # feature -> browsed | official
    sources: dict[str, list[str]] = Field(default_factory=dict)   # browsed feature -> agreeing URLs
    captured: dict[str, Any] = Field(default_factory=dict)        # rendered, never scored


# ─────────────────────────── browsed features ────────────────────────────

def _year(label: str | None) -> int | None:
    m = _FY_NUM.search(str(label or ""))
    return int(m.group(1)) if m else None


def _series(items: list[Sourced]) -> list[tuple[int, float, Sourced]]:
    """(fiscal year, value, sourced) oldest first; entries without a numeric
    value or a readable year are dropped, not guessed. One value per year."""
    by_year: dict[int, tuple[float, Sourced]] = {}
    for s in items or []:
        y = _year(s.as_of)
        if y is None or not isinstance(s.value, (int, float)):
            continue
        by_year[y] = (float(s.value), s)
    return [(y, v, s) for y, (v, s) in sorted(by_year.items())]


def _annualised(first: tuple[int, float], last: tuple[int, float]) -> float | None:
    """Growth multiple per year between two positive readings; None when the
    span is zero or either side is not positive."""
    (y0, v0), (y1, v1) = first, last
    if y1 <= y0 or v0 <= 0 or v1 <= 0:
        return None
    return (v1 / v0) ** (1.0 / (y1 - y0))


def pat_growth(series: list[Sourced]) -> tuple[float | None, list[str]]:
    """Annualised PAT growth multiple over the longest run of PROFITABLE years.

    Returns (feature, source urls). The feature is:
      None  — fewer than one corroborated year (nothing to say);
      0.0   — the latest year is a loss. A loss-making trajectory is a real,
              bottom reading, not an absent one (plan IPO-3b), and 0.0 is
              what score_feature maps to 0 by construction;
      1.0   — profitable in the latest year only, i.e. growth unmeasured
              (a flat multiple: sits below the mid anchor, above the floor);
      else  — (last / first_positive) ** (1 / years).
    """
    rows = _series(series)
    if not rows:
        return None, []
    urls = sorted({u for _, _, s in rows for u in (s.sources or [s.source_url]) if u})
    if rows[-1][1] <= 0:
        return 0.0, urls
    positive: list[tuple[int, float]] = []
    for y, v, _ in reversed(rows):
        if v <= 0:
            break
        positive.append((y, v))
    positive.reverse()
    if len(positive) < 2:
        return 1.0, urls
    return _annualised(positive[0], positive[-1]), urls


def revenue_growth(series: list[Sourced]) -> tuple[float | None, list[str]]:
    """Annualised revenue growth multiple, first to last corroborated year.
    None with fewer than two years — one figure is a level, not a trend."""
    rows = _series(series)
    if len(rows) < 2:
        return None, []
    urls = sorted({u for _, _, s in rows for u in (s.sources or [s.source_url]) if u})
    return _annualised((rows[0][0], rows[0][1]), (rows[-1][0], rows[-1][1])), urls


def peer_pe_discount(issue_pe: Sourced, peers: list[Sourced]) -> tuple[float | None, list[str]]:
    """median(peer P/E) / issue P/E — above 1 means priced BELOW peers, so the
    feature rises with substance like every other. Dark unless the issue P/E
    corroborated AND at least one peer did; IPO-2c found peers rarely do, so
    expect None here more often than not — S must not lean on it."""
    ipe = issue_pe.value if isinstance(issue_pe.value, (int, float)) else None
    pvals = [float(p.value) for p in peers or [] if isinstance(p.value, (int, float)) and p.value > 0]
    if ipe is None or ipe <= 0 or not pvals:
        return None, []
    urls = sorted({u for s in [issue_pe, *peers] for u in (s.sources or [s.source_url]) if u})
    return statistics.median(pvals) / float(ipe), urls


# ─────────────────────────── the reading ─────────────────────────────────

def _f(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _weights_and_anchors():
    from core.ipo.hype import _anchors, _weights
    return _weights("IPO_SUBSTANCE_WEIGHTS"), _anchors("IPO_SUBSTANCE_ANCHORS")


def read_substance(research: IpoSubstance | None, snaps: list[IpoSignalSnapshot] | None = None,
                   row: Mapping[str, Any] | None = None, symbol: str = "") -> SubstanceReading:
    """S for one issue from its corroborated research and its captured book.
    Never raises — a malformed dossier must not stop the deep dive."""
    try:
        research = research or IpoSubstance()
        snap = final_demand_snapshot(snaps or [])
        combined = snap.combined if snap else {}
        row = row or {}

        feats: dict[str, float | None] = {}
        sources: dict[str, list[str]] = {}
        feats["pat_growth"], sources["pat_growth"] = pat_growth(research.pat_cr)
        feats["revenue_growth"], sources["revenue_growth"] = revenue_growth(research.revenue_cr)
        feats["peer_pe_discount"], sources["peer_pe_discount"] = peer_pe_discount(
            research.issue_pe, research.peer_pe)
        feats["qib_x"] = _f(combined.get("qib"))
        feats["mutual_fund_x"] = _f(combined.get("mutual_fund"))
        sources = {k: v for k, v in sources.items() if v}

        weights, anchors = _weights_and_anchors()
        from core.config import settings
        min_cov = float(getattr(settings, "IPO_INDEX_MIN_COVERAGE", 0.5))
        index, coverage, components = score_index(feats, weights, anchors, min_coverage=min_cov)

        captured: dict[str, Any] = {
            "promoter": research.promoter.value,
            "parent_track": research.parent_track.value,
            "ebitda_margin": research.ebitda_margin.value,
            "issue_pe": research.issue_pe.value,
            "peer_pe": {p.label: p.value for p in research.peer_pe if p.label},
            "anchor_names": [a.value for a in research.anchor_names if a.value],
            "red_flags": [r.value for r in research.red_flags if r.value],
            "fii_x": _f(combined.get("fii")),
            "dom_fi_x": _f(combined.get("dom_fi")),
            "ofs_share": _f(row.get("ofs_share")),
            "docs_read": research.docs_read,
            "dropped": list(research.dropped),
        }
        return SubstanceReading(
            symbol=symbol or research.symbol or (snap.symbol if snap else ""),
            as_of=snap.captured_at if snap else "",
            features=feats, components=components, index=index, coverage=coverage,
            fitted=False,
            dark=sorted(k for k, v in components.items() if v is None),
            provenance={k: ("browsed" if k in BROWSED_FEATURES else "official") for k in components},
            sources=sources, captured=captured,
        )
    except Exception as exc:
        logger.warning("[ipo_substance] reading failed (non-fatal): %s", exc)
        return SubstanceReading(symbol=symbol, dark=list(SUBSTANCE_FEATURES))
