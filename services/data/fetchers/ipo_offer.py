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
  4. UNBALANCED PARENTHESES — 6 of 209 spine rows. NSE simply forgets the
     closing ")" on a trailing carve-out (PINELABS, LENSKART, REGAAL,
     BLUESTONE, TRANSRAILL), or emits a lone ")" with no "(" at all
     (WAKEFIT). The first draft refused every such row outright, which threw
     away six readable splits: in all six the two legs are fully stated
     BEFORE the malformed punctuation. `_strip_parens` is therefore
     depth-aware and defined for malformed input, and the honesty check moved
     to `_legs_survived` — if stripping removed a "Fresh Issue" / "Offer for
     Sale" heading, the row is unreadable (None) rather than a fabricated
     0.0/1.0 from a mangled sentence. `_parens_balanced` survives as a log
     signal only.
  5. AMOUNTS WITH NO "Rs." PREFIX — 17 of 209 spine rows, the single largest
     cause of the original 23% failure rate. NSE writes "Fresh Issue upto
     5000 million" with no currency on one or both legs. A number followed by
     a unit word is money; a share count in this feed always says "Equity
     Shares", so the two remain distinguishable. Unit words also appear
     pluralised ("8000 millions", NIVABUPA).
  6. THE ABBREVIATION "OFS" — NSDL states a pure offer-for-sale as
     "comprising OFS of 50,145,001 Equity Shares" and never spells the phrase
     out, so the heading regex must accept the word-bounded abbreviation.
  7. WHICH AMOUNT BELONGS TO A LEG. The figure for a leg is the FIRST amount
     after its heading, so `_parse_leg` takes the earliest-matching pattern
     rather than a fixed rupee/shares/bare priority. NIVABUPA's OFS clause is
     "up to 14,000 millions and Anchor Allocation 13,37,83,783 Equity
     Shares": a fixed priority would return the trailing anchor share count.

A NOTE ON WHAT IS NOT A PARSE FAILURE. 15 of the 209 rows disclose no split at
all in this row — 13 state one single total ("Initial Public Offer of up to
77,86,120 Equity Shares", STUDDS) and 2 carry no Issue Size row (IGIL,
ADANIENPP1). None is the correct answer for those, and widening the parser
until they produced a number would be fabricating the signal, not measuring it.

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
# NSE writes both "8000 million" and "8000 millions" (NIVABUPA). The trailing
# plural is stripped before the multiplier lookup rather than doubling the table.
_UNIT_WORDS = r"crores?|millions?|lakhs?|lacs?|thousands?"

