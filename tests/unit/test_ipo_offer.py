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
