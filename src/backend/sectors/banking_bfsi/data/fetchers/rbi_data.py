"""
data/fetchers/rbi_data.py — Banking BFSI
==========================================
Fetches RBI MPC outcomes and system-level credit/deposit growth.

Sources (free tier):
  - Tavily → RBI MPC press release page (~1,000 tokens)
  - Serper → RBI weekly credit data snippet (~275 tokens)

Status: stub — implement in Phase 7.
        The ContextBuilder falls back to Serper news snippets until then.
"""
from __future__ import annotations


def get_mpc_outcome(serper_key: str) -> str:
    """
    Fetch the latest RBI Monetary Policy Committee outcome.

    Returns a text snippet with:
    - repo rate decision (cut / hold / hike)
    - MPC stance (withdrawal / neutral / accommodative)
    - forward guidance language
    - vote count (e.g. 4-2 hold)

    Implementation plan (Phase 7):
    1. Use Tavily to fetch https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx
       filtered to MPC press releases — returns full page text.
    2. Extract repo rate, stance, vote tally from the text.
    3. Cache result for 30 days (MPC meets every ~45 days).
    """
    raise NotImplementedError(
        "rbi_data.get_mpc_outcome not implemented — Phase 7. "
        "ContextBuilder uses Serper news fallback."
    )


def get_system_credit_growth(serper_key: str) -> dict:
    """
    Fetch RBI weekly statistical supplement for system credit and deposit growth.

    Returns dict with keys:
    - credit_growth_yoy_pct (float)
    - deposit_growth_yoy_pct (float)
    - cd_ratio (float)  — credit-to-deposit ratio
    - as_of_date (str)

    Implementation plan (Phase 7):
    1. Tavily → https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx
       (RBI Weekly Statistical Supplement, Table 1 — Money Stock Measures)
    2. Parse credit growth % YoY and deposit growth % YoY.
    3. Cache for 7 days (published weekly on Fridays).
    """
    raise NotImplementedError(
        "rbi_data.get_system_credit_growth not implemented — Phase 7. "
        "ContextBuilder uses Serper news fallback."
    )


def get_rbi_policy_rate() -> float:
    """
    Return the current RBI repo rate.

    Implementation plan (Phase 7):
    Use Tavily to fetch the RBI policy rates page and parse the current repo rate.
    For now, returns the last known value (hardcoded until live fetch is implemented).
    """
    return 6.25  # last known repo rate — update after each MPC meeting
