"""PI Prospect P2 — grey-market premium via a DEDICATED Serper key.

Ships dark. `ipo.gmp_enabled` is false and `SERPER_API_KEY_IPO` is unset, in
which case this module returns None and issues no request at all.

Why its own key: the shared SERPER_API_KEY runs at ~83 calls/day against a
2,500/month cap (prod counter, 2026-08-13: 924 calls on day 13 of 31,
projecting ~2,200-2,420). Real headroom is 80-300 calls/month, so IPO polling
on the shared key would compete directly with the daily pipeline. The spec's
original "~2,300 calls/mo headroom" was never measured and is wrong.

NOTE: `search_serper` calls `record_call("serper")` regardless of which API
key was passed in — the shared counter does not distinguish keys. So once
`ipo.gmp_enabled` is flipped on, GMP's calls land in the SAME counter that
the ~83/day headroom projection above is based on. Re-check headroom before
enabling, not just SERPER_API_KEY_IPO's own budget.

GMP is unofficial grey-market chatter scraped from search snippets, so a
single number is treated as a rumour: a reading requires agreement between at
least `ipo.gmp_min_sources` DISTINCT domains, and the spread between them must
be within `ipo.gmp_agreement_tolerance`. Callers render the result as
unofficial, always.
"""
from __future__ import annotations

import logging
import re
import statistics
from urllib.parse import urlparse

from services.data.fetchers.news import search_serper

logger = logging.getLogger(__name__)

