"""PI Prospect P1 — outcome-curve maths against a synthetic tape."""
import pandas as pd
import pytest

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


def test_backfill_preserves_prior_ofs_share(tmp_path, monkeypatch):
    """Same defect class as test_backfill_preserves_prior_enriched_predictors,
    now for ofs_share: listPastIPO never carries the OFS/fresh split either,
    so a plain re-run of the base backfill must carry a prior enrich_ofs
    result forward rather than silently reset it to None."""
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
                           ofs_share=0.62, outcomes={"1": 5.0}))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))

    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.ofs_share == 0.62
    assert rec.total_x == 69.91 and rec.qib_x == 197.55 and rec.retail_x == 7.95


def test_backfill_preserves_prior_issue_price(tmp_path, monkeypatch):
    """I2 (third instance of the a578ac6 defect class): the live spine already
    holds rows with issue_price null, proving a vintage of listPastIPO can
    genuinely serve no price for a symbol. If a later vintage drops the price
    for a symbol that USED to have one, a plain --since re-run must not wipe
    it — issue_price is not recoverable from the tape, and compute_outcomes
    refuses to compute outcomes/excess without it, so losing the price here
    would silently destroy the whole outcome curve too."""
    tape = _tape("NEWCO", [400.0] * 6)
    monkeypatch.setattr(bf, "_load_past_ipos", lambda since, until: [
        # This vintage of the feed has NO price for NEWCO.
        {"symbol": "NEWCO", "company": "NewCo Ltd", "listing_date": "2026-06-15",
         "issue_price": None, "total_x": None, "qib_x": None, "retail_x": None},
    ])
    monkeypatch.setattr(bf, "_load_tape", lambda end: tape)
    monkeypatch.setattr(bf, "build_index_pct", lambda a, b: (lambda s, e: 0.0))

    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="NEWCO", company="NewCo Ltd",
                           listing_date="2026-06-15", issue_price=200.0,
                           total_x=69.91, qib_x=197.55, retail_x=7.95,
                           outcomes={"1": 5.0}))

    bf.run_backfill(base_dir=str(tmp_path), on=date(2026, 8, 12))

    rec = IpoHistoryStore(base_dir=str(tmp_path)).load_all()[0]
    assert rec.issue_price == 200.0            # carried forward, not wiped
    # And the carried-forward price actually fed compute_outcomes, so the
    # outcome curve is NOT nulled out alongside a "missing" price.
    assert rec.outcomes["1"] == 100.0           # 400 vs the carried 200.0


def test_enrich_ofs_populates_the_split_from_the_detail_feed(tmp_path, monkeypatch):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="LEAP", issue_price=53.0, outcomes={"1": 5.0}))

    monkeypatch.setattr(bf, "_fetch_issue_info", lambda symbol: {
        "dataList": [{"title": "Issue Size",
                      "value": "Fresh Issue aggregating upto Rs. 4,800 million "
                               "and Offer for Sale aggregating upto Rs. 20,000 million"}]
    })

    result = bf.enrich_ofs(store)
    assert result["updated"] == 1
    rec = store.load_all()[0]
    assert rec.ofs_share == pytest.approx(0.806452, abs=1e-6)
    assert rec.outcomes == {"1": 5.0}          # curves untouched
    assert rec.issue_price == 53.0             # untouched columns survive


def test_enrich_ofs_skips_rows_that_already_have_the_split(tmp_path, monkeypatch):
    """Resumability: the pass costs one throttled NSE call per row, so a
    re-run must not repeat work it already did."""
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="DONE", ofs_share=0.5, outcomes={"1": 1.0}))
    calls = []
    monkeypatch.setattr(bf, "_fetch_issue_info", lambda s: calls.append(s) or None)
    result = bf.enrich_ofs(store)
    assert calls == [] and result["pending"] == 0


def test_enrich_ofs_leaves_the_row_intact_when_the_split_is_unreadable(tmp_path, monkeypatch):
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="IGIL", outcomes={"1": 2.0}))
    monkeypatch.setattr(bf, "_fetch_issue_info", lambda s: {})   # IGIL shape
    result = bf.enrich_ofs(store)
    assert result["failed"] == 1 and result["updated"] == 0
    rec = store.load_all()[0]
    assert rec.ofs_share is None               # absent, never a fabricated 0/1
    assert rec.outcomes == {"1": 2.0}


