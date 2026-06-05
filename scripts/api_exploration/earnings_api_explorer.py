"""
scripts/api_exploration/earnings_api_explorer.py
=================================================
Earnings Call Transcript Explorer — Two sources tested:
  1. EarningsAPI.com (earningscalls.dev) — free tier, programmatic access
  2. AlphaStreet (alphastreet.com) — enterprise API, real India coverage

Signal value for StockAgent:
  Management guidance in earnings call Q&A is a leading indicator.
  CFO tone on margins, capex guidance, demand outlook → feed into
  fundamentals agent and RAG layer for guidance surprise detection.

Setup:
  EarningsAPI: register at https://earningscalls.dev → get free API key
  AlphaStreet: contact sales at alphastreet.com/Datafeed (enterprise only)
"""

from __future__ import annotations

import json
import re
from datetime import date

import requests

# ─── CREDENTIALS ──────────────────────────────────────────────────────────────
EARNINGS_API_KEY   = "YOUR_EARNINGSAPI_KEY"     # https://earningscalls.dev
ALPHASTREET_KEY    = "YOUR_ALPHASTREET_KEY"      # enterprise; contact sales
# ──────────────────────────────────────────────────────────────────────────────

EARNINGS_BASE    = "https://earningscalls.dev/api/v1"
ALPHASTREET_BASE = "https://api.alphastreet.com/v2"

# Indian tickers — try both NSE symbols and exchange-qualified forms
INDIA_TICKERS = {
    "TATAMOTORS": "TATAMOTORS.NS",
    "HDFCBANK":   "HDFCBANK.NS",
    "INFY":       "INFY.NS",
    "TCS":        "TCS.NS",
    "RELIANCE":   "RELIANCE.NS",
    "ADANIGREEN": "ADANIGREEN.NS",
}

TIMEOUT = 15


# ─── EARNINGSAPI.COM ──────────────────────────────────────────────────────────

def earningsapi_search_transcripts(ticker: str, limit: int = 5) -> list[dict]:
    """
    Search for earnings call transcripts by ticker.
    Returns list of available calls with metadata.
    """
    resp = requests.get(
        f"{EARNINGS_BASE}/transcripts",
        headers={"Authorization": f"Bearer {EARNINGS_API_KEY}"},
        params={"ticker": ticker, "limit": limit},
        timeout=TIMEOUT,
    )
    if resp.status_code == 401:
        print(f"[earningsapi] 401 Unauthorized — check EARNINGS_API_KEY")
        return []
    if resp.status_code == 404:
        print(f"[earningsapi] No transcripts found for {ticker}")
        return []
    resp.raise_for_status()
    return resp.json().get("data", resp.json() if isinstance(resp.json(), list) else [])


