"""PR-003: fresh overnight news (published-date freshness, no repeats across
briefs) and the "Before the open" market figures.

The invariants are stated in the story's terms and the expected results are
worked out by hand from the fixtures, not read back from the code:

- an article is overnight news only if it was PUBLISHED on or after the
  previous brief's date (IST); an unreadable date never is;
- a story shown in one of the user's last 5 briefs is not shown again, whether
  it comes back under the same URL or reworded under another one; a follow-up
  naming new entities is a new development and is shown;
- each market figure carries its own instrument's close and its as-of date; a
  failed one is named "unavailable" and shows no number.

Every transport is fixture-backed: feed files on disk, a stored brief history,
Yahoo frames through the injectable reader, and stubs for the LLM narration
and the delivery channel. The hermetic suite fails any test that reaches out.
"""
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import core.delivery.brief as br
import services.background.macro_news_cache as mnc
import services.data.fetchers.macro as macro
from core.portfolio.store import PortfolioStore
from services.background.macro_news_fetcher import (
    MacroNewsFetcher, _newsapi_date, _normalize_serper_date,
)

IST = ZoneInfo("Asia/Kolkata")
MON, TUE, WED, THU, FRI = (date(2026, 10, d) for d in (12, 13, 14, 15, 16))


@pytest.fixture
def feed_dir(tmp_path, monkeypatch):
    d = tmp_path / "macro_news"
    d.mkdir()
    monkeypatch.setattr(mnc, "_DATA_DIR", d)
    return d


def _write_feed(feed_dir, fetched: date, entries: list[dict]) -> None:
    rows = [{"id": f"e{i:04d}", "severity": "HIGH", "impact_tags": ["policy"],
             "title": e.get("title", e["summary"]), **e} for i, e in enumerate(entries, 1)]
    (feed_dir / f"{fetched.isoformat()}_macro_feed.json").write_text(json.dumps(
        {"date": fetched.isoformat(), "last_refresh": "", "refresh_count": 1, "entries": rows}),
        encoding="utf-8")


# ---------------------------------------------------------------------------
# A week of feed files: the measured defect, day by day
# ---------------------------------------------------------------------------

A = {"url": "https://www.example-news.in/markets/sebi-rbi-bond-index-derivatives",
     "summary": "SEBI and RBI working on corporate bond index derivatives, says SEBI chief",
     "published_date": "2026-10-12"}
# The same article, as Google ranks it again with a tracking tag / mobile host.
A_UTM = {**A, "url": A["url"] + "?utm_source=serper&utm_medium=news"}
A_MOBILE = {**A, "url": "https://m.example-news.in/markets/sebi-rbi-bond-index-derivatives/"}
# A June article Google still ranks for a policy query (the July defect).
S = {"url": "https://example-daily.in/india/2026/Jun/05/india-gdp-growth",
     "summary": "India posts 7.7% GDP growth in 2025-26, economy strong amid global turmoil",
     "published_date": "2026-06-05"}
U = {"url": "https://example-radio.in/markets-closed-good-friday",
     "summary": "Indian stock markets remain closed on account of Good Friday",
     "published_date": ""}
# A reworded copy of A from another outlet: the same salient entities.
R = {"url": "https://another-outlet.in/sebi-chief-bond-derivatives",
     "summary": "SEBI chief says SEBI, RBI working on derivatives for corporate bond index",
     "published_date": "2026-10-13"}
# A genuine development on A's topic: new entities, a newer publish date.
N = {"url": "https://www.example-news.in/markets/sebi-approves-bond-index-derivatives",
     "summary": "SEBI approves corporate bond index derivatives; trading to start in January",
     "published_date": "2026-10-13"}
B = {"url": "https://example-wire.in/commodities/crude-jumps-iran",
     "summary": "Crude oil jumps 5% as Iran tensions escalate",
     "published_date": "2026-10-14"}
# Published Wednesday, first fetched Thursday: still news since Wednesday's brief.
T = {"url": "https://example-wire.in/global/fed-holds-rates",
     "summary": "US Fed holds rates steady, signals two cuts in 2026",
     "published_date": "2026-10-14"}
# Published Monday, first fetched Thursday: three days old, not overnight.
P = {"url": "https://example-daily.in/markets/rupee-record-low",
     "summary": "Rupee falls to record low of 96.5 against the dollar",
     "published_date": "2026-10-12"}
# Friday: a crude follow-up with new entities, and T reworded by another outlet.
Q = {"url": "https://example-wire.in/commodities/crude-falls-ceasefire",
     "summary": "Crude oil falls 4% as US-Iran ceasefire announced",
     "published_date": "2026-10-16"}
