"""PI Prospect P0 — bid-ladder parsing. Payload shapes verified live against
NSE 2026-08-11 for MOLBIO (spec section 11.2/11.4)."""
import services.data.fetchers.ipo_bids as bids_mod
from services.data.fetchers.ipo_bids import fetch_bid_ladder, parse_bid_ladder

_PAYLOAD = {
    "companyName": "MOLBIO",
    # NSE-only ladder: key `noOfTime`, and note `noOfsharesBid` (lowercase s).
    "bidDetails": [
        {"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)",
         "noOfSharesOffered": "2325145", "noOfsharesBid": "1312326",
         "noOfTime": "0.5644060908029391"},
        {"srNo": "1(a)", "category": "Foreign Institutional Investors(FIIs)",
         "noOfSharesOffered": "", "noOfsharesBid": "871110", "noOfTime": ""},
        {"srNo": "1(c)", "category": "Mutual funds",
         "noOfSharesOffered": "", "noOfsharesBid": "0", "noOfTime": ""},
        {"srNo": "2", "category": "Non Institutional Investors",
         "noOfSharesOffered": "1743860", "noOfsharesBid": "6284124",
         "noOfTime": "3.6035713876113906"},
        # Sub-band of NII — must NOT be mistaken for the NII row itself.
        {"srNo": "2.1", "category": "Non Institutional Investors(Bid amount of "
                                    "more than Ten Lakhs)",
         "noOfSharesOffered": "1162574", "noOfsharesBid": "3564342",
         "noOfTime": "3.0659054821456526"},
        {"srNo": "3", "category": "Retail Individual Investors(RIIs)",
         "noOfSharesOffered": "4069005", "noOfsharesBid": "9056556",
         "noOfTime": "2.2257421654679708"},
        {"srNo": "4", "category": "Employees",
         "noOfSharesOffered": "20519", "noOfsharesBid": "78030",
         "noOfTime": "3.8028169014084505"},
        {"srNo": None, "category": "Total", "noOfSharesOffered": "8158529.0",
         "noOfsharesBid": "1.6731036E7", "noOfTime": "2.05074174523373"},
    ],
    # All-exchange ladder: key `noOfTotalMeant`, `noOfShareOffered` (no s on
    # Share), and a HEADER ROW whose values are column labels.
    "activeCat": {
        "updateTime": "11-Aug-2026 17:00:56",
        "dataList": [
            {"srNo": "Sr.No.", "category": "Category",
             "noOfShareOffered": "No.of shares offered/reserved",
             "noOfSharesBid": "No. of shares bid for",
             "noOfTotalMeant": "No. of times of total meant for the category"},
            {"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)",
             "noOfShareOffered": "2325145", "noOfSharesBid": "3234672",
             "noOfTotalMeant": "1.3911700130529494"},
            {"srNo": "1(b)", "category": "Financial Institutions/ Banks",
             "noOfShareOffered": "", "noOfSharesBid": "245600",
             "noOfTotalMeant": "0.42"},
            {"srNo": "1(c)", "category": "Mutual funds",
             "noOfShareOffered": "", "noOfSharesBid": "218268",
             "noOfTotalMeant": ""},
            # Combined-ladder total: real figure per module docstring above
            # (25,437,636 all-exchange bids vs. 16,731,036 NSE-only).
            {"srNo": None, "category": "Total", "noOfShareOffered": "8158529.0",
             "noOfSharesBid": "25437636", "noOfTotalMeant": "3.117918"},
        ],
    },
    "demandGraph": {"totalBidAtCutOff": "7752114", "TOTAL_BIDS": "16731036"},
}


def test_parses_both_ladders_without_conflating_them():
    out = parse_bid_ladder(_PAYLOAD)
    # NSE-only vs all-exchange genuinely disagree — spec section 11.4.
    assert out["nse_only"]["qib"] == 0.5644060908029391
    assert out["combined"]["qib"] == 1.3911700130529494
    assert out["nse_only"]["total"] == 2.05074174523373
    assert out["nse_only"]["retail"] == 2.2257421654679708
    assert out["nse_only"]["employee"] == 3.8028169014084505
    assert out["updated_at"] == "11-Aug-2026 17:00:56"


def test_nii_sub_band_does_not_overwrite_the_nii_total():
    """srNo 2.1 is a sub-band of srNo 2 and shares its category prefix."""
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["nii"] == 3.6035713876113906


