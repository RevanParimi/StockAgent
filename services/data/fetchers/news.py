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

from backend.shared.data.fetchers.symbol_resolver import resolve_company_name
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
    except Exception as exc:
        logger.debug("[news] Date parse failed for %r: %s", s, exc)
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
    tbs: str | None = None,
) -> list[dict]:
    """
    Search Google via Serper API.

    Returns list of dicts: {title, snippet, link, date}
    Returns [] if no key is available or request fails.

    Parameters
    ----------
    api_key : override the default SERPER_API_KEY (use for dual-key routing)
    tbs     : Google recency filter, e.g. "qdr:d"/"qdr:w"/"qdr:m". None = no bound.
    """
    key = api_key or settings.SERPER_API_KEY
    if not key:
        logger.debug("[news] No Serper API key — skipping Serper search")
        return []

    params: dict = {"q": query, "num": n, "hl": "en"}
    if tbs:
        params["tbs"] = tbs

    try:
        resp = requests.post(
            _SERPER_URL,
            headers={
                "X-API-KEY": key,
                "Content-Type": "application/json",
            },
            json=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("[news] Serper returned non-JSON for query %r: %s", query, exc)
            return []
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
    tbs: str | None = None,
) -> list[dict]:
    """
    Search Google News via Serper /news endpoint.

    Unlike search_serper() which hits /search (web results), this hits /news
    and returns actual news articles with relative publication dates.

    geo="in"  → India-filtered results (default, for Nifty/NSE queries)
    geo=None  → global results, no country filter (for OpenAI, Fed, Musk etc.)
    tbs       → Google recency filter, e.g. "qdr:d"/"qdr:w"/"qdr:m". Without it
                Google happily returns months-old articles for a ticker query
                (measured 2026-07-31: 5 of 5 results were 2-6 months stale).

    Returns list of dicts: {title, snippet, link, date, source}
    """
    from backend.shared.config import settings as _s
    key = api_key or _s.SERPER_API_KEY
    if not key:
        logger.debug("[news] No Serper key for /news search — skipping")
        return []

    params: dict = {"q": query, "num": n, "hl": "en"}
    if geo:
        params["gl"] = geo
    if tbs:
        params["tbs"] = tbs

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
    tbs: str | None = None,
) -> str:
    """
    Run up to `max_queries` searches (Serper preferred, NewsAPI fallback)
    and return a formatted string suitable for prompt injection.

    F6 (2026-07-31): results are recency-bounded. Unbounded, this path served
    2-4 MONTH old articles to the preopen shock rater and an 11-year-old one to
    the research loop, most of them undated so the prompt read
    "[Date: date unknown]" and the model could not tell. The bound also makes
    Google return date metadata far more often.

    Parameters
    ----------
    api_key : Serper key override for dual-key routing (pass via get_serper_key)
    tbs     : recency bound override — "qdr:d"/"qdr:w"/"qdr:m", "" to disable.
              None (default) uses settings.NEWS_SEARCH_RECENCY.
    """
    if not queries:
        return "No news queries provided."

    from backend.shared.config import settings as _s
    recency = (getattr(_s, "NEWS_SEARCH_RECENCY", "qdr:m") if tbs is None else tbs) or None

    lines: list[str] = []
    for query in queries[:max_queries]:
        results = search_serper(query, n=settings.NEWS_ARTICLES_PER_QUERY,
                                api_key=api_key, tbs=recency)
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


# ---------------------------------------------------------------------------
# RL daily review — per-ticker news context
# ---------------------------------------------------------------------------

def _managed_ticker_names() -> dict[str, str]:
    """
    Ticker -> company name from the managed-ticker registry
    (data/managed_tickers.json). Second name source after the curated
    overrides: the learned company-name cache does not exist in prod, but every
    managed ticker carries a real name in the registry ("PAYTM" ->
    "One 97 Communications Ltd"). Zero network, zero API cost.
    """
    from services.api.log_buffer import load_managed_tickers
    return {
        str(t.get("sym", "")).upper(): str(t.get("name", "") or "")
        for t in load_managed_tickers()
        if t.get("sym")
    }


def _company_name_for_news(ticker: str) -> str:
    """
    Best-effort company name: curated override / learned cache -> managed-ticker
    registry -> "" (caller queries by symbol alone). Never raises — a blind news
    query is bad, but a crashed daily review is worse.
    """
    try:
        name = resolve_company_name(ticker)
        if name:
            return name
    except Exception as exc:
        logger.debug("[news] company-name resolution failed for %s: %s", ticker, exc)
    try:
        name = _managed_ticker_names().get(ticker.upper(), "")
        if name:
            return name
    except Exception as exc:
        logger.debug("[news] managed-ticker registry unreadable for %s: %s", ticker, exc)
    return ""


