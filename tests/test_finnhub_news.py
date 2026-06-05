"""
tests/test_finnhub_news.py
==========================
3-Agent test: Finnhub /company-news vs current Serper per-ticker news.

Agent 1 — Researcher : fetches Finnhub /company-news for 3 NSE tickers
                       (tries both symbol formats: NSE:TICKER and TICKER.NS)
                       Also fetches current Serper output for same tickers as baseline.
Agent 2 — Designer   : evaluates article volume, freshness, coverage per agent type
                       (sentiment, fundamentals, risk_macro)
Agent 3 — Reviewer   : LLM compares Finnhub vs Serper side-by-side per agent type.
                       PASS if Finnhub is >= Serper quality. FAIL with specific gaps.

Run:
    python -m tests.test_finnhub_news

Requires: FINNHUB_API_KEY and OPENROUTER_API_KEY in .env
          SERPER_API_KEY in .env (for baseline comparison)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

import requests

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
SERPER_API_KEY  = os.getenv("SERPER_API_KEY", "")
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL       = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

# NSE tickers to test — one from each major sector we cover
TEST_TICKERS = [
    ("TATAMOTORS", "automobile"),
    ("HDFCBANK",   "banking_bfsi"),
    ("TCS",        "it_sector"),
]

# Days lookback for each use case
DAYS_AGENT_ANALYSIS = 7   # user-triggered agent analysis
DAYS_RL_REVIEW      = 2   # RL daily review (yesterday + today)

# Agent types and what they need from news
AGENT_NEWS_NEEDS = {
    "sentiment":    ["brand", "consumer", "management", "CEO", "guidance", "employee", "controversy"],
    "fundamentals": ["revenue", "profit", "earnings", "EBITDA", "margin", "results", "quarter", "annual"],
    "risk_macro":   ["regulatory", "RBI", "SEBI", "penalty", "risk", "debt", "lawsuit", "probe"],
}

TIMEOUT = 10


# ---------------------------------------------------------------------------
# Agent 1 — Researcher
# ---------------------------------------------------------------------------

def _finnhub_fetch(ticker: str, days: int) -> tuple[list[dict], str, dict]:
    """
    Try both NSE symbol formats. Returns (articles, working_format, diagnostics).
    Format tried: NSE:TICKER first, then TICKER.NS, then plain TICKER.
    Prints raw API response for diagnosis when articles=0.
    """
    from_date = (date.today() - timedelta(days=days)).isoformat()
    to_date   = date.today().isoformat()
    url       = "https://finnhub.io/api/v1/company-news"
    diagnostics: dict[str, object] = {}

    for fmt in [f"NSE:{ticker}", f"{ticker}.NS", ticker]:
        try:
            resp = requests.get(
                url,
                params={
                    "symbol": fmt,
                    "from":   from_date,
                    "to":     to_date,
                    "token":  FINNHUB_API_KEY,
                },
                timeout=TIMEOUT,
            )
            status_code = resp.status_code
            diagnostics[fmt] = {"http_status": status_code}
            resp.raise_for_status()
            data = resp.json()
            diagnostics[fmt]["response_type"] = type(data).__name__
            if isinstance(data, dict):
                # Error response from Finnhub e.g. {"error": "You don't have access..."}
                diagnostics[fmt]["error"] = data.get("error", str(data))
            elif isinstance(data, list):
                diagnostics[fmt]["count"] = len(data)
                if len(data) > 0:
                    articles = [
                        {
                            "title":          a.get("headline", ""),
                            "snippet":        a.get("summary", "")[:200],
                            "url":            a.get("url", ""),
                            "source":         a.get("source", ""),
                            "published_date": date.fromtimestamp(a["datetime"]).isoformat() if a.get("datetime") else "unknown",
                            "datetime_unix":  a.get("datetime", 0),
                        }
                        for a in data
                        if a.get("headline")
                    ]
                    return articles, fmt, diagnostics
        except requests.HTTPError as exc:
            diagnostics[fmt] = {"http_status": exc.response.status_code if exc.response else "?", "error": str(exc)}
        except Exception as exc:
            diagnostics[fmt] = {"error": str(exc)}

    return [], "none_worked", diagnostics


def _yfinance_fetch(ticker: str) -> list[dict]:
    """Fetch news from yfinance .news attribute — already used in project."""
    try:
        import yfinance as yf
        t = yf.Ticker(f"{ticker}.NS")
        news = t.news or []
        return [
            {
                "title":          n.get("content", {}).get("title", "") or n.get("title", ""),
                "snippet":        (n.get("content", {}).get("summary", "") or n.get("summary", ""))[:200],
                "url":            (n.get("content", {}).get("canonicalUrl", {}).get("url", "")
                                   or n.get("link", "")),
                "source":         (n.get("content", {}).get("provider", {}).get("displayName", "")
                                   or n.get("publisher", "")),
                "published_date": date.fromtimestamp(
                    n.get("content", {}).get("pubDate") or n.get("providerPublishTime", 0) or 0
                ).isoformat() if (n.get("content", {}).get("pubDate") or n.get("providerPublishTime")) else "unknown",
            }
            for n in news[:10]
            if n.get("content", {}).get("title") or n.get("title")
        ]
    except Exception as exc:
        return []


def _serper_fetch(ticker: str, company_hint: str = "") -> list[dict]:
    """Fetch current Serper output for ticker — baseline comparison."""
    if not SERPER_API_KEY:
        return []
    queries = [
        f"{ticker} NSE India stock news",
        f"{ticker} India stock quarterly results revenue",
    ]
    results = []
    for q in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 5, "gl": "in", "hl": "en"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            for item in resp.json().get("news", []):
                results.append({
                    "title":          item.get("title", ""),
                    "snippet":        item.get("snippet", ""),
                    "url":            item.get("link", ""),
                    "source":         item.get("source", ""),
                    "published_date": item.get("date", ""),
                })
        except Exception:
            pass
    return results


def agent_researcher() -> dict[str, dict]:
    """Fetch Finnhub + Serper for each test ticker."""
    print("\n" + "=" * 65)
    print("AGENT 1 — RESEARCHER: Fetching Finnhub vs Serper")
    print("=" * 65)

    if not FINNHUB_API_KEY:
        print("ERROR: FINNHUB_API_KEY not set in .env")
        sys.exit(1)

    results = {}

    for ticker, sector in TEST_TICKERS:
        print(f"\n  [{ticker}] ({sector})")

        # Finnhub — 7-day (agent analysis use case)
        finn_7d, fmt_7d, diag_7d = _finnhub_fetch(ticker, DAYS_AGENT_ANALYSIS)
        print(f"    Finnhub 7d (format={fmt_7d}): {len(finn_7d)} articles")

        # Finnhub — 2-day (RL daily review use case)
        finn_2d, fmt_2d, diag_2d = _finnhub_fetch(ticker, DAYS_RL_REVIEW)
        print(f"    Finnhub 2d (format={fmt_2d}): {len(finn_2d)} articles")

        # Print diagnostics if nothing returned
        if not finn_7d:
            print(f"    Finnhub diagnostics (all formats tried):")
            for fmt, info in diag_7d.items():
                print(f"      {fmt}: {info}")

        # yfinance .news — already in project, free, test if it returns India news
        yf_articles = _yfinance_fetch(ticker)
        print(f"    yfinance .news:               {len(yf_articles)} articles")

        # Serper baseline
        serper = _serper_fetch(ticker)
        print(f"    Serper baseline:              {len(serper)} articles")

        # Print sample titles — encode safely for Windows console
        def safe(s: str) -> str:
            return s.encode("ascii", "replace").decode("ascii")

        if finn_7d:
            print(f"    Finnhub sample titles:")
            for a in finn_7d[:3]:
                print(f"      [{a['published_date']}] [{safe(a['source'])}] {safe(a['title'])[:75]}")
        else:
            print(f"    Finnhub: NO ARTICLES RETURNED for any format")

        if serper:
            print(f"    Serper sample titles:")
            for a in serper[:2]:
                print(f"      [{safe(a['published_date'])}] {safe(a['title'])[:75]}")

        if yf_articles:
            print(f"    yfinance sample titles:")
            for a in yf_articles[:3]:
                print(f"      [{safe(a['published_date'])}] [{safe(a['source'])}] {safe(a['title'])[:70]}")

        results[ticker] = {
            "sector":         sector,
            "finnhub_7d":     finn_7d,
            "finnhub_2d":     finn_2d,
            "finnhub_format": fmt_7d,
            "finnhub_diag":   diag_7d,
            "yfinance":       yf_articles,
            "serper":         serper,
        }

    return results


# ---------------------------------------------------------------------------
# Agent 2 — Designer
# ---------------------------------------------------------------------------

def _score_coverage(articles: list[dict], needs: dict[str, list[str]]) -> dict[str, int]:
    """Count how many articles match each agent type's keyword needs."""
    scores = {}
    for agent_type, keywords in needs.items():
        hits = 0
        for a in articles:
            text = (a.get("title", "") + " " + a.get("snippet", "")).lower()
            if any(kw.lower() in text for kw in keywords):
                hits += 1
        scores[agent_type] = hits
    return scores