# "Rs 120", "₹130", "Rs. 1,250", "-₹15" — group 1 is an optional leading minus
# immediately against the currency token, group 2 is the magnitude. GMP is
# routinely quoted at a discount (negative), so the sign must be captured,
# not assumed away.
_GMP_RE = re.compile(r"(-)?\s*(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
# A snippet saying "discount" without an explicit minus sign is still
# reporting a negative GMP (e.g. "GMP at a discount of Rs 15").
_DISCOUNT_RE = re.compile(r"\bdiscount\b", re.IGNORECASE)
# "no discount", "not a discount", "without a discount", "zero discount" —
# these DENY a discount. The word "discount" in that phrase carries no sign
# signal at all (positive OR negative) and must be excluded before either
# the negative-window check or the ambiguity check ever sees it.
_NEGATED_DISCOUNT_RE = re.compile(
    r"\b(?:no|not|without|zero)\s+(?:a\s+|any\s+)?discount\b", re.IGNORECASE)
# Anchors the currency figure to GMP/premium wording so an unrelated price
# band or issue-price figure earlier in the snippet isn't mistaken for GMP.
_KEYWORD_RE = re.compile(r"\bgmp\b|\bpremium\b|grey\s*market", re.IGNORECASE)
# How far past a GMP/premium keyword to look for "the" figure that follows
# it (chars). Generous enough for "GMP today is around Rs 120" but tight
# enough to not reach into an unrelated clause.
_KEYWORD_WINDOW = 40
# How close "discount" must sit to the matched figure to count as ITS sign
# qualifier ("at a discount of Rs 15" ~ 3 chars) rather than an unrelated
# mention elsewhere in the snippet ("No discount seen, GMP is now Rs 120" ~
# 17 chars) — measured, not guessed; see the sign tests for the two shapes.
_DISCOUNT_WINDOW = 10
# Guards against picking up a share count or a market-cap figure. Symmetric —
# a discount is bounded the same way a premium is.
_MAX_PLAUSIBLE_GMP = 5000.0


def _gap(a: re.Match, b: re.Match) -> float:
    """Character distance between two regex matches (0 if they overlap).

    The single shared "how near is near" primitive for this module — both
    the GMP/premium keyword anchor (deciding WHICH figure is the GMP) and
    the discount-word sign check (deciding WHAT SIGN that figure has) are
    built on this, so there is exactly one notion of proximity here, not two
    independently-tuned ones.
    """
    if a.start() >= b.end():
        return a.start() - b.end()
    if b.start() >= a.end():
        return b.start() - a.end()
    return 0.0


def _discount_matches(snippet: str) -> list[re.Match]:
    """Real ("discount" is being reported), not denied, discount mentions.

    "No discount seen" must not count as a discount indicator at all — a
    _DISCOUNT_RE match whose span sits inside a _NEGATED_DISCOUNT_RE match is
    dropped before anything downstream ever sees it.
    """
    negated_spans = [(m.start(), m.end()) for m in _NEGATED_DISCOUNT_RE.finditer(snippet)]
    return [d for d in _DISCOUNT_RE.finditer(snippet)
            if not any(s <= d.start() and d.end() <= e for s, e in negated_spans)]


def _extract_gmp(snippet: str) -> float | None:
    """The GMP figure nearest a GMP/premium keyword, signed correctly, or
    None if no plausible figure is found.

    Proximity: real GMP phrasing overwhelmingly puts the number AFTER the
    keyword ("GMP is Rs 120", "premium of Rs 130"), so this prefers the
    nearest ₹/Rs-prefixed number that FOLLOWS a "GMP"/"premium"/"grey market"
    keyword within `_KEYWORD_WINDOW` characters. A plain nearest-by-distance
    search is not enough: a price band or issue price stated right before
    the keyword (e.g. "...band Rs 490 - Rs 500, GMP today is Rs 120") can sit
    textually closer to the keyword than the true GMP figure that follows
    it. Only falls back to nearest-in-either-direction if nothing follows
    within the window.

    Sign is resolved in three states, not two — round-3 fix. Widening
    `_DISCOUNT_WINDOW` to catch more phrasing was rejected on purpose: any
    fixed threshold is tuned to invented examples (this heuristic is
    UNVALIDATED against real search snippets — SERPER_API_KEY_IPO is not yet
    provisioned) and just moves the inversion boundary rather than removing
    it. So the window's job is narrowed to only what it was actually
    measured for — confidently attributing "discount" to a nearby figure —
    and anything it can't confidently place is dropped rather than guessed:

    - CONFIDENTLY NEGATIVE: an explicit minus sits immediately against the
      currency token, OR a real (non-negated) "discount" mention sits within
      `_DISCOUNT_WINDOW` characters of this figure.
    - CONFIDENTLY POSITIVE: no real "discount" mention anywhere in the
      snippet at all (a negated one, e.g. "no discount", does not count —
      see `_discount_matches`).
    - AMBIGUOUS: a real "discount" mention exists in the snippet but not
      within the window of this figure. Returns None for this figure — the
      caller drops the source. This is deliberately the SAME safety rule as
      the module's other "can't tell -> don't guess" behaviour: dropping one
      of two required sources yields an honest None, never a confidently
      wrong sign.
    """
    matches = list(_GMP_RE.finditer(snippet))
    if not matches:
        return None

    keyword_matches = list(_KEYWORD_RE.finditer(snippet))
    if keyword_matches:
        def _forward_gap(m: re.Match) -> float | None:
            gaps = [_gap(m, k) for k in keyword_matches if m.start() >= k.end()]
            return min(gaps) if gaps else None

        forward = [(m, _forward_gap(m)) for m in matches]
        forward = [(m, gap) for m, gap in forward
                   if gap is not None and gap <= _KEYWORD_WINDOW]
        if forward:
            match = min(forward, key=lambda pair: pair[1])[0]
        else:
            match = min(matches, key=lambda m: min(_gap(m, k) for k in keyword_matches))
    else:
        match = matches[0]

    try:
        value = float(match.group(2).replace(",", ""))
    except ValueError:
        return None

    if match.group(1):
        value = -value  # explicit minus on the figure itself -> confidently negative
    else:
        discount_matches = _discount_matches(snippet)
        if discount_matches:
            if any(_gap(match, d) <= _DISCOUNT_WINDOW for d in discount_matches):
                value = -value  # confidently negative
            else:
                return None  # ambiguous: "discount" is present but not attached to this figure
        # else: no real discount mention at all -> confidently positive, value unchanged

    if abs(value) > _MAX_PLAUSIBLE_GMP:
        return None
    return value


def _numbers_by_domain(results: list[dict]) -> dict[str, float]:
    """One number per domain — the first plausible one. An aggregator echoed
    across two result pages is one source, not two.

    Zero is a valid value here: a GMP of exactly 0 is a real, meaningful
    reading (grey-market demand has collapsed to nothing), so it must reach
    `out` like any other figure — it is absence of a *source*, not absence
    of premium, that is excluded.
    """
    out: dict[str, float] = {}
    for item in results or []:
        domain = urlparse(str(item.get("link") or "")).netloc.lower()
        if not domain or domain in out:
            continue
        value = _extract_gmp(str(item.get("snippet") or ""))
        if value is None:
            continue
        out[domain] = value
    return out


def fetch_gmp(company: str, issue_price: float | None = None) -> dict | None:
    """Median GMP across agreeing sources, or None. Never raises.

    None means "not collected" — never "no premium". A GMP of zero is a real
    and meaningful reading, which is exactly why absence must not render as 0.
    """
    from core.config import settings

    if not getattr(settings, "IPO_GMP_ENABLED", False):
        return None
    key = getattr(settings, "SERPER_API_KEY_IPO", "")
    if not key:
        logger.debug("[ipo_gmp] no SERPER_API_KEY_IPO — skipping, no call made")
        return None
    if not company:
        return None

    try:
        results = search_serper(f"{company} IPO GMP grey market premium today",
                                n=6, api_key=key)
    except Exception as exc:
        logger.warning("[ipo_gmp] search failed for %s (non-fatal): %s", company, exc)
        return None

    by_domain = _numbers_by_domain(results)
    min_sources = int(getattr(settings, "IPO_GMP_MIN_SOURCES", 2))
    if len(by_domain) < min_sources:
        logger.debug("[ipo_gmp] %s: %d source(s), need %d — discarding",
                     company, len(by_domain), min_sources)
        return None

    values = sorted(by_domain.values())
    tolerance = float(getattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25))
    lo, hi = values[0], values[-1]
    # Relative spread against the smaller-magnitude reading. Magnitude-based
    # (not a plain lo*(1+tolerance) bound) because GMP can be negative — a
    # discount of Rs 17 and a discount of Rs 15 must be able to agree, and a
    # sign-naive multiply-by-(1+tolerance) pushes a negative bound the wrong
    # way (it would flag even two IDENTICAL negative readings as disagreeing).
    if lo == 0 and hi == 0:
        pass  # both exactly zero -> trivially agree
    else:
        # NB an opposite-sign pair (one premium reading, one discount reading)
        # is rejected here too, but that's emergent, not a separate guard: for
        # opposite signs, spread = |hi - lo| >= 2 * reference always, so it
        # only survives if tolerance >= ~2.0 (200%) — unreachable at the
        # shipped 0.25. Raising gmp_agreement_tolerance toward/above 1.0
        # weakens this; if you do, add an explicit sign check here.
        reference = min(abs(lo), abs(hi))
        if reference == 0 or abs(hi - lo) > reference * tolerance:
            logger.debug("[ipo_gmp] %s: sources disagree (%s) — discarding",
                         company, values)
            return None

    gmp = float(statistics.median(values))
    pct = (gmp / issue_price * 100.0) if issue_price else None
    return {"gmp": gmp, "gmp_pct": pct, "sources": len(by_domain)}
