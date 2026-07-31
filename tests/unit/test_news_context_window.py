"""tests/unit/test_news_context_window.py — AUD-041 date-filtered RL news context
+ F1 (sensing audit): company-name resolution and one /search fallback when the
/news endpoint comes back empty."""
from datetime import date, timedelta

import services.data.fetchers.news as news


def _patch_results(monkeypatch, results, fallback=None, calls=None):
    """
    Stub both Serper endpoints. `calls` (dict) records queries per endpoint under
    "news"/"search" and the keyword args under "news_kw"/"search_kw".
    """
    def _news(query, *a, **k):
        if calls is not None:
            calls.setdefault("news", []).append(query)
            calls.setdefault("news_kw", []).append(k)
        return results

    def _search(query, *a, **k):
        if calls is not None:
            calls.setdefault("search", []).append(query)
            calls.setdefault("search_kw", []).append(k)
        return fallback or []

    monkeypatch.setattr(news, "search_serper_news", _news)
    monkeypatch.setattr(news, "search_serper", _search)
    # Registry lookup is stubbed empty by default so tests never touch data/.
    monkeypatch.setattr(news, "_managed_ticker_names", dict)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "SERPER_API_KEY", "test-key", raising=False)


def _fresh(title, source="ET"):
    return {"date": date.today().isoformat(), "title": title, "snippet": "s", "source": source}


def test_old_articles_are_dropped(monkeypatch):
    stale = (date.today() - timedelta(days=86)).isoformat()
    _patch_results(monkeypatch, [
        _fresh("Fresh headline"),
        {"date": stale, "title": "April ghost", "snippet": "s", "source": "ET"},
    ])
    ctx = news.get_news_context("TATAELXSI")
    assert "Fresh headline" in ctx
    assert "April ghost" not in ctx


def test_undated_articles_are_dropped(monkeypatch):
    _patch_results(monkeypatch, [
        {"date": "", "title": "Undated thing", "snippet": "s", "source": "ET"},
    ])
    assert news.get_news_context("TCS") == "Market context unavailable."


def test_all_stale_returns_unavailable(monkeypatch):
    stale = (date.today() - timedelta(days=30)).isoformat()
    _patch_results(monkeypatch, [
        {"date": stale, "title": "Old", "snippet": "s", "source": "ET"},
    ])
    assert news.get_news_context("TCS") == "Market context unavailable."


def test_window_label_is_honest(monkeypatch):
    _patch_results(monkeypatch, [_fresh("Now")])
    ctx = news.get_news_context("TCS", window_days=3)
    assert "last 3 days" in ctx
    assert "48h" not in ctx


def test_relative_dates_still_work(monkeypatch):
    _patch_results(monkeypatch, [
        {"date": "2 hours ago", "title": "Breaking", "snippet": "s", "source": "ET"},
        {"date": "2 weeks ago", "title": "Stale relative", "snippet": "s", "source": "ET"},
    ])
    ctx = news.get_news_context("INFY")
    assert "Breaking" in ctx
    assert "Stale relative" not in ctx


# ---------------------------------------------------------------------------
# F1 — company-name resolution (raw NSE symbols were returning nothing)
# ---------------------------------------------------------------------------

def test_company_name_is_used_in_query(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: "Tata Elxsi Limited")
    news.get_news_context("TATAELXSI")
    assert "Tata Elxsi Limited" in calls["news"][0]
    assert "TATAELXSI" in calls["news"][0]


def test_resolver_failure_falls_back_to_ticker_query(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)

    def _boom(_t):
        raise RuntimeError("cache corrupt")

    monkeypatch.setattr(news, "resolve_company_name", _boom)
    ctx = news.get_news_context("YESBANK")
    assert "Result" in ctx
    assert "YESBANK" in calls["news"][0]


def test_unresolvable_ticker_queries_symbol_only(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: None)
    news.get_news_context("NEWLISTING")
    assert calls["news"][0].startswith("NEWLISTING")


# ---------------------------------------------------------------------------
# F1 — managed-ticker registry as the second name source. The learned
# company-name cache does not exist in prod (verified 2026-07-31), so the
# curated overrides alone covered 1 of the 12 news-blind tickers; the registry
# (data/managed_tickers.json) carries a real name for every managed ticker.
# ---------------------------------------------------------------------------

def test_managed_registry_supplies_name_when_resolver_misses(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: None)
    monkeypatch.setattr(news, "_managed_ticker_names",
                        lambda: {"PAYTM": "One 97 Communications Ltd"})
    news.get_news_context("PAYTM")
    assert "One 97 Communications Ltd" in calls["news"][0]


def test_curated_name_wins_over_registry(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: "Adani Green Energy Limited")
    monkeypatch.setattr(news, "_managed_ticker_names",
                        lambda: {"ADANIGREEN": "Adani Green Energy Ltd"})
    news.get_news_context("ADANIGREEN")
    assert "Adani Green Energy Limited" in calls["news"][0]


def test_registry_failure_falls_back_to_ticker_query(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: None)

    def _boom():
        raise OSError("registry unreadable")

    monkeypatch.setattr(news, "_managed_ticker_names", _boom)
    ctx = news.get_news_context("OLECTRA")
    assert "Result" in ctx
    assert calls["news"][0].startswith("OLECTRA")


def test_registry_name_equal_to_symbol_is_not_duplicated(monkeypatch):
    """Bootstrapped rows use the symbol as the name — don't emit 'X X ...'."""
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    monkeypatch.setattr(news, "resolve_company_name", lambda t: None)
    monkeypatch.setattr(news, "_managed_ticker_names", lambda: {"SUZLON": "SUZLON"})
    news.get_news_context("SUZLON")
    assert calls["news"][0].startswith("SUZLON NSE")