def test_enrich_ofs_never_wipes_columns_it_did_not_touch(tmp_path, monkeypatch):
    """The one thing that must not go wrong (a578ac6's defect class): the OFS
    pass touches ONE row and must not disturb the untouched row, nor any
    column on the touched row it did not itself set."""
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="LEAP", issue_price=53.0, total_x=12.3,
                           qib_x=30.1, retail_x=4.5, outcomes={"1": 8.0, "5": 10.0}))
    store.append(IpoRecord(symbol="UNTOUCHED", total_x=2.0, ofs_share=0.9))

    monkeypatch.setattr(bf, "_fetch_issue_info", lambda symbol: {
        "dataList": [{"title": "Issue Size",
                      "value": "Fresh Issue aggregating upto Rs. 4,800 million "
                               "and Offer for Sale aggregating upto Rs. 20,000 million"}]
    })

    result = bf.enrich_ofs(store)
    assert result["updated"] == 1

    rows = {r.symbol: r for r in store.load_all()}
    leap = rows["LEAP"]
    assert leap.ofs_share == pytest.approx(0.806452, abs=1e-6)
    assert leap.total_x == 12.3 and leap.qib_x == 30.1 and leap.retail_x == 4.5
    assert leap.outcomes == {"1": 8.0, "5": 10.0}
    assert leap.issue_price == 53.0

    untouched = rows["UNTOUCHED"]
    assert untouched.total_x == 2.0 and untouched.ofs_share == 0.9


def test_enrich_ofs_flushes_progress_before_a_later_failure(tmp_path, monkeypatch):
    """Round-2 fix: the docstring used to claim 'resumable by design' while
    only writing once at the very end — self-contradictory, since nothing
    written means nothing to skip on the next run. Progress must actually
    reach disk periodically (every _OFS_FLUSH_EVERY rows), so an interrupted
    run keeps what it completed and only re-fetches the still-in-flight
    batch, not the whole pass (~200 throttled NSE calls on a live run)."""
    monkeypatch.setattr(bf, "_OFS_FLUSH_EVERY", 2)

    store = IpoHistoryStore(base_dir=str(tmp_path))
    for symbol in ("A", "B", "C", "D", "E"):
        store.append(IpoRecord(symbol=symbol, outcomes={"1": 1.0}))

    ok_info = {"dataList": [{"title": "Issue Size",
                             "value": "Fresh Issue aggregating upto Rs. 100 million "
                                      "and Offer for Sale aggregating upto Rs. 300 million"}]}

    def _fetch(symbol: str):
        if symbol == "D":
            raise RuntimeError("simulated interruption (e.g. an API cutoff)")
        return ok_info

    monkeypatch.setattr(bf, "_fetch_issue_info", _fetch)

    with pytest.raises(RuntimeError):
        bf.enrich_ofs(store)

    rows = {r.symbol: r for r in store.load_all()}
    # A and B formed the first full batch (_OFS_FLUSH_EVERY=2 here) and were
    # flushed to disk BEFORE D raised.
    assert rows["A"].ofs_share == pytest.approx(0.75)
    assert rows["B"].ofs_share == pytest.approx(0.75)
    # C succeeded but was still sitting in the in-flight batch (only 1 of 2)
    # when D raised, so it was never flushed and is lost — the honest,
    # documented cost of flushing every N rows instead of every single row.
    assert rows["C"].ofs_share is None
    assert rows["D"].ofs_share is None
    assert rows["E"].ofs_share is None       # never reached at all
    # Nothing else about the untouched rows was disturbed.
    for symbol in ("C", "D", "E"):
        assert rows[symbol].outcomes == {"1": 1.0}


def test_upsert_many_with_retry_recovers_from_a_transient_permission_error(tmp_path, monkeypatch):
    """Round-3 fix: enrich_ofs's periodic flush calls store.upsert_many(),
    which rewrites the whole file via tmp.replace() exactly like upsert()
    does -- the same OneDrive-synced-working-copy race that
    _upsert_with_retry exists to paper over for the per-row path (§9b). A
    transient PermissionError on the first attempt must be retried, not
    propagated, or a routine sync-lock race kills the whole ~200-call
    throttled --ofs pass outright."""
    store = IpoHistoryStore(base_dir=str(tmp_path))
    store.append(IpoRecord(symbol="AAA"))

    real_upsert_many = store.upsert_many
    calls = []

    def _flaky_upsert_many(recs):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("WinError 5: simulated OneDrive lock race")
        return real_upsert_many(recs)

    monkeypatch.setattr(store, "upsert_many", _flaky_upsert_many)
    monkeypatch.setattr(bf.time, "sleep", lambda s: None)   # don't actually wait

    written = bf._upsert_many_with_retry(store, [IpoRecord(symbol="AAA", total_x=1.0)])
    assert written == 1
    assert len(calls) == 2                          # failed once, retried, succeeded
    assert store.load_all()[0].total_x == 1.0        # the retried write actually landed


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
