"""PI Prospect P3 — the verdict (design §3 "Verdict grid", plan 2026-09-21 / IPO-3c).

Two readings come in (`hype.HypeReading`, `substance.SubstanceReading`) and one
structured judgement comes out. Nothing here scores a feature or touches a
ledger: this module only decides what the two indices are ALLOWED to assert.

What it is allowed to assert, and why:

  SHORT   — the listing-day lean, from `demand` ALONE. `demand` is the only
            index in this PI with measured evidence behind it (IPO-1: on the
            P1 spine of 188 graded listings, the strong cohort listed positive
            92% of the time and the weak cohort 34%). `froth` moves the BAND,
            never the lean — on the same spine the high-froth cohort's mean is
            unchanged and its spread is visibly wider (strong lean, 1 td:
            p25–p75 of +16.4→+42.5 at low froth against +15.3→+51.8 at high).
            So froth buys a wider range and a de-rating caution, not a
            different direction.
  LONG    — SHIPS DARK. `lean` is hard-wired None. The spine's 252-td evidence
            is 77 rows from one regime (62 of 80 matured rows are 2024
            listings) and supports no direction. The reasoning is still
            recorded — `h_minus_s` and the quadrant — so that when a second
            regime matures the question can be asked of kept data rather than
            re-derived. Flipping this is a config edit gated on those rows,
            not a code change.

The honesty rule that outranks the thresholds (IPO-1, "the caveat that shapes
P3 more than any number above"): the spine holds FINAL subscription, known at
close of day 3. The deep dive fires at T−1, when the book is still open and
QIBs have not yet bid. A lean issued then rests on interim demand, which the
spine cannot see. So `short.evidenced` is True only once the book has closed,
the hit-rate is quoted only when it is True, and `IPO-5b` gates the visible
flip on that one flag rather than re-deriving the rule at the surface.

OFS share reaches this module inside the readings and changes nothing here —
it is UNVALIDATED (spec §3) after three measurements, and no code path in this
file reads it. A test asserts that.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from pydantic import BaseModel, Field

from core.ipo.hype import HypeReading
from core.ipo.substance import SubstanceReading

logger = logging.getLogger(__name__)

LEANS: tuple[str, ...] = ("strong", "mixed", "weak")
QUADRANTS: tuple[str, ...] = ("quiet_compounder", "genuine_star", "ignore", "froth")

# §3's grid, as (high substance?, high hype?) -> quadrant.
_GRID: dict[tuple[bool, bool], str] = {
    (True, False): "quiet_compounder",   # dull listing, re-rates later (Ather)
    (True, True): "genuine_star",        # pops and holds (rare)
    (False, False): "ignore",
    (False, True): "froth",              # pops, then de-rates (Ola)
}

QUADRANT_LABELS: dict[str, str] = {
    "quiet_compounder": "quiet compounder — substance without the noise",
    "genuine_star": "genuine star — substance the crowd has also found",
    "ignore": "ignore — neither the business nor the book argues for it",
    "froth": "froth — a hot book over a business that did not read as strong",
}

# The states in which the book is final, i.e. the slot the spine evidence covers.
CLOSED_STATES: frozenset[str] = frozenset({"closed", "listed"})


class ShortView(BaseModel):
    lean: str | None = None                       # strong | mixed | weak | None
    band: tuple[float, float] | None = None       # listing-day return band, % vs issue price
    basis: str = ""
    evidenced: bool = False                       # is the spine hit-rate admissible here


class LongView(BaseModel):
    lean: None = None                             # HARD-WIRED dark (IPO-1), not a default
    basis: str = ""
    h_minus_s: float | None = None                # the de-rating force, recorded not asserted


class IpoVerdict(BaseModel):
    symbol: str = ""
    close_date: str = ""
    as_of: str = ""                               # captured_at of the snapshot scored
    state: str = ""                               # issue state at that snapshot
    short: ShortView = Field(default_factory=ShortView)
    long: LongView = Field(default_factory=LongView)
    quadrant: str | None = None
    hype: float | None = None                     # froth — H proper, UNFITTED
    substance: float | None = None                # S — UNFITTED except its qib_x leg
    demand: float | None = None                   # the one fitted reading
    dark: list[str] = Field(default_factory=list)  # side-prefixed, e.g. hype.gmp_pct


# ─────────────────────────── configuration ───────────────────────────────

def _settings() -> Any:
    from core.config import settings
    return settings


def _num(name: str, fallback: float) -> float:
    try:
        return float(getattr(_settings(), name, fallback))
    except (TypeError, ValueError):
        return fallback


def _band_table(name: str) -> dict[str, tuple[float, float]]:
    raw = getattr(_settings(), name, None)
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for key, val in raw.items():
        try:
            lo, hi = (float(v) for v in val)
        except (TypeError, ValueError):
            continue
        if lo <= hi:
            out[str(key)] = (lo, hi)
    return out


def _cohorts() -> dict[str, dict[str, float]]:
    """Per-lean spine measurements quoted in the basis: n, positive, mean_pct.

    These live beside the thresholds in config because they ARE the
    thresholds' evidence — moving `short_strong` without re-measuring here
    would leave the basis quoting a hit-rate for a cohort that no longer
    exists. config.yaml says so at the block.
    """
    raw = getattr(_settings(), "IPO_SHORT_COHORTS", None)
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, dict[str, float]] = {}
    for key, val in raw.items():
        if not isinstance(val, Mapping):
            continue
        row: dict[str, float] = {}
        for field in ("n", "positive", "mean_pct"):
            try:
                row[field] = float(val[field])
            except (KeyError, TypeError, ValueError):
                break
        if len(row) == 3:
            out[str(key)] = row
    return out


# ─────────────────────────── the pieces ──────────────────────────────────

def lean_of(demand: float | None) -> str | None:
    """strong / mixed / weak from the fitted demand index, or None when it is
    dark. A dark index yields NO lean — never a defaulted "mixed"."""
    if demand is None:
        return None
    if demand >= _num("IPO_SHORT_STRONG", 70.0):
        return "strong"
    if demand <= _num("IPO_SHORT_WEAK", 30.0):
        return "weak"
    return "mixed"


def band_of(lean: str | None, froth: float | None) -> tuple[tuple[float, float] | None, bool]:
    """(band, widened_by_froth) for a lean.

    The base band is that lean cohort's p25–p75 listing-day return on the
    spine. When froth is high, the high-froth sub-cohort's own band replaces
    it — a measured substitution, not a multiplier applied to a fitted number.
    An absent config table yields None: no band is better than an invented one.
    """
    if lean is None:
        return None, False
    if froth is not None and froth >= _num("IPO_FROTH_HIGH", 50.0):
        widened = _band_table("IPO_SHORT_BANDS_HIGH_FROTH").get(lean)
        if widened is not None:
            return widened, True
    return _band_table("IPO_SHORT_BANDS").get(lean), False


def quadrant_of(froth: float | None, substance: float | None) -> str | None:
    """§3's grid. None when either axis is dark — a quadrant read off one axis
    is a guess with a name on it."""
    if froth is None or substance is None:
        return None
    high = _num("IPO_QUADRANT_HIGH", 50.0)
    return _GRID[(substance >= high, froth >= high)]


# ─────────────────────────── the basis, in words ─────────────────────────

def _short_basis(lean: str | None, demand: float | None, froth: float | None,
                 band: tuple[float, float] | None, widened: bool, evidenced: bool,
                 state: str) -> str:
    if lean is None:
        return ("No lean: the demand index is dark — under "
                f"{_num('IPO_INDEX_MIN_COVERAGE', 0.5):.0%} of its weight was captured. "
                "An unread book is unread, not weak.")

    strong, weak = _num("IPO_SHORT_STRONG", 70.0), _num("IPO_SHORT_WEAK", 30.0)
    rule = {"strong": f"demand {demand} >= {strong:g}",
            "mixed": f"{weak:g} < demand {demand} < {strong:g}",
            "weak": f"demand {demand} <= {weak:g}"}[lean]
    parts = [f"{rule} -> {lean}."]

    if evidenced:
        c = _cohorts().get(lean)
        if c:
            parts.append(
                f"On the P1 spine that cohort listed positive {c['positive']:.0%} of the time "
                f"(n={c['n']:g}, mean {c['mean_pct']:+.1f}% vs issue price at 1 td).")
        else:
            parts.append("No cohort measurement is configured for this lean, so no hit-rate "
                         "is quoted.")
    else:
        parts.append(
            f"The book is not closed yet (state={state or 'unknown'}), so this reads interim "
            "demand. The spine holds FINAL subscription and QIBs bid overwhelmingly on the last "
            "day, so its hit-rate is NOT admissible here (IPO-1) — this lean awaits forward "
            "validation from the P2 capture.")

    if band is not None:
        parts.append(f"Band {band[0]:+.1f}% to {band[1]:+.1f}% is that cohort's p25-p75 "
                     "listing-day return.")
        if widened:
            parts.append(
                f"Taken from the high-froth sub-cohort: froth {froth} >= "
                f"{_num('IPO_FROTH_HIGH', 50.0):g}. Froth moves the band, not the lean — on the "
                "spine that sub-cohort's mean is unchanged and its spread is wider, so expect a "
                "sharper pop and a sharper de-rating.")
    else:
        parts.append("No band: none is configured for this lean.")
    return " ".join(parts)


def _long_basis(h_minus_s: float | None, froth: float | None, substance: float | None,
                quadrant: str | None) -> str:
    parts = ["LONG ships dark: the spine's 252-td evidence is 77 rows from one regime and "
             "supports no direction (IPO-1). Recorded, not asserted:"]
    if h_minus_s is not None:
        parts.append(f"H - S = {h_minus_s:+.1f} (froth {froth} minus substance {substance}), "
                     "the de-rating force of §3.")
    elif substance is None:
        parts.append("H - S unavailable — substance is dark, so the business was not read. "
                     "That is unread, not low substance.")
    else:
        parts.append("H - S unavailable — the froth reading is dark.")
    parts.append(f"Quadrant: {QUADRANT_LABELS[quadrant]}." if quadrant
                 else "No quadrant: it needs both axes.")
    parts.append("S is UNFITTED — the spine has no Substance column.")
    return " ".join(parts)


# ─────────────────────────── the verdict ─────────────────────────────────

def decide_verdict(hype: HypeReading | None, substance: SubstanceReading | None, *,
                   row: Mapping[str, Any] | None = None, symbol: str = "",
                   close_date: str = "", state: str = "") -> IpoVerdict:
    """The structured judgement for one issue. Pure over the two readings — it
    fetches nothing, writes nothing, and never raises."""
    try:
        hype = hype or HypeReading()
        substance = substance or SubstanceReading()
        row = row or {}

        state = state or hype.state or ""
        demand, froth, s_index = hype.demand, hype.froth, substance.index

        lean = lean_of(demand)
        band, widened = band_of(lean, froth)
        evidenced = lean is not None and state in CLOSED_STATES
        quadrant = quadrant_of(froth, s_index)
        h_minus_s = (round(froth - s_index, 1)
                     if (froth is not None and s_index is not None) else None)

        dark = sorted({f"hype.{k}" for k in hype.dark}
                      | {f"substance.{k}" for k in substance.dark})
        return IpoVerdict(
            symbol=symbol or hype.symbol or substance.symbol or str(row.get("symbol", "")),
            close_date=close_date or str(row.get("issue_end", "") or ""),
            as_of=hype.as_of or substance.as_of,
            state=state,
            short=ShortView(lean=lean, band=band, evidenced=evidenced,
                            basis=_short_basis(lean, demand, froth, band, widened,
                                               evidenced, state)),
            long=LongView(basis=_long_basis(h_minus_s, froth, s_index, quadrant),
                          h_minus_s=h_minus_s),
            quadrant=quadrant, hype=froth, substance=s_index, demand=demand, dark=dark,
        )
    except Exception as exc:
        logger.warning("[ipo_verdict] decision failed (non-fatal): %s", exc)
        return IpoVerdict(symbol=symbol, close_date=close_date, state=state,
                          short=ShortView(basis="No verdict: the readings could not be combined."),
                          long=LongView(basis="LONG ships dark."))
