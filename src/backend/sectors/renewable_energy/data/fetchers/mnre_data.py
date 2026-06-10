"""
data/fetchers/mnre_data.py — Renewable Energy
================================================
Fetches MNRE auction results, state-wise MW data, and policy updates.

Sources (free tier):
  - Tavily → MNRE auction results page (~1,000 tokens)
  - Serper → state MW capacity and auction news snippets (~275 tokens each)

Status: stub — implement in Phase 7.
        ContextBuilder uses Tavily + Serper fallback for MNRE context.
"""
from __future__ import annotations


def get_mnre_auction_results(serper_key: str) -> str:
    """
    Fetch latest MNRE auction results (GW awarded, L1 tariff, subscription rate).

    Returns formatted text with:
    - Total GW awarded in last auction
    - L1 tariff (Rs/kWh) for solar and wind
    - Subscription rate (oversubscribed % above base capacity)
    - Developer names that won

    Implementation plan (Phase 7):
    1. Tavily → https://mnre.gov.in/knowledge-center/announcements
       Filter to auction results pages → returns full page text (~1,000 tokens).
    2. Parse GW awarded, tariff, developer names from text.
    3. Cache for 30 days (auctions happen ~monthly).

    Alternative: Serper search "MNRE auction results {month} {year} GW tariff"
    → title + 2-line snippet from Mercom India / PV Magazine (~275 tokens).
    """
    raise NotImplementedError(
        "mnre_data.get_mnre_auction_results not implemented — Phase 7. "
        "ContextBuilder uses Tavily + Serper news fallback."
    )


def get_state_capacity_mw(company_name: str, serper_key: str) -> dict:
    """
    Fetch state-wise commissioned MW for a RE developer.

    Returns dict: {"Rajasthan": 1200, "Gujarat": 800, "Andhra Pradesh": 400, ...}

    Implementation plan (Phase 7):
    1. Serper: "{company_name} state-wise MW capacity solar wind installed {year}"
       → parse capacity table from annual report snippet or press release.
    2. Tavily: fetch company investor presentation page for capacity breakup.
    3. Cache per company, refresh annually (or on new commissioning announcement).
    """
    raise NotImplementedError(
        "mnre_data.get_state_capacity_mw not implemented — Phase 7. "
        "ContextBuilder uses Serper news fallback."
    )


def get_rpo_target(year: int = 2026) -> dict:
    """
    Return the RPO (Renewable Purchase Obligation) target for the given year.

    Returns dict: {"total_rpo_pct": 43.33, "solar_pct": 10.0, "non_solar_pct": 33.33}

    Implementation plan (Phase 7):
    1. Tavily → MoP (Ministry of Power) RPO schedule notification.
    2. Parse target percentages from gazette notification text.
    3. Hardcode current known values until live fetch is implemented.
    """
    return {
        "total_rpo_pct": 43.33,
        "solar_pct": 10.0,
        "non_solar_pct": 33.33,
        "year": year,
        "source": "hardcoded — update from MoP notification in Phase 7",
    }
