"""
services/background/macro_news_fetcher.py
==========================================
Two-agent background fetcher for India macro/market news.

FetchAgent  — hits Serper /news + NewsAPI top-headlines
ReviewAgent — LLM validates coverage, assigns severity + impact_tags,
              returns satisfied/missing_topics for gap-filling

Architecture:
  - Runs in APScheduler daemon thread (sync only — no asyncio)
  - Max 2 iterations per run (FetchAgent → ReviewAgent → refine if needed)
  - Always writes partial results even if reviewer is not satisfied
  - Severity and tags are fully LLM-assigned (no keyword heuristics)

Two query modes (called by separate APScheduler jobs):
  "market_hours" — runs at 9:00 / 12:00 / 15:00 IST weekdays
                   Serper /news for real-time Nifty/market news
  "daily"        — runs at 7:30 IST weekdays
                   NewsAPI top-headlines + policy/RBI Serper queries

CRITICAL (from live testing):
  - Do NOT append date strings to Serper queries — returns zero results
  - Serper /news returns key "news" (not "organic")
  - Dates from Serper are relative ("5 hours ago") — normalised to ISO here
  - NewsAPI NEWSAPI_KEY is optional — graceful skip if not set
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 2
_SERPER_NEWS_URL = "https://google.serper.dev/news"
_NEWSAPI_URL     = "https://newsapi.org/v2/top-headlines"
_TIMEOUT         = 12  # seconds

# ── Impact tag vocabulary — must match canonical sector keys used by the
#    classify node so that reviewer criterion 4 intersection works. ──────────
VALID_IMPACT_TAGS: str = (
    "automobile, banking_bfsi, it_sector, renewable_energy, pharma, fmcg, "
    "metals, oilgas, capgoods, chemicals, defence, insurance, realestate, "
    "gold, crude, fuel, currency, inr, rbi, sebi, policy, budget, "
    "economy, markets, inflation, interest_rate, fii, global"
)

# ── Queries (no date strings — confirmed to break Serper results) ────────────
MARKET_QUERIES: list[str] = [
    "India Nifty Sensex stock market news",
    "Indian economy major development today",
]

DAILY_QUERIES: list[str] = [
    "India RBI SEBI policy announcement",
    "India government economic policy news",
]


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------

def _normalize_serper_date(date_str: str) -> str:
    """
    Convert Serper's relative date strings to ISO YYYY-MM-DD.
    Serper returns: "5 hours ago", "1 day ago", "2 days ago", "Apr 10, 2026"
    """
    if not date_str:
        return date.today().isoformat()
    today = date.today()
    s = date_str.strip().lower()

    if re.search(r"\d+\s+(hour|minute|second)s?\s+ago", s):
        return today.isoformat()
    m = re.match(r"(\d+)\s+days?\s+ago", s)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    m = re.match(r"(\d+)\s+weeks?\s+ago", s)
    if m:
        return (today - timedelta(weeks=int(m.group(1)))).isoformat()
    try:
        from dateutil import parser as _dp
        return _dp.parse(date_str).date().isoformat()
    except Exception:
        return today.isoformat()


# ---------------------------------------------------------------------------
# MacroNewsFetcher
# ---------------------------------------------------------------------------

class MacroNewsFetcher:
    """
    FetchAgent + ReviewAgent orchestrator.
    All methods are synchronous — designed to run inside APScheduler threads.
    """

    def __init__(self) -> None:
        from services.background.macro_news_cache import MacroNewsCache
        self._cache = MacroNewsCache()

    # ------------------------------------------------------------------
    # Public entry point (called by scheduler jobs)
    # ------------------------------------------------------------------

    def fetch_and_review(self, query_type: str) -> dict:
        """
        Run one fetch+review cycle.

        Parameters
        ----------
        query_type : "market_hours" | "daily"
            Determines which query set to use.

        Returns
        -------
        dict with keys: new_entries (int), query_type (str), iterations (int)
        """
        queries = MARKET_QUERIES if query_type == "market_hours" else DAILY_QUERIES
        logger.info("[MacroFetcher] Starting %s run (%d queries)", query_type, len(queries))

        all_tagged: list[dict] = []
        seen_urls:  set[str]  = set()

        for iteration in range(1, _MAX_ITERATIONS + 1):
            # ── FetchAgent ────────────────────────────────────────────
            raw = self._fetch_results(queries, include_headlines=(query_type == "daily"))
            if not raw:
                logger.warning("[MacroFetcher] Iteration %d: no raw results", iteration)
                break

            # ── ReviewAgent (LLM) ─────────────────────────────────────
            review = self._review_coverage(raw)
            for entry in review.get("tagged_entries", []):
                url = entry.get("url", "")
                if url and url not in seen_urls:
                    all_tagged.append(entry)
                    seen_urls.add(url)

            satisfied = review.get("satisfied", True)
            missing   = review.get("missing_topics", [])

            if satisfied or iteration >= _MAX_ITERATIONS:
                if not satisfied:
                    logger.warning(
                        "[MacroFetcher] Not satisfied after %d iteration(s) — "
                        "writing partial results (missing: %s)",
                        iteration, missing,
                    )
                break

            # ── Refine queries for next iteration ─────────────────────
            queries = [f"India {topic}" for topic in missing[:2]]
            logger.info("[MacroFetcher] Iteration %d done; refining for: %s", iteration, missing)

        # Always write whatever we have — never discard on dissatisfied state
        added = self._cache.add_entries(all_tagged)
        logger.info(
            "[MacroFetcher] %s run complete — %d new entries added",
            query_type, added,
        )
        return {"new_entries": added, "query_type": query_type, "iterations": iteration}

    # ------------------------------------------------------------------
    # FetchAgent
    # ------------------------------------------------------------------

    def _fetch_results(self, queries: list[str], include_headlines: bool = False) -> list[dict]:
        """Run Serper /news for each query, optionally NewsAPI top-headlines."""
        results: list[dict] = []

        for query in queries:
            results.extend(self._serper_news(query))

        if include_headlines:
            results.extend(self._newsapi_top_headlines())

        return results

    def _serper_news(self, query: str) -> list[dict]:
        """
        Hit Serper /news endpoint.
        Uses SERPER_API_KEY_2 first (less consumed by RL pipeline during market hours),
        falls back to SERPER_API_KEY_1.
        """
        try:
            from backend.shared.config import settings as _s
            key = _s.SERPER_API_KEY_2 or _s.SERPER_API_KEY
            if not key:
                logger.debug("[MacroFetcher] No Serper key configured — skipping")
                return []

            resp = requests.post(
                _SERPER_NEWS_URL,
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": 5, "gl": "in", "hl": "en"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data  = resp.json()
            items = data.get("news", [])  # key is "news" not "organic"
            return [
                {
                    "source":         "serper_news",
                    "title":          item.get("title", ""),
                    "snippet":        item.get("snippet", ""),
                    "url":            item.get("link", ""),
                    "published_date": _normalize_serper_date(item.get("date", "")),
                    "query_used":     query,
                }
                for item in items
                if item.get("title")
            ]
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body   = (exc.response.text or "")[:200] if exc.response is not None else ""
            if status == 400:
                logger.warning(
                    "[MacroFetcher] Serper key exhausted (HTTP 400) for query '%s' | body: %s",
                    query, body,
                )
            else:
                logger.warning(
                    "[MacroFetcher] Serper HTTP %s for query '%s': %s | body: %s",
                    status, query, exc, body,
                )
            return []
        except Exception as exc:
            logger.warning("[MacroFetcher] Serper news failed for '%s': %s", query, exc, exc_info=True)
            return []

    def _newsapi_top_headlines(self) -> list[dict]:
        """NewsAPI /top-headlines?country=in&category=business — daily policy/RBI run."""
        try:
            from backend.shared.config import settings as _s
            if not _s.NEWSAPI_KEY:
                logger.debug("[MacroFetcher] NEWSAPI_KEY not set — skipping top-headlines")
                return []

            resp = requests.get(
                _NEWSAPI_URL,
                params={
                    "country":  "in",
                    "category": "business",
                    "apiKey":   _s.NEWSAPI_KEY,
                    "pageSize": 10,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            return [
                {
                    "source":         "newsapi_headlines",
                    "title":          a.get("title", ""),
                    "snippet":        a.get("description", "") or "",
                    "url":            a.get("url", ""),
                    "published_date": (a.get("publishedAt", "") or "")[:10],
                    "query_used":     "top_headlines_india_business",
                }
                for a in articles
                if a.get("title") and "[Removed]" not in (a.get("title", ""))
            ]
        except Exception as exc:
            logger.warning("[MacroFetcher] NewsAPI top-headlines failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # ReviewAgent (LLM)
    # ------------------------------------------------------------------

    def _review_coverage(self, raw_results: list[dict]) -> dict:
        """
        LLM-based review: assigns severity + impact_tags + summary per article,
        and judges whether coverage is adequate.

        Uses sync OpenAI client (get_llm_client) — safe for APScheduler thread context.
        Falls back to accepting raw results as LOW-severity if LLM fails.

        Returns
        -------
        {
          "satisfied":      bool,
          "missing_topics": list[str],   # specific search terms if not satisfied
          "tagged_entries": list[dict],  # raw_results with severity/impact_tags/summary added
        }
        """
        if not raw_results:
            return {"satisfied": False, "missing_topics": ["India market news"], "tagged_entries": []}

        today = date.today().isoformat()
        articles_text = "\n".join(
            f"{i}. [{r.get('published_date', 'unknown')}] {r.get('title', '')} — "
            f"{(r.get('snippet', '') or '')[:120]}"
            for i, r in enumerate(raw_results[:15], 1)
        )

        prompt = f"""Today is {today}. You are reviewing India market/economy news for a stock market assistant.