_FRESH_RE = re.compile(r"fresh\s+issue", re.IGNORECASE)
# "OFS" is the abbreviation NSE uses when it never spells the phrase out at all
# (NSDL: "Initial Public Offer comprising OFS of 50,145,001 Equity Shares").
# Word-bounded so it cannot match inside a longer token.
_OFS_RE = re.compile(r"offer\s+for\s+sale|\bOFS\b", re.IGNORECASE)
_RUPEE_RE = re.compile(
    rf"rs\.?\s*([\d,]+(?:\.\d+)?)\s*({_UNIT_WORDS})?",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*equity\s*shares?", re.IGNORECASE)
# A bare "<number> <unit word>" with no "Rs." prefix. NSE omits the currency on
# one or both legs in 17 of the 209 spine rows - by far the largest single cause
# of the 23% parse-failure rate. It is unambiguously money: a share count in
# this feed always says "Equity Shares", never a unit word.
_BARE_UNIT_RE = re.compile(
    rf"([\d,]+(?:\.\d+)?)\s*({_UNIT_WORDS})\b", re.IGNORECASE)

_BLANK: dict[str, float | None] = {
    "ofs_amount": None, "fresh_amount": None, "ofs_share": None,
}


def _parens_balanced(text: str) -> bool:
    """False if `text` has an unmatched '(' or ')' anywhere, including a ')'
    that closes before any '(' opened. Retained for OBSERVABILITY only - NSE
    really does ship malformed Issue Size prose (6 of 209 spine rows) and the
    operator should be able to see that in the log. Correctness no longer rests
    on it: `_strip_parens` is depth-aware and `_legs_survived` is the check.
    """
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _strip_parens(text: str) -> str:
    r"""Remove parenthetical sub-portions (anchor/employee carve-outs) BEFORE
    any amount is extracted. This is the single easiest way to get a
    silently-wrong number: a naive regex over the raw sentence captures the
    parenthetical figure as if it were one of the two top-level legs.

    Depth-aware, one pass, and defined for malformed input - which matters,
    because NSE ships plenty of it:

      * NESTED groups are removed whole. The previous looped `\([^)]*\)`
        substitution stopped at the INNER ')', so "(including (anchor Rs. 999
        million) employee Rs. 888 million)" left "employee Rs. 888 million)"
        behind - and that leftover is the figure the leg then read.
      * An UNMATCHED '(' is treated as opening a group that runs to the end of
        the string. In all six spine rows of this shape NSE simply forgot the
        ')' on a trailing carve-out, so everything after it is exactly what
        should be dropped.
      * A STRAY ')' with no '(' open is dropped and the surrounding text kept.
        WAKEFIT ends with one and its carve-out is not parenthesised at all.

    Dropping-to-end is only safe because the caller checks `_legs_survived`:
    if the discarded span took a "Fresh Issue" / "Offer for Sale" heading with
    it, the sentence can no longer be read honestly and the answer is None.
    """
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth > 0:
                depth -= 1
                out.append(" ")     # keep a token separator behind the group
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _legs_survived(raw: str, stripped: str) -> bool:
    """True when stripping parentheticals removed no leg heading.

    THE safety property behind `_strip_parens`'s drop-to-end behaviour. If an
    unmatched '(' sat before a real leg, dropping through to end-of-string
    would delete that leg's heading - and the parse would then fall into the
    fresh-only or OFS-only branch and return a REAL-looking 0.0 or 1.0,
    asserting "the promoters sold nothing" on the strength of a punctuation
    accident. Same wrong-number-rather-than-absent class as total_x_nse_only
    and the GMP sign; refusing the row is the only honest answer.

    Compared with >= rather than ==: stripping can JOIN text across a removed
    group ("Fresh (x) Issue" -> "Fresh   Issue"), legitimately creating a
    heading that was not matchable before.
    """
    return (len(_FRESH_RE.findall(stripped)) >= len(_FRESH_RE.findall(raw))
            and len(_OFS_RE.findall(stripped)) >= len(_OFS_RE.findall(raw)))


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
    """(amount, unit) for one clause; unit is 'inr' or 'shares'.

    Whichever pattern matches EARLIEST in the clause wins, because a leg's own
    figure is the first amount stated after its heading. Position, not pattern
    priority, is what makes NIVABUPA read correctly: its OFS clause is
    "up to 14,000 millions and Anchor Allocation 13,37,83,783 Equity Shares",
    where a fixed rupee -> shares -> bare ordering would have returned the
    trailing anchor share count instead of the OFS figure ahead of it.

    An explicit "Rs." wins a positional tie: it starts one token earlier than
    the bare-unit match inside the same phrase ("Rs. 4,180 million"), and it is
    the more specific statement of the same number.
    """
    if not clause:
        return None, None

    candidates: list[tuple[int, float, str]] = []

    m = _RUPEE_RE.search(clause)
    if m:
        num = _to_number(m.group(1))
        if num is not None:
            mult = _UNIT_MULTIPLIERS.get(
                (m.group(2) or "").lower().rstrip("s"), 1.0)
            candidates.append((m.start(), num * mult, "inr"))

    m = _SHARE_RE.search(clause)
    if m:
        num = _to_number(m.group(1))
        if num is not None:
            candidates.append((m.start(), num, "shares"))

    m = _BARE_UNIT_RE.search(clause)
    if m:
        num = _to_number(m.group(1))
        if num is not None:
            mult = _UNIT_MULTIPLIERS.get(m.group(2).lower().rstrip("s"), 1.0)
            candidates.append((m.start(), num * mult, "inr"))

    if not candidates:
        return None, None
    _pos, amount, unit = min(candidates, key=lambda c: c[0])
    return amount, unit


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

    raw = text
    if not _parens_balanced(raw):
        # NSE genuinely ships malformed prose here (6 of 209 spine rows are a
        # forgotten ')'). Worth seeing in the log, but no longer a reason to
        # refuse the row: _strip_parens is defined for this input, and
        # _legs_survived below is what actually keeps the reading honest.
        logger.info(
            "[ipo_offer] unbalanced parentheses in Issue Size text - "
            "stripping depth-aware: %r", raw)

    text = _strip_parens(raw)
    if not _legs_survived(raw, text):
        logger.warning(
            "[ipo_offer] stripping parentheticals removed a leg heading - "
            "ofs_share unreadable rather than fabricated: %r", raw)
        return dict(_BLANK)
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
