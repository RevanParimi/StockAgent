"""
tools/news_fetcher.py
=====================
News and search result fetching via Serper API (Google search)
and NewsAPI. Falls back gracefully when API keys are not set.

Public API
----------
search_serper(query, n)       → list[dict]  (title, snippet, link, date)
search_newsapi(query, n)      → list[dict]
fetch_news_context(queries)   → str   (formatted for prompt injection)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from config import settings

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Request timeout in seconds
_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Serper (Google Search API)
# ---------------------------------------------------------------------------

def search_serper(query: str, n: int = settings.NEWS_ARTICLES_PER_QUERY) -> list[dict]:
    """
    Search Google via Serper API.

    Returns list of dicts: {title, snippet, link, date}
    Returns [] if SERPER_API_KEY is not set or request fails.
    """
    if not settings.SERPER_API_KEY:
        logger.debug("[news] SERPER_API_KEY not set — skipping Serper search")
        return []

    try:
        resp = requests.post(
            _SERPER_URL,
            headers={
                "X-API-KEY": settings.SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": n, "gl": "in", "hl": "en"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:n]:
            results.append({
                "title":   item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link":    item.get("link", ""),
                "date":    item.get("date", ""),
            })
        return results
    except Exception as exc:
        logger.warning("[news] Serper search failed for '%s': %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# NewsAPI
# ---------------------------------------------------------------------------

def search_newsapi(query: str, n: int = settings.NEWS_ARTICLES_PER_QUERY) -> list[dict]:
    """
    Search news articles via NewsAPI.

    Returns list of dicts: {title, description, source, publishedAt, url}
    Returns [] if NEWSAPI_KEY is not set or request fails.
    """
    if not settings.NEWSAPI_KEY:
        logger.debug("[news] NEWSAPI_KEY not set — skipping NewsAPI search")
        return []

    from_date = (date.today() - timedelta(days=30)).isoformat()
    try:
        resp = requests.get(
            _NEWSAPI_URL,
            params={
                "q": query,
                "apiKey": settings.NEWSAPI_KEY,
                "language": "en",
                "sortBy": "publishedAt",
                "from": from_date,
                "pageSize": n,
                "domains": ",".join(settings.NEWS_SOURCES),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])[:n]
        return [
            {
                "title":       a.get("title", ""),
                "description": a.get("description", ""),
                "source":      a.get("source", {}).get("name", ""),
                "publishedAt": a.get("publishedAt", ""),
                "url":         a.get("url", ""),
            }
            for a in articles
        ]
    except Exception as exc:
        logger.warning("[news] NewsAPI search failed for '%s': %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# Multi-query context builder
# ---------------------------------------------------------------------------

def fetch_news_context(
    queries: list[str],
    max_queries: int = settings.SERPER_MAX_QUERIES,
) -> str:
    """
    Run up to `max_queries` searches (Serper preferred, NewsAPI fallback)
    and return a formatted string suitable for prompt injection.
    """
    if not queries:
        return "No news queries provided."

    lines: list[str] = []
    for query in queries[:max_queries]:
        results = search_serper(query, n=settings.NEWS_ARTICLES_PER_QUERY)
        if not results:
            results = search_newsapi(query, n=settings.NEWS_ARTICLES_PER_QUERY)

        if not results:
            lines.append(f"[No results for: {query}]")
            continue

        lines.append(f"\n--- Search: {query} ---")
        for r in results:
            title = r.get("title") or r.get("description", "")
            snippet = r.get("snippet") or r.get("description", "")
            dt = r.get("date") or r.get("publishedAt", "")
            lines.append(f"• [{dt}] {title}: {snippet}")

    return "\n".join(lines) if lines else "No news data available."
