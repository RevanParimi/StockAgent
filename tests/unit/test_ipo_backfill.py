"""PI Prospect P1 — outcome-curve maths against a synthetic tape."""
import pandas as pd

from core.ipo.outcomes import compute_outcomes, symbol_sessions


def _tape(symbol: str, closes: list[float], start="2026-06-15") -> pd.DataFrame:
    days = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({
        "symbol": [symbol] * len(closes),
        "series": ["EQ"] * len(closes),
        "date": [d.date().isoformat() for d in days],
        "open": closes, "close": closes,
    })


def test_returns_are_measured_against_issue_price_not_first_close():
    """A 'listing pop' is issue price to market. Measuring from the first
    close would silently discard the entire listing-day move - the single
    most important number in the whole dataset."""
    tape = _tape("NEWCO", [400.0, 410.0, 420.0, 430.0, 440.0])
    sessions = symbol_sessions(tape, "NEWCO")
    outcomes, _excess, n = compute_outcomes(sessions, issue_price=200.0,
                                            index_pct=lambda a, b: 0.0)
    assert n == 5
    assert outcomes["1"] == 100.0          # 400 vs 200 issue price
    assert outcomes["5"] == 120.0          # 440 vs 200


def test_immature_horizons_are_absent_not_zero():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, _e, n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                       issue_price=200.0,
                                       index_pct=lambda a, b: 0.0)
    assert n == 2
    assert "1" in outcomes
    assert "5" not in outcomes and "252" not in outcomes


def test_excess_subtracts_the_index_over_the_same_dates():
    tape = _tape("NEWCO", [220.0, 220.0, 220.0, 220.0, 220.0])
    outcomes, excess, _n = compute_outcomes(
        symbol_sessions(tape, "NEWCO"), issue_price=200.0,
        index_pct=lambda a, b: 4.0,        # index +4% over the same window
    )
    assert outcomes["5"] == 10.0
    assert excess["5"] == 6.0


def test_only_eq_series_rows_count():
    tape = pd.concat([_tape("NEWCO", [400.0, 410.0]),
                      pd.DataFrame({"symbol": ["NEWCO"], "series": ["BE"],
                                    "date": ["2026-06-17"], "open": [999.0],
                                    "close": [999.0]})])
    assert len(symbol_sessions(tape, "NEWCO")) == 2


def test_zero_or_missing_issue_price_yields_no_outcomes():
    tape = _tape("NEWCO", [400.0, 410.0])
    outcomes, excess, _n = compute_outcomes(symbol_sessions(tape, "NEWCO"),
                                            issue_price=0.0,
                                            index_pct=lambda a, b: 0.0)
    assert outcomes == {} and excess == {}


from datetime import date

import scripts.ipo_backfill as bf
from core.ipo.history import IpoHistoryStore, IpoRecord


def test_backfill_joins_feed_to_tape(tmp_path, monkeypatch):
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": 22.7, "qib_x": 45.2, "retail_x": 8.1},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    result = bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    assert result["written"] == 1
    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.symbol == "NEWCO"
    assert rec.outcomes["1"] == 100.0
    assert rec.sessions_available == 6


def test_backfill_is_idempotent(tmp_path, monkeypatch):
    """Re-running must not duplicate rows — outcomes mature over time, so this
    script is expected to be run repeatedly."""
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        # listPastIPO never carries bid data — total_x/qib_x/retail_x are
        # always None on the real feed. A fixture with total_x set (as this
        # test used to do) is a shape the real feed cannot produce, and it
        # is exactly why this test never caught the row-wipe bug (Finding 1).
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": None, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    assert len(IpoHistoryStore(base_dir=str(tmp_path)).load_all()) == 1


def test_backfill_preserves_prior_enriched_predictors(tmp_path, monkeypatch):
    """The past-IPO feed never carries bid data. A naive rebuild that upserts
    a fresh IpoRecord straight from the feed would overwrite the WHOLE row —
    including total_x/qib_x/retail_x that a separate enrich_predictors() pass
    already wrote — with None, destroying every enriched predictor on every
    re-run. The module docstring says "re-run it freely"; this proves that
    claim is actually true."""
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": None, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="NEWCO", company="NewCo Ltd",
                           listing_date="2026-06-15", issue_price=200.0,
                           total_x=69.91, qib_x=197.55, retail_x=7.95,
                           outcomes={"1": 5.0}))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))

    rows = IpoHistoryStore(base_dir=str(tmp_path)).load_all()
    assert len(rows) == 1
    rec = rows[0]
    assert rec.total_x == 69.91 and rec.qib_x == 197.55 and rec.retail_x == 7.95
    # Outcomes are recomputed fresh from the tape every run (that is the
    # point — horizons mature over time), so this is NOT expected to be
    # carried forward like the predictors are.
    assert rec.outcomes["1"] == 100.0


