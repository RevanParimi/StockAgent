"""PR-006: the daily company-event feed.

The invariants, each with expected values written by hand from the card and
from the recorded NSE payload (tests/fixtures/company_events/), not read
back from the code:

- `published_at` is the source's own date, never the fetch time; an item
  with no usable date is stored with `published_at` None and never counts as
  new;
- one stock's item is never filed under another: an NSE row must name the
  code asked for, an article must mention the company, and the model never
  names the stock;
- the same item fetched on two runs is stored once and classified once;
- every stored event cites an item it was given; ungrounded, invalid and
  malformed answers are dropped and counted;
- the symbol cap and the daily query cap hold over any number of runs;
- a source, quota or classifier failure logs and skips, the next run asks
  again, and the run never raises;
- a member reads events only for their own stocks and the shelf.

Transports are blocked by tests/hermetic.py. NSE is a fake client behind the
real fetcher, Serper a fake `requests.post` or the feed's search seam, and
the model a fake call.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.shared.schemas.events import CompanyEvent
from core.config import settings
from core.events import classify as cl
from core.events import feed
from core.events import sources as src
from core.events.store import EventStore, valid_symbol
from services.data.fetchers import nse_announcements

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 22, 8, 15, tzinfo=IST)        # Thursday, a trading day
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "company_events"
REPO = Path(__file__).resolve().parents[2]
# The feed's own seams, as shipped, before any fixture replaces them.
REAL_SEARCH_NEWS = feed._search_news
REAL_NEWS_QUERY = feed._news_query


def _nse() -> dict:
    return json.loads((FIX / "nse_maruti_20261022.json").read_text("utf-8"))


def _news() -> list[dict]:
    return json.loads((FIX / "serper_news_maruti.json").read_text("utf-8"))["news"]


def _norm_news(rows: list[dict]) -> list[dict]:
    """What search_serper_news_status returns for Serper rows."""
    return [{k: r.get(k, "") for k in ("title", "snippet", "link", "date", "source")} for r in rows]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_ITEM_LINE = re.compile(r"^\[(\d+)\] (.+?) \| published (.+?) \| (.*)$", re.M)


class FakeModel:
    """Answers every item in the prompt: results/positive/high when its title
    says "result", else other/neutral/low, with the item's own title as the
    sentence (so every figure is grounded). Titles containing a string in
    `unrelated` are answered "not about this company"."""

    def __init__(self, unrelated=(), fail=False, extra=None):
        self.calls: list[list[str]] = []
        self.unrelated = tuple(unrelated)
        self.fail = fail
        self.extra = extra or {}

    def __call__(self, system: str, user: str) -> str:
        found = _ITEM_LINE.findall(user)
        self.calls.append([title for _, _, _, title in found])
        if self.fail:
            raise RuntimeError("provider unavailable")
        events = []
        for n, _label, _published, title in found:
            if any(u in title for u in self.unrelated):
                events.append({"item": int(n), "about_company": False})
                continue
            res = "result" in title.lower()
            events.append({"item": int(n), "about_company": True, "what": title[:200],
                           "category": "results" if res else "other",
                           "direction": "positive" if res else "neutral",
                           "materiality": "high" if res else "low", **self.extra})
        return json.dumps({"events": events})


class FakeNse:
    """The nse client's two methods. Announcements are filtered by filing day
    as NSE does; board meetings are returned whole, as NSE does without a range."""

    def __init__(self, by_symbol: dict, fail: set | None = None):
        self.by_symbol = by_symbol
        self.fail = fail or set()
        self.calls: list[tuple] = []

    def announcements(self, symbol=None, from_date=None, to_date=None, **_):
        self.calls.append(("announcements", symbol, from_date, to_date))
        if ("announcements", symbol) in self.fail:
            raise ConnectionError("NSE 503")
        rows = self.by_symbol.get(symbol, {}).get("announcements", [])
        def filed(r):
            return datetime.strptime(r["an_dt"], "%d-%b-%Y %H:%M:%S").date()
        return [r for r in rows if from_date.date() <= filed(r) <= to_date.date()]

    def boardMeetings(self, symbol=None, **_):
        self.calls.append(("board_meetings", symbol))
        if ("board_meetings", symbol) in self.fail:
            raise ConnectionError("NSE 503")
        return list(self.by_symbol.get(symbol, {}).get("board_meetings", []))


def _event(symbol="MARUTI", eid="nse:1", published="2026-10-21T15:39:05+05:30", **kw) -> CompanyEvent:
    base = dict(id=eid, symbol=symbol, what="Board approved results", category="results",
                direction="positive", materiality="high", source="nse_announcement",
                published_at=published, fetched_at="2026-10-22T08:15:00+05:30")
    base.update(kw)
    return CompanyEvent(**base)


@pytest.fixture()
def feed_env(tmp_path, monkeypatch):
    """The feed on: a temp store, fake NSE, fake search, fake model, and every
    seam recorded."""
    for name, value in (("EVENTS_ENABLED", True), ("EVENTS_DATA_DIR", str(tmp_path / "events")),
                        ("EVENTS_MAX_SYMBOLS", 60), ("EVENTS_NEWS_QUERIES_PER_DAY", 60),
                        ("EVENTS_LOOKBACK_DAYS", 7), ("EVENTS_MAX_ITEMS_PER_SYMBOL", 24),
                        ("EVENTS_MAX_ITEMS_PER_CALL", 12), ("EVENTS_SEEN_DAYS", 30),
                        ("EVENTS_INGEST_ON_RESULTS", True)):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(nse_announcements, "_SLEEP_BETWEEN_CALLS", 0)
    env = {
        "tracked": [("MARUTI", "held")],
        "identity": {},
        "codes": {},
        "nse": FakeNse({"MARUTI": _nse()}),
        "news": {"MARUTI": (_norm_news(_news()), "ok")},
        "searches": [],
        "model": FakeModel(),
        "managed": {"MARUTI": "automobile"},
        "ingested": [],
        "store": EventStore(tmp_path / "events"),
    }
    monkeypatch.setattr(feed, "tracked_symbols", lambda: list(env["tracked"]))
    monkeypatch.setattr(feed, "_identity_issue", lambda s, on: env["identity"].get(s, ""))
    monkeypatch.setattr(feed, "_nse_code", lambda s, on: env["codes"].get(s, s))
    monkeypatch.setattr(feed, "_make_nse", lambda: env["nse"])
    monkeypatch.setattr(feed, "_close_nse", lambda n: None)
    monkeypatch.setattr(feed, "_news_query", lambda s: (
        f"Maruti Suzuki India Limited {s} NSE India company news" if s == "MARUTI"
        else f"{s} NSE India company news", "Maruti Suzuki India Limited" if s == "MARUTI" else ""))

    def search(query):
        symbol = query.split(" NSE India")[0].split()[-1]
        env["searches"].append(symbol)
        return env["news"].get(symbol, ([], "empty"))
    monkeypatch.setattr(feed, "_search_news", search)
    monkeypatch.setattr(cl, "_call_llm", lambda system, user: env["model"](system, user))
    monkeypatch.setattr(feed, "_managed_enabled_sectors", lambda: dict(env["managed"]))
    monkeypatch.setattr(feed, "_ingest", lambda s, sector: env["ingested"].append((s, sector)) or 1)
    monkeypatch.setattr(feed, "_search_usage", lambda: {"calls": 7, "limit": 2500})
    return env


def _run(env, now=NOW, slot="am") -> dict:
    return feed.run_event_feed(slot, now=now, store=env["store"])


# ---------------------------------------------------------------------------
# Sources: publication time comes from the source
# ---------------------------------------------------------------------------

def test_recorded_announcements_keep_nse_ids_and_filing_times():
    items, foreign, ahead = src.announcement_items(_nse()["announcements"], "MARUTI", NOW)
    assert foreign == 0 and ahead == 0
    assert [(i.source_id, i.published_at, i.published_raw) for i in items] == [
        ("nse:106823400", "2026-10-21T15:39:05+05:30", "21-Oct-2026 15:39:05"),
        ("nse:106819161", "2026-10-15T19:13:00+05:30", "15-Oct-2026 19:13:00"),
        ("nse:106815691", "2026-10-13T13:15:47+05:30", "13-Oct-2026 13:15:47"),
    ]
    assert items[0].announcement_id == "106823400"
    assert items[0].title == "Analysts/Institutional Investor Meet/Con. Call Updates"
    assert items[0].url.startswith("https://nsearchives.nseindia.com/corporate/MARUTI")


def test_an_announcement_for_another_code_is_dropped_and_counted():
    rows = _nse()["announcements"]
    other = dict(rows[0], symbol="MARUTIHOLD", seq_id="999")
    items, foreign, _ = src.announcement_items([other, rows[1]], "MARUTI", NOW)
    assert foreign == 1
    assert [i.source_id for i in items] == ["nse:106819161"]


def test_sort_date_fallback_is_read_year_first():
    """FIX-004's trap: "2026-10-08 17:10:00" read day-first is 10 Aug."""
    row = dict(_nse()["announcements"][0], an_dt="", sort_date="2026-10-08 17:10:00")
    (item,), _, _ = src.announcement_items([row], "MARUTI", NOW)
    assert item.published_at == "2026-10-08T17:10:00+05:30"
    assert item.published_raw == "2026-10-08 17:10:00"


