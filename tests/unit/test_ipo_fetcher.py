"""Compass Phase C — IPO feed fetcher: normalization + degraded mode (spec §6.2/§8)."""
import json
from datetime import date

import pytest

import services.data.fetchers.ipo as ipo_mod
import services.data.fetchers.ipo_bids as bids_mod
from services.data.fetchers.ipo import load_ipo_cache, refresh_ipo_cache


class _FakeNSE:
    def __init__(self, past=None, current=None, upcoming=None, fail=False):
        self._past, self._current, self._upcoming = past or [], current or [], upcoming or []
        self._fail = fail

    def listPastIPO(self, from_date=None, to_date=None):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._past

    def listCurrentIPO(self):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._current

    def listUpcomingIPO(self):
        if self._fail:
            raise RuntimeError("NSE 403")
        return self._upcoming

    def exit(self):
        pass


_PAST_ROW = {
    "symbol": "NEWCO", "companyName": "NewCo Ltd", "series": "EQ",
    "listingDate": "15-Jun-2026", "issuePrice": "300 to 315",
    "qibSubscriptionTimes": "45.2", "retailSubscriptionTimes": "8.1",
    "noOfTimesSubscribed": "22.7",
}
_SME_ROW = {
    "symbol": "TINYCO", "companyName": "Tiny SME Ltd", "series": "SM",
    "listingDate": "20-Jun-2026", "issuePrice": "60",
}


def test_refresh_normalizes_and_excludes_sme(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(past=[_PAST_ROW, _SME_ROW],
                                         upcoming=[{"symbol": "SOON", "companyName": "Soon Ltd",
                                                    "series": "EQ", "issuePrice": "100"}]))
    result = refresh_ipo_cache(cache_path=cache)
    assert result["degraded"] is False
    past_syms = [r["symbol"] for r in result["past"]]
    assert past_syms == ["NEWCO"]                    # SME row dropped
    rec = result["past"][0]
    assert rec["listing_date"] == "2026-06-15"       # NSE date parsed to ISO
    assert rec["issue_price"] == 315.0               # upper band of "300 to 315"
    assert rec["qib_x"] == 45.2 and rec["retail_x"] == 8.1
    assert rec["status"] == "past"
    assert result["upcoming"][0]["status"] == "upcoming"


def test_degraded_mode_keeps_stale_cache(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    (tmp_path / "ipo.json").write_text(json.dumps({
        "fetched_at": "old", "degraded": False,
        "current": [], "upcoming": [],
        "past": [{"symbol": "OLDCO", "company": "Old Co", "series": "EQ",
                  "listing_date": "2026-05-01", "issue_price": 100.0,
                  "qib_x": None, "retail_x": None, "total_x": None, "status": "past"}],
    }), encoding="utf-8")
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(fail=True))
    result = refresh_ipo_cache(cache_path=cache)
    assert result["degraded"] is True
    assert result["past"][0]["symbol"] == "OLDCO"    # stale kept


def test_missing_subscription_fields_are_none(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    row = dict(_PAST_ROW)
    for k in ("qibSubscriptionTimes", "retailSubscriptionTimes", "noOfTimesSubscribed"):
        row.pop(k)
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(past=[row]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["qib_x"] is None and rec["retail_x"] is None and rec["total_x"] is None


def test_zero_total_subscription_is_treated_as_unavailable(tmp_path, monkeypatch):
    """NSE serves a literal 0.00 total on the raw list feed too (the same
    pathology already guarded for the ladder in parse_bid_ladder) — a bare
    0.0 with no category breakdown means unknown, not 'nobody bid'."""
    cache = str(tmp_path / "ipo.json")
    row = dict(_PAST_ROW)
    row["noOfTimesSubscribed"] = "0.00"
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(past=[row]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["total_x"] is None
    assert rec["total_x_nse_only"] is False


def test_feed_total_is_flagged_nse_only(tmp_path, monkeypatch):
    """`noOfTime`/`noOfTimesSubscribed` on the raw list feed is the NSE-only
    figure — the ladder's all-exchange `combined` total is the one the
    market actually quotes. A total that survives straight from the feed
    (no ladder enrichment) must be flagged so downstream renderers can
    qualify it instead of showing it as if it were the complete figure."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(past=[_PAST_ROW]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["total_x"] == 22.7
    assert rec["total_x_nse_only"] is True


def test_ladder_supplied_total_clears_the_nse_only_flag(tmp_path, monkeypatch):
    """Once _enrich_open_issues overwrites total_x with the ladder's
    all-exchange combined total, the NSE-only flag must clear — that figure
    is no longer the under-reporting NSE-only one."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda symbol: {
        "symbol": symbol, "updated_at": "11-Aug-2026 17:00:56",
        "combined": {"qib": 1.39, "retail": 2.22, "total": 2.05,
                     "fii": None, "dom_fi": None, "mutual_fund": None,
                     "nii": None, "employee": None},
        "nse_only": {k: None for k in
                     ("qib", "fii", "dom_fi", "mutual_fund", "nii",
                      "retail", "employee", "total")},
        "cutoff_share": 0.46})
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]
    assert rec["total_x"] == 2.05
    assert rec["total_x_nse_only"] is False