def test_managed_ticker_names_reads_the_registry(monkeypatch):
    """The real helper maps sym -> name from load_managed_tickers()."""
    import services.api.log_buffer as log_buffer
    monkeypatch.setattr(log_buffer, "load_managed_tickers", lambda: [
        {"sym": "yesbank", "name": "Yes Bank Ltd", "sector": "banking_bfsi"},
        {"sym": "", "name": "junk row"},
    ])
    assert news._managed_ticker_names()["YESBANK"] == "Yes Bank Ltd"


# ---------------------------------------------------------------------------
# F1 — RECENCY. Measured 2026-07-31 against live Serper: the /news endpoint
# always returned 5 articles for the raw-symbol query, but they were months old
# (Jan/Apr/May) and the AUD-041 filter dropped every one — that, not an empty
# response, is what made 12 of 16 tickers "news blind". Asking Serper for a
# recency-bounded result set (tbs=qdr:w) took YESBANK from 0 to 4 in-window
# articles with the query otherwise unchanged.
# ---------------------------------------------------------------------------

def test_news_query_is_recency_bounded(monkeypatch):
    calls: dict[str, list] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    news.get_news_context("TCS")
    assert calls["news_kw"][0]["tbs"] == "qdr:w"


def test_recency_window_is_configurable(monkeypatch):
    calls: dict[str, list] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "NEWS_CONTEXT_RECENCY", "qdr:d", raising=False)
    news.get_news_context("TCS")
    assert calls["news_kw"][0]["tbs"] == "qdr:d"


def test_recency_bound_can_be_disabled(monkeypatch):
    calls: dict[str, list] = {}
    _patch_results(monkeypatch, [_fresh("Result")], calls=calls)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "NEWS_CONTEXT_RECENCY", "", raising=False)
    news.get_news_context("TCS")
    assert calls["news_kw"][0]["tbs"] is None


def test_fallback_search_is_recency_bounded_too(monkeypatch):
    calls: dict[str, list] = {}
    _patch_results(monkeypatch, [], fallback=[_fresh("Recovered")], calls=calls)
    news.get_news_context("PAYTM")
    assert calls["search_kw"][0]["tbs"] == "qdr:w"


def test_search_serper_news_sends_tbs_to_serper(monkeypatch):
    sent: dict = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"news": []}

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(news.requests, "post", _post)
    news.search_serper_news("q", api_key="k", tbs="qdr:w")
    assert sent["tbs"] == "qdr:w"


def test_search_serper_news_omits_tbs_when_unset(monkeypatch):
    sent: dict = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"news": []}

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(news.requests, "post", _post)
    news.search_serper_news("q", api_key="k")
    assert "tbs" not in sent


def test_search_serper_sends_tbs_to_serper(monkeypatch):
    sent: dict = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"organic": []}

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(news.requests, "post", _post)
    news.search_serper("q", api_key="k", tbs="qdr:d")
    assert sent["tbs"] == "qdr:d"


# ---------------------------------------------------------------------------
# F1 — single /search fallback when /news yields nothing usable
# ---------------------------------------------------------------------------

def test_fallback_search_fires_when_news_endpoint_empty(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [], fallback=[_fresh("Recovered by fallback")], calls=calls)
    ctx = news.get_news_context("PAYTM")
    assert "Recovered by fallback" in ctx
    assert len(calls["search"]) == 1          # exactly one extra Serper call


def test_fallback_search_fires_when_all_news_results_are_stale(monkeypatch):
    stale = (date.today() - timedelta(days=40)).isoformat()
    calls: dict[str, list[str]] = {}
    _patch_results(
        monkeypatch,
        [{"date": stale, "title": "Old", "snippet": "s", "source": "ET"}],
        fallback=[_fresh("Recovered by fallback")],
        calls=calls,
    )
    ctx = news.get_news_context("OLAELEC")
    assert "Recovered by fallback" in ctx
    assert len(calls["search"]) == 1


def test_fallback_not_called_when_news_endpoint_has_results(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [_fresh("Primary")], fallback=[_fresh("Should not appear")],
                   calls=calls)
    ctx = news.get_news_context("TCS")
    assert "Primary" in ctx
    assert "search" not in calls


def test_fallback_results_respect_the_date_filter(monkeypatch):
    """AUD-041 must hold on the fallback path too — undated/old must not leak."""
    stale = (date.today() - timedelta(days=90)).isoformat()
    _patch_results(monkeypatch, [], fallback=[
        {"date": stale, "title": "April ghost", "snippet": "s"},
        {"date": "", "title": "Undated ghost", "snippet": "s"},
    ])
    assert news.get_news_context("RBLBANK") == "Market context unavailable."


def test_fallback_is_capped_at_one_extra_call(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [], fallback=[], calls=calls)
    assert news.get_news_context("IDFCFIRSTB") == "Market context unavailable."
    assert len(calls["search"]) == 1          # no retry loop


def test_fallback_can_be_disabled_by_config(monkeypatch):
    calls: dict[str, list[str]] = {}
    _patch_results(monkeypatch, [], fallback=[_fresh("Recovered by fallback")], calls=calls)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "NEWS_CONTEXT_FALLBACK_SEARCH", False, raising=False)
    assert news.get_news_context("PAYTM") == "Market context unavailable."
    assert "search" not in calls