@pytest.mark.parametrize("an_dt, sort_date", [
    ("", ""),                                   # no date at all
    ("sometime last week", ""),                 # unreadable
    ("22/10/2026 08:00", "08-10-2026 17:10"),   # neither in NSE's formats
])
def test_an_unreadable_filing_time_is_none_never_the_fetch_time(an_dt, sort_date):
    row = dict(_nse()["announcements"][0], an_dt=an_dt, sort_date=sort_date)
    (item,), _, ahead = src.announcement_items([row], "MARUTI", NOW)
    assert item.published_at is None and ahead == 0


@pytest.mark.parametrize("an_dt, sort_date", [
    ("22-Oct-2026 08:25:01", ""),               # 10 minutes 1 second after the fetch
    ("22-Oct-2026 09:00:00", ""),               # 45 minutes after
    ("23-Oct-2026 10:00:00", "2026-10-23 10:00:00"),   # tomorrow, both fields
    ("", "2026-10-22 09:00:00"),                # only sort_date, 45 minutes after
])
def test_a_filing_timed_after_the_fetch_is_left_for_a_later_run(an_dt, sort_date):
    """Not stored undated: the row is counted and not an item, so a later
    fetch (the 7-day window brings it back) dates it."""
    row = dict(_nse()["announcements"][0], an_dt=an_dt, sort_date=sort_date)
    assert src.announcement_items([row], "MARUTI", NOW) == ([], 0, 1)
    later = NOW + timedelta(days=1, hours=2)
    (item,), _, ahead = src.announcement_items([row], "MARUTI", later)
    expected = {"22-Oct-2026 08:25:01": "2026-10-22T08:25:01+05:30",
                "22-Oct-2026 09:00:00": "2026-10-22T09:00:00+05:30",
                "23-Oct-2026 10:00:00": "2026-10-23T10:00:00+05:30",
                "": "2026-10-22T09:00:00+05:30"}[an_dt]
    assert (item.published_at, item.source_id, ahead) == (expected, "nse:106823400", 0)


def test_a_filing_stamped_seconds_after_the_fetch_clock_is_kept():
    for an_dt, expected in (("22-Oct-2026 08:16:30", "2026-10-22T08:16:30+05:30"),
                            ("22-Oct-2026 08:25:00", "2026-10-22T08:25:00+05:30")):  # exactly 10 min
        row = dict(_nse()["announcements"][0], an_dt=an_dt)
        (item,), _, ahead = src.announcement_items([row], "MARUTI", NOW)
        assert (item.published_at, ahead) == (expected, 0)


def test_a_board_meeting_timed_after_the_fetch_is_left_and_keeps_one_identity():
    """Two rows for the 05-Nov meeting, filed 18:41:20 and 18:41:25. Fetched
    at 18:40 neither is an item; fetched at 18:42 both are, as one item dated
    by the earlier; the next morning gives the same id. The id depends only
    on the rows, never on the clock."""
    base = _nse()["board_meetings"][0]
    rows = [dict(base, bm_timestamp="22-Oct-2026 18:41:20", bm_date="05-Nov-2026",
                 bm_purpose="Board Meeting Intimation"),
            dict(base, bm_timestamp="22-Oct-2026 18:41:25", bm_date="05-Nov-2026",
                 bm_purpose="Financial Results")]
    since = date(2026, 10, 15)
    early = datetime(2026, 10, 22, 18, 31, 19, tzinfo=IST)      # 18:41:20 is 10 min 1 s later
    assert src.board_meeting_items(rows, "MARUTI", early, since) == ([], 0, 2)
    at = datetime(2026, 10, 22, 18, 42, tzinfo=IST)
    (item,), _, ahead = src.board_meeting_items(rows, "MARUTI", at, since)
    assert (item.published_at, item.title, ahead) == (
        "2026-10-22T18:41:20+05:30", "Board Meeting Intimation / Financial Results", 0)
    morning = datetime(2026, 10, 23, 8, 15, tzinfo=IST)
    (again,), _, _ = src.board_meeting_items(rows, "MARUTI", morning, since)
    assert again.source_id == item.source_id
    assert item.source_id == "nsebm:" + hashlib.sha1(b"MARUTI|05-Nov-2026|2026-10-22").hexdigest()[:16]


def test_board_meeting_rows_merge_and_date_by_filing_never_meeting_day():
    """The recorded rows: two filed 08-Oct-2026 for the 27-Oct meeting (an
    intimation and "Financial Results"), one filed 15-Jul for 31-Jul."""
    items, foreign, ahead = src.board_meeting_items(_nse()["board_meetings"], "MARUTI", NOW,
                                                    since=date(2026, 10, 1))
    assert foreign == 0 and ahead == 0
    assert len(items) == 1
    item = items[0]
    assert item.published_at == "2026-10-08T12:44:21+05:30"      # the earlier filing
    assert item.published_raw == "08-Oct-2026 12:44:21"
    assert "2026-10-27" not in (item.published_at or "")         # not the meeting day
    assert item.title == "Financial Results / Board Meeting Intimation"
    assert "(meeting on 27-Oct-2026)" in item.text
    assert item.source_id.startswith("nsebm:")
    # A later run sees the same rows: the same identity.
    again, _, _ = src.board_meeting_items(list(reversed(_nse()["board_meetings"])), "MARUTI", NOW,
                                       since=date(2026, 10, 1))
    assert [i.source_id for i in again] == [item.source_id]


def test_board_meetings_outside_the_filing_window_or_for_another_code():
    rows = _nse()["board_meetings"]
    items, _, _ = src.board_meeting_items(rows, "MARUTI", NOW, since=date(2026, 10, 15))
    assert items == []                                            # all filed before 15 Oct
    items, foreign, _ = src.board_meeting_items(rows, "M&M", NOW, since=date(2026, 7, 1))
    assert items == [] and foreign == 3


def test_an_undated_board_meeting_is_kept_only_for_an_upcoming_meeting():
    row = dict(_nse()["board_meetings"][0], bm_timestamp="")
    (item,), _, _ = src.board_meeting_items([row], "MARUTI", NOW, since=date(2026, 10, 15))
    assert item.published_at is None
    old = dict(_nse()["board_meetings"][2], bm_timestamp="")     # meeting 31-Jul
    assert src.board_meeting_items([old], "MARUTI", NOW, since=date(2026, 10, 15))[0] == []


