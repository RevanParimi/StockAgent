"""PI Prospect P2 — OFS/fresh-issue split parser.

The real payload carries no `freshIssue` / `offerForSale` keys (an earlier
draft of this parser assumed it did). The split lives only as free prose in
the "Issue Size" row of `issueInfo.dataList`. Every shape below is a real
captured payload from tests/fixtures/ipo_issue_info_shapes.json — a parser
green against one invented string is the exact failure mode this project has
already been bitten by (see test_backfill_is_idempotent's history).
"""
import json
import pathlib

import pytest

from services.data.fetchers.ipo_offer import parse_offer_split

_FIXTURE = json.loads(
    pathlib.Path("tests/fixtures/ipo_issue_info_shapes.json").read_text(encoding="utf-8")
)


def _issue_info(symbol: str) -> dict:
    return _FIXTURE[symbol]["issueInfo"]


# ---------------------------------------------------------------------------
# Real captured payloads, one per observed shape
# ---------------------------------------------------------------------------

def test_both_legs_in_rupees():
    """LEAP: 'Fresh Issue ... Rs. 4,800 million and Offer for Sale ... Rs.
    20,000 million' -- and the parenthetical anchor/employee carve-out must
    NOT be read as a third leg."""
    out = parse_offer_split(_issue_info("LEAP"))
    assert out["fresh_amount"] == pytest.approx(4_800e6)
    assert out["ofs_amount"] == pytest.approx(20_000e6)
    assert out["ofs_share"] == pytest.approx(0.806452, abs=1e-6)


def test_both_legs_in_share_counts():
    """TECHNOCRAF: 'Fresh Issue of up to 9,505,000 equity shares and Offer
    for Sale of up to 2,376,000 equity shares'."""
    out = parse_offer_split(_issue_info("TECHNOCRAF"))
    assert out["fresh_amount"] == pytest.approx(9_505_000)
    assert out["ofs_amount"] == pytest.approx(2_376_000)
    assert out["ofs_share"] == pytest.approx(0.2, abs=1e-3)


def test_mixed_units_without_issue_price_is_none():
    """ARDEE: fresh leg in Rs., OFS leg in a raw share count. Without a
    price to reconcile them, comparing the two numbers directly would be
    comparing incommensurable units -- the reading must be None, not a
    number computed from nonsense."""
    out = parse_offer_split(_issue_info("ARDEE"))
    assert out["ofs_share"] is None
    # The raw legs are still surfaced even though they can't be compared.
    assert out["fresh_amount"] == pytest.approx(3_200e6)
    assert out["ofs_amount"] == pytest.approx(19_975_000)


def test_mixed_units_reconciled_via_issue_price():
    """Same ARDEE payload, now with the issue price (Rs. 53, the upper band)
    supplied so the share leg can be converted to Rupees and compared."""
    out = parse_offer_split(_issue_info("ARDEE"), issue_price=53.0)
    assert out["ofs_share"] == pytest.approx(0.248593, abs=1e-6)


def test_fresh_only_is_a_real_zero():
    """MVELECTRO: 'Fresh Issue aggregating upto Rs. 2900 million (Including
    anchor portion of 30,70,587 Equity Shares)' -- no OFS leg at all. 0.0 is
    a real disclosed reading (nobody is selling down), not "could not tell".
    """
    out = parse_offer_split(_issue_info("MVELECTRO"))
    assert out["ofs_share"] == 0.0
    assert out["fresh_amount"] == pytest.approx(2_900e6)
    assert out["ofs_amount"] == 0.0


def test_ofs_only_is_a_real_one():
    """LCL: 'Offer for Sale of up to 25,931,407 Equity Shares. (Including
    ...)' -- no fresh leg. 1.0 is a real disclosed reading (pure OFS)."""
    out = parse_offer_split(_issue_info("LCL"))
    assert out["ofs_share"] == 1.0
    assert out["ofs_amount"] == pytest.approx(25_931_407)
    assert out["fresh_amount"] == 0.0


def test_empty_issue_info_is_unreadable():
    """IGIL: `issueInfo` present but `{}` -- no dataList, no Issue Size row,
    nothing to read. None, not a fabricated 0.0 or 1.0."""
    out = parse_offer_split(_issue_info("IGIL"))
    assert out == {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}


def test_every_fixture_shape_stays_within_bounds():
    """Guard against a parser that only works on hand-picked shapes: run all
    six real shapes and check every non-None ofs_share is a valid share."""
    for symbol, entry in _FIXTURE.items():
        out = parse_offer_split(entry["issueInfo"], issue_price=53.0)
        if out["ofs_share"] is not None:
            assert 0.0 <= out["ofs_share"] <= 1.0, symbol


# ---------------------------------------------------------------------------
# Unreadable input, in every shape this function can be handed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("junk", [
    None, "", {}, "not a split at all", [],
    {"dataList": "not a list"},
    {"dataList": []},
    {"dataList": [{"title": "Issue Size", "value": "no numbers or legs here"}]},
])
def test_unreadable_input_is_none_not_zero(junk):
    out = parse_offer_split(junk)
    assert out == {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}