W = {"url": "https://another-outlet.in/fed-steady-two-cuts",
     "summary": "US Fed holds rates steady and signals two cuts in 2026",
     "published_date": "2026-10-15"}

FETCHED = {
    MON: [A, S, U],
    TUE: [A, S, R, N],
    WED: [A_UTM, N, U, B],
    THU: [A_MOBILE, N, B, T, P],
    FRI: [A, B, T, Q, W],
}
STORY = {e["summary"]: name for name, e in
         dict(A=A, S=S, U=U, R=R, N=N, B=B, T=T, P=P, Q=Q, W=W).items()}
PUBLISHED = {name: e["published_date"] for name, e in
             dict(A=A, S=S, U=U, R=R, N=N, B=B, T=T, P=P, Q=Q, W=W).items()}

# Worked out by hand. Each day's floor is the previous brief's date (Monday's
# is Friday 9 Oct, the previous trading day); the files read run from the day
# before the floor to the brief's day, one entry per exact URL string.
EXPECTED_SHOWN = {MON: ["A"], TUE: ["N"], WED: ["B"], THU: ["T"], FRI: ["Q"]}
EXPECTED_COUNTS = {
    MON: {"since": "2026-10-09", "candidates": 3, "undated": 1, "stale": 1, "repeats": 0, "shown": 1},
    TUE: {"since": "2026-10-12", "candidates": 5, "undated": 1, "stale": 1, "repeats": 2, "shown": 1},
    WED: {"since": "2026-10-13", "candidates": 7, "undated": 1, "stale": 3, "repeats": 2, "shown": 1},
    THU: {"since": "2026-10-14", "candidates": 10, "undated": 1, "stale": 7, "repeats": 1, "shown": 1},
    FRI: {"since": "2026-10-15", "candidates": 10, "undated": 1, "stale": 7, "repeats": 1, "shown": 1},
}


def _frame(tz: str, closes: dict) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in closes]).tz_localize(tz)
    return pd.DataFrame({"Close": list(closes.values())}, index=idx)


def _week_frames(ticker: str) -> pd.DataFrame:
    """Daily bars across the fixture week; every value is distinct per ticker."""
    zone = {"^N225": "Asia/Tokyo", "^HSI": "Asia/Hong_Kong", "INR=X": "Europe/London"}
    base = {"^GSPC": 5800.0, "^IXIC": 18000.0, "^N225": 39000.0, "^HSI": 21000.0,
            "BZ=F": 74.0, "INR=X": 84.0, "^TNX": 4.1}[ticker]
    step = 0.01 if ticker == "^TNX" else base / 1000
    days = [date(2026, 10, d) for d in (5, 6, 7, 8, 9, 12, 13, 14, 15, 16)]
    return _frame(zone.get(ticker, "America/New_York"),
                  {d.isoformat(): round(base + step * i, 4) for i, d in enumerate(days)})


@pytest.fixture
def week(tmp_path, monkeypatch, feed_dir):
    """run_morning_brief for one user over the fixture week, everything real
    except the LLM narration and the delivery channel."""
    for fetched, entries in FETCHED.items():
        _write_feed(feed_dir, fetched, entries)
    monkeypatch.setattr(br.settings, "PORTFOLIO_DATA_DIR", str(tmp_path / "portfolio"))
    monkeypatch.setattr(br, "active_user_ids", lambda: ["u1"])
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("Headline.", []))
    monkeypatch.setattr(br, "_ipo_watch", lambda *a, **k: [])
    monkeypatch.setattr(br, "upcoming_lockin_alerts", lambda on, symbols=None: [])
    monkeypatch.setattr(macro, "_yahoo_daily_bars", _week_frames)
    sent: list[dict] = []
    monkeypatch.setattr(br, "deliver", lambda title, text, **k: sent.append(
        {"title": title, "text": text, **k}) or {"delivered": True})
    for day in FETCHED:
        assert br.run_morning_brief(on=day)["status"] == "completed"
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "portfolio"))
    briefs = {b["date"]: b for b in store.load_recent_briefs(date(2026, 10, 17), 10)}
    return briefs, sent


def _shown(brief: dict) -> list[str]:
    return [STORY[i["headline"]] for i in brief["overnight"]]


def test_each_brief_shows_only_what_was_published_since_the_previous_one(week):
    briefs, _ = week
    assert {d: _shown(briefs[d.isoformat()]) for d in FETCHED} == EXPECTED_SHOWN
    order = sorted(FETCHED)
    for prev, day in zip([None] + order, order):
        floor = prev or date(2026, 10, 9)
        for name in _shown(briefs[day.isoformat()]):
            assert floor <= date.fromisoformat(PUBLISHED[name]) <= day, (day, name)