def test_news_dates_are_the_sources_age_counted_back_in_ist():
    items = src.news_items(_norm_news(_news()), NOW)
    by_title = {}
    for i in items:
        by_title.setdefault(i.title, i)
    # "10 hours ago" at 08:15 IST on 22 Oct is 22:15 on 21 Oct.
    assert by_title["Maruti Suzuki Q2 results: net profit rises 12% to Rs 3,500 crore"].published_at == "2026-10-21"
    assert by_title["Tata Motors shares slip after JLR wholesales update"].published_at == "2026-10-22"
    assert by_title["Maruti Suzuki raises prices across models from November"].published_at == "2026-10-20"
    undated = by_title["Maruti Suzuki EV launch: what we know so far"]
    assert undated.published_at is None and undated.published_raw == ""
    # No link: dropped. The same URL with other tracking parameters: once.
    assert "Maruti Suzuki to expand Kharkhoda plant capacity" not in by_title
    assert len(items) == 5
    assert len({i.source_id for i in items}) == 5


def test_news_age_property_against_an_independent_clock():
    """For any age in hours, the stored day is the IST day of fetch minus age,
    computed here without the feed's code."""
    rng = random.Random(6)
    for _ in range(200):
        hours = rng.randint(0, 200)
        now = NOW + timedelta(minutes=rng.randint(-600, 600))
        (item,) = src.news_items([{"title": "Maruti Suzuki", "link": "https://news.example.com/a",
                                   "date": f"{hours} hours ago"}], now)
        expected = (now.astimezone(IST) - timedelta(hours=hours)).date().isoformat()
        assert item.published_at == expected


def test_a_future_news_date_is_none():
    (item,) = src.news_items([{"title": "Maruti Suzuki", "link": "https://news.example.com/a",
                               "date": "Oct 30, 2026"}], NOW)
    assert item.published_at is None


@pytest.mark.parametrize("names, codes, text, expected", [
    (["Tata Elxsi Limited"], {"TATAELXSI"}, "Tata Motors shares slip after JLR update", False),
    (["Tata Elxsi Limited"], {"TATAELXSI"}, "Tata Elxsi wins a design order", True),
    (["Mahindra & Mahindra Limited"], {"M&M"}, "M&M shares rise 3% on SUV demand", True),
    (["Tata Consultancy Services Limited"], {"TCS"}, "TCS signs a deal with a European bank", True),
    (["Vodafone Idea Limited"], {"IDEA"}, "a bright idea for the markets", False),
    (["State Bank of India"], {"SBIN"}, "State Bank raises Rs 10,000 crore via bonds", True),
    (["Bank of Baroda"], {"BANKBARODA"}, "Bank of Baroda cuts lending rates", True),
    (["Bank of Baroda"], {"BANKBARODA"}, "Bank stocks fall as yields rise", False),
    (["Maruti Suzuki India Limited"], {"MARUTI"}, "Maruti Suzuki's sales rise", True),
    (["Adani Ports and Special Economic Zone Limited"], {"ADANIPORTS"}, "Adani Ports handles record cargo", True),
    ([], {"MARUTI"}, "Maruti hikes prices", False),        # no name known, ticker not in capitals
])
def test_an_article_must_mention_the_company(names, codes, text, expected):
    item = src.SourceItem("news", "news:x", text, "", "https://news.example.com/x", None, None, "")
    assert src.mentions_company(item, src.name_phrases(names), codes) is expected


# ---------------------------------------------------------------------------
# Classifier: only what the items support
# ---------------------------------------------------------------------------

def _items():
    ann, _, _ = src.announcement_items(_nse()["announcements"][:2], "MARUTI", NOW)
    news = src.news_items(_norm_news(_news()[:1]), NOW)
    return ann + news


def test_a_valid_answer_gives_events_whose_facts_come_from_the_cited_item():
    items = _items()
    raw = json.dumps({"events": [
        {"item": 3, "about_company": True, "what": "Q2 net profit rose 12% to Rs 3,500 crore.",
         "category": "results", "direction": "positive", "materiality": "high",
         # The model cannot rename, re-date or re-source the event:
         "symbol": "TATAMOTORS", "published_at": "2026-10-22", "source": "nse_announcement"},
        {"item": 1, "about_company": True, "what": "Schedule of an analysts' meet was filed.",
         "category": "other", "direction": "neutral", "materiality": "low"},
        {"item": 2, "about_company": True, "what": "Action taken or orders passed was filed.",
         "category": "regulatory", "direction": "negative", "materiality": "medium"},
    ]})
    out = cl.classify_items("MARUTI", "Maruti Suzuki India Limited", items,
                            fetched_at="2026-10-22T08:15:00+05:30", call=lambda s, u: raw)
    assert not out.failed and out.ungrounded == out.invalid == out.duplicate == 0
    got = {e.id: (e.symbol, e.category, e.direction, e.materiality, e.source, e.published_at)
           for e in out.events}
    assert got == {
        items[2].source_id: ("MARUTI", "results", "positive", "high", "news", "2026-10-21"),
        "nse:106823400": ("MARUTI", "other", "neutral", "low", "nse_announcement",
                          "2026-10-21T15:39:05+05:30"),
        "nse:106819161": ("MARUTI", "regulatory", "negative", "medium", "nse_announcement",
                          "2026-10-15T19:13:00+05:30"),
    }
    assert all(e.fetched_at == "2026-10-22T08:15:00+05:30" for e in out.events)
    cited = {i.source_id for i in items}
    assert {e.id for e in out.events} <= cited                    # every event cites an item


@pytest.mark.parametrize("entry, field", [
    ({"item": 9, "what": "x", "category": "other", "direction": "neutral", "materiality": "low"}, "ungrounded"),
    ({"item": 0, "what": "x", "category": "other", "direction": "neutral", "materiality": "low"}, "ungrounded"),
    ({"item": True, "what": "x", "category": "other", "direction": "neutral", "materiality": "low"}, "ungrounded"),
    ({"what": "x", "category": "other", "direction": "neutral", "materiality": "low"}, "ungrounded"),
    ({"item": 3, "what": "Q2 net profit rose 15% to Rs 3,500 crore.", "category": "results",
      "direction": "positive", "materiality": "high"}, "ungrounded"),           # 15% is not in it
    ({"item": 3, "what": "Profit rose to Rs 35 billion.", "category": "results",
      "direction": "positive", "materiality": "high"}, "ungrounded"),           # converted units
    ({"item": 1, "what": "x", "category": "earnings", "direction": "neutral", "materiality": "low"}, "invalid"),
    ({"item": 1, "what": "x", "category": "other", "direction": "up", "materiality": "low"}, "invalid"),
    ({"item": 1, "what": "", "category": "other", "direction": "neutral", "materiality": "low"}, "invalid"),
    ("not an object", "invalid"),
])
def test_an_unsupported_answer_is_dropped_and_counted(entry, field):
    raw = json.dumps({"events": [entry]})
    out = cl.classify_items("MARUTI", "Maruti Suzuki", _items(), fetched_at="t", call=lambda s, u: raw)
    assert out.events == [] and not out.failed
    assert getattr(out, field) == 1


def test_not_about_the_company_and_duplicates():
    items = _items()
    raw = json.dumps({"events": [
        {"item": 3, "about_company": "false"},
        {"item": 1, "what": "Meet schedule filed.", "category": "other", "direction": "neutral",
         "materiality": "low"},
        {"item": 1, "what": "Again.", "category": "other", "direction": "neutral", "materiality": "low"},
    ]})
    out = cl.classify_items("MARUTI", "Maruti Suzuki", items, fetched_at="t", call=lambda s, u: raw)
    assert out.unrelated == {items[2].source_id}
    assert [e.id for e in out.events] == ["nse:106823400"]
    assert out.duplicate == 1


@pytest.mark.parametrize("raw", ["not json", '{"events": "x"}', "[]", '{"result": []}',
                                 '{"events": [{"item": 1, "what": "a'])
def test_malformed_output_stores_nothing(raw):
    out = cl.classify_items("MARUTI", "Maruti Suzuki", _items(), fetched_at="t", call=lambda s, u: raw)
    assert out.failed and out.events == []


def test_a_failed_call_stores_nothing():
    def boom(system, user):
        raise TimeoutError("read timeout")
    out = cl.classify_items("MARUTI", "Maruti Suzuki", _items(), fetched_at="t", call=boom)
    assert out.failed and out.events == [] and "read timeout" in out.error


