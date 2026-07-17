"""tests/unit/test_news_context_window.py — AUD-041 date-filtered RL news context."""
from datetime import date, timedelta

import services.data.fetchers.news as news


def _patch_results(monkeypatch, results):
    monkeypatch.setattr(news, "search_serper_news", lambda *a, **k: results)
    from backend.shared.config import settings as _s
    monkeypatch.setattr(_s, "SERPER_API_KEY", "test-key", raising=False)


def test_old_articles_are_dropped(monkeypatch):
    today = date.today().isoformat()
    stale = (date.today() - timedelta(days=86)).isoformat()
    _patch_results(monkeypatch, [
        {"date": today, "title": "Fresh headline", "snippet": "s", "source": "ET"},
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
    today = date.today().isoformat()
    _patch_results(monkeypatch, [
        {"date": today, "title": "Now", "snippet": "s", "source": "ET"},
    ])
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