def agent_designer(research: dict[str, dict]) -> dict[str, dict]:
    """Evaluate Finnhub vs Serper coverage per ticker per agent type."""
    print("\n" + "=" * 65)
    print("AGENT 2 — DESIGNER: Coverage Evaluation per Agent Type")
    print("=" * 65)

    evaluations = {}

    for ticker, data in research.items():
        finn  = data["finnhub_7d"]
        serp  = data["serper"]
        fmt   = data["finnhub_format"]

        finn_coverage = _score_coverage(finn, AGENT_NEWS_NEEDS)
        serp_coverage = _score_coverage(serp, AGENT_NEWS_NEEDS)

        # Freshness check — today or yesterday
        today     = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        finn_fresh = [a for a in finn if a["published_date"] in (today, yesterday)]
        serp_fresh = [a for a in serp if any(
            age in a["published_date"].lower()
            for age in ["hour", "minute", "today", today, yesterday]
        )]

        print(f"\n  [{ticker}] (format used: {fmt})")
        print(f"    {'Agent type':<16} | Finnhub hits | Serper hits")
        print(f"    {'-'*16}-+-{'-'*12}-+-{'-'*11}")
        for agent_type in AGENT_NEWS_NEEDS:
            fh = finn_coverage[agent_type]
            sh = serp_coverage[agent_type]
            flag = "[OK]" if fh >= sh else ("[~]" if fh > 0 else "[X]")
            print(f"    {agent_type:<16} | {fh:^12} | {sh:^11}  {flag}")
        print(f"    {'articles (total)':<16} | {len(finn):^12} | {len(serp):^11}")
        print(f"    {'fresh (<=1d)':<16} | {len(finn_fresh):^12} | {len(serp_fresh):^11}")

        evaluations[ticker] = {
            "finnhub_coverage": finn_coverage,
            "serper_coverage":  serp_coverage,
            "finnhub_total":    len(finn),
            "serper_total":     len(serp),
            "finnhub_fresh":    len(finn_fresh),
            "serper_fresh":     len(serp_fresh),
            "finnhub_format":   fmt,
        }

    return evaluations