def test_load_missing_cache_returns_empty_degraded(tmp_path):
    out = load_ipo_cache(cache_path=str(tmp_path / "nope.json"))
    assert out == {"fetched_at": "", "degraded": True,
                   "current": [], "upcoming": [], "past": []}


_LIVE_CURRENT_ROW = {
    # Shape verified live against NSE 2026-08-11 (spec section 11.1).
    "symbol": "MILKYMIST", "companyName": "Milky Mist Dairy Food Limited",
    "series": "EQ", "status": "Active", "category": "Total",
    "issueStartDate": "11-Aug-2026", "issueEndDate": "13-Aug-2026",
    "issuePrice": "Rs.133 to Rs.140",
    "noOfSharesOffered": "8.1798244E7", "noOfsharesBid": "4.3481697E7",
    "noOfTime": "0.5315724992825029",
}


def test_current_issue_noOfTime_populates_total_x(tmp_path, monkeypatch):
    """NSE ships the total subscription x as `noOfTime`, not any of the three
    names the fetcher originally guessed."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    # _LIVE_CURRENT_ROW's window (11-13 Aug 2026) would be open on today's
    # real date in some test runs, which would otherwise route this call
    # through the live ladder enrichment added in Task 4. Stub the fetch AND
    # pin `on` past the close (2026-08-20) so the execution path is fixed by
    # the test, not by the wall clock: this test is about the raw-feed
    # noOfTime mapping, not the ladder.
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 20))["current"][0]
    assert rec["total_x"] == 0.5315724992825029
    assert rec["issue_price"] == 140.0        # upper band of "Rs.133 to Rs.140"


def test_issue_window_dates_are_parsed(tmp_path, monkeypatch):
    """The current/upcoming feeds carry issueStartDate/issueEndDate, NOT
    listingDate — the key the fetcher originally looked for (spec 11.1)."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    # See test_current_issue_noOfTime_populates_total_x — same reason.
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 20))["current"][0]
    assert rec["issue_start"] == "2026-08-11"
    assert rec["issue_end"] == "2026-08-13"
    assert rec["listing_date"] == ""          # genuinely absent on this feed


def test_past_rows_keep_their_listing_date(tmp_path, monkeypatch):
    """Regression guard: listPastIPO DOES carry listingDate and that path
    must survive the addition of the window keys."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(past=[_PAST_ROW]))
    rec = refresh_ipo_cache(cache_path=cache)["past"][0]
    assert rec["listing_date"] == "2026-06-15"


def test_open_issues_are_enriched_with_the_bid_ladder(tmp_path, monkeypatch):
    """Only OPEN issues are worth a per-symbol NSE call; upcoming ones have no
    bids yet and closed ones will not change."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    calls = []

    def _fake_ladder(symbol):
        calls.append(symbol)
        return {"symbol": symbol, "updated_at": "11-Aug-2026 17:00:56",
                "combined": {"qib": 1.39, "retail": 2.22, "total": 2.05,
                             "fii": None, "dom_fi": None, "mutual_fund": None,
                             "nii": None, "employee": None},
                "nse_only": {k: None for k in
                             ("qib", "fii", "dom_fi", "mutual_fund", "nii",
                              "retail", "employee", "total")},
                "cutoff_share": 0.46}

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", _fake_ladder)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]

    assert calls == ["MILKYMIST"]
    assert rec["qib_x"] == 1.39 and rec["retail_x"] == 2.22
    assert rec["cutoff_share"] == 0.46
    assert rec["bid_ladder"]["combined"]["qib"] == 1.39


