"""
data/fetchers/deal_wins.py — IT Sector
=========================================
Fetches TCV deal win announcements and pipeline commentary for Indian IT companies.

Sources (free tier):
  - Serper → company press release snippets for deal wins (~275 tokens per query)
  - Tavily → investor presentation page for pipeline commentary (~1,000 tokens)

Status: stub — implement in Phase 7.
        ContextBuilder uses Serper news search as fallback.
"""
from __future__ import annotations


def get_deal_wins(ticker: str, company_name: str, serper_key: str) -> str:
    """
    Fetch recent TCV deal win announcements from press releases and news.

    Returns a formatted text block with:
    - Recent large deal wins (TCV in $M, client vertical, duration)
    - Pipeline commentary from last investor call
    - Win rate vs competitor mentions (Accenture, Cognizant)

    Implementation plan (Phase 7):
    1. Serper search: "{company_name} TCV large deal win Q{N} {year}"
       → returns title + 2-line snippet (~275 tokens per query)
    2. Serper search: "{company_name} deal pipeline total contract value {year}"
    3. Tavily: fetch investor presentation page if URL known
       → returns full page text (~1,000 tokens)
    4. Parse TCV values, vertical names, duration from text.
    """
    raise NotImplementedError(
        "deal_wins.get_deal_wins not implemented — Phase 7. "
        "ContextBuilder uses Serper news fallback."
    )


def get_tcv_trend(ticker: str, quarters: int = 4) -> list[dict]:
    """
    Compile TCV data over last N quarters from news snippets.

    Returns list of dicts:
    [{"quarter": "Q3 FY2025", "tcv_usd_bn": 1.2, "large_deals": 3}, ...]

    Implementation plan (Phase 7):
    1. Serper search per quarter (up to 4 queries).
    2. Parse TCV mentions from earnings result press releases.
    3. Cache result for 30 days per ticker.
    """
    raise NotImplementedError(
        "deal_wins.get_tcv_trend not implemented — Phase 7."
    )