def test_the_same_url_fetched_every_day_appears_in_at_most_one_brief(week):
    """A is fetched all five days (once with utm tags, once on the mobile host)."""
    briefs, _ = week
    appearances = {}
    for b in briefs.values():
        for name in _shown(b):
            appearances.setdefault(name, []).append(b["date"])
    assert appearances["A"] == ["2026-10-12"]
    assert all(len(days) == 1 for days in appearances.values()), appearances


def test_stale_undated_and_reworded_items_never_reach_the_brief(week):
    briefs, sent = week
    shown = {n for b in briefs.values() for n in _shown(b)}
    assert not shown & {"S", "U", "P", "R", "W"}
    for message in sent:
        for never in (S, U, P, R, W):
            assert never["summary"] not in message["text"]
            assert never["summary"] not in (message.get("html_body") or "")


def test_the_brief_records_why_items_were_dropped(week):
    briefs, _ = week
    assert {d: briefs[d.isoformat()]["overnight_filter"] for d in FETCHED} == EXPECTED_COUNTS


def test_a_rerun_on_the_same_day_shows_the_same_items(week, tmp_path, monkeypatch):
    """Briefs dated the run's own day are not history, so a manual rerun at
    10:00 does not suppress what 08:50 showed."""
    briefs, _ = week
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "portfolio"))
    again = br.build_morning_brief("u1", FRI, store=store, markets=[])
    assert _shown(again) == _shown(briefs["2026-10-16"]) == ["Q"]


def test_the_delivered_brief_carries_the_market_line_with_as_of_dates(week):
    _, sent = week
    wed = next(m for m in sent if m["title"].endswith("2026-10-14"))
    # Tuesday 13 Oct is the S&P's 7th bar: 5800 + 5.8 * 6 = 5834.80, after
    # 5829.00 (+0.0995...% -> +0.10%). Nikkei trades on Wednesday: 8th bar.
    assert "S&P 500 5,834.80 (+0.10%), as of Tue 13 Oct" in wed["text"]
    assert "Nikkei 225 39,273.00 (+0.10%), as of Wed 14 Oct" in wed["text"]
    assert "US 10-year yield 4.16% (+1 bp), as of Tue 13 Oct" in wed["text"]
    assert "Before the open" in wed["html_body"]


# ---------------------------------------------------------------------------
# Repeats: realistic follow-ups against what was shown
# ---------------------------------------------------------------------------

def _overnight_after(shown_headline: str, candidate: str, monkeypatch,
                     shown_url="https://a.example/shown", url="https://b.example/new"):
    class _Cache:
        def entries_fetched(self, start, end, severities):
            return [{"summary": candidate, "url": url, "severity": "HIGH",
                     "published_date": "2026-10-14"}]
    monkeypatch.setattr(mnc, "MacroNewsCache", _Cache)
    recent = [{"date": "2026-10-13", "overnight": [{"headline": shown_headline, "story_key":
               br._story_key(shown_headline, [br._norm_url(shown_url)],
                             frozenset(br.settings.DELIVERY_BRIEF_OVERNIGHT_STOPWORDS))}]}]
    items, counts = br._overnight_items(WED, recent)
    return [i["headline"] for i in items], counts


@pytest.mark.parametrize("shown,follow_up", [
    ("RBI keeps repo rate unchanged at 5.5%", "RBI cuts repo rate by 25 bps to 5.25%"),
    ("Govt raises equity limits for NRIs, OCIs to boost foreign investment.",
     "SEBI notifies higher NRI, OCI equity limits; rules effective from August 1"),
    ("Rupee falls to record low of 96.5 against the dollar",
     "Rupee recovers 40 paise from record low after RBI intervention"),
    ("US Fed holds rates steady, signals two cuts in 2026",
     "US Fed cuts rates by 50 bps in surprise move"),
    ("SEBI, RBI working on derivatives linked to corporate bond indices: SEBI chief",
     "SEBI approves corporate bond index derivatives; trading to start in January"),
    ("Crude oil jumps 5% as Iran tensions escalate",
     "Crude oil falls 4% as US-Iran ceasefire announced"),
    ("India's inflation breaches target after more than a year, setting stage for rate hikes",
     "India's June retail inflation at 6.2%, above RBI's 6% upper band"),
    ("Fed holds rates", "Fed cuts rates"),
    # A new figure is a new development even when every word is the same.
    ("Rupee falls to record low of 96.5 against the dollar",
     "Rupee falls to fresh record low of 97.2 against the dollar"),
    ("Sensex falls 1,100 points as FII selling deepens",
     "Sensex falls 1,450 points as FII selling deepens"),
])
def test_a_material_follow_up_is_shown(shown, follow_up, monkeypatch):
    heads, counts = _overnight_after(shown, follow_up, monkeypatch)
    assert heads == [follow_up] and counts["repeats"] == 0