def test_ladder_is_skipped_for_issues_not_open(tmp_path, monkeypatch):
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    calls = []
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder",
                        lambda s: calls.append(s) or None)
    # 2026-08-20 is after the 13-Aug close.
    refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 20))
    assert calls == []


def test_ladder_failure_leaves_the_row_intact(tmp_path, monkeypatch):
    """A dead ladder endpoint must not lose the total_x the feed already gave."""
    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]
    assert rec["total_x"] == 0.5315724992825029
    assert rec["qib_x"] is None


def test_past_feed_sme_is_excluded_via_securityType(tmp_path, monkeypatch):
    """listPastIPO carries NO `series` key — it marks type in `securityType`.
    The SME guard read only `series`, so 287 SME rows leaked into a universe
    the spec restricts to mainboard (verified against live NSE 2026-08-12)."""
    cache = str(tmp_path / "ipo.json")
    rows = [
        {"symbol": "MAINCO", "company": "Main Co", "securityType": "EQ",
         "listingDate": "15-Jun-2026", "issuePrice": "315"},
        {"symbol": "SMECO", "company": "SME Co", "securityType": "SME",
         "listingDate": "16-Jun-2026", "issuePrice": "60"},
        {"symbol": "815CHLI36", "company": "A Bond", "securityType": "N0",
         "listingDate": "17-Mar-2026", "issuePrice": "######"},
        {"symbol": "TTCO", "company": "T2T Co", "securityType": "BE",
         "listingDate": "18-Jun-2026", "issuePrice": "120"},
    ]
    monkeypatch.setattr(ipo_mod, "_make_nse_client", lambda: _FakeNSE(past=rows))
    out = [r["symbol"] for r in refresh_ipo_cache(cache_path=cache)["past"]]
    assert out == ["MAINCO", "TTCO"]      # SME and the bond both dropped


def test_open_issue_ladder_stub_does_not_write_a_false_zero(tmp_path, monkeypatch):
    """Regression for the vulnerability that motivated moving the
    placeholder-total guard into parse_bid_ladder (the chokepoint every
    ladder consumer passes through): _enrich_open_issues calls the REAL
    fetch_bid_ladder -> parse_bid_ladder chain (nothing about it is
    monkeypatched here, only the network layer underneath), so this proves
    the fix, not just the mock. If NSE serves the same degenerate `combined`
    stub observed live on IGIL for a currently-OPEN issue, the morning
    brief's ladder for an actively-bidding IPO must not end up with
    total_x = 0.0 — that would be a false claim of zero demand on a live
    issue, arguably higher-stakes than the historical backfill."""
    class _FakeResp:
        def json(self):
            return {
                "companyName": "MILKYMIST",
                "bidDetails": [],
                "activeCat": {
                    "updateTime": "Updated as on null",
                    "dataList": [
                        {"srNo": "Sr.No.", "category": "Category",
                         "noOfShareOffered": "x", "noOfSharesBid": "x",
                         "noOfTotalMeant": "x"},
                        {"srNo": None, "category": "Total",
                         "noOfShareOffered": "0.0", "noOfSharesBid": "0.0",
                         "noOfTotalMeant": "0.00"},
                    ],
                },
                "demandGraph": {},
            }

    class _FakeLadderNSE:
        def _req(self, *a, **kw):
            return _FakeResp()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(bids_mod, "nse_session", lambda: _FakeLadderNSE())

    cache = str(tmp_path / "ipo.json")
    monkeypatch.setattr(ipo_mod, "_make_nse_client",
                        lambda: _FakeNSE(current=[_LIVE_CURRENT_ROW]))
    rec = refresh_ipo_cache(cache_path=cache, on=date(2026, 8, 12))["current"][0]

    # noOfTime from the raw feed itself, untouched by the stubbed ladder.
    assert rec["total_x"] == 0.5315724992825029
    assert rec["qib_x"] is None


