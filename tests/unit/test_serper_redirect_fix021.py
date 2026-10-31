"""FIX-021: a Google redirect link is not an article's identity.

Since about 01:30 UTC on 30 Oct 2026 Serper returns the links after a
search's top 3 as `google.com/goto` links. The rule under test: where a Serper
response is parsed, a link on google.com (or a subdomain) is no link.

The invariants, with Serper's responses written out by hand here (no helper
of the code under test builds or judges a link):

- one article fetched in two runs, once at rank 2 under its own address and
  once at rank 4 under a redirect, is one stored event and one classifier
  item, in either order;
- a publisher's link that merely contains "google" keeps its link;
- a redirect never counts as an IPO grey-market source, never doubles a chat
  result and is never a macro headline's link;
- the event run record counts the articles dropped this way.

Transports are blocked by tests/hermetic.py; Serper is a fake `requests.post`
behind the real parsers.
"""
from __future__ import annotations

import asyncio

import pytest

import services.data.fetchers.ipo_gmp as gmp_mod
from core.config import settings
from core.events import feed
from services.background import macro_news_fetcher as mf
from services.data.fetchers import news as news_mod
from tests.unit.test_company_events_pr006 import (  # noqa: F401  (feed_env is a fixture)
    NOW, REAL_SEARCH_NEWS, FakeNse, feed_env,
)

GOTO_EXPORT = "https://www.google.com/goto?sig=AFQjCNG4x9&id=7c1e"     # the export-order article
GOTO_PLANT = "https://www.google.com/goto?sig=AFQjCNHq2b&id=91aa"      # an article never seen otherwise
EXPORT = "https://www.livemint.com/companies/news/maruti-suzuki-wins-export-order-11730261234.html"
Q2 = "https://economictimes.indiatimes.com/markets/maruti-suzuki-q2-results/articleshow/1.cms"
PRICES = "https://www.business-standard.com/companies/maruti-suzuki-raises-prices-1251030.html"
SUV = "https://www.ndtvprofit.com/business/maruti-suzuki-launches-new-suv"


def _resp(body: dict):
    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return body
    return Resp()