@pytest.mark.parametrize("shown,reworded", [
    ("SEBI, RBI working on derivatives linked to corporate bond indices: SEBI chief",
     "SEBI and RBI are working on corporate bond index derivatives, says SEBI chief"),
    ("RBI hikes repo rate by 25 bps to 6.0% to fight inflation",
     "RBI hikes repo rate by 25 bps to 6% as inflation breaches target"),
    ("RBI raised equity investment limits for NRIs and OCIs.",
     "RBI raised equity investment limits for NRIs and OCIs, boosting inflows."),
    ("Rupee rallies strongly after RBI announces new measures to attract foreign investors",
     "Rupee rallies strongly after RBI announces new measures to attract foreign investors"),
])
def test_a_reworded_copy_of_a_shown_story_is_suppressed(shown, reworded, monkeypatch):
    heads, counts = _overnight_after(shown, reworded, monkeypatch)
    assert heads == [] and counts["repeats"] == 1


def test_the_same_figure_written_differently_is_not_new():
    """6.0% and 6%, 1,00,000 and 100000 are one figure each."""
    a = br._headline_numbers("Repo at 6.0%; Sensex 1,00,000; rupee 96.50")
    b = br._headline_numbers("Repo at 6%; Sensex 100000; rupee 96.5")
    assert a == b == {"6", "100000", "96.5"}
    assert br._headline_numbers("Nifty up 100 points") == {"100"}


def test_the_same_article_is_a_repeat_whatever_its_wording_today(monkeypatch):
    """The LLM rewrites the summary on every fetch; the URL still matches."""
    heads, counts = _overnight_after(
        "Rupee rallies after RBI steps", "Brand new wording about an unrelated-sounding thing",
        monkeypatch, shown_url="https://www.x.example/a/?utm_campaign=1",
        url="http://m.x.example/a")
    assert heads == [] and counts["repeats"] == 1


@pytest.mark.xfail(strict=True, reason=(
    "Known limit, recorded in the PR-003 receipt: a follow-up that reverses one "
    "verb of an otherwise identical headline keeps 5 of 6 entities and reads as "
    "a reworded repeat for up to 5 briefs."))
def test_known_limit_a_one_verb_reversal_is_shown(monkeypatch):
    heads, _ = _overnight_after("Govt approves bill to raise FDI cap in insurance to 100%",
                                "Govt withdraws bill to raise FDI cap in insurance to 100%",
                                monkeypatch)
    assert heads == ["Govt withdraws bill to raise FDI cap in insurance to 100%"]


def test_a_brief_stored_before_pr003_still_counts_as_shown(monkeypatch):
    """Old briefs carry headlines but no story keys."""
    class _Cache:
        def entries_fetched(self, start, end, severities):
            return [{"summary": "Govt raises equity limits for NRIs, OCIs to boost foreign investment.",
                     "url": "https://n.example/1", "severity": "HIGH", "published_date": "2026-10-14"}]
    monkeypatch.setattr(mnc, "MacroNewsCache", _Cache)
    legacy = [{"date": "2026-10-13", "overnight": [
        {"headline": "Govt raises equity limits for NRIs, OCIs to boost foreign investment.",
         "severity": "HIGH"}]}]
    items, counts = br._overnight_items(WED, legacy)
    assert items == [] and counts["repeats"] == 1


def test_a_story_merged_into_a_shown_item_counts_as_shown(feed_dir, tmp_path, monkeypatch):
    """Two outlets on one story on Tuesday: the brief merges them and shows one
    headline, and remembers both URLs. Wednesday's refetch of the other is a
    repeat although most of its wording is new (7 of 10 entities)."""
    first = {"url": "https://one.example/nri-limits", "published_date": "2026-10-13",
             "summary": "Govt raises equity limits for NRIs, OCIs to boost foreign investment and inflows."}
    second = {"url": "https://two.example/nri-oci-cap", "published_date": "2026-10-13",
              "summary": "NRI, OCI investors cheer doubled equity cap; brokers expect $5bn"}
    _write_feed(feed_dir, TUE, [first, second])
    _write_feed(feed_dir, WED, [second])
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("h", []))
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "p"))
    tue = br.build_morning_brief("u1", TUE, store=store, markets=[])
    assert [i["headline"] for i in tue["overnight"]] == [first["summary"]]
    store.save_brief(tue)
    wed = br.build_morning_brief("u1", WED, store=store, markets=[])
    # Both Tuesday items are still on or after Wednesday's floor (Tuesday).
    assert wed["overnight"] == [] and wed["overnight_filter"]["repeats"] == 2


