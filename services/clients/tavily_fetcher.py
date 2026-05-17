"""
tools/tavily_fetcher.py
=======================
Full-page content extraction via Tavily API.

Tavily is purpose-built for LLM/RAG use cases: it searches Google,
visits each result URL, strips HTML, and returns the full readable text.
Unlike Serper (which returns a 2-line snippet), Tavily returns the
complete document — critical for policy circulars, regulatory PDFs,
and government press releases.

Free tier: 1,000 calls/month.
Used by:   Policy & Regulatory agent (2 calls per analysis).

Public API
----------
search_tavily(query, max_results)  → list[dict]  {title, content, url}
fetch_tavily_context(queries)      → str   (formatted for prompt injection)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from core.config import settings
from services.data.stores.api_usage import record_call

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT = 15  # Tavily fetches pages, so slower than Serper
_TAVILY_CACHE_DIR = Path("data/tavily_cache")


def _cache_path(queries: list[str], max_queries: int) -> Path:
    """Deterministic cache path keyed on sorted query content + current month."""
    month = date.today().strftime("%Y-%m")
    canonical = "|".join(sorted(queries[:max_queries]))
    q_hash = hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]
    return _TAVILY_CACHE_DIR / month / f"{q_hash}.txt"


def search_tavily(
    query: str,
    max_results: int = 3,
    search_depth: str = "advanced",
) -> list[dict]:
    """
    Search via Tavily and return full extracted page content.

    Parameters
    ----------
    query        : search query string
    max_results  : number of results to return (default 3)
    search_depth : "basic" (snippets) or "advanced" (full content, default)

    Returns
    -------
    list of dicts: {title, content, url, score}
    Returns [] if TAVILY_API_KEY is not set or request fails.
    """
    if not settings.TAVILY_API_KEY:
        logger.debug("[tavily] TAVILY_API_KEY not set — skipping Tavily search")
        return []

    try:
        resp = requests.post(
            _TAVILY_URL,
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title":          item.get("title", ""),
                "content":        item.get("content", ""),
                "url":            item.get("url", ""),
                "published_date": item.get("published_date", ""),  # e.g. "2026-05-07T10:30:00Z"
                "score":          item.get("score", 0.0),
            })
        record_call("tavily")
        return results
    except Exception as exc:
        logger.warning("[tavily] Search failed for '%s': %s", query, exc)
        return []


def fetch_tavily_context(
    queries: list[str],
    max_queries: int = 2,
    max_results_per_query: int = 2,
) -> str:
    """
    Run up to `max_queries` Tavily searches and return formatted context.
    Results are cached to disk for the current calendar month — same query
    within the same month returns cached result without hitting the API.
    Default max_queries=2 to stay within 1,000/month free tier.

    Parameters
    ----------
    queries               : list of search query strings
    max_queries           : max Tavily calls (default 2 — budget guard)
    max_results_per_query : results per call (default 2)

    Returns
    -------
    str — multi-line context block
    """
    if not queries:
        return "No Tavily queries provided."

    # --- Cache check ---
    cache_file = _cache_path(queries, max_queries)
    if cache_file.exists():
        logger.debug("[tavily] Cache hit: %s", cache_file.name)
        return cache_file.read_text(encoding="utf-8")

    # --- Live fetch (existing logic unchanged) ---
    lines: list[str] = []
    for query in queries[:max_queries]:
        results = search_tavily(query, max_results=max_results_per_query)

        if not results:
            lines.append(f"[No Tavily results for: {query}]")
            continue

        lines.append(f"\n--- Tavily (full content): {query} ---")
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            # Truncate long content — limit from settings (STATIC_AUDIT #16)
            from backend.shared.config import settings as _tav_settings
            _max = _tav_settings.TAVILY_MAX_CONTENT_CHARS
            if len(content) > _max:
                content = content[:_max] + "…"
            lines.append(f"• {title}\n  {content}\n  Source: {url}")

    result = "\n".join(lines) if lines else "No Tavily data available."

    # --- Write to cache ---
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(result, encoding="utf-8")
        logger.debug("[tavily] Cache written: %s", cache_file.name)
    except Exception as exc:
        logger.warning("[tavily] Cache write failed (non-fatal): %s", exc)

    return result