def test_a_closed_issue_keeps_its_final_ladder(monkeypatch):
    """The most valuable row in the capture ledger is a closed issue's FINAL
    ladder. Before this fix it was destroyed by the next 08:00 pass: the row is
    rebuilt from _normalise, and _enrich_open_issues only refetches OPEN issues.
    """
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    ladder = {"symbol": "MOLBIO",
              "combined": {"qib": 90.0, "retail": 12.0, "total": 40.0,
                           "dom_fi": 0.2, "fii": 1.0, "mutual_fund": 0.3,
                           "nii": 5.0, "employee": None},
              "nse_only": {"qib": 45.0, "total": 20.0},
              "cutoff_share": 0.46}

    previous = {"MOLBIO": {"symbol": "MOLBIO", "bid_ladder": ladder,
                           "cutoff_share": 0.46, "qib_x": 90.0,
                           "retail_x": 12.0, "total_x": 40.0,
                           "total_x_nse_only": False}}

    # Window ended yesterday => state is "closed", so no refetch happens.
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-12", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder",
                        lambda s: pytest.fail("a closed issue must not be refetched"))
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["qib_x"] == 90.0
    assert rows[0]["bid_ladder"]["combined"]["dom_fi"] == 0.2
    assert rows[0]["cutoff_share"] == 0.46


def test_a_failed_refetch_keeps_the_previous_ladder(monkeypatch):
    """An open issue whose fetch fails must not lose yesterday's numbers."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    previous = {"MOLBIO": {"symbol": "MOLBIO", "cutoff_share": 0.46,
                           "qib_x": 90.0, "total_x": 40.0,
                           "bid_ladder": {"combined": {"total": 40.0}}}}
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: None)
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["cutoff_share"] == 0.46


def test_budget_is_spent_only_on_a_successful_fetch(monkeypatch):
    """A run of dead-endpoint failures must not exhaust IPO_MAX_LADDER_FETCHES
    with zero enrichment (§9b). With the budget cap at 1, a failed fetch on
    the first open issue must not stop the second open issue from being
    enriched — the old code decremented the budget before checking the
    result, so one dead symbol could silently zero out the whole pass."""
    from core.config import settings
    import services.data.fetchers.ipo as ipo_mod

    monkeypatch.setattr(settings, "IPO_MAX_LADDER_FETCHES", 1)

    rows = [
        {"symbol": "DEADCO", "issue_start": "2026-08-12", "issue_end": "2026-08-14",
         "listing_date": "", "qib_x": None, "retail_x": None, "total_x": None,
         "total_x_nse_only": False},
        {"symbol": "LIVECO", "issue_start": "2026-08-12", "issue_end": "2026-08-14",
         "listing_date": "", "qib_x": None, "retail_x": None, "total_x": None,
         "total_x_nse_only": False},
    ]

    def _fake_ladder(symbol):
        if symbol == "DEADCO":
            return None
        return {"symbol": symbol,
                "combined": {"qib": 5.0, "retail": 3.0, "total": 4.0,
                             "dom_fi": None, "fii": None, "mutual_fund": None,
                             "nii": None, "employee": None},
                "nse_only": {}, "cutoff_share": 0.5}

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", _fake_ladder)
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13))

    assert rows[0]["total_x"] is None       # DEADCO's failed fetch, no data
    assert rows[1]["total_x"] == 4.0        # LIVECO still got its fetch


def test_a_carried_total_keeps_its_nse_only_qualifier():
    """An NSE-only total shown unqualified is a WRONG number, not an incomplete
    one — the qualifier must travel with the value it qualifies."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    previous = {"MOLBIO": {"symbol": "MOLBIO", "total_x": 20.0,
                           "total_x_nse_only": True}}
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-12", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]
    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)
    assert rows[0]["total_x"] == 20.0
    assert rows[0]["total_x_nse_only"] is True