@pytest.mark.parametrize("dropped,shown_again", [(None, True), ("2026-10-07", False)])
def test_only_the_users_last_five_briefs_count(feed_dir, tmp_path, monkeypatch, dropped, shown_again):
    """Crude was shown on 6 Oct. With six briefs since, 6 Oct is outside the
    last five and a fresh article on the same story is shown again; with five,
    it is inside and the article is a repeat."""
    crude = "Crude oil jumps 5% as Iran tensions escalate"
    history = [{"date": "2026-10-06", "overnight": [{"headline": crude}]}] + [
        {"date": f"2026-10-{d:02d}", "overnight": []} for d in (7, 8, 9, 12, 13)]
    history = [b for b in history if b["date"] != dropped]
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, WED,
                        [{"url": "https://c.example/new", "summary": crude,
                          "published_date": "2026-10-14"}], history=history)
    assert ([i["headline"] for i in brief["overnight"]] == [crude]) is shown_again


def test_load_recent_briefs_returns_the_last_n_before_the_day(tmp_path):
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path))
    for d in (5, 6, 7, 8, 9, 12, 13):
        store.save_brief({"date": f"2026-10-{d:02d}", "overnight": []})
    got = [b["date"] for b in store.load_recent_briefs(date(2026, 10, 13), 5)]
    assert got == ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12"]
    assert store.load_recent_briefs(date(2026, 10, 5), 5) == []


# ---------------------------------------------------------------------------
# The publish-date floor: first brief, gaps, time zones
# ---------------------------------------------------------------------------

def _brief_with(feed_dir, tmp_path, monkeypatch, on, entries, history=()):
    _write_feed(feed_dir, on, entries)
    monkeypatch.setattr(br, "_narrate_brief", lambda b: ("h", []))
    store = PortfolioStore(user_id="u1", base_dir=str(tmp_path / "p"))
    for b in history:
        store.save_brief(b)
    return br.build_morning_brief("u1", on, store=store, markets=[])


def test_a_users_first_brief_reaches_back_to_the_previous_trading_day(feed_dir, tmp_path, monkeypatch):
    friday = {"url": "https://f.example/1", "summary": "Friday evening policy move", "published_date": "2026-10-09"}
    thursday = {"url": "https://f.example/2", "summary": "Thursday budget leak story", "published_date": "2026-10-08"}
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, MON, [friday, thursday])
    assert [i["headline"] for i in brief["overnight"]] == [friday["summary"]]


def test_a_gap_in_briefs_never_reaches_back_more_than_four_days(feed_dir, tmp_path, monkeypatch):
    """The last brief was 10 days ago; a 6-day-old article is still not overnight."""
    six = {"url": "https://g.example/6", "summary": "Six day old cement price story", "published_date": "2026-10-10"}
    three = {"url": "https://g.example/3", "summary": "Three day old steel export story", "published_date": "2026-10-13"}
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, date(2026, 10, 16), [six, three],
                        history=[{"date": "2026-10-06", "overnight": []}])
    assert brief["overnight_filter"]["since"] == "2026-10-12"
    assert [i["headline"] for i in brief["overnight"]] == [three["summary"]]


def test_utc_publish_times_are_judged_by_their_ist_date(feed_dir, tmp_path, monkeypatch):
    """Previous brief Wednesday. 20:00 UTC Tuesday is 01:30 IST Wednesday: on
    or after the floor. 18:00 UTC Tuesday is 23:30 IST Tuesday: before it."""
    after = {"url": "https://t.example/1", "summary": "Wall Street rallies on chip earnings",
             "published_date": _newsapi_date("2026-10-13T20:00:00Z")}
    before = {"url": "https://t.example/2", "summary": "European bond yields edge lower",
              "published_date": _newsapi_date("2026-10-13T18:00:00Z")}
    assert (after["published_date"], before["published_date"]) == ("2026-10-14", "2026-10-13")
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, THU, [after, before],
                        history=[{"date": "2026-10-14", "overnight": []}])
    assert [i["headline"] for i in brief["overnight"]] == [after["summary"]]


