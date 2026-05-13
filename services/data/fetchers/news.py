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
import re
from datetime import date, timedelta

import requests

from core.config import settings
from services.data.stores.api_usage import record_call

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"


def _normalize_date(date_str: str) -> str:
    """
    Convert Serper's relative or formatted dates to absolute ISO YYYY-MM-DD.
    Examples: "2 days ago" → "2026-04-17", "Apr 15, 2026" → "2026-04-15"
    """
    if not date_str:
        return "date unknown"
    today = date.today()
    s = date_str.strip()

    if re.search(r'\d+\s+(hour|minute|second)s?\s+ago', s, re.I):
        return today.isoformat()

    m = re.match(r'(\d+)\s+days?\s+ago', s, re.I)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()

    m = re.match(r'(\d+)\s+weeks?\s+ago', s, re.I)
    if m:
        return (today - timedelta(weeks=int(m.group(1)))).isoformat()

    m = re.match(r'(\d+)\s+months?\s+ago', s, re.I)
    if m:
        return (today - timedelta(days=int(m.group(1)) * 30)).isoformat()

    try:
        from dateutil import parser as _dp
        return _dp.parse(s).date().isoformat()
    except Exception:
        return s
_NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Request timeout — now from settings (STATIC_AUDIT #15)
from backend.shared.config import settings as _news_settings
_TIMEOUT = _news_settings.SERPER_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Serper (Google Search API)
# ---------------------------------------------------------------------------

def search_serper(
    query: str,
    n: int = settings.NEWS_ARTICLES_PER_QUERY,
    api_key: str | None = None,
) -> list[dict]:
    """
    Search Google via Serper API.

    Returns list of dicts: {title, snippet, link, date}
    Returns [] if no key is available or request fails.

    Parameters
    ----------
    api_key : override the default SERPER_API_KEY (use for dual-key routing)
    """
    key = api_key or settings.SERPER_API_KEY
    if not key:
        logger.debug("[news] No Serper API key — skipping Serper search")
        return []

    try:
        resp = requests.post(
            _SERPER_URL,
            headers={
                "X-API-KEY": key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": n, "hl": "en"},
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
        record_call("serper")
        return results
    except Exception as exc:
        logger.warning("[news] Serper search failed for '%s': %s", query, exc)
        return []


def search_serper_news(
    query: str,
    n: int = 5,
    api_key: str | None = None,
    geo: str | None = "in",
) -> list[dict]:
    """
    Search Google News via Serper /news endpoint.

    Unlike search_serper() which hits /search (web results), this hits /news
    and returns actual news articles with relative publication dates.

    geo="in"  → India-filtered results (default, for Nifty/NSE queries)
    geo=None  → global results, no country filter (for OpenAI, Fed, Musk etc.)

    Returns list of dicts: {title, snippet, link, date, source}
    """
    from backend.shared.config import settings as _s
    key = api_key or _s.SERPER_API_KEY_2 or _s.SERPER_API_KEY
    if not key:
        logger.debug("[news] No Serper key for /news search — skipping")
        return []

    params: dict = {"q": query, "num": n, "hl": "en"}
    if geo:
        params["gl"] = geo

    try:
        resp = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("news", [])[:n]:
            results.append({
                "title":   item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link":    item.get("link", ""),
                "date":    item.get("date", ""),    # relative: "22 hours ago"
                "source":  item.get("source", ""),
            })
        record_call("serper")   # counts against same Serper quota as /search calls
        return results
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        if code == 400:
            logger.warning("[news] Serper /news key exhausted for '%s' — will fall back", query)
        else:
            logger.warning("[news] Serper /news HTTP %s for '%s': %s", code, query, exc)
        return []
    except Exception as exc:
        logger.warning("[news] Serper /news failed for '%s': %s", query, exc)
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
    api_key: str | None = None,
) -> str:
    """
    Run up to `max_queries` searches (Serper preferred, NewsAPI fallback)
    and return a formatted string suitable for prompt injection.

    Parameters
    ----------
    api_key : Serper key override for dual-key routing (pass via get_serper_key)
    """
    if not queries:
        return "No news queries provided."

    lines: list[str] = []
    for query in queries[:max_queries]:
        results = search_serper(query, n=settings.NEWS_ARTICLES_PER_QUERY, api_key=api_key)
        if not results:
            results = search_newsapi(query, n=settings.NEWS_ARTICLES_PER_QUERY)

        if not results:
            lines.append(f"[No results for: {query}]")
            continue

        lines.append(f"\n--- Search: {query} ---")
        for r in results:
            title = r.get("title") or r.get("description", "")
            snippet = r.get("snippet") or r.get("description", "")
            raw_dt = r.get("date") or r.get("publishedAt", "")
            dt = _normalize_date(raw_dt)
            lines.append(f"• [Date: {dt}] {title}: {snippet}")

    return "\n".join(lines) if lines else "No news data available."
