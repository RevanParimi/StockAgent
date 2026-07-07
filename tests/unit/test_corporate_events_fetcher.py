"""Compass Phase A — corporate-events calendar fetcher with degraded mode."""
import json
from datetime import date

import services.data.fetchers.corporate_events as ce


class _FakeNSE:
    """Stands in for nse.NSE — returns canned boardMeetings/actions."""
    def __init__(self, download_folder=None):
        pass

    def boardMeetings(self, symbol):
        if symbol == "BROKEN":
            raise RuntimeError("NSE 403")
        return [
            {"bm_date": "15-Jul-2026", "bm_purpose": "Financial Results", "bm_symbol": symbol},
            {"bm_date": "20-Aug-2026", "bm_purpose": "Fund Raising", "bm_symbol": symbol},
        ]

    def actions(self, symbol):
        return [{"subject": "Dividend - Rs 8 Per Share", "exDate": "10-Jul-2026"}]

    def exit(self):
        pass


def _patch_nse(monkeypatch):
    monkeypatch.setattr(ce, "_make_nse_client", lambda: _FakeNSE())


def test_refresh_normalises_board_meetings(tmp_path, monkeypatch):
    _patch_nse(monkeypatch)
    cache = tmp_path / "events.json"
    result = ce.refresh_events_calendar(["INFY"], cache_path=str(cache))
    events = result["events"]["INFY"]
    assert events[0]["date"] == "2026-07-15"
    assert events[0]["kind"] == "results"
    assert events[1]["kind"] == "meeting"
    assert result["degraded"] == []
    assert json.loads(cache.read_text(encoding="utf-8"))["events"]["INFY"]


def test_refresh_degraded_keeps_stale_entry(tmp_path, monkeypatch):
    _patch_nse(monkeypatch)
    cache = tmp_path / "events.json"
    stale = {
        "fetched_at": "2026-07-01T00:00:00",
        "degraded": [],
        "events": {"BROKEN": [{"symbol": "BROKEN", "date": "2026-07-20",
                                "kind": "results", "desc": "old entry"}]},
    }
    cache.write_text(json.dumps(stale), encoding="utf-8")
    result = ce.refresh_events_calendar(["BROKEN"], cache_path=str(cache))
    assert "BROKEN" in result["degraded"]
    assert result["events"]["BROKEN"][0]["desc"] == "old entry"   # stale kept


def test_fetch_corp_actions_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("nse import failed")
    monkeypatch.setattr(ce, "_make_nse_client", boom)
    assert ce.fetch_corp_actions("MARUTI") == []


def test_next_results_event():
    calendar = {"events": {"INFY": [
        {"symbol": "INFY", "date": "2026-07-01", "kind": "results", "desc": "past"},
        {"symbol": "INFY", "date": "2026-07-15", "kind": "results", "desc": "future"},
        {"symbol": "INFY", "date": "2026-07-10", "kind": "meeting", "desc": "not results"},
    ]}}
    ev = ce.next_results_event("INFY", date(2026, 7, 6), calendar)
    assert ev is not None and ev.date == "2026-07-15"
    assert ce.next_results_event("TCS", date(2026, 7, 6), calendar) is None


def test_next_results_event_unsorted_and_corrupt_entries():
    calendar = {"events": {"INFY": [
        {"symbol": "INFY", "date": "2026-09-01", "kind": "results", "desc": "later"},
        {"symbol": "INFY", "date": "not-a-date", "kind": "results", "desc": "corrupt"},
        {"symbol": "INFY", "date": "2026-07-15", "kind": "results", "desc": "earliest future"},
    ]}}
    ev = ce.next_results_event("INFY", date(2026, 7, 6), calendar)
    assert ev is not None and ev.date == "2026-07-15"