def test_a_zero_total_is_none_not_a_division_error():
    info = {"dataList": [{"title": "Issue Size",
                          "value": "Fresh Issue aggregating upto Rs. 0 million "
                                   "and Offer for Sale aggregating upto Rs. 0 million"}]}
    out = parse_offer_split(info)
    assert out["ofs_share"] is None


def test_issue_size_title_match_is_case_and_whitespace_tolerant():
    info = {"dataList": [{"title": "  issue   SIZE  ",
                          "value": "Fresh Issue aggregating upto Rs. 100 million "
                                   "and Offer for Sale aggregating upto Rs. 300 million"}]}
    out = parse_offer_split(info)
    assert out["ofs_share"] == pytest.approx(0.75)


def test_a_row_with_null_title_does_not_crash_the_scan():
    """dataList rows commonly carry `title: null` (the SEBI-circular
    boilerplate row observed in every real fixture) ahead of Issue Size."""
    info = {"dataList": [
        {"title": None, "value": "some boilerplate"},
        {"title": "Issue Size",
         "value": "Fresh Issue aggregating upto Rs. 100 million "
                  "and Offer for Sale aggregating upto Rs. 300 million"},
    ]}
    out = parse_offer_split(info)
    assert out["ofs_share"] == pytest.approx(0.75)


def test_unbalanced_parens_yields_none_not_a_fabricated_zero():
    """An unmatched '(' before the OFS clause makes the naive
    \\([^)]*\\) strip regex consume through to the NEXT ')' it finds,
    however far away -- deleting the OFS heading and its figure entirely,
    not just the intended carve-out. parse_offer_split would then take the
    fresh-only branch and return ofs_share=0.0, asserting "no promoter
    selling" when the truth is "we could not read it". 0.0 is a real
    reading, which is exactly why it must never be fabricated from a
    parsing accident -- the same wrong-number-not-absent failure class as
    total_x_nse_only (Task 3) and the GMP sign (Task 8)."""
    info = {"dataList": [{"title": "Issue Size",
                          "value": "Fresh Issue aggregating upto Rs. 100 million "
                                   "(Note: subject to approval and Offer for Sale "
                                   "aggregating upto Rs. 300 million (including "
                                   "Anchor Investor Portion of 50,000 Equity Shares)"}]}
    out = parse_offer_split(info)
    assert out == {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}


