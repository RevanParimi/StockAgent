"""
tests/test_rss_feed.py
======================
3-Agent test: RSS feeds as macro news replacement for MacroNewsFetcher.

Agent 1 — Researcher : polls all 5 India RSS feeds, prints raw results
Agent 2 — Designer   : evaluates coverage per impact category our system needs
Agent 3 — Reviewer   : uses LLM to judge if RSS output is sufficient to replace
                        Serper+NewsAPI in MacroNewsFetcher; PASS / FAIL with reasons

Run:
    python -m tests.test_rss_feed

No API keys needed — all RSS feeds are public.
"""

from __future__ import annotations

import json
import sys
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# RSS sources — all India-native financial/market feeds
# ---------------------------------------------------------------------------
RSS_SOURCES = {
    "Investing.com India":  "https://in.investing.com/rss/news.rss",
    "ET Markets":           "https://economictimes.indiatimes.com/markets/rss.cms",
    "ET Top Stories":       "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "LiveMint":             "https://www.livemint.com/rss/markets",
    "BusinessLine":         "https://www.thehindubusinessline.com/markets/?service=rss",
    "Moneycontrol":         "https://www.moneycontrol.com/rss/results.xml",
    "BusinessStandard":     "https://www.business-standard.com/rss/latest.rss",
}

# Impact tags our MacroNewsFetcher ReviewAgent looks for
REQUIRED_COVERAGE = [
    "rbi_policy", "nifty_sensex", "economy_budget", "fii_dii", "sector_news"
]

CUTOFF_HOURS = 48   # articles older than this are considered stale


# ---------------------------------------------------------------------------
# Agent 1 — Researcher
# ---------------------------------------------------------------------------

def agent_researcher() -> list[dict]:
    """Poll all RSS feeds and return unified article list."""
    try:
        import feedparser
    except ImportError:
        print("[Researcher] feedparser not installed. Run: pip install feedparser")
        sys.exit(1)

    all_articles: list[dict] = []
    cutoff = datetime.now() - timedelta(hours=CUTOFF_HOURS)

    print("\n" + "=" * 60)
    print("AGENT 1 — RESEARCHER: Polling India RSS Feeds")
    print("=" * 60)

    for source_name, url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(url)
            entries = feed.entries
            fresh = 0
            stale = 0

            for entry in entries:
                title   = getattr(entry, "title",   "").strip()
                summary = getattr(entry, "summary", "")[:200].strip()
                link    = getattr(entry, "link",    "")

                # Parse published date
                pub_date = None
                for attr in ("published_parsed", "updated_parsed"):
                    val = getattr(entry, attr, None)
                    if val:
                        try:
                            pub_date = datetime(*val[:6])
                        except Exception:
                            pass
                        break

                pub_str = pub_date.strftime("%Y-%m-%d %H:%M") if pub_date else "unknown"
                age_ok  = (pub_date is None) or (pub_date >= cutoff)

                if not title:
                    continue

                article = {
                    "source":         source_name,
                    "title":          title,
                    "snippet":        summary,
                    "url":            link,
                    "published_date": pub_date.strftime("%Y-%m-%d") if pub_date else date.today().isoformat(),
                    "published_at":   pub_str,
                    "is_fresh":       age_ok,
                }
                all_articles.append(article)

                if age_ok:
                    fresh += 1
                else:
                    stale += 1

            status = f"{fresh} fresh / {stale} stale" if entries else "EMPTY or unreachable"
            print(f"  [{source_name}] {status}")

        except Exception as exc:
            print(f"  [{source_name}] FAILED: {exc}")

    fresh_total = sum(1 for a in all_articles if a["is_fresh"])
    print(f"\n  Total: {len(all_articles)} articles ({fresh_total} fresh within {CUTOFF_HOURS}h)")

    return all_articles


# ---------------------------------------------------------------------------
# Agent 2 — Designer
# ---------------------------------------------------------------------------

def agent_designer(articles: list[dict]) -> dict:
    """
    Evaluate coverage gaps without LLM — keyword heuristics per category.
    Returns coverage_report dict for Reviewer.
    """
    print("\n" + "=" * 60)
    print("AGENT 2 — DESIGNER: Evaluating Coverage")
    print("=" * 60)

    keywords = {
        "rbi_policy":      ["rbi", "repo rate", "monetary policy", "mpc", "rbi governor", "interest rate"],
        "nifty_sensex":    ["nifty", "sensex", "bse", "nse", "index", "market", "rally", "fall", "points"],
        "economy_budget":  ["gdp", "inflation", "budget", "fiscal", "government", "ministry", "finance"],
        "fii_dii":         ["fii", "fpi", "dii", "foreign investor", "institutional", "outflow", "inflow"],
        "sector_news":     ["bank", "auto", "it", "pharma", "energy", "renewable", "sector", "earnings"],
    }

    fresh_articles = [a for a in articles if a["is_fresh"]]
    coverage: dict[str, list[str]] = {cat: [] for cat in REQUIRED_COVERAGE}

    for article in fresh_articles:
        text = (article["title"] + " " + article["snippet"]).lower()
        for cat, kws in keywords.items():
            if any(kw in text for kw in kws):
                coverage[cat].append(article["title"][:80])

    print(f"\n  Fresh articles analyzed: {len(fresh_articles)}")
    print(f"\n  Coverage by category:")
    all_covered = True
    for cat, hits in coverage.items():
        status = f"[OK] {len(hits)} articles" if hits else "[MISSING]"
        if not hits:
            all_covered = False
        print(f"    {cat:20s} : {status}")
        if hits:
            for h in hits[:2]:
                print(f"        >> {h}")

    # Source diversity
    sources_represented = {a["source"] for a in fresh_articles}
    print(f"\n  Sources with fresh data: {sources_represented}")

    # Freshness check
    very_fresh = [a for a in fresh_articles
                  if a["published_date"] == date.today().isoformat()]
    print(f"  Articles from today:     {len(very_fresh)}")

    return {
        "total_articles":     len(articles),
        "fresh_articles":     len(fresh_articles),
        "today_articles":     len(very_fresh),
        "coverage":           {k: len(v) for k, v in coverage.items()},
        "all_covered":        all_covered,
        "sources_active":     list(sources_represented),
        "sample_titles":      [a["title"] for a in fresh_articles[:5]],
    }


