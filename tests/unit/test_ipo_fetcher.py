"""Compass Phase C — IPO feed fetcher: normalization + degraded mode (spec §6.2/§8)."""
import json
from datetime import date

import services.data.fetchers.ipo as ipo_mod
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