@pytest.fixture()
def serper(monkeypatch):
    """Serper's HTTP answers, in order, behind the real parsers; each request
    is recorded."""
    from backend.shared.config import settings as shared
    monkeypatch.setattr(shared, "SERPER_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "SERPER_API_KEY", "test-key", raising=False)   # /search reads this one
    monkeypatch.setattr(news_mod, "record_call", lambda api: None)
    state = {"bodies": [], "sent": []}

    def post(url, headers=None, json=None, timeout=None):
        state["sent"].append((url, json))
        body = state["bodies"].pop(0)
        return _resp(body(json) if callable(body) else body)
    monkeypatch.setattr(news_mod.requests, "post", post)
    monkeypatch.setattr(mf.requests, "post", post)
    return state


# ---------------------------------------------------------------------------
# The idempotency invariant: two runs, one article, one event
# ---------------------------------------------------------------------------

# Morning: the export order is result 2, under its own address; result 4 is a
# redirect for an article Serper never shows otherwise.
MORNING = {"news": [
    {"title": "Maruti Suzuki Q2 results: net profit rises 12%", "link": Q2,
     "snippet": "Maruti Suzuki posted...", "date": "10 hours ago", "source": "ET"},
    {"title": "Maruti Suzuki wins export order from Japan", "link": EXPORT,
     "snippet": "The order covers...", "date": "2 hours ago", "source": "Mint"},
    {"title": "Maruti Suzuki raises prices across models", "link": PRICES,
     "snippet": "From November...", "date": "1 day ago", "source": "BS"},
    {"title": "Maruti Suzuki plant visit by analysts", "link": GOTO_PLANT,
     "snippet": "Analysts visited...", "date": "3 hours ago", "source": "Moneycontrol"},
    # No link at all: dropped as before, and not counted as a redirect.
    {"title": "Maruti Suzuki to expand Kharkhoda plant capacity",
     "snippet": "Capacity...", "date": "1 day ago", "source": "PTI"},
]}
# Evening: a new SUV story leads, and the export order slips to result 4,
# where Serper gives only a redirect.
EVENING = {"news": [
    {"title": "Maruti Suzuki launches new SUV", "link": SUV,
     "snippet": "The SUV...", "date": "1 hour ago", "source": "NDTV Profit"},
    {"title": "Maruti Suzuki Q2 results: net profit rises 12%", "link": Q2,
     "snippet": "Maruti Suzuki posted...", "date": "18 hours ago", "source": "ET"},
    {"title": "Maruti Suzuki raises prices across models", "link": PRICES,
     "snippet": "From November...", "date": "1 day ago", "source": "BS"},
    {"title": "Maruti Suzuki wins export order from Japan", "link": GOTO_EXPORT,
     "snippet": "The order covers...", "date": "12 hours ago", "source": "Mint"},
]}
EVENING_AT = NOW.replace(hour=18, minute=30)


def _stored_news(env) -> list[tuple[str, str]]:
    return sorted((e.what, e.source_url) for e in env["store"].load("MARUTI") if e.source == "news")


@pytest.mark.parametrize("order", ["linked_first", "redirect_first"])
def test_one_article_at_rank_2_and_rank_4_is_one_event_and_one_classifier_item(
        feed_env, serper, monkeypatch, order):
    feed_env["nse"] = FakeNse({})                 # news only
    monkeypatch.setattr(feed, "_search_news", REAL_SEARCH_NEWS)
    bodies = [MORNING, EVENING] if order == "linked_first" else [EVENING, MORNING]
    recs = []
    for body, at, slot in zip(bodies, (NOW, EVENING_AT), ("am", "pm")):
        serper["bodies"].append(body)
        recs.append(feed.run_event_feed(slot, now=at, store=feed_env["store"]))

    sent_titles = [t for call in feed_env["model"].calls for t in call]
    assert sent_titles.count("Maruti Suzuki wins export order from Japan") == 1
    assert "Maruti Suzuki plant visit by analysts" not in sent_titles
    assert "Maruti Suzuki to expand Kharkhoda plant capacity" not in sent_titles
    # Four articles came with an address of their own: each is stored once,
    # under it. The plant visit came only as a redirect and is never stored.
    assert _stored_news(feed_env) == sorted([
        ("Maruti Suzuki Q2 results: net profit rises 12%", Q2),
        ("Maruti Suzuki wins export order from Japan", EXPORT),
        ("Maruti Suzuki raises prices across models", PRICES),
        ("Maruti Suzuki launches new SUV", SUV),
    ])
    assert all("google.com" not in (e.source_url or "") for e in feed_env["store"].load("MARUTI"))
    # The morning returns five articles, the evening four; each run drops one
    # for its redirect link (the morning's link-less article is not one).
    counts = {"linked_first": [(5, 1), (4, 1)], "redirect_first": [(4, 1), (5, 1)]}[order]
    assert [(r["news_results"], r["news_redirect_links"]) for r in recs] == counts
    assert sum(r["events_stored"] for r in recs) == 4


def test_the_run_record_starts_both_counts_at_zero_without_a_search(feed_env, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_NEWS_QUERIES_PER_DAY", 0)
    rec = feed.run_event_feed("am", now=NOW, store=feed_env["store"])
    assert rec["news_results"] == 0 and rec["news_redirect_links"] == 0
    assert rec["news_not_searched"] == 1


# ---------------------------------------------------------------------------
# The parsers: /search and /news
# ---------------------------------------------------------------------------

REDIRECTS = [
    "https://www.google.com/goto?sig=AFQjCNG4x9&id=7c1e",
    "https://google.com/goto?sig=AFQjCNG4x9",                # bare host
    "http://WWW.GOOGLE.COM/goto?x=1",                        # case
    "https://www.google.com.:443/goto?x=1",                  # trailing dot, port
    "https://news.google.com/rss/articles/CBMiK2h0dHBz",     # a subdomain
    "//www.google.com/goto?x=1",                             # no scheme
    "www.google.com/goto?x=1",                               # no scheme, no slashes
    "  https://www.google.com/goto?x=1  ",                   # padded
]
PUBLISHERS = [
    "https://www.livemint.com/technology/google-pixel-deal-11730.html",   # path
    "https://economictimes.indiatimes.com/a.cms?ref=google.com",          # query
    "https://www.googleblog.example.com/post",                            # host contains it
    "https://notgoogle.com/a",                                            # suffix without a dot
    "https://google.com.evil.example/a",                                  # google.com as a label
    "https://google.com@evil.example/a",                                  # user info; host evil.example
    "https://www.moneycontrol.com/news/business/google-india-plans.html",
]


@pytest.mark.parametrize("endpoint", ["search", "news"])
def test_a_google_link_is_no_link_and_a_publisher_link_is_unchanged(serper, endpoint):
    items = [{"title": f"T{i}", "snippet": "s", "link": link, "date": "1 hour ago", "source": "S"}
             for i, link in enumerate(REDIRECTS + PUBLISHERS)]
    key = "organic" if endpoint == "search" else "news"
    serper["bodies"].append({key: items})
    n = len(items)
    if endpoint == "search":
        rows = news_mod.search_serper("q", n=n)
    else:
        rows, status = news_mod.search_serper_news_status("q", n=n)
        assert status == "ok"
    assert serper["sent"][0][0] == f"https://google.serper.dev/{endpoint}"
    assert [r["title"] for r in rows] == [f"T{i}" for i in range(n)]
    assert [r["link"] for r in rows] == [""] * len(REDIRECTS) + PUBLISHERS
    assert [r.get("redirect", False) for r in rows] == [True] * len(REDIRECTS) + [False] * len(PUBLISHERS)
    if endpoint == "news":
        assert all(r["source"] == "S" for r in rows)


def test_a_missing_or_empty_link_is_left_as_it_was(serper):
    serper["bodies"].append({"news": [{"title": "No link"}, {"title": "Empty", "link": ""}]})
    rows = news_mod.search_serper_news("q")
    assert rows == [
        {"title": "No link", "snippet": "", "link": "", "date": "", "source": ""},
        {"title": "Empty", "snippet": "", "link": "", "date": "", "source": ""},
    ]


# ---------------------------------------------------------------------------
# The IPO grey-market check (switched off in production)
# ---------------------------------------------------------------------------

@pytest.fixture()
def gmp_on(monkeypatch):
    monkeypatch.setattr(settings, "IPO_GMP_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SERPER_API_KEY_IPO", "ipo-key", raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_MIN_SOURCES", 2, raising=False)
    monkeypatch.setattr(settings, "IPO_GMP_AGREEMENT_TOLERANCE", 0.25, raising=False)


def test_one_real_site_and_redirects_is_fewer_than_two_sources(serper, gmp_on):
    serper["bodies"].append({"organic": [
        {"title": "a", "snippet": "Molbio IPO GMP Rs 120 today", "link": "https://ipowatch.example/molbio"},
        {"title": "b", "snippet": "Molbio GMP Rs 118", "link": "https://www.google.com/goto?id=1"},
        {"title": "c", "snippet": "Molbio GMP Rs 121", "link": "https://www.google.com/goto?id=2"},
        {"title": "d", "snippet": "grey market premium Rs 119", "link": "https://google.com/goto?id=3"},
    ]})
    assert gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=500.0) is None
    assert serper["sent"][0][1]["q"] == "Molbio Diagnostics IPO GMP grey market premium today"


def test_two_real_sites_still_agree_beside_a_redirect(serper, gmp_on):
    """The control: the check still reads real sites."""
    serper["bodies"].append({"organic": [
        {"title": "a", "snippet": "Molbio IPO GMP Rs 120 today", "link": "https://ipowatch.example/molbio"},
        {"title": "b", "snippet": "Molbio GMP Rs 999", "link": "https://www.google.com/goto?id=1"},
        {"title": "c", "snippet": "Molbio GMP Rs 130", "link": "https://investorgain.example/molbio"},
    ]})
    assert gmp_mod.fetch_gmp("Molbio Diagnostics", issue_price=500.0) == {
        "gmp": 125.0, "gmp_pct": 25.0, "sources": 2}


# ---------------------------------------------------------------------------
# Chat news search
# ---------------------------------------------------------------------------

def _chat_search(monkeypatch, serper, by_variant: dict) -> str:
    from services.api.routes import ui_data
    monkeypatch.setattr(ui_data, "_nse_market_context", lambda: "MARKET")
    monkeypatch.setattr(ui_data, "_build_search_variants", lambda q, today: list(by_variant))
    serper["bodies"].extend([lambda req: {"news": by_variant[req["q"]]}] * len(by_variant))
    return asyncio.run(ui_data._chat_tool_search_news("Maruti export order"))


@pytest.mark.parametrize("linked_first", [True, False])
def test_chat_lists_one_article_once_with_its_own_link(monkeypatch, serper, linked_first):
    linked = [{"title": "Maruti Suzuki wins export order from Japan", "link": EXPORT,
               "snippet": "s", "date": "2 hours ago", "source": "Mint"}]
    redirected = [
        {"title": "Maruti Suzuki launches new SUV", "link": SUV, "snippet": "s",
         "date": "1 hour ago", "source": "NDTV Profit"},
        {"title": "Maruti Suzuki raises prices across models", "link": PRICES, "snippet": "s",
         "date": "1 day ago", "source": "BS"},
        {"title": "Maruti Suzuki Q2 results", "link": Q2, "snippet": "s",
         "date": "3 hours ago", "source": "ET"},
        {"title": "Maruti  Suzuki wins export ORDER from Japan", "link": GOTO_EXPORT,
         "snippet": "s", "date": "12 hours ago", "source": "Mint"},
    ]
    variants = {"v1": linked, "v2": redirected} if linked_first else {"v2": redirected, "v1": linked}
    text = _chat_search(monkeypatch, serper, variants)
    assert text.lower().count("wins export order from japan") == 1
    assert f"Source: Mint | {EXPORT}" in text
    assert "google.com" not in text
    assert text.count("Title: ") == 4


def test_chat_shows_an_article_seen_only_by_redirect_without_a_link(monkeypatch, serper):
    text = _chat_search(monkeypatch, serper, {"v1": [
        {"title": "Maruti Suzuki plant visit by analysts", "link": GOTO_PLANT, "snippet": "s",
         "date": "3 hours ago", "source": "Moneycontrol"}]})
    assert "Title: Maruti Suzuki plant visit by analysts\nSource: Moneycontrol\n" in text
    assert "google.com" not in text and "| \n" not in text


def test_two_articles_of_one_title_with_their_own_links_stay_two():
    from services.api.routes.ui_data import _rrf_fuse
    a = {"title": "Sensex closes higher", "link": "https://a.example/1"}
    b = {"title": "Sensex closes higher", "link": "https://b.example/1"}
    assert _rrf_fuse([[a], [b]]) == [a, b]


# ---------------------------------------------------------------------------
# Macro headlines
# ---------------------------------------------------------------------------

def test_a_macro_headline_is_never_kept_under_a_redirect(serper):
    serper["bodies"].append({"news": [
        {"title": "RBI holds repo rate", "link": "https://www.livemint.com/economy/rbi-holds.html",
         "date": "2 hours ago"},
        {"title": "Nifty ends flat", "link": "https://www.google.com/goto?id=9", "date": "1 hour ago"},
        {"title": "Google India plans data centre", "date": "3 hours ago",
         "link": "https://www.moneycontrol.com/news/business/google-india-plans.html"},
        {"title": "FII flows turn positive", "link": "https://news.google.com/rss/articles/x",
         "date": "4 hours ago"},
    ]})
    fetcher = mf.MacroNewsFetcher.__new__(mf.MacroNewsFetcher)
    rows = fetcher._serper_news("India Nifty Sensex stock market news")
    assert [(r["title"], r["url"]) for r in rows] == [
        ("RBI holds repo rate", "https://www.livemint.com/economy/rbi-holds.html"),
        ("Google India plans data centre",
         "https://www.moneycontrol.com/news/business/google-india-plans.html"),
    ]


def test_chat_macro_fallback_shows_no_redirect(monkeypatch, serper):
    from services.api.routes import ui_data

    class _Empty:
        def get_all_today(self):
            return []
    monkeypatch.setattr("services.background.macro_news_cache.MacroNewsCache", _Empty)
    serper["bodies"].append({"news": [
        {"title": "Nifty ends flat", "link": "https://www.google.com/goto?id=9",
         "date": "1 hour ago", "source": "ET"},
        {"title": "RBI holds repo rate", "link": "https://www.livemint.com/economy/rbi-holds.html",
         "date": "2 hours ago", "source": "Mint"}]})
    text = asyncio.run(ui_data._chat_tool_get_macro_news())
    assert "google.com" not in text
    assert "Nifty ends flat — ET\n" in text
    assert "RBI holds repo rate — Mint | https://www.livemint.com/economy/rbi-holds.html" in text