def test_balanced_parens_with_a_carve_out_still_parses_normally():
    """Regression guard: the balance check must not make ordinary,
    well-formed input unreadable — only genuinely unbalanced text."""
    info = {"dataList": [{"title": "Issue Size",
                          "value": "Fresh Issue aggregating upto Rs. 100 million "
                                   "and Offer for Sale aggregating upto Rs. 300 million "
                                   "(including Anchor Investor Portion of 50,000 "
                                   "Equity Shares)"}]}
    out = parse_offer_split(info)
    assert out["ofs_share"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Real shapes that the parser MISSED. Diagnosed 2026-08-18 by re-fetching all
# 48 spine rows with ofs_share=None: the 23% failure rate was three concrete
# bugs, not an irreducible property of NSE's prose. Every text below is the
# live captured value, not an invented string.
# ---------------------------------------------------------------------------

def test_bare_million_amounts_parse_without_an_rs_prefix():
    """RUBICON: 'Fresh Issue upto 5000 million and ... offer for sale of up to
    8774.99 million'. NSE omits 'Rs.' on one or both legs in 17 of the 209
    spine rows — the single largest cause of the failure rate. A number
    followed by a unit word is money; a share count always says 'Equity
    Shares'."""
    out = parse_offer_split(_issue_info("RUBICON"))
    assert out["fresh_amount"] == pytest.approx(5_000e6)
    assert out["ofs_amount"] == pytest.approx(8_774.99e6)
    assert out["ofs_share"] == pytest.approx(8774.99 / (5000 + 8774.99), abs=1e-6)


def test_bare_million_fresh_leg_reconciles_against_a_share_count_ofs_leg():
    """CAPILLARY: fresh '3,450 million' (no 'Rs.') + OFS '9,228,796 Equity
    Shares'. Mixed units still need the issue price; the point here is that the
    fresh leg is now readable at all."""
    out = parse_offer_split(_issue_info("CAPILLARY"), issue_price=577.0)
    assert out["fresh_amount"] == pytest.approx(3_450e6)
    assert out["ofs_amount"] == pytest.approx(9_228_796 * 577.0)
    assert 0.0 < out["ofs_share"] < 1.0


def test_one_leg_with_rs_and_one_without_are_the_same_unit():
    """OMNI: 'Rs. 4,180 million' vs a bare '1,650 million'. Both are Rupees, so
    no issue price is needed — treating the bare leg as a share count would
    have demanded one and then produced a nonsense ratio."""
    out = parse_offer_split(_issue_info("OMNI"))
    assert out["ofs_share"] == pytest.approx(1650 / (4180 + 1650), abs=1e-6)


def test_plural_millions_is_a_unit_word():
    """NIVABUPA: '8000 millions' and '14,000 millions'."""
    out = parse_offer_split(_issue_info("NIVABUPA"))
    assert out["fresh_amount"] == pytest.approx(8_000e6)
    assert out["ofs_amount"] == pytest.approx(14_000e6)


def test_bare_million_fresh_only_is_a_real_zero():
    """ARSSBL: 'Fresh Issue up to 7450 million' and nothing else."""
    out = parse_offer_split(_issue_info("ARSSBL"))
    assert out["fresh_amount"] == pytest.approx(7_450e6)
    assert out["ofs_share"] == 0.0


def test_bare_million_ofs_only_is_a_real_one():
    """CARRARO: 'Initial Public Offer for Sale up to 12,500 million'."""
    out = parse_offer_split(_issue_info("CARRARO"))
    assert out["ofs_amount"] == pytest.approx(12_500e6)
    assert out["ofs_share"] == 1.0


def test_an_unclosed_paren_after_both_legs_still_parses():
    """PINELABS: NSE simply forgot the closing ')'. Both legs are fully stated
    BEFORE the stray '(', so refusing the whole row threw away a readable
    split. Six spine rows are this shape. Dropping an unmatched '(' through to
    end-of-string is safe precisely because the leg keywords survive it — the
    invariant asserted in the two tests below."""
    out = parse_offer_split(_issue_info("PINELABS"), issue_price=221.0)
    assert out["fresh_amount"] == pytest.approx(20_800e6)
    assert out["ofs_amount"] == pytest.approx(82_348_779 * 221.0)
    assert 0.0 < out["ofs_share"] < 1.0


def test_a_stray_close_paren_with_no_open_still_parses():
    """WAKEFIT: one ')' and no '(' at all, and the anchor carve-out is not
    parenthesised. The first share-count match after the OFS heading is the
    real OFS figure, not the anchor portion that follows it."""
    out = parse_offer_split(_issue_info("WAKEFIT"), issue_price=195.0)
    assert out["fresh_amount"] == pytest.approx(3_771.78e6)
    assert out["ofs_amount"] == pytest.approx(46_754_405 * 195.0)


def test_the_abbreviation_ofs_counts_as_an_offer_for_sale():
    """NSDL: 'comprising OFS of 50,145,001 Equity Shares' — the words 'offer
    for sale' never appear. A pure OFS reads 1.0 with no issue price needed."""
    out = parse_offer_split(_issue_info("NSDL"))
    assert out["ofs_amount"] == pytest.approx(50_145_001)
    assert out["ofs_share"] == 1.0


def test_a_single_total_with_no_split_disclosed_stays_none():
    """STUDDS: 'Initial Public Offer of up to 77,86,120 Equity Shares'. There
    is no split in this row to read. 13 spine rows are this shape and they are
    NOT parse failures — they are non-disclosures, and None is the correct,
    honest answer. Widening the parser until this produced a number would be
    fabricating the signal."""
    out = parse_offer_split(_issue_info("STUDDS"))
    assert out == {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}


def test_a_third_employee_leg_does_not_displace_the_ofs_figure():
    """URBANCO: 'Fresh Issue upto 4,695 Million and Offer for Sale upto 14,280
    Million and Employee Reservation Portion upto 25 Million'. The OFS clause
    runs to end-of-string, so the first amount in it — not the employee
    portion trailing it — is the OFS leg."""
    out = parse_offer_split(_issue_info("URBANCO"))
    assert out["ofs_amount"] == pytest.approx(14_280e6)
    assert out["ofs_share"] == pytest.approx(14280 / (4695 + 14280), abs=1e-6)


def test_nested_parentheticals_are_removed_whole():
    """Synthetic (no spine row nests today), but the depth-aware strip that
    recovers the unbalanced rows above must not regress into the old looped
    single-pass behaviour, which leaves the outer group's tail behind.
    The carve-out sits BEFORE the real figure and states its own 'Rs.' amount,
    so the old single-pass leftover ('employee Rs. 888 million)') is what the
    fresh leg would read — a wrong number, not a stray character.
    """
    info = {"dataList": [{"title": "Issue Size",
                          "value": "Fresh Issue (including (anchor Rs. 999 million) "
                                   "employee Rs. 888 million) aggregating upto "
                                   "Rs. 100 million and Offer for Sale aggregating "
                                   "upto Rs. 300 million"}]}
    out = parse_offer_split(info)
    assert out["fresh_amount"] == pytest.approx(100e6)
    assert out["ofs_amount"] == pytest.approx(300e6)
    assert out["ofs_share"] == pytest.approx(0.75)


def test_stripping_that_would_swallow_a_leg_keyword_refuses():
    """The safety property that makes dropping an unmatched '(' acceptable: if
    the discarded span contains a leg heading, the sentence can no longer be
    read honestly and the answer is None — never a fabricated 0.0 claiming the
    promoters sold nothing."""
    info = {"dataList": [{"title": "Issue Size",
                          "value": "Fresh Issue aggregating upto Rs. 100 million "
                                   "(subject to Offer for Sale aggregating upto "
                                   "Rs. 300 million"}]}
    out = parse_offer_split(info)
    assert out == {"ofs_amount": None, "fresh_amount": None, "ofs_share": None}