Articles ({min(len(raw_results), 15)} total):
{articles_text}

For each article assign:
- severity: HIGH (PM/RBI Governor/Finance Minister statement, major market event, systemic policy),
            MEDIUM (sector or company news, minor policy),
            LOW (routine/minor)
- impact_tags: 1-5 tags chosen ONLY from this exact list:
  {VALID_IMPACT_TAGS}
- summary: 12 words max

Also judge overall coverage:
- satisfied: true if ≥1 HIGH article exists AND ≥1 article published within 48h of today
- missing_topics: if not satisfied, give 1-2 specific search terms (e.g. "RBI rate decision", "Nifty circuit breaker")

Respond ONLY with JSON inside <json> tags:
<json>
{{
  "satisfied": true,
  "missing_topics": [],
  "tagged_entries": [
    {{"index": 1, "severity": "HIGH", "impact_tags": ["gold", "policy"], "summary": "Modi discouraged gold investment for one year."}}
  ]
}}
</json>"""

        try:
            from services.clients.llm_client import get_llm_client
            from backend.shared.config import settings as _s

            client = get_llm_client()
            resp = client.chat.completions.create(
                model=_s.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise financial news quality reviewer. "
                            "Output only valid JSON inside <json> tags. No other text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=600,
            )

            raw_text = resp.choices[0].message.content or ""
            # Strip <think> blocks (Qwen3)
            raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

            m = re.search(r"<json>(.*?)</json>", raw_text, re.DOTALL)
            review_data = json.loads(m.group(1).strip() if m else raw_text)

        except Exception as exc:
            logger.warning(
                "[MacroFetcher] ReviewAgent LLM failed: %s — "
                "marking unsatisfied so caller may retry with refined queries",
                exc, exc_info=True,
            )
            # Fallback: accept all results without tags (never discard)
            return {
                "satisfied": False,
                "missing_topics": ["India market news"],
                "tagged_entries": [
                    {
                        **r,
                        "severity":    "LOW",
                        "impact_tags": [],
                        "summary":     (r.get("title", "") or "")[:80],
                    }
                    for r in raw_results
                ],
            }

        # Merge LLM tags back into raw results by index
        tag_map: dict[int, dict] = {
            item["index"]: item
            for item in review_data.get("tagged_entries", [])
            if isinstance(item.get("index"), int)
        }

        merged: list[dict] = []
        for i, r in enumerate(raw_results[:15], 1):
            td = tag_map.get(i, {})
            merged.append({
                **r,
                "severity":    td.get("severity", "LOW"),
                "impact_tags": td.get("impact_tags", []),
                "summary":     td.get("summary", (r.get("title", "") or "")[:80]),
            })

        return {
            "satisfied":      bool(review_data.get("satisfied", True)),
            "missing_topics": review_data.get("missing_topics", []),
            "tagged_entries": merged,
        }