def _recent_article_lines(
    results: list[dict], max_articles: int, window_days: int
) -> tuple[list[str], int]:
    """
    AUD-041 filter: keep only articles dated within `window_days`; drop
    dated-but-old and undated ones. Returns (formatted bullet lines, dropped).
    """
    cutoff = date.today() - timedelta(days=window_days)
    lines: list[str] = []
    dropped = 0
    for r in results[:max_articles]:
        date_str = _normalize_date(r.get("date", ""))
        try:
            article_date = date.fromisoformat(date_str)
        except ValueError:
            dropped += 1            # undated/unparseable — can't correlate
            continue
        if article_date < cutoff:
            dropped += 1            # AUD-041: the April-ghost class
            continue
        title   = r.get("title", "").strip()
        snippet = r.get("snippet", "").strip()
        source  = r.get("source", "")
        if title:
            lines.append(
                f"• [Date: {date_str}]"
                + (f" [{source}]" if source else "")
                + f" {title}"
                + (f": {snippet}" if snippet else "")
            )
    return lines, dropped


def get_news_context(ticker: str, max_articles: int = 5, window_days: int = 3) -> str:
    """
    Fetch recent news for a specific NSE ticker for the RL daily review.

    Called by daily_review.py to populate FeedbackAgentInput.market_context_today.
    Uses Serper /news with a company-specific query and geo=in for India.

    F1 (sensing audit 2026-07-31). 12 of 16 tickers ran news-blind on 2026-07-30,
    which matters because a blind review funnels real news-driven misses into
    model_bias and contaminates the learned weights. Measured cause: Serper was
    NOT returning nothing — it returned 5 articles every time, all months old
    (Jan/Apr/May), and the window filter below dropped every one. Three levers,
    in order of effect:
      1. `tbs` recency bound on the search itself (data_fetch.news_context_recency)
         — took YESBANK from 0 to 4 in-window articles, query unchanged.
      2. company name in the query (curated override / learned cache, else the
         managed-ticker registry) — buys specificity: company headlines instead
         of "11 BSE 500 stocks" roundups.
      3. if the result set is STILL empty, ONE /search call with the same query
         (kill-switch: data_fetch.news_context_fallback_search). No retries —
         hard cap of +1 Serper call per blind ticker-day.

    AUD-041: articles are FILTERED to the last `window_days` calendar days
    (3 covers the Monday-reviews-Friday weekend gap); dated-but-old and
    undated articles are dropped — the old "(last 48h context)" label carried
    months-old stories straight into the RL training signal. The filter applies
    to the fallback results too; a recovered-but-undated article is still dropped.

    Returns a formatted string with [Date: YYYY-MM-DD] tags so FeedbackAgent
    can correlate articles with the trading day under review.
    Returns "Market context unavailable." on failure — never raises.

    Parameters
    ----------
    ticker       : NSE symbol e.g. "TATAMOTORS", "HDFCBANK"
    max_articles : cap on number of articles returned (default 5)
    window_days  : drop articles older than this many calendar days (default 3)
    """
    try:
        from backend.shared.config import settings as _s
        key = _s.SERPER_API_KEY
        if not key:
            logger.debug("[news] get_news_context: no Serper key configured")
            return "Market context unavailable."

        company = _company_name_for_news(ticker)

        # Company-specific query — geo=in keeps results India-relevant, and tbs
        # bounds Google to recent articles (without it the top hits are stale
        # "Q3/Q4 results" roundups that the window filter then throws away).
        recency = getattr(_s, "NEWS_CONTEXT_RECENCY", "qdr:w") or None
        prefix  = f"{company} " if company and company.upper() != ticker.upper() else ""
        query   = f"{prefix}{ticker} NSE India company news"
        results = search_serper_news(query, n=max_articles, api_key=key, geo="in",
                                     tbs=recency)
        lines, dropped = _recent_article_lines(results, max_articles, window_days)

        if not lines and getattr(_s, "NEWS_CONTEXT_FALLBACK_SEARCH", True):
            # /news came back empty or entirely stale — one web-search retry.
            fb = search_serper(query, n=max_articles, api_key=key, tbs=recency)
            fb_lines, fb_dropped = _recent_article_lines(fb, max_articles, window_days)
            lines, dropped = fb_lines, dropped + fb_dropped
            if fb_lines:
                logger.info("[news] get_news_context: /search fallback recovered "
                            "%d articles for %s", len(fb_lines), ticker)

        if dropped:
            logger.debug("[news] get_news_context: dropped %d stale/undated articles for %s",
                         dropped, ticker)
        if not lines:
            logger.debug("[news] get_news_context: no in-window results for %s", ticker)
            return "Market context unavailable."

        header = f"Recent news for {company or ticker} (last {window_days} days):"
        return "\n".join([header, *lines])

    except Exception as exc:
        logger.warning("[news] get_news_context failed for %s: %s", ticker, exc)
        return "Market context unavailable."