def test_the_prompt_shows_the_sources_raw_date_and_the_company():
    seen = {}
    def call(system, user):
        seen["user"] = user
        return '{"events": []}'
    cl.classify_items("MARUTI", "Maruti Suzuki India Limited", _items(), fetched_at="t", call=call)
    assert "COMPANY: Maruti Suzuki India Limited (NSE: MARUTI)" in seen["user"]
    assert "[1] NSE announcement | published 21-Oct-2026 15:39:05 |" in seen["user"]
    assert "[3] news (Example Business Daily) | published 10 hours ago |" in seen["user"]


def test_ungrounded_figures_by_hand():
    assert cl.ungrounded_figures("Profit up 12% to Rs 3,500 crore in Q2 FY27",
                                 "profit rose 12% at Rs 3500 crore for Q2 FY2026-27") == []
    assert cl.ungrounded_figures("Profit up 15%", "Profit up 12%") == ["15"]
    assert cl.ungrounded_figures("Dividend of Rs 5 per share", "Dividend declared") == []  # one digit


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def test_an_id_is_stored_once(tmp_path):
    store = EventStore(tmp_path)
    assert len(store.append_new("MARUTI", [_event(eid="nse:1"), _event(eid="nse:2")])) == 2
    assert store.append_new("MARUTI", [_event(eid="nse:1", what="other words")]) == []
    assert store.append_new("MARUTI", [_event(eid="nse:3"), _event(eid="nse:3")]) != []
    lines = (tmp_path / "MARUTI.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["nse:1", "nse:2", "nse:3"]


def test_an_event_cannot_be_written_into_another_stocks_file(tmp_path):
    with pytest.raises(ValueError):
        EventStore(tmp_path).append_new("MARUTI", [_event(symbol="TATAMOTORS")])


@pytest.mark.parametrize("symbol", ["../x", "MARUTI.NS", "^NSEI", "", "a b", "maruti", "X" * 30])
def test_only_a_stock_symbol_names_a_file(tmp_path, symbol):
    assert not valid_symbol(symbol)
    with pytest.raises(ValueError):
        EventStore(tmp_path).path(symbol)


@pytest.mark.parametrize("symbol", ["MARUTI", "M&M", "BAJAJ-AUTO", "J&KBANK", "NAM_INDIA"])
def test_nse_symbols_are_valid(symbol):
    assert valid_symbol(symbol)


def test_read_since_never_returns_an_undated_event(tmp_path):
    store = EventStore(tmp_path)
    store.append_new("MARUTI", [
        _event(eid="a", published="2026-10-21T15:39:05+05:30"),
        _event(eid="b", published="2026-10-22"),
        _event(eid="c", published=None),
        _event(eid="d", published="2026-10-20"),
    ])
    assert [e.id for e in store.read("MARUTI", since=date(2026, 10, 21))] == ["b", "a"]
    assert [e.id for e in store.read("MARUTI")] == ["b", "a", "d", "c"]
    assert [e.id for e in store.read("MARUTI", limit=1)] == ["b"]


def test_a_half_written_line_is_skipped(tmp_path):
    store = EventStore(tmp_path)
    store.append_new("MARUTI", [_event(eid="a")])
    with open(tmp_path / "MARUTI.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"id": "b", "symb')
    assert [e.id for e in store.load("MARUTI")] == ["a"]


def test_state_prunes_old_seen_items(tmp_path):
    store = EventStore(tmp_path)
    store.save_state({"queries": {"day": "2026-10-22", "used": 4},
                      "seen": {"MARUTI": {"news:old": "2026-09-01", "news:new": "2026-10-20"}}},
                     date(2026, 10, 22), keep_days=30)
    assert store.load_state() == {"queries": {"day": "2026-10-22", "used": 4},
                                  "seen": {"MARUTI": {"news:new": "2026-10-20"}}}


# ---------------------------------------------------------------------------
# The feed, end to end
# ---------------------------------------------------------------------------

def test_two_runs_store_each_item_once_and_classify_it_once(feed_env):
    rec1 = _run(feed_env)
    assert rec1["status"] == "ok"
    # NSE window 15-22 Oct: the 21 Oct and 15 Oct filings (the 13 Oct one is
    # outside it); board meetings were filed 8 Oct and 15 Jul, outside it.
    # News: 5 articles with a link, 1 about Tata Motors (not a mention).
    stored = feed_env["store"].load("MARUTI")
    by_source = sorted((e.source, e.id) for e in stored)
    assert [s for s, _ in by_source].count("nse_announcement") == 2
    assert [s for s, _ in by_source].count("news") == 4
    assert rec1["news_unmatched"] == 1
    assert rec1["events_stored"] == 6 and rec1["items_new"] == 6
    assert len(feed_env["model"].calls) == 1

    rec2 = _run(feed_env, now=NOW + timedelta(hours=10, minutes=15), slot="pm")
    assert rec2["events_stored"] == 0 and rec2["items_new"] == 0
    assert len(feed_env["model"].calls) == 1                     # nothing sent again
    assert len(feed_env["store"].load("MARUTI")) == 6


def test_stored_dates_are_the_sources(feed_env):
    _run(feed_env)
    got = {e.title: (e.published_at, e.published_raw) for e in feed_env["store"].load("MARUTI")}
    assert got["Analysts/Institutional Investor Meet/Con. Call Updates"] == (
        "2026-10-21T15:39:05+05:30", "21-Oct-2026 15:39:05")
    assert got["Maruti Suzuki EV launch: what we know so far"] == (None, "")
    for event in feed_env["store"].load("MARUTI"):
        assert event.fetched_at == "2026-10-22T08:15:00+05:30"
        assert event.published_at != event.fetched_at


def test_nse_is_asked_for_the_registry_code_and_events_filed_under_the_apps_symbol(feed_env):
    rows = _nse()
    tvs = {"announcements": [dict(rows["announcements"][0], symbol="TVSMOTOR", seq_id="5001",
                                  sm_name="TVS Motor Company Limited")],
           "board_meetings": []}
    feed_env["nse"] = FakeNse({"TVSMOTOR": tvs})
    feed_env["tracked"] = [("TVSMOTORS", "held")]
    feed_env["codes"] = {"TVSMOTORS": "TVSMOTOR"}
    feed_env["news"] = {}
    rec = _run(feed_env)
    assert ("announcements", "TVSMOTOR") in [c[:2] for c in feed_env["nse"].calls]
    assert [e.id for e in feed_env["store"].load("TVSMOTORS")] == ["nse:5001"]
    assert rec["nse_rows_foreign"] == 0


def test_the_shipped_registry_resolves_codes_and_skips_unresolved_identities(feed_env, monkeypatch):
    """Through the real identity seams and config/instruments.yaml: TVSMOTORS
    is asked for as TVSMOTOR, and TATAMOTORS (quarantined) is skipped."""
    monkeypatch.setenv("INSTRUMENT_REGISTRY_PATH", str(REPO / "config" / "instruments.yaml"))
    from core.portfolio.identity_reconcile import symbol_identity_issue
    from backend.shared.data.fetchers.symbol_resolver import nse_symbol
    monkeypatch.setattr(feed, "_identity_issue", symbol_identity_issue)
    monkeypatch.setattr(feed, "_nse_code", nse_symbol)
    feed_env["tracked"] = [("TATAMOTORS", "held"), ("TVSMOTORS", "watched")]
    feed_env["news"] = {}
    rec = _run(feed_env)
    assert list(rec["identity_skipped"]) == ["TATAMOTORS"]
    assert [c[1] for c in feed_env["nse"].calls if c[0] == "announcements"] == ["TVSMOTOR"]
    assert rec["symbols_used"] == 1


def test_the_symbol_cap_keeps_holdings_first(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_MAX_SYMBOLS", 3)
    feed_env["tracked"] = [("AAA", "held"), ("BBB", "held"), ("CCC", "watched"),
                           ("DDD", "shelf"), ("EEE", "shelf")]
    rec = _run(feed_env)
    assert rec["symbols_tracked"] == 5 and rec["symbols_used"] == 3 and rec["symbols_over_cap"] == 2
    assert [c[1] for c in feed_env["nse"].calls if c[0] == "announcements"] == ["AAA", "BBB", "CCC"]
    assert rec["by_group"] == {"held": 2, "watched": 1, "shelf": 2}


def test_the_daily_query_cap_holds_over_any_number_of_runs(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_NEWS_QUERIES_PER_DAY", 5)
    feed_env["tracked"] = [(s, "held") for s in ("AAA", "BBB", "CCC", "DDD")]
    used = []
    for k in range(4):                                   # four runs on one day
        rec = _run(feed_env, now=NOW + timedelta(hours=k))
        used.append(rec["news_queries_used"])
        assert rec["news_run_budget"] <= 3               # ceil(5 / 2)
    assert used == [3, 2, 0, 0]
    assert sum(used) <= 5
    assert len(feed_env["searches"]) == 5
    rec = _run(feed_env, now=NOW + timedelta(days=1))     # a new day
    assert rec["news_queries_before"] == 0 and rec["news_queries_used"] == 3
    assert rec["news_not_searched"] == 1


def test_a_spent_credit_stops_the_runs_searches(feed_env):
    feed_env["tracked"] = [("AAA", "held"), ("BBB", "held"), ("CCC", "held")]
    feed_env["news"] = {"AAA": ([], "exhausted")}
    rec = _run(feed_env)
    assert feed_env["searches"] == ["AAA"]
    assert rec["news_exhausted"] and rec["news_failed"] == {"AAA": "exhausted"}
    assert rec["status"] == "partial"


def test_a_source_failure_skips_and_the_next_run_retries(feed_env):
    feed_env["nse"].fail = {("announcements", "MARUTI")}
    feed_env["news"] = {"MARUTI": ([], "http_503")}
    rec = _run(feed_env)
    assert rec["status"] == "partial"
    assert "announcements" in rec["nse_failed"]["MARUTI"]
    assert rec["news_failed"] == {"MARUTI": "http_503"}
    assert feed_env["store"].load("MARUTI") == []
    feed_env["nse"].fail = set()
    feed_env["news"] = {"MARUTI": (_norm_news(_news()), "ok")}
    rec = _run(feed_env, now=NOW + timedelta(hours=10))
    assert rec["status"] == "ok" and rec["events_stored"] == 6


def test_a_classifier_failure_stores_nothing_and_the_next_run_retries(feed_env):
    feed_env["model"].fail = True
    rec = _run(feed_env)
    assert rec["llm_failed"] == 1 and rec["events_stored"] == 0 and rec["status"] == "partial"
    assert feed_env["store"].load("MARUTI") == []
    feed_env["model"].fail = False
    rec = _run(feed_env, now=NOW + timedelta(hours=10))
    assert rec["events_stored"] == 6
    assert len(feed_env["model"].calls) == 2 and len(feed_env["model"].calls[1]) == 6


def test_an_unrelated_answer_is_not_asked_again(feed_env):
    feed_env["model"] = FakeModel(unrelated=("Stocks to watch",))
    rec = _run(feed_env)
    assert rec["items_unrelated"] == 1 and rec["events_stored"] == 5
    _run(feed_env, now=NOW + timedelta(hours=10))
    assert len(feed_env["model"].calls) == 1
    assert "Stocks to watch" not in " ".join(e.title for e in feed_env["store"].load("MARUTI"))


def test_items_are_capped_per_stock_and_batched_per_call(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_MAX_ITEMS_PER_SYMBOL", 5)
    monkeypatch.setattr(settings, "EVENTS_MAX_ITEMS_PER_CALL", 2)
    rec = _run(feed_env)
    assert rec["items_new"] == 5 and rec["items_over_cap"] == 1
    assert [len(c) for c in feed_env["model"].calls] == [2, 2, 1]
    # The undated article is the one left for the next run.
    assert "Maruti Suzuki EV launch: what we know so far" not in {
        e.title for e in feed_env["store"].load("MARUTI")}


def test_the_run_never_raises(feed_env, monkeypatch):
    def broken():
        raise RuntimeError("users table locked")
    monkeypatch.setattr(feed, "tracked_symbols", broken)
    rec = _run(feed_env)
    assert rec["status"] == "failed" and "users table locked" in rec["error"]
    assert feed_env["store"].load_runs()[-1]["status"] == "failed"


def test_one_stocks_crash_does_not_stop_the_others(feed_env, monkeypatch):
    feed_env["tracked"] = [("AAA", "held"), ("MARUTI", "held")]
    real = feed._nse_code
    def code(symbol, on):
        if symbol == "AAA":
            raise KeyError("registry entry malformed")
        return real(symbol, on)
    monkeypatch.setattr(feed, "_nse_code", code)
    rec = _run(feed_env)
    assert rec["status"] == "partial" and "AAA" in rec["nse_failed"]
    assert len(feed_env["store"].load("MARUTI")) == 6


def test_disabled_does_nothing(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_ENABLED", False)
    rec = _run(feed_env)
    assert rec["status"] == "disabled"
    assert feed_env["nse"].calls == [] and feed_env["searches"] == []
    assert not feed_env["store"].base_dir.exists()


def test_a_qualifying_filing_runs_the_ingestor_once_under_the_managed_sector(feed_env):
    """The 21 Oct filing ("Analysts/Institutional Investor Meet/Con. Call
    Updates") is one the ingestor qualifies; the 15 Oct one is not."""
    rec = _run(feed_env)
    assert feed_env["ingested"] == [("MARUTI", "automobile")]
    assert rec["ingest"] == {"MARUTI": 1}
    _run(feed_env, now=NOW + timedelta(hours=10))
    assert feed_env["ingested"] == [("MARUTI", "automobile")]   # not again


def test_no_ingestion_for_a_stock_without_a_dossier_or_for_news(feed_env):
    feed_env["managed"] = {}
    rec = _run(feed_env)
    assert feed_env["ingested"] == [] and rec["ingest_not_managed"] == ["MARUTI"]


def test_a_board_meeting_intimation_does_not_run_the_ingestor(feed_env, monkeypatch):
    """The meeting has not happened: the ingestor would skip it (FIX-004)."""
    monkeypatch.setattr(settings, "EVENTS_LOOKBACK_DAYS", 30)
    feed_env["nse"] = FakeNse({"MARUTI": {"announcements": [],
                                          "board_meetings": _nse()["board_meetings"]}})
    feed_env["news"] = {}
    rec = _run(feed_env)
    assert rec["events_stored"] == 1
    assert feed_env["ingested"] == []


def test_the_ingest_switch(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_INGEST_ON_RESULTS", False)
    _run(feed_env)
    assert feed_env["ingested"] == []


def test_the_run_record_counts_and_names_no_user(feed_env, caplog):
    caplog.set_level("INFO")
    feed_env["tracked"] = [("MARUTI", "held"), ("ZZZ", "shelf")]
    feed_env["identity"] = {"ZZZ": "ZZZ identity unresolved: no listing"}
    rec = _run(feed_env)
    row = feed_env["store"].load_runs()[-1]
    assert row["symbols_tracked"] == 2 and row["symbols_used"] == 1
    assert row["identity_skipped"] == {"ZZZ": "ZZZ identity unresolved: no listing"}
    assert row["news_queries_used"] == 1 and row["llm_calls"] == 1
    assert row["serper_month_calls"] == 7
    assert rec == {k: v for k, v in row.items()}
    assert "[events] search usage: 1 news queries this run, 1 of 60 today; Serper this month 7 of 2500" \
        in caplog.text
    for path in feed_env["store"].base_dir.iterdir():
        if path.is_file():
            text = path.read_text("utf-8")
            assert settings.PORTFOLIO_DEFAULT_USER_ID not in text
            assert "user_id" not in text


def test_real_search_transport_through_the_feed(feed_env, monkeypatch):
    """The real search_serper_news_status and company_news_query, with
    Serper's response faked at requests.post."""
    from backend.shared.config import settings as shared
    from services.data.fetchers import news as news_mod
    monkeypatch.setattr(shared, "SERPER_API_KEY", "test-key", raising=False)
    sent = []

    class Resp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"news": _news()}

    def post(url, headers=None, json=None, timeout=None):
        sent.append((url, json))
        return Resp()
    monkeypatch.setattr(news_mod.requests, "post", post)
    monkeypatch.setattr(news_mod, "record_call", lambda api: None)
    monkeypatch.setattr(feed, "_search_news", REAL_SEARCH_NEWS)
    monkeypatch.setattr(feed, "_news_query", REAL_NEWS_QUERY)
    rec = _run(feed_env)
    assert sent == [("https://google.serper.dev/news",
                     {"q": "Maruti Suzuki India Limited MARUTI NSE India company news", "num": 5,
                      "hl": "en", "gl": "in", "tbs": "qdr:d"})]
    # num=5 keeps the first five results: the Q2 article, Tata Motors (not a
    # mention), the roundup, the Q2 duplicate and the price rise. With the
    # two filings: 2 + 3 events.
    assert rec["events_stored"] == 5 and rec["news_unmatched"] == 1


# ---------------------------------------------------------------------------
# A run that takes time: each stock is read against its own fetch
# ---------------------------------------------------------------------------

PM = datetime(2026, 10, 22, 18, 30, tzinfo=IST)             # Thu, the evening run
AM_NEXT = datetime(2026, 10, 23, 8, 15, tzinfo=IST)         # Fri, the morning run
FILED = datetime(2026, 10, 22, 18, 41, 20, tzinfo=IST)      # 11 min 20 s after PM
RESULTS_ROW = {
    "symbol": "MARUTI", "desc": "Financial Result Updates", "an_dt": "22-Oct-2026 18:41:20",
    "sort_date": "2026-10-22 18:41:20", "seq_id": "900001", "sm_name": "Maruti Suzuki India Limited",
    "attchmntText": "Maruti Suzuki India Limited has informed the Exchange about the Financial "
                    "Results for the quarter ended September 30, 2026",
    "attchmntFile": "https://nsearchives.nseindia.com/corporate/MARUTI_22102026184120_res.pdf",
}
INTIMATION_ROW = {
    "bm_symbol": "MARUTI", "bm_timestamp": "22-Oct-2026 18:41:20", "bm_date": "05-Nov-2026",
    "bm_purpose": "Financial Results", "sm_name": "Maruti Suzuki India Limited",
    "bm_desc": "To consider and approve the financial results for the period ended September 30, 2026",
    "attachment": "https://nsearchives.nseindia.com/corporate/MARUTI_bm_22102026.pdf",
}
INTIMATION_ID = "nsebm:" + hashlib.sha1(b"MARUTI|05-Nov-2026|2026-10-22").hexdigest()[:16]


class World:
    """NSE and the clock of a run that takes time. Each NSE call takes `step`
    seconds of world time, and a filing is visible once NSE's clock (the
    world's plus `nse_ahead`) has reached its time. The feed's clock reads the
    world's time."""

    def __init__(self, step, ann=None, bms=None, nse_ahead=0):
        self.t = PM
        self.step = timedelta(seconds=step)
        self.nse_ahead = timedelta(seconds=nse_ahead)
        self.ann = ann or {}                   # code -> [(filed, row)]
        self.bms = bms or {}
        self.calls: list[tuple[str, str, datetime]] = []

    def clock(self) -> datetime:
        return self.t

    def _visible(self, rows):
        return [(filed, dict(row)) for filed, row in rows if filed <= self.t + self.nse_ahead]

    def announcements(self, symbol=None, from_date=None, to_date=None, **_):
        self.calls.append(("announcements", symbol, self.t))
        out = [row for filed, row in self._visible(self.ann.get(symbol, []))
               if from_date.date() <= filed.date() <= to_date.date()]
        self.t += self.step
        return out

    def boardMeetings(self, symbol=None, **_):
        self.calls.append(("board_meetings", symbol, self.t))
        out = [row for _, row in self._visible(self.bms.get(symbol, []))]
        self.t += self.step
        return out


def _clocked_run(env, world, slot, at) -> dict:
    world.t = at
    env["nse"] = world
    return feed.run_event_feed(slot, now=at, store=env["store"], clock=world.clock)


def _maruti_last(env, before=49):
    env["tracked"] = [(f"S{n:02d}", "held") for n in range(before)] + [("MARUTI", "held")]
    env["news"] = {}


def test_a_filing_made_during_a_long_run_keeps_its_time_and_is_ingested(feed_env):
    """The 18:30 run tracks 50 stocks and each NSE call takes 7.5 s, so
    MARUTI, the 50th, asks NSE at 18:42:15 and 18:42:22.5, and its fetches
    return at 18:42:30. NSE shows a results filing and a board-meeting
    intimation filed at 18:41:20, more than 10 minutes after the start. By
    hand: both stored with that time and fetched_at 18:42:30; a since-22-Oct
    read returns both; the results filing runs MARUTI's ingestion in this
    run; the next morning stores and sends nothing again."""
    world = World(7.5, ann={"MARUTI": [(FILED, RESULTS_ROW)]},
                  bms={"MARUTI": [(FILED, INTIMATION_ROW)]})
    _maruti_last(feed_env)
    rec = _clocked_run(feed_env, world, "pm", PM)
    assert [c[2] for c in world.calls if c[1] == "MARUTI"] == [
        datetime(2026, 10, 22, 18, 42, 15, tzinfo=IST),
        datetime(2026, 10, 22, 18, 42, 22, 500000, tzinfo=IST)]
    stored = {e.id: (e.published_at, e.fetched_at) for e in feed_env["store"].load("MARUTI")}
    assert stored == {
        "nse:900001": ("2026-10-22T18:41:20+05:30", "2026-10-22T18:42:30+05:30"),
        INTIMATION_ID: ("2026-10-22T18:41:20+05:30", "2026-10-22T18:42:30+05:30")}
    assert sorted(e.id for e in feed_env["store"].read("MARUTI", since=date(2026, 10, 22))) == \
        sorted(stored)
    assert feed_env["ingested"] == [("MARUTI", "automobile")] and rec["ingest"] == {"MARUTI": 1}
    assert rec["nse_rows_ahead"] == 0
    assert (rec["started_at"], rec["finished_at"]) == ("2026-10-22T18:30:00+05:30",
                                                       "2026-10-22T18:42:30+05:30")
    calls = len(feed_env["model"].calls)
    rec2 = _clocked_run(feed_env, world, "am", AM_NEXT)
    assert rec2["items_new"] == 0 and len(feed_env["model"].calls) == calls
    assert len(feed_env["store"].load("MARUTI")) == 2
    assert feed_env["ingested"] == [("MARUTI", "automobile")]


def test_news_ages_count_back_from_the_stocks_own_fetch(feed_env, monkeypatch):
    """Each NSE call takes 21 s, so MARUTI, the 50th, is fetched at 19:05:00.
    "19 hours ago" is then 00:05 on 22 Oct; counted from the run's start
    (18:30) it would be 23:30 on 21 Oct."""
    monkeypatch.setattr(settings, "EVENTS_NEWS_QUERIES_PER_DAY", 200)
    world = World(21)
    _maruti_last(feed_env)
    feed_env["news"] = {"MARUTI": ([{"title": "Maruti Suzuki opens a new plant", "snippet": "",
                                     "link": "https://news.example.com/plant",
                                     "date": "19 hours ago", "source": "Example"}], "ok")}
    _clocked_run(feed_env, world, "pm", PM)
    (event,) = feed_env["store"].load("MARUTI")
    assert (event.published_at, event.fetched_at) == ("2026-10-22", "2026-10-22T19:05:00+05:30")


def test_the_scheduler_call_reads_the_clock_seam_per_stock(feed_env, monkeypatch):
    """run_event_feed(slot), as the jobs call it: started_at is the first
    read, each stock's fetched_at the read after its own fetches (5 s per NSE
    call), finished_at the last."""
    rows = {code: [(PM - timedelta(hours=1),
                    dict(RESULTS_ROW, symbol=code, seq_id=f"70{n}", an_dt="22-Oct-2026 17:30:00",
                         sort_date="2026-10-22 17:30:00"))]
            for n, code in enumerate(("AAA", "BBB", "CCC"))}
    world = World(5, ann=rows)
    feed_env["nse"] = world
    feed_env["tracked"] = [("AAA", "held"), ("BBB", "held"), ("CCC", "held")]
    feed_env["news"] = {}
    monkeypatch.setattr(feed, "_clock", world.clock)
    rec = feed.run_event_feed("pm", store=feed_env["store"])
    assert rec["started_at"] == "2026-10-22T18:30:00+05:30"
    assert {code: [e.fetched_at for e in feed_env["store"].load(code)]
            for code in ("AAA", "BBB", "CCC")} == {
        "AAA": ["2026-10-22T18:30:10+05:30"], "BBB": ["2026-10-22T18:30:20+05:30"],
        "CCC": ["2026-10-22T18:30:30+05:30"]}
    assert rec["finished_at"] == "2026-10-22T18:30:30+05:30"


def test_a_filing_nse_stamps_ahead_of_our_clock_waits_for_the_next_run(feed_env):
    """NSE's clock runs 11 min 10 s ahead of ours, so at our 18:42:15 it shows
    filings stamped 18:53:20, more than 10 minutes after our fetch (18:42:30).
    They are counted and not stored undated; the next morning stores each
    once with that time, and the results filing is ingested then."""
    filed = datetime(2026, 10, 22, 18, 53, 20, tzinfo=IST)
    ann = dict(RESULTS_ROW, an_dt="22-Oct-2026 18:53:20", sort_date="2026-10-22 18:53:20")
    bm = dict(INTIMATION_ROW, bm_timestamp="22-Oct-2026 18:53:20")
    world = World(7.5, ann={"MARUTI": [(filed, ann)]}, bms={"MARUTI": [(filed, bm)]},
                  nse_ahead=670)
    _maruti_last(feed_env)
    rec = _clocked_run(feed_env, world, "pm", PM)
    assert rec["nse_rows_ahead"] == 2 and rec["items_fetched"] == 0
    assert feed_env["store"].load("MARUTI") == [] and feed_env["model"].calls == []
    rec2 = _clocked_run(feed_env, world, "am", AM_NEXT)
    assert sorted((e.id, e.published_at) for e in feed_env["store"].load("MARUTI")) == sorted([
        ("nse:900001", "2026-10-22T18:53:20+05:30"), (INTIMATION_ID, "2026-10-22T18:53:20+05:30")])
    assert rec2["nse_rows_ahead"] == 0
    assert feed_env["ingested"] == [("MARUTI", "automobile")]


@pytest.mark.parametrize("seed", range(25))
def test_any_run_length_stores_each_filing_once_with_its_own_time(feed_env, seed):
    """Random stocks, NSE call times and filing times over three runs. The
    expected rows come from the world's timetable, computed here: a filing is
    first seen by the first run whose call for its stock comes at or after
    it, and is stored then, once, with its own time and that stock's fetch
    time (the run's start plus two calls per stock up to and including it).
    A board meeting's two rows filed the same day are one event, dated by the
    earlier."""
    rng = random.Random(seed)
    codes = [f"Q{n:02d}" for n in range(rng.randint(1, 12))]
    step = timedelta(seconds=rng.choice([1, 7.5, 20, 45, 90]))
    runs = [(PM, "pm"), (AM_NEXT, "am"), (datetime(2026, 10, 23, 18, 30, tzinfo=IST), "pm")]
    span = int((runs[-1][0] + 2 * step * len(codes) - PM).total_seconds()) + 9000
    ann: dict = {}
    bms: dict = {}
    want: dict = {code: {} for code in codes}
    serial = 5000

    def first_seen(filed, i, offset):
        for start, _slot in runs:
            if filed <= start + 2 * step * i + offset:
                return (start + 2 * step * (i + 1)).isoformat(timespec="seconds")
        return None

    for i, code in enumerate(codes):
        for _ in range(rng.randint(0, 4)):
            serial += 1
            filed = PM - timedelta(hours=2) + timedelta(seconds=rng.randint(0, span))
            ann.setdefault(code, []).append((filed, {
                "symbol": code, "desc": f"Credit Rating {serial}", "seq_id": str(serial),
                "an_dt": filed.strftime("%d-%b-%Y %H:%M:%S"),
                "sort_date": filed.strftime("%Y-%m-%d %H:%M:%S"),
                "attchmntFile": f"https://nsearchives.nseindia.com/corporate/{serial}.pdf"}))
            fetched = first_seen(filed, i, timedelta(0))
            if fetched:
                want[code][f"nse:{serial}"] = (filed.isoformat(), fetched)
        for _ in range(rng.randint(0, 3)):
            serial += 1
            meeting = f"{rng.randint(1, 28):02d}-Dec-2026 #{serial}"
            filed = PM - timedelta(hours=2) + timedelta(seconds=rng.randint(0, span))
            members = [filed]
            second = filed + timedelta(seconds=rng.randint(1, 900))
            if rng.random() < 0.5 and second.date() == filed.date():
                members.append(second)
            for k, at in enumerate(members):
                bms.setdefault(code, []).append((at, {
                    "bm_symbol": code, "bm_date": meeting, "bm_purpose": f"Purpose {serial}-{k}",
                    "bm_timestamp": at.strftime("%d-%b-%Y %H:%M:%S")}))
            fetched = first_seen(filed, i, step)
            if fetched:
                key = f"{code}|{meeting}|{filed.date().isoformat()}".encode()
                want[code]["nsebm:" + hashlib.sha1(key).hexdigest()[:16]] = (filed.isoformat(), fetched)

    world = World(step.total_seconds(), ann=ann, bms=bms)
    feed_env["tracked"] = [(code, "held") for code in codes]
    feed_env["news"] = {}
    recs = [_clocked_run(feed_env, world, slot, at) for at, slot in runs]
    for code in codes:
        got = {e.id: (e.published_at, e.fetched_at) for e in feed_env["store"].load(code)}
        assert got == want[code], (seed, code)
    assert [r["nse_rows_ahead"] for r in recs] == [0, 0, 0]
    sent = [title for call in feed_env["model"].calls for title in call]
    assert len(sent) == len(set(sent))


# ---------------------------------------------------------------------------
# GET /events/{symbol}: a member sees only their own stocks and the shelf
# ---------------------------------------------------------------------------

@pytest.fixture()
def api(tmp_path, monkeypatch):
    """The real app: an owner holding INFY, a member holding MARUTI and
    watching TCS, AUROPHARMA on the shelf, and events for those and for
    HDFCBANK, which nobody holds."""
    from fastapi.testclient import TestClient

    from backend.shared.schemas.discovery import Shelf, ShelfIdea
    from core.discovery.shelf import ShelfStore
    from services.api.server import app
    from services.data.stores import user_store

    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"))
    monkeypatch.setattr(settings, "DISCOVERY_DATA_DIR", str(tmp_path / "disc"))
    monkeypatch.setattr(settings, "EVENTS_DATA_DIR", str(tmp_path / "events"))
    owner = user_store.create_user("o@example.invalid", "pw-for-tests-1", "O", role="owner",
                                   user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
    member = user_store.create_user("m@example.invalid", "pw-for-tests-1", "M")

    def holding(sym):
        return {"symbol": sym, "sector": "generic", "qty": 1, "avg_buy_price": 100,
                "adj_avg_price": 100, "adj_qty": 1, "buy_date": "2026-10-01"}
    for user_id, doc in ((owner["user_id"], {"holdings": [holding("INFY")]}),
                         (member["user_id"], {"holdings": [holding("MARUTI")],
                                              "watchlist": [{"symbol": "TCS", "added": "2026-10-01"}]})):
        path = tmp_path / "portfolio" / user_id / "portfolio.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(json.dumps({"user_id": user_id, **doc}).encode("utf-8"))
    ShelfStore().save(Shelf(ideas=[ShelfIdea(symbol="AUROPHARMA", sector="pharma",
                                             added="2026-10-17", conviction=0.7)]))
    store = EventStore(tmp_path / "events")
    for sym in ("MARUTI", "TCS", "AUROPHARMA", "INFY", "HDFCBANK"):
        store.append_new(sym, [_event(symbol=sym, eid=f"nse:{sym}:1"),
                               _event(symbol=sym, eid=f"nse:{sym}:2", published="2026-10-19"),
                               _event(symbol=sym, eid=f"news:{sym}:3", source="news", published=None)])
    tokens = {"owner": user_store.create_session(owner["user_id"], True),
              "member": user_store.create_session(member["user_id"], True)}
    yield TestClient(app), {k: {"Authorization": f"Bearer {v}"} for k, v in tokens.items()}
    if user_store._conn_holder.get("conn") is not None:
        user_store._conn_holder["conn"].close()


@pytest.mark.parametrize("symbol", ["MARUTI", "TCS", "AUROPHARMA", "maruti"])
def test_a_member_reads_their_own_stocks_and_the_shelf(api, symbol):
    client, headers = api
    r = client.get(f"/events/{symbol}", headers=headers["member"])
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == symbol.upper() and body["count"] == 3
    assert [e["id"] for e in body["events"]] == [f"nse:{symbol.upper()}:1", f"nse:{symbol.upper()}:2",
                                                f"news:{symbol.upper()}:3"]


def test_a_member_cannot_tell_which_other_stocks_are_tracked(api):
    """INFY is the owner's holding and has events; ZZZZ has none. A member
    gets the same answer for both."""
    client, headers = api
    infy = client.get("/events/INFY", headers=headers["member"])
    none = client.get("/events/ZZZZ", headers=headers["member"])
    assert infy.status_code == none.status_code == 404
    assert infy.json()["detail"].replace("INFY", "X") == none.json()["detail"].replace("ZZZZ", "X")
    assert client.get("/events/HDFCBANK", headers=headers["member"]).status_code == 404


def test_the_owner_reads_any_stock_and_since_filters_by_publication(api):
    client, headers = api
    r = client.get("/events/HDFCBANK", headers=headers["owner"])
    assert r.status_code == 200 and r.json()["count"] == 3
    r = client.get("/events/MARUTI?since=2026-10-20", headers=headers["owner"])
    assert [e["id"] for e in r.json()["events"]] == ["nse:MARUTI:1"]
    assert r.json()["since"] == "2026-10-20"
    r = client.get("/events/MARUTI?limit=1", headers=headers["owner"])
    assert r.json()["count"] == 1


@pytest.mark.parametrize("path, code", [("/events/BAD$", 422), ("/events/MARUTI?limit=0", 422),
                                        ("/events/MARUTI?since=yesterday", 422),
                                        ("/events/MARUTI.NS", 422)])
def test_bad_requests(api, path, code):
    client, headers = api
    assert client.get(path, headers=headers["owner"]).status_code == code


def test_no_session_no_events(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    assert client.get("/events/MARUTI").status_code == 401


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def test_fetch_company_filings_sends_the_window_and_keeps_a_working_endpoint(monkeypatch):
    monkeypatch.setattr(nse_announcements, "_SLEEP_BETWEEN_CALLS", 0)
    fake = FakeNse({"MARUTI": _nse()}, fail={("board_meetings", "MARUTI")})
    out = nse_announcements.fetch_company_filings(fake, "MARUTI", date(2026, 10, 15), date(2026, 10, 22))
    assert fake.calls[0] == ("announcements", "MARUTI", datetime(2026, 10, 15), datetime(2026, 10, 22))
    assert [r["seq_id"] for r in out["announcements"]] == ["106823400", "106819161"]
    assert out["board_meetings"] == [] and "board_meetings" in out["error"]


def test_fetch_company_filings_override_and_dict_payloads(monkeypatch):
    monkeypatch.setattr(nse_announcements, "_SLEEP_BETWEEN_CALLS", 0)
    out = nse_announcements.fetch_company_filings(None, "TATAMOTORS", date(2026, 10, 15), date(2026, 10, 22))
    assert out == {"announcements": [], "board_meetings": [], "error": "symbol_override"}

    class DictNse:
        def announcements(self, **kw):
            return {"data": [{"symbol": "X"}, "junk"]}
        def boardMeetings(self, **kw):
            return None
    out = nse_announcements.fetch_company_filings(DictNse(), "X", date(2026, 10, 15), date(2026, 10, 22))
    assert out == {"announcements": [{"symbol": "X"}], "board_meetings": [], "error": None}


@pytest.mark.parametrize("behaviour, expected", [
    ("ok", "ok"), ("empty", "empty"), (400, "exhausted"), (503, "http_503"), ("raise", "error"),
])
def test_search_serper_news_status(monkeypatch, behaviour, expected):
    import requests
    from backend.shared.config import settings as shared
    from services.data.fetchers import news as news_mod
    monkeypatch.setattr(shared, "SERPER_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(news_mod, "record_call", lambda api: None)

    class Resp:
        def __init__(self, code, body):
            self.status_code, self.body = code, body
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)
        def json(self):
            return self.body

    def post(url, headers=None, json=None, timeout=None):
        if behaviour == "raise":
            raise requests.ConnectionError("reset")
        if isinstance(behaviour, int):
            return Resp(behaviour, {})
        return Resp(200, {"news": _news()[:2] if behaviour == "ok" else []})
    monkeypatch.setattr(news_mod.requests, "post", post)
    results, status = news_mod.search_serper_news_status("q")
    assert status == expected
    assert news_mod.search_serper_news("q") == results
    assert (len(results) == 2) is (expected == "ok")


def test_search_serper_news_status_without_a_key(monkeypatch):
    from backend.shared.config import settings as shared
    from services.data.fetchers import news as news_mod
    monkeypatch.setattr(shared, "SERPER_API_KEY", "", raising=False)
    assert news_mod.search_serper_news_status("q") == ([], "no_key")


# ---------------------------------------------------------------------------
# The scheduler jobs
# ---------------------------------------------------------------------------

def test_jobs_registered_at_0815_and_1830_on_weekdays(monkeypatch):
    from services.scheduler.python.scheduler import AutomobileScheduler
    monkeypatch.setattr(settings, "EVENTS_ENABLED", True)
    sched = AutomobileScheduler()
    for job_id, hour, minute in (("company_events_am", "8", "15"), ("company_events_pm", "18", "30")):
        job = sched._scheduler.get_job(job_id)
        assert job is not None, job_id
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert (fields["hour"], fields["minute"], fields["day_of_week"]) == (hour, minute, "mon-fri")


def test_jobs_absent_when_disabled_or_misconfigured(monkeypatch):
    from services.scheduler.python.scheduler import AutomobileScheduler
    monkeypatch.setattr(settings, "EVENTS_ENABLED", False)
    sched = AutomobileScheduler()
    assert sched._scheduler.get_job("company_events_am") is None
    monkeypatch.setattr(settings, "EVENTS_ENABLED", True)
    monkeypatch.setattr(settings, "EVENTS_EVENING", "25:99")
    sched = AutomobileScheduler()
    assert sched._scheduler.get_job("company_events_am") is not None
    assert sched._scheduler.get_job("company_events_pm") is None


@pytest.mark.parametrize("day, runs", [(date(2026, 10, 22), 1), (date(2026, 10, 24), 0)])
def test_the_job_runs_on_trading_days_and_records_its_outcome(monkeypatch, day, runs):
    import core.events.feed as feed_mod
    from core.intelligence.rl import nse_calendar
    from services.data.stores import job_outcomes
    from services.scheduler.python.scheduler import AutomobileScheduler
    calls = []
    monkeypatch.setattr(feed_mod, "run_event_feed",
                        lambda slot: calls.append(slot) or {"status": "ok", "symbols_used": 3,
                                                            "events_stored": 2})
    monkeypatch.setattr(nse_calendar, "now_ist", lambda: datetime(day.year, day.month, day.day, 8, 15,
                                                                   tzinfo=IST))
    AutomobileScheduler()._company_events_job("am")
    assert calls == ["am"] * runs
    outcome = job_outcomes.load_job_outcomes().get("company_events_am")
    if runs:
        assert outcome["status"] == "ok" and outcome["events_stored"] == 2
    else:
        assert outcome is None
