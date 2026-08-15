"""PI Prospect P2 — OFS vs fresh-issue split, extracted from the free-text
"Issue Size" row of /api/ipo-detail's `issueInfo.dataList` (spec section 3
calls the split "the single strongest Ola/Ather discriminator": promoters
cashing out versus fresh capital entering the business; unlike GMP it is
disclosed, official, and free).

LIVE INVESTIGATION CORRECTION (2026-08-14): an earlier draft of this module
assumed `issueInfo` carried structured `freshIssue` / `offerForSale` keys.
A live probe across 14 symbols found no such keys anywhere. `issueInfo` is
shaped `{"symbol": ..., "dataList": [{"title": ..., "value": ...}, ...]}` —
about 39 prose rows — and the split lives ONLY inside the row whose `title`
is exactly "Issue Size", as one free-text sentence, e.g.:

    "Fresh Issue aggregating upto Rs. 4,800 million and Offer for Sale
     aggregating upto Rs. 20,000 million (including Employee Reservation
     Portion aggregating up to Rs. 12.50 million and Anchor Investor
     Portion of 46,768,854 Equity Shares)"

Three complications, each independently able to produce a silently wrong
number if skipped (verified against tests/fixtures/ipo_issue_info_shapes.json,
one real captured payload per shape):

  1. PARENTHETICALS. "(including ... 12.50 million)" and "(Including anchor
     portion of ...)" are sub-portions of one of the two legs, not a third
     leg. They are stripped BEFORE any amount is extracted, or a naive
     regex reads the parenthetical figure as the real one.
  2. MIXED UNITS. 3 of 8 sampled symbols state one leg in Rupees and the
     other in a raw share count (e.g. ARDEE: fresh in Rs., OFS in shares —
     the majority shape among rows that carry both legs). The two numbers
     are not comparable until one is converted via the issue price; without
     a price they are left unreconciled and the reading is None rather than
     a nonsense ratio built from incommensurable numbers.
  3. INDIAN DIGIT GROUPING. "1,99,75,000" is 19,975,000. Stripping every
     comma (not just every third digit) parses this correctly regardless of
     grouping style.

0.0 and 1.0 are REAL readings (pure fresh issue; pure offer-for-sale). None
means the split could not be read. Collapsing the two would turn "we could
not tell" into "the promoters kept everything", inverting the signal — same
dark-signal discipline as parse_bid_ladder (services/data/fetchers/
ipo_bids.py) and _normalise (services/data/fetchers/ipo.py).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_UNIT_MULTIPLIERS: dict[str, float] = {
    "crore": 1e7,
    "million": 1e6,
    "lakh": 1e5,
    "lac": 1e5,
    "thousand": 1e3,
}

_FRESH_RE = re.compile(r"fresh\s+issue", re.IGNORECASE)
_OFS_RE = re.compile(r"offer\s+for\s+sale", re.IGNORECASE)
_RUPEE_RE = re.compile(
    r"rs\.?\s*([\d,]+(?:\.\d+)?)\s*(crore|million|lakh|lac|thousand)?",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*equity\s*shares?", re.IGNORECASE)

_BLANK: dict[str, float | None] = {
    "ofs_amount": None, "fresh_amount": None, "ofs_share": None,
}


def _strip_parens(text: str) -> str:
    """Remove parenthetical sub-portions (anchor/employee carve-outs) BEFORE
    any amount is extracted. This is the single easiest way to get a
    silently-wrong number: a naive regex over the raw sentence captures the
    parenthetical figure as if it were one of the two top-level legs.
    Looped (not a single pass) in case a vintage nests parentheses, though
    none of the 8 sampled symbols do.
    """
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\([^)]*\)", " ", text)
    return text


def _to_number(raw: str) -> float | None:
    """'1,99,75,000' -> 19975000.0. Plain comma-stripping is correct
    regardless of Western (4,800) or Indian (1,99,75,000) digit grouping."""
    text = raw.replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_leg(clause: str) -> tuple[float | None, str | None]:
    """(amount, unit) for one clause; unit is 'inr' or 'shares'. Rupee is
    tried first: a share count is only meaningful once we know money isn't
    what's being stated."""
    if not clause:
        return None, None
    m = _RUPEE_RE.search(clause)
    if m:
        num = _to_number(m.group(1))
        if num is None:
            return None, None
        mult = _UNIT_MULTIPLIERS.get((m.group(2) or "").lower(), 1.0)
        return num * mult, "inr"
    m = _SHARE_RE.search(clause)
    if m:
        num = _to_number(m.group(1))
        return (num, "shares") if num is not None else (None, None)
    return None, None