def test_a_fresh_all_exchange_total_is_not_downgraded_by_a_stale_flag(monkeypatch):
    """The inverse case: a successful ladder fetch yields the all-exchange
    total with nse_only False, and carry-forward must not resurrect a stale
    True over it."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    previous = {"MOLBIO": {"symbol": "MOLBIO", "total_x": 20.0,
                           "total_x_nse_only": True}}
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-12",
             "issue_end": "2026-08-14", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: {
        "symbol": s, "combined": {"qib": 90.0, "retail": 12.0, "total": 40.0,
                                   "dom_fi": None, "fii": None,
                                   "mutual_fund": None, "nii": None,
                                   "employee": None},
        "nse_only": {}, "cutoff_share": 0.46})

    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["total_x_nse_only"] is False


def test_a_fresh_successful_fetch_wins_over_carry_forward(monkeypatch):
    """Global constraint: a fresh successful fetch must always win over
    carried-forward data. Give an open issue both a previous row with stale
    numbers AND a successful fetch that differs on every field, and assert
    the fresh values win throughout."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    previous = {"MOLBIO": {"symbol": "MOLBIO",
                           "bid_ladder": {"combined": {"total": 999.0}},
                           "cutoff_share": 0.99, "qib_x": 999.0,
                           "retail_x": 999.0, "total_x": 999.0,
                           "total_x_nse_only": True}}
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-12",
             "issue_end": "2026-08-14", "listing_date": "",
             "qib_x": None, "retail_x": None, "total_x": None,
             "total_x_nse_only": False}]

    fresh_ladder = {"symbol": "MOLBIO",
                    "combined": {"qib": 90.0, "retail": 12.0, "total": 40.0,
                                 "dom_fi": 0.2, "fii": 1.0, "mutual_fund": 0.3,
                                 "nii": 5.0, "employee": None},
                    "nse_only": {"qib": 45.0, "total": 20.0},
                    "cutoff_share": 0.46}
    monkeypatch.setattr(ipo_mod, "fetch_bid_ladder", lambda s: fresh_ladder)

    ipo_mod._enrich_open_issues(rows, date(2026, 8, 13), previous=previous)

    assert rows[0]["total_x"] == 40.0
    assert rows[0]["qib_x"] == 90.0
    assert rows[0]["retail_x"] == 12.0
    assert rows[0]["cutoff_share"] == 0.46
    assert rows[0]["bid_ladder"] == fresh_ladder
    assert rows[0]["total_x_nse_only"] is False


def test_capture_writes_one_snapshot_per_issue(tmp_path):
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.ipo.signals import IpoSignalStore

    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "cutoff_share": 0.46,
             "bid_ladder": {"combined": {"total": 40.0, "qib": 90.0,
                                         "dom_fi": 0.2},
                            "nse_only": {"total": 20.0}}}]

    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 1
    snaps = store.load_symbol("MOLBIO")
    assert len(snaps) == 1
    assert snaps[0].state == "open"
    assert snaps[0].combined["total"] == 40.0
    assert snaps[0].combined["dom_fi"] == 0.2
    assert snaps[0].cutoff_share == 0.46


def test_capture_skips_an_issue_with_no_ladder(tmp_path):
    """An upcoming issue has no bids. Writing an all-None snapshot would put a
    row in the ledger asserting a reading was taken when none was."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.ipo.signals import IpoSignalStore

    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "ARDEE", "issue_start": "2026-09-01",
             "issue_end": "2026-09-03", "listing_date": ""}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 0
    assert store.load_all() == []


def test_capture_is_off_when_the_flag_is_false(tmp_path, monkeypatch):
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod
    from core.config import settings
    from core.ipo.signals import IpoSignalStore

    monkeypatch.setattr(settings, "IPO_SIGNALS_ENABLED", False, raising=False)
    store = IpoSignalStore(base_dir=str(tmp_path))
    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "bid_ladder": {"combined": {"total": 40.0}}}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=store) == 0


def test_capture_never_raises_into_the_refresh(tmp_path, monkeypatch):
    """A dead ledger must not break the cache write the brief depends on."""
    from datetime import date
    import services.data.fetchers.ipo as ipo_mod

    class Boom:
        def append(self, snap):
            raise OSError("disk gone")

    rows = [{"symbol": "MOLBIO", "issue_start": "2026-08-10",
             "issue_end": "2026-08-14", "listing_date": "",
             "bid_ladder": {"combined": {"total": 40.0}}}]
    assert ipo_mod._capture_signals(rows, date(2026, 8, 13), store=Boom()) == 0