# ---------------------------------------------------------------------------
# Agent 3 — Reviewer (LLM)
# ---------------------------------------------------------------------------

def agent_reviewer(research: dict[str, dict], evaluations: dict[str, dict]) -> None:
    """LLM compares Finnhub vs Serper per ticker and gives a PASS/FAIL verdict."""
    print("\n" + "=" * 65)
    print("AGENT 3 — REVIEWER: LLM Side-by-Side Comparison")
    print("=" * 65)

    if not OPENROUTER_KEY:
        print("  [Reviewer] No OPENROUTER_API_KEY — rule-based fallback")
        _rule_based_review(evaluations)
        return

    from openai import OpenAI
    client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

    for ticker, data in research.items():
        ev = evaluations[ticker]
        finn_sample = "\n".join(
            f"  [{a['published_date']}] [{a['source']}] {a['title']}"
            for a in data["finnhub_7d"][:8]
        ) or "  (no articles returned)"

        serp_sample = "\n".join(
            f"  [{a['published_date']}] {a['title']}"
            for a in data["serper"][:5]
        ) or "  (no articles returned)"

        prompt = f"""Today is {date.today().isoformat()}.
Ticker: {ticker} (NSE India, sector: {data['sector']})
Finnhub symbol format that worked: {ev['finnhub_format']}

FINNHUB articles (last 7 days):
{finn_sample}

SERPER/Google articles (current):
{serp_sample}

Our agents that need company-specific news:
- sentiment:    needs brand, management tone, consumer reactions, controversies
- fundamentals: needs earnings, revenue, results, margin data
- risk_macro:   needs regulatory, RBI/SEBI actions, debt, legal issues

Evaluate both sources and answer ONLY with this JSON:
{{
  "ticker": "{ticker}",
  "finnhub_article_count": {ev['finnhub_total']},
  "finnhub_format_working": "{ev['finnhub_format']}",
  "verdict": "PASS" or "FAIL",
  "sentiment_agent": "better_finnhub" or "better_serper" or "equal" or "both_poor",
  "fundamentals_agent": "better_finnhub" or "better_serper" or "equal" or "both_poor",
  "risk_macro_agent": "better_finnhub" or "better_serper" or "equal" or "both_poor",
  "can_replace_serper": true or false,
  "finnhub_gaps": ["<gap1>", "<gap2>"],
  "recommendation": "<one sentence>",
  "rl_daily_review_suitable": true or false
}}"""

        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "You are a concise financial data quality reviewer. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            raw = resp.choices[0].message.content or ""
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            result = json.loads(raw)

            print(f"\n  [{ticker}]")
            print(f"    Verdict:                  {result.get('verdict', '?')}")
            print(f"    Finnhub format working:   {result.get('finnhub_format_working', '?')}")
            print(f"    Finnhub article count:    {result.get('finnhub_article_count', '?')}")
            print(f"    sentiment agent:          {result.get('sentiment_agent', '?')}")
            print(f"    fundamentals agent:       {result.get('fundamentals_agent', '?')}")
            print(f"    risk_macro agent:         {result.get('risk_macro_agent', '?')}")
            print(f"    Can replace Serper:       {result.get('can_replace_serper', '?')}")
            print(f"    RL daily review suitable: {result.get('rl_daily_review_suitable', '?')}")
            if result.get("finnhub_gaps"):
                print(f"    Gaps:                     {result['finnhub_gaps']}")
            print(f"    Recommendation:           {result.get('recommendation', '')}")

        except Exception as exc:
            print(f"  [{ticker}] LLM review failed: {exc}")
            _rule_based_review_ticker(ticker, ev)


def _rule_based_review(evaluations: dict[str, dict]) -> None:
    for ticker, ev in evaluations.items():
        _rule_based_review_ticker(ticker, ev)


def _rule_based_review_ticker(ticker: str, ev: dict) -> None:
    finn_total = ev["finnhub_total"]
    serp_total = ev["serper_total"]
    fmt        = ev["finnhub_format"]
    verdict    = "PASS" if finn_total >= max(serp_total * 0.6, 3) else "FAIL"
    print(f"\n  [{ticker}] Rule-based: {verdict}")
    print(f"    Finnhub: {finn_total} articles (format: {fmt})")
    print(f"    Serper:  {serp_total} articles")
    if finn_total == 0:
        print(f"    CRITICAL: Finnhub returned 0 articles — NSE format may not be supported")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nStockAgent — Finnhub News Test (3-Agent Loop)")
    print("Tests whether Finnhub /company-news can replace Serper per-ticker news\n")

    research    = agent_researcher()
    evaluations = agent_designer(research)
    agent_reviewer(research, evaluations)

    print("\n" + "=" * 65)
    print("Test complete.")
    print("=" * 65)
