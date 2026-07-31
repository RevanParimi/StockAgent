"""tests/unit/test_news_search_recency.py — F6: recency bound on the shared
`fetch_news_context()` path that feeds the analyst bundle, the preopen shock
check, the RL research loop and the indicator price fallback.

Measured 2026-07-31 against live Serper, unbounded: the preopen "overnight
macro" query returned articles aged 44/60/90/120 days and NOTHING fresh, and a
research query returned an article 4,146 days old. Undated results are common
too, so the prompt shows "[Date: date unknown]" and the LLM cannot tell.
"""
import core.intelligence.rl.workflows.preopen_check as preopen
import services.data.fetchers.news as news


def _capture(monkeypatch, serper_results=None):
    """Record every search_serper call; keep NewsAPI silent."""
    calls: list[dict] = []

    def _serper(query, n=5, api_key=None, tbs=None):
        calls.append({"query": query, "n": n, "tbs": tbs})
        return serper_results if serper_results is not None else [
            {"title": "T", "snippet": "s", "link": "l", "date": "1 day ago"}
        ]

    monkeypatch.setattr(news, "search_serper", _serper)
    monkeypatch.setattr(news, "search_newsapi", lambda *a, **k: [])
    return calls


def test_fetch_news_context_bounds_recency_by_default(monkeypatch):
    calls = _capture(monkeypatch)
    news.fetch_news_context(["some query"], max_queries=1)
    assert calls[0]["tbs"] == "qdr:m"


def test_fetch_news_context_recency_is_configurable(monkeypatch):
    calls = _capture(monkeypatch)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "NEWS_SEARCH_RECENCY", "qdr:w", raising=False)
    news.fetch_news_context(["some query"], max_queries=1)
    assert calls[0]["tbs"] == "qdr:w"


def test_caller_can_tighten_the_recency_bound(monkeypatch):
    calls = _capture(monkeypatch)
    news.fetch_news_context(["some query"], max_queries=1, tbs="qdr:d")
    assert calls[0]["tbs"] == "qdr:d"


def test_caller_can_disable_the_recency_bound(monkeypatch):
    calls = _capture(monkeypatch)
    news.fetch_news_context(["some query"], max_queries=1, tbs="")
    assert calls[0]["tbs"] is None


def test_newsapi_fallback_still_runs_when_serper_is_empty(monkeypatch):
    _capture(monkeypatch, serper_results=[])
    seen = []
    monkeypatch.setattr(news, "search_newsapi",
                        lambda q, n=5: seen.append(q) or [
                            {"title": "N", "description": "d", "publishedAt": "2026-07-30"}
                        ])
    out = news.fetch_news_context(["q"], max_queries=1)
    assert seen == ["q"]
    assert "N" in out


def test_preopen_asks_for_overnight_news_only(monkeypatch):
    """The shock rater must not score 'overnight' off month-old headlines."""
    seen: dict = {}

    def _fetch(queries, max_queries=3, api_key=None, tbs=None):
        seen["tbs"] = tbs
        return "ctx"

    monkeypatch.setattr(news, "fetch_news_context", _fetch)
    from datetime import date
    preopen._fetch_overnight_context(date.today())
    assert seen["tbs"] == "qdr:w"