# ---------------------------------------------------------------------------
# Agent 3 — Reviewer (LLM)
# ---------------------------------------------------------------------------

def agent_reviewer(articles: list[dict], coverage_report: dict) -> None:
    """
    LLM judges if RSS output can replace Serper+NewsAPI in MacroNewsFetcher.
    PASS if: ≥1 HIGH severity article exists AND ≥3 categories covered AND ≥1 today article.
    """
    print("\n" + "=" * 60)
    print("AGENT 3 — REVIEWER: LLM Quality Judgment")
    print("=" * 60)

    try:
        from dotenv import load_dotenv
        load_dotenv()
        import os
        from openai import OpenAI

        api_key  = os.getenv("OPENROUTER_API_KEY", "")
        model    = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")
        base_url = "https://openrouter.ai/api/v1"

        if not api_key:
            print("  [Reviewer] No OPENROUTER_API_KEY — running rule-based fallback")
            _rule_based_review(coverage_report)
            return

        client = OpenAI(api_key=api_key, base_url=base_url)

        fresh_sample = [a for a in articles if a["is_fresh"]][:15]
        articles_text = "\n".join(
            f"{i}. [{a['published_date']}] [{a['source']}] {a['title']}"
            for i, a in enumerate(fresh_sample, 1)
        )

        prompt = f"""Today is {date.today().isoformat()}. You are reviewing India financial RSS feed output.

These {len(fresh_sample)} articles were fetched from India RSS feeds in the last 48 hours:
{articles_text}

Coverage report:
{json.dumps(coverage_report['coverage'], indent=2)}

Our MacroNewsFetcher ReviewAgent needs:
1. At least 1 HIGH-severity article (RBI/MPC/FM statement, major market event, systemic policy)
2. At least 3 of 5 categories covered: rbi_policy, nifty_sensex, economy_budget, fii_dii, sector_news
3. At least 1 article from TODAY
4. Source diversity (not all from one portal)

Evaluate and respond ONLY with this JSON:
{{
  "verdict": "PASS" or "FAIL",
  "has_high_severity": true/false,
  "categories_covered": <integer 0-5>,
  "has_today_article": true/false,
  "source_diversity": "good" or "poor",
  "can_replace_serper": true/false,
  "gaps": ["<specific gap 1>", "<specific gap 2>"],
  "recommendation": "<one sentence>"
}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise financial news quality reviewer. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=400,
        )

        import re
        raw = resp.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        result = json.loads(raw)

        print(f"\n  Verdict:            {result.get('verdict', '?')}")
        print(f"  Has HIGH severity:  {result.get('has_high_severity', '?')}")
        print(f"  Categories covered: {result.get('categories_covered', '?')}/5")
        print(f"  Has today article:  {result.get('has_today_article', '?')}")
        print(f"  Source diversity:   {result.get('source_diversity', '?')}")
        print(f"  Can replace Serper: {result.get('can_replace_serper', '?')}")
        if result.get("gaps"):
            print(f"  Gaps:               {result['gaps']}")
        print(f"  Recommendation:     {result.get('recommendation', '')}")

    except Exception as exc:
        print(f"  [Reviewer] LLM failed: {exc}")
        print("  Running rule-based fallback...")
        _rule_based_review(coverage_report)


def _rule_based_review(report: dict) -> None:
    covered = sum(1 for v in report["coverage"].values() if v > 0)
    has_today = report["today_articles"] > 0
    has_fresh  = report["fresh_articles"] > 0
    verdict = "PASS" if (covered >= 3 and has_fresh) else "FAIL"
    print(f"\n  Rule-based verdict:  {verdict}")
    print(f"  Categories covered:  {covered}/5")
    print(f"  Has today article:   {has_today}")
    print(f"  Fresh articles:      {report['fresh_articles']}")
    if covered < 3:
        print("  FAIL reason: fewer than 3 categories covered")
    if not has_fresh:
        print("  FAIL reason: no fresh articles within 48h")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nSTockAgent — RSS Feed Test (3-Agent Loop)")
    print("Tests whether RSS feeds can replace Serper+NewsAPI for macro news\n")

    articles        = agent_researcher()
    coverage_report = agent_designer(articles)
    agent_reviewer(articles, coverage_report)

    print("\n" + "=" * 60)
    print("Test complete.")
    print("=" * 60)