def _issue_size_text(issue_info: dict) -> str | None:
    """The raw value of the row titled "Issue Size" (case/whitespace
    tolerant), or None if no such row exists — covers IGIL's `issueInfo: {}`
    and any dataList that doesn't carry the row at all."""
    data_list = issue_info.get("dataList")
    if not isinstance(data_list, list):
        return None
    for row in data_list:
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title") or "").split()).casefold()
        if title == "issue size":
            value = row.get("value")
            return str(value) if value is not None else ""
    return None


def parse_offer_split(issue_info: object, issue_price: float | None = None) -> dict:
    """Parse the fresh-issue / offer-for-sale split out of an
    /api/ipo-detail `issueInfo` dict. Never raises.

    Returns {"ofs_amount", "fresh_amount", "ofs_share"} — any may be None.
    `issue_price` (Rupees per share) is consulted ONLY when the two legs are
    stated in different units (one in Rupees, one in a share count); it is
    unused otherwise, including in the fresh-only and OFS-only cases where
    no reconciliation is needed.
    """
    if not isinstance(issue_info, dict):
        return dict(_BLANK)

    text = _issue_size_text(issue_info)
    if not text:
        return dict(_BLANK)

    text = _strip_parens(text)
    fresh_m = _FRESH_RE.search(text)
    ofs_m = _OFS_RE.search(text)

    if not fresh_m and not ofs_m:
        return dict(_BLANK)

    if fresh_m and ofs_m:
        if fresh_m.start() < ofs_m.start():
            fresh_clause = text[fresh_m.end():ofs_m.start()]
            ofs_clause = text[ofs_m.end():]
        else:
            ofs_clause = text[ofs_m.end():fresh_m.start()]
            fresh_clause = text[fresh_m.end():]
        fresh_amt, fresh_unit = _parse_leg(fresh_clause)
        ofs_amt, ofs_unit = _parse_leg(ofs_clause)
        if fresh_amt is None or ofs_amt is None:
            return {"ofs_amount": ofs_amt, "fresh_amount": fresh_amt, "ofs_share": None}

        if fresh_unit != ofs_unit:
            # Mixed units: reconcile the share-count leg to Rupees via the
            # issue price. Comparing a Rupee figure to a raw share count
            # directly would silently produce a meaningless ratio.
            if not issue_price or issue_price <= 0:
                return {"ofs_amount": ofs_amt, "fresh_amount": fresh_amt, "ofs_share": None}
            if fresh_unit == "shares":
                fresh_amt = fresh_amt * issue_price
            if ofs_unit == "shares":
                ofs_amt = ofs_amt * issue_price

        total = fresh_amt + ofs_amt
        if total <= 0:
            return {"ofs_amount": ofs_amt, "fresh_amount": fresh_amt, "ofs_share": None}
        return {"ofs_amount": ofs_amt, "fresh_amount": fresh_amt,
                "ofs_share": round(ofs_amt / total, 6)}

    if fresh_m:
        # Fresh-only: a disclosed pure fresh issue. ofs_share of 0.0 is a
        # REAL reading here, not "could not tell".
        fresh_amt, _unit = _parse_leg(text[fresh_m.end():])
        if fresh_amt is None or fresh_amt <= 0:
            return dict(_BLANK)
        return {"ofs_amount": 0.0, "fresh_amount": fresh_amt, "ofs_share": 0.0}

    # OFS-only: a disclosed pure offer-for-sale. ofs_share of 1.0 is a REAL
    # reading here, not "could not tell".
    ofs_amt, _unit = _parse_leg(text[ofs_m.end():])
    if ofs_amt is None or ofs_amt <= 0:
        return dict(_BLANK)
    return {"ofs_amount": ofs_amt, "fresh_amount": 0.0, "ofs_share": 1.0}