def test_over_the_cap_the_newest_items_are_kept(feed_dir, tmp_path, monkeypatch):
    """Four unrelated fresh stories for three places, listed oldest first in
    the feed: the one published on the floor day is the one left out."""
    stories = [("Monday cement price note", "2026-10-12"), ("Tuesday steel export curbs", "2026-10-13"),
               ("Tuesday pharma recall order", "2026-10-13"), ("Wednesday telecom tariff hike", "2026-10-14")]
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, WED,
                        [{"url": f"https://k.example/{i}", "summary": s, "published_date": p}
                         for i, (s, p) in enumerate(stories)],
                        history=[{"date": "2026-10-12", "overnight": []}])
    assert br.settings.DELIVERY_BRIEF_MAX_OVERNIGHT == 3
    assert [i["headline"] for i in brief["overnight"]] == [
        "Wednesday telecom tariff hike", "Tuesday steel export curbs", "Tuesday pharma recall order"]


def test_an_item_dated_after_the_brief_is_never_shown(feed_dir, tmp_path, monkeypatch):
    future = {"url": "https://z.example/1", "summary": "Misdated budget preview", "published_date": "2026-10-20"}
    brief = _brief_with(feed_dir, tmp_path, monkeypatch, WED, [future])
    assert brief["overnight"] == [] and brief["overnight_filter"]["undated"] == 1


def test_an_entry_published_on_the_floor_but_filed_the_day_before_is_found(feed_dir):
    """Files are named by the server's (UTC) fetch date; 01:00 IST Wednesday is
    still Tuesday in UTC."""
    _write_feed(feed_dir, TUE, [{"url": "https://e.example/1", "summary": "Early hours item",
                                 "published_date": "2026-10-14"}])
    got = mnc.MacroNewsCache().entries_published(WED, THU, ("HIGH",))
    assert [e["summary"] for e in got] == ["Early hours item"]


# ---------------------------------------------------------------------------
# The fetcher: publish dates from Serper and NewsAPI
# ---------------------------------------------------------------------------

FETCH_AT = datetime(2026, 10, 15, 7, 30, tzinfo=IST)     # the 07:30 IST daily run


@pytest.mark.parametrize("raw,expected", [
    ("5 hours ago", "2026-10-15"),        # 02:30 IST today
    ("10 hours ago", "2026-10-14"),       # 21:30 IST yesterday, not "today"
    ("45 mins ago", "2026-10-15"),
    ("1 day ago", "2026-10-14"),
    ("3 days ago", "2026-10-12"),
    ("2 weeks ago", "2026-10-01"),
    ("1 month ago", "2026-09-15"),
    ("Oct 10, 2026", "2026-10-10"),
    ("just now", "2026-10-15"),
])
def test_serper_dates_become_the_ist_publish_date(raw, expected):
    assert _normalize_serper_date(raw, now=FETCH_AT) == expected


@pytest.mark.parametrize("raw", ["", "   ", "sometime", "n/a", "Oct 30, 2026", "Breaking",
                                 "999999 years ago"])
def test_an_unreadable_or_future_date_is_empty_never_today(raw):
    assert _normalize_serper_date(raw, now=FETCH_AT) == ""


def test_a_utc_fetch_clock_does_not_move_the_ist_date():
    """At 20:00 UTC on the 14th it is 01:30 IST on the 15th."""
    late = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
    assert _normalize_serper_date("1 hour ago", now=late) == "2026-10-15"


def test_newsapi_dates_are_ist_and_unreadable_ones_empty():
    assert _newsapi_date("2026-10-13T20:00:00Z") == "2026-10-14"
    assert _newsapi_date("2026-10-13T10:00:00+00:00") == "2026-10-13"
    assert _newsapi_date("") == "" and _newsapi_date("yesterday-ish") == ""


def test_the_serper_reader_stores_an_unreadable_date_as_empty(monkeypatch):
    """Through the real reader: the defect stamped such an item with today."""
    import backend.shared.config.settings as cfg
    import services.background.macro_news_fetcher as mf
    monkeypatch.setattr(cfg, "SERPER_API_KEY", "test-key", raising=False)

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"news": [{"title": "Old RBI story", "link": "https://r.example/1", "date": "sometime"},
                             {"title": "Fresh story", "link": "https://r.example/2", "date": "2 hours ago"}]}
    monkeypatch.setattr(mf.requests, "post", lambda *a, **k: _Resp())
    fetcher = MacroNewsFetcher.__new__(MacroNewsFetcher)
    rows = fetcher._serper_news("India RBI SEBI policy announcement")
    assert rows[0]["published_date"] == "" and rows[0]["published_raw"] == "sometime"
    assert rows[1]["published_date"] == datetime.now(IST).date().isoformat() \
        or rows[1]["published_date"] == (datetime.now(IST) - timedelta(hours=2)).date().isoformat()