def test_symbols_that_never_traded_are_recorded_not_dropped(tmp_path, monkeypatch):
    """Survivorship guard (spec section 7 risk 5): an IPO with no tape is a
    fact about the market, not a row to discard."""
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        {"symbol": "GHOSTCO", "company": "Ghost Co", "listing_date": "2026-06-15",
         "issue_price": 200.0, "total_x": None, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: _tape("OTHER", [10.0]))
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))
    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.symbol == "GHOSTCO"
    assert rec.sessions_available == 0 and rec.outcomes == {}


def test_enrich_populates_predictors_from_the_ladder(tmp_path, monkeypatch):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="INDGN", listing_date="2024-05-13",
                           issue_price=100.0, outcomes={"1": 5.0}))

    monkeypatch.setattr(bf, "fetch_bid_ladder", lambda s: {
        "symbol": s, "updated_at": "",
        "combined": {"qib": 197.55, "retail": 7.95, "total": 69.91,
                     "fii": None, "dom_fi": None, "mutual_fund": None,
                     "nii": None, "employee": None},
        "nse_only": {k: None for k in
                     ("qib", "fii", "dom_fi", "mutual_fund", "nii",
                      "retail", "employee", "total")},
        "cutoff_share": None})

    result = bf.enrich_predictors(store)
    assert result["enriched"] == 1
    rec = store.load_all()[0]
    assert rec.total_x == 69.91 and rec.qib_x == 197.55 and rec.retail_x == 7.95
    assert rec.outcomes == {"1": 5.0}          # curves untouched


def test_enrich_skips_rows_that_already_have_predictors(tmp_path, monkeypatch):
    """Resumability: the pass costs one throttled NSE call per row, so a
    re-run must not repeat work it already did."""
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="DONE", total_x=12.0, outcomes={"1": 1.0}))
    calls = []
    monkeypatch.setattr(bf, "fetch_bid_ladder", lambda s: calls.append(s) or None)
    result = bf.enrich_predictors(store)
    assert calls == [] and result["skipped"] == 1


def test_enrich_leaves_the_row_intact_when_the_ladder_is_unavailable(tmp_path, monkeypatch):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="GHOST", outcomes={"1": 2.0}))
    monkeypatch.setattr(bf, "fetch_bid_ladder", lambda s: None)
    result = bf.enrich_predictors(store)
    assert result["failed"] == 1
    rec = store.load_all()[0]
    assert rec.total_x is None                 # absent, never 0
    assert rec.outcomes == {"1": 2.0}


def test_enrich_rejects_a_placeholder_total_with_no_category_breakdown(tmp_path, monkeypatch):
    """Live NSE (verified 2026-08-12 against IGIL, listed 2024-12-20): for
    some older listings the `combined` ladder (activeCat.dataList) is a
    stub — a single "Total" row of literal "0.00" with `updateTime:
    "Updated as on null"` and no QIB/retail breakdown at all. The real
    subscription data still exists (bidDetails/nse_only shows IGIL at
    31.5x QIB), it just isn't in the ladder this fetcher reads.

    The guard itself now lives in parse_bid_ladder
    (services/data/fetchers/ipo_bids.py) — the chokepoint every ladder
    consumer passes through, not just this script — so `fetch_bid_ladder`
    already returns `total: None` for a stub, never the literal `0.0`
    (see tests/unit/test_ipo_bids.py for that guard's own unit test, and
    tests/unit/test_ipo_fetcher.py::test_open_issue_ladder_stub_does_not_write_a_false_zero
    for the live open-issue path this also protects). This test documents
    enrich_predictors' side of the resulting contract: given a ladder
    already shaped as the fetch layer actually produces it, a total-only
    outcome must not survive as a written predictor.
    """
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="IGIL", outcomes={"1": 12.9856}))
    monkeypatch.setattr(bf, "fetch_bid_ladder", lambda s: {
        "symbol": s, "updated_at": "Updated as on null",
        "combined": {"qib": None, "retail": None, "total": None,
                     "fii": None, "dom_fi": None, "mutual_fund": None,
                     "nii": None, "employee": None},
        "nse_only": {"qib": 31.507063099685354, "retail": None, "total": None,
                     "fii": None, "dom_fi": None, "mutual_fund": None,
                     "nii": None, "employee": None},
        "cutoff_share": None})
    result = bf.enrich_predictors(store)
    assert result["failed"] == 1 and result["enriched"] == 0
    rec = store.load_all()[0]
    assert rec.total_x is None                 # NOT 0.0 — the dark-signal rule
    assert rec.qib_x is None and rec.retail_x is None
    assert rec.outcomes == {"1": 12.9856}