def earningsapi_get_transcript(transcript_id: str) -> dict:
    """Fetch full transcript text by ID."""
    resp = requests.get(
        f"{EARNINGS_BASE}/transcripts/{transcript_id}",
        headers={"Authorization": f"Bearer {EARNINGS_API_KEY}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def earningsapi_demo(tickers: list[str]) -> None:
    """Check India coverage and print available transcripts."""
    print("\n=== EarningsAPI.com — India Coverage Check ===")
    for nse_ticker, yf_ticker in [(t, INDIA_TICKERS.get(t, t)) for t in tickers]:
        # Try both NSE ticker and Yahoo Finance format
        for try_ticker in [nse_ticker, yf_ticker]:
            calls = earningsapi_search_transcripts(try_ticker, limit=3)
            if calls:
                print(f"\n  ✓ {nse_ticker} ({try_ticker}) — {len(calls)} calls found:")
                for call in calls:
                    print(
                        f"    [{call.get('id', 'N/A')}] "
                        f"Q{call.get('quarter', '?')} {call.get('year', '?')} | "
                        f"Date: {call.get('date', 'N/A')} | "
                        f"Title: {call.get('title', 'N/A')[:60]}"
                    )
                break
        else:
            print(f"  ✗ {nse_ticker} — no transcripts found on EarningsAPI")


def extract_guidance_snippets(transcript_text: str, max_snippets: int = 5) -> list[str]:
    """
    Extract forward-looking guidance statements from transcript text.
    Looks for keywords: guidance, expect, target, outlook, FY, margin.
    """
    guidance_keywords = [
        r"guid\w+", r"expect\w+", r"target\w+", r"outlook", r"FY\d{2}",
        r"margin\w*", r"revenue\w*", r"growth\w*", r"capex", r"confident",
        r"next quarter", r"going forward",
    ]
    pattern = "|".join(guidance_keywords)
    sentences = re.split(r"(?<=[.!?])\s+", transcript_text)
    hits = [s.strip() for s in sentences if re.search(pattern, s, re.I)]
    return hits[:max_snippets]


# ─── ALPHASTREET (ENTERPRISE) ─────────────────────────────────────────────────

def alphastreet_search_transcripts(company_name: str, limit: int = 5) -> list[dict]:
    """
    Search AlphaStreet India transcripts by company name.
    Requires enterprise API key — contact alphastreet.com/Datafeed.
    """
    resp = requests.get(
        f"{ALPHASTREET_BASE}/events",
        headers={"X-Api-Key": ALPHASTREET_KEY, "Accept": "application/json"},
        params={"search": company_name, "country": "IN", "limit": limit},
        timeout=TIMEOUT,
    )
    if resp.status_code in (401, 403):
        print("[alphastreet] Enterprise API key required")
        return []
    resp.raise_for_status()
    return resp.json().get("events", [])


def alphastreet_demo(company_names: list[str]) -> None:
    """Check AlphaStreet India coverage."""
    print("\n=== AlphaStreet — India Coverage Check ===")
    for name in company_names:
        calls = alphastreet_search_transcripts(name, limit=3)
        if calls:
            print(f"\n  ✓ {name} — {len(calls)} events:")
            for ev in calls:
                print(
                    f"    [{ev.get('event_id')}] "
                    f"{ev.get('event_date', 'N/A')} | "
                    f"{ev.get('title', 'N/A')[:60]}"
                )
        else:
            print(f"  ✗ {name} — no results (or enterprise key not set)")


# ─── GUIDANCE EXTRACTION DEMO ─────────────────────────────────────────────────

def demo_guidance_extraction(sample_text: str | None = None) -> None:
    """
    Show how to extract guidance snippets from transcript text.
    In production, replace sample_text with actual transcript from API.
    """
    if sample_text is None:
        # Sample earnings call snippet (placeholder — replace with real API response)
        sample_text = """
        Good morning. Thank you for joining our Q3 FY2026 earnings call.
        We expect revenue growth of 12-15% for the full year FY2026.
        Our EBITDA margin target remains at 18-20% despite input cost pressures.
        The EV transition capex will be approximately ₹5,000 crores over next 3 years.
        Going forward, we are confident in our market share gains in the premium segment.
        Domestic volumes are expected to grow 8-10% in Q4 FY2026.
        We maintain our guidance for double-digit top-line growth.
        Export markets outlook remains cautious due to USD/INR movement.
        """

    snippets = extract_guidance_snippets(sample_text)
    print("\n=== Guidance Extraction Demo ===")
    print("  Input: sample earnings call text")
    print("  Extracted forward-looking statements:")
    for i, s in enumerate(snippets, 1):
        print(f"  {i}. {s[:120]}")
    print("\n  [production] Replace sample_text with transcript from earningsapi_get_transcript()")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Earnings Transcript API Explorer ===\n")

    TICKERS_TO_TEST = ["TATAMOTORS", "HDFCBANK", "TCS", "INFY"]

    if EARNINGS_API_KEY == "YOUR_EARNINGSAPI_KEY":
        print("[earningsapi] No key set — register free at https://earningscalls.dev")
        print("  After signup, paste your API key into EARNINGS_API_KEY at top of file\n")
    else:
        earningsapi_demo(TICKERS_TO_TEST)

    if ALPHASTREET_KEY == "YOUR_ALPHASTREET_KEY":
        print("[alphastreet] Enterprise API — contact https://alphastreet.com/Datafeed")
        print("  Free web access to Indian transcripts: https://alphastreet.com/india/\n")
    else:
        alphastreet_demo(["Tata Motors", "HDFC Bank", "Infosys", "TCS"])

    # Guidance extraction always runs (no API needed)
    demo_guidance_extraction()

    print("\n[tip] ArthaLens (https://arthalens.ai) provides free AI-summarized")
    print("      Indian earnings calls — no API, but useful for manual research.")