# ---------------------------------------------------------------------------
# Chat and the daily review read the same freshness rule
# ---------------------------------------------------------------------------

def test_chat_reads_only_what_was_published_today_or_yesterday(feed_dir, monkeypatch):
    monkeypatch.setattr(mnc, "ist_today", lambda: THU)
    _write_feed(feed_dir, WED, [
        {"url": "https://c.example/fresh", "summary": "Fresh RBI liquidity step",
         "title": "Fresh RBI liquidity step", "published_date": "2026-10-14"}])
    _write_feed(feed_dir, THU, [
        {"url": "https://c.example/old", "summary": "Old GDP story", "title": "Old GDP story",
         "published_date": "2026-10-11"},
        {"url": "https://c.example/undated", "summary": "Undated closure", "title": "Undated closure",
         "published_date": ""},
        {"url": "https://c.example/medium", "summary": "Fresh metals note", "title": "Fresh metals note",
         "published_date": "2026-10-15", "severity": "MEDIUM"}])
    cache = mnc.MacroNewsCache()
    assert [e["title"] for e in cache.get_high_severity()] == ["Fresh RBI liquidity step"]
    context = cache.get_formatted_context()
    assert "Fresh RBI liquidity step" in context and "Old GDP story" not in context
    assert {e["title"] for e in cache.get_all_today()} == {"Fresh RBI liquidity step", "Fresh metals note"}


def test_the_daily_review_ignores_an_old_article_fetched_on_the_reviewed_day(feed_dir):
    _write_feed(feed_dir, THU, [
        {"url": "https://d.example/old", "summary": "Three day old rupee story",
         "title": "Three day old rupee story", "published_date": "2026-10-12"},
        {"url": "https://d.example/new", "summary": "Wednesday night Fed move",
         "title": "Wednesday night Fed move", "published_date": "2026-10-14", "severity": "MEDIUM"}])
    block = mnc.MacroNewsCache().get_for_daily_review(for_date=THU)
    assert "Wednesday night Fed move" in block and "Three day old rupee story" not in block


# ---------------------------------------------------------------------------
# Before the open: fixture Yahoo frames
# ---------------------------------------------------------------------------

def _frames_for_tuesday(ticker):
    frames = {
        # Tuesday's own US session has not closed at 08:50 IST: its bar is ignored.
        "^GSPC": _frame("America/New_York", {"2026-10-09": 5800.0, "2026-10-12": 5829.0,
                                             "2026-10-13": 5850.0}),
        "^N225": _frame("Asia/Tokyo", {"2026-10-12": 39000.0, "2026-10-13": 38805.0}),
        # No Tuesday session in Hong Kong: closed, neither shown nor "unavailable".
        "^HSI": _frame("Asia/Hong_Kong", {"2026-10-09": 21000.0, "2026-10-12": 21210.0}),
        # A gap (NaN) and a bar dated after the brief: neither is used.
        "BZ=F": _frame("America/New_York", {"2026-10-09": 74.0, "2026-10-12": float("nan"),
                                            "2026-10-13": 75.11, "2026-10-14": 99.0}),
        "INR=X": _frame("Europe/London", {"2026-10-13": 84.12}),
        "^TNX": _frame("America/New_York", {"2026-10-09": 4.10, "2026-10-12": 4.13}),
    }
    if ticker not in frames:
        raise RuntimeError("Yahoo said no")
    return frames[ticker]


def test_each_figure_is_its_own_instruments_close_with_its_as_of_date():
    rows = {r["label"]: r for r in macro.get_overnight_markets(TUE, history=_frames_for_tuesday)}
    assert (rows["S&P 500"]["status"], rows["S&P 500"]["value"], rows["S&P 500"]["change_pct"],
            rows["S&P 500"]["as_of"]) == ("ok", 5829.0, 0.5, "2026-10-12")
    assert (rows["Nikkei 225"]["value"], rows["Nikkei 225"]["change_pct"],
            rows["Nikkei 225"]["as_of"]) == (38805.0, -0.5, "2026-10-13")
    assert (rows["Brent crude"]["value"], rows["Brent crude"]["change_pct"],
            rows["Brent crude"]["as_of"]) == (75.11, 1.5, "2026-10-13")
    assert (rows["US 10-year yield"]["value"], rows["US 10-year yield"]["change_bp"]) == (4.13, 3.0)
    assert rows["Hang Seng"]["status"] == "closed"
    for label in ("Nasdaq Composite", "USD/INR"):
        assert rows[label]["status"] == "unavailable"
        assert not {"value", "change_pct", "change_bp"} & set(rows[label])


