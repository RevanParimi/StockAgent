"""Compass Phase C — IPO feed fetcher: normalization + degraded mode (spec §6.2/§8)."""
import json

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
    rec = refresh_ipo_cache(cache_path=cache)["current"][0]
    assert rec["total_x"] == 0.5315724992825029
    assert rec["issue_price"] == 140.0        # upper band of "Rs.133 to Rs.140"