def test_header_row_is_skipped():
    """activeCat's first row carries column LABELS as values; parsing it as
    data would emit a garbage category."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert all(v is None or isinstance(v, float) for v in combined.values())


def test_blank_x_becomes_none_not_zero():
    """FII/MF lines report bid quantity but no multiple. Zero would be a lie
    (dark-signal pattern: absent means absent)."""
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["fii"] is None
    assert parse_bid_ladder(_PAYLOAD)["nse_only"]["mutual_fund"] is None


def test_cutoff_share_is_a_fraction_of_total_bids():
    assert round(parse_bid_ladder(_PAYLOAD)["cutoff_share"], 4) == 0.4633


def test_empty_payload_yields_all_none_and_never_raises():
    out = parse_bid_ladder({})
    assert out["cutoff_share"] is None
    assert set(out["combined"].values()) == {None}


def test_fetch_returns_none_when_nse_fails(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("NSE 403")
        def __exit__(self, *a): return False
    monkeypatch.setattr(bids_mod, "nse_session", lambda: _Boom())
    assert fetch_bid_ladder("MOLBIO") is None


def test_fetch_returns_none_when_req_fails(monkeypatch):
    """_req raises ConnectionError on non-2xx; it must degrade to None."""
    class _ReqFails:
        def _req(self, *a, **kw): raise ConnectionError("NSE non-2xx")
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(bids_mod, "nse_session", lambda: _ReqFails())
    assert fetch_bid_ladder("MOLBIO") is None


_STUB_PAYLOAD = {
    # Live shape verified 2026-08-12 against IGIL (listed 2024-12-20, a
    # heavily-subscribed IPO — QIB 31.5x per bidDetails below). For some
    # older listings NSE's activeCat degenerates to a two-row stub: the
    # header plus a single "Total" row of literal "0.00", no category
    # breakdown at all, and updateTime "Updated as on null".
    "companyName": "IGIL",
    "bidDetails": [
        {"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)",
         "noOfSharesOffered": "31911839", "noOfsharesBid": "1005448325",
         "noOfTime": "31.507063099685354"},
    ],
    "activeCat": {
        "updateTime": "Updated as on null",
        "dataList": [
            {"srNo": "Sr.No.", "category": "Category",
             "noOfShareOffered": "No.of shares offered/reserved",
             "noOfSharesBid": "No. of shares bid for",
             "noOfTotalMeant": "No. of times of total meant for the category"},
            {"srNo": None, "category": "Total", "noOfShareOffered": "0.0",
             "noOfSharesBid": "0.0", "noOfTotalMeant": "0.00"},
        ],
    },
    "demandGraph": {},
}


def test_placeholder_total_with_no_category_breakdown_is_rejected():
    """Recording that stub's `0.00` as `combined["total"]` would assert
    'nobody subscribed' about a hot issue — the exact inversion the
    dark-signal rule exists to prevent. A genuine combined ladder always
    carries qib/retail alongside total (true on every other symbol this
    fetcher has ever parsed), so total-only must be treated as unavailable.
    This is the single chokepoint every consumer of `combined`/`nse_only`
    passes through — the earlier fix inside scripts/ipo_backfill.py left
    the live _enrich_open_issues path (services/data/fetchers/ipo.py)
    exposed to writing this false zero into the morning brief."""
    out = parse_bid_ladder(_STUB_PAYLOAD)
    assert out["combined"]["total"] is None       # NOT 0.0
    assert out["combined"]["qib"] is None and out["combined"]["retail"] is None
    # nse_only has real data (qib present) here, so its total (absent from
    # this fixture) is unaffected by the guard — the rule applies uniformly
    # per-ladder, not by assuming combined is the only untrustworthy one.
    assert out["nse_only"]["qib"] == 31.507063099685354


def test_combined_total_carries_a_real_value():
    """The P1 predictor column. Previously only ever asserted `is None`, so a
    parser that silently stopped reading totals would not have been caught."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert combined["total"] is not None
    assert combined["total"] > 0


def test_dom_fi_is_parsed_as_its_own_category():
    """srNo 1(b). P2's capture ledger is its first consumer."""
    combined = parse_bid_ladder(_PAYLOAD)["combined"]
    assert "dom_fi" in combined