def test_the_market_line_names_failures_and_invents_no_figure():
    rows = macro.get_overnight_markets(TUE, history=_frames_for_tuesday)
    text = br.render_brief_text({"date": "2026-10-13", "before_the_open": rows})
    assert "S&P 500 5,829.00 (+0.50%), as of Mon 12 Oct" in text
    assert "Nikkei 225 38,805.00 (-0.50%), as of Tue 13 Oct" in text
    assert "Brent crude $75.11 (+1.50%), as of Tue 13 Oct" in text
    assert "US 10-year yield 4.13% (+3 bp), as of Mon 12 Oct" in text
    assert "Unavailable: Nasdaq Composite, USD/INR." in text
    assert "Hang Seng" not in text and "99.00" not in text and "5,850" not in text
    html = br.render_brief_html({"date": "2026-10-13", "before_the_open": rows})
    assert "S&amp;P 500 5,829.00 (+0.50%), as of Mon 12 Oct" in html
    assert "Unavailable: Nasdaq Composite, USD/INR." in html
    api = br.enrich_brief_for_api({"date": "2026-10-13", "before_the_open": rows})
    assert api["before_the_open_unavailable"] == ["Nasdaq Composite", "USD/INR"]
    assert len(api["before_the_open_lines"]) == 4


def test_a_weekend_quote_is_neither_the_level_nor_the_previous_session():
    """Yahoo's INR=X carried a Sunday bar on 18 Oct 2026 (94.96 after Friday's
    94.52) though the rupee does not trade at weekends. Monday's brief must
    measure Monday against Friday, and a brief built before Monday's bar
    exists reads Friday's close."""
    inr = [{"label": "USD/INR", "ticker": "INR=X", "session": "24h", "unit": "inr"}]
    week = {"2026-10-15": 95.00, "2026-10-16": 94.50, "2026-10-18": 94.96}
    live = _frame("Europe/London", {**week, "2026-10-19": 94.69})
    [row] = macro.get_overnight_markets(date(2026, 10, 19), instruments=inr, history=lambda t: live)
    # 94.69 / 94.50 - 1 = +0.201%: against Friday, not Sunday's 94.96 (-0.28%).
    assert (row["value"], row["change_pct"], row["as_of"]) == (94.69, 0.2, "2026-10-19")
    early = _frame("Europe/London", week)
    [row] = macro.get_overnight_markets(date(2026, 10, 19), instruments=inr, history=lambda t: early)
    # 94.50 / 95.00 - 1 = -0.526%, as of Friday.
    assert (row["value"], row["change_pct"], row["as_of"]) == (94.5, -0.53, "2026-10-16")


def test_a_stale_or_implausible_figure_is_unavailable():
    stale = {"^GSPC": _frame("America/New_York", {"2026-09-29": 5700.0, "2026-09-30": 5710.0}),
             "^TNX": _frame("America/New_York", {"2026-10-09": 41.0, "2026-10-12": 41.3})}
    rows = macro.get_overnight_markets(
        TUE, history=stale.__getitem__,
        instruments=[{"label": "S&P 500", "ticker": "^GSPC", "session": "us_close", "unit": "index"},
                     {"label": "US 10-year yield", "ticker": "^TNX", "session": "us_close", "unit": "yield"}])
    assert [r["status"] for r in rows] == ["unavailable", "unavailable"]


def test_a_total_market_failure_names_every_figure_unavailable(monkeypatch):
    def _boom(on):
        raise RuntimeError("yfinance import broke")
    monkeypatch.setattr(macro, "get_overnight_markets", _boom)
    rows = br._before_the_open(TUE)
    assert [r["status"] for r in rows] == ["unavailable"] * len(br.settings.DELIVERY_BRIEF_MARKETS)
    _, missing = br._market_lines(rows)
    assert missing == [m["label"] for m in br.settings.DELIVERY_BRIEF_MARKETS]


def test_an_empty_market_list_removes_the_section(monkeypatch):
    monkeypatch.setattr(br.settings, "DELIVERY_BRIEF_MARKETS", [])
    assert br._before_the_open(TUE) == []
    assert "BEFORE THE OPEN" not in br.render_brief_text({"date": "2026-10-13", "before_the_open": []})
