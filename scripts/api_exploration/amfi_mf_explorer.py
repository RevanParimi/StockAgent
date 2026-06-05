"""
scripts/api_exploration/amfi_mf_explorer.py
============================================
AMFI Mutual Fund Explorer — Free, no auth, no rate limits.
Tests: NAV history for any MF scheme, institutional herding signal detection.

Data source: mfapi.in (third-party wrapper around AMFI official data)
No API key needed. Run directly.

Signal value for StockAgent:
  Track which MF schemes are accumulating a stock across weeks →
  detect institutional conviction building before price moves.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from collections import defaultdict

import requests

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError for box-drawing chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://api.mfapi.in/mf"
TIMEOUT = 10


# ─── SCHEME DISCOVERY ─────────────────────────────────────────────────────────

def list_schemes(query: str = "") -> list[dict]:
    """
    List all MF schemes (14,000+). Optionally filter by name.
    Returns: [{schemeCode, schemeName}, ...]
    """
    resp = requests.get(BASE, timeout=TIMEOUT)
    resp.raise_for_status()
    schemes = resp.json()
    if query:
        q = query.lower()
        schemes = [s for s in schemes if q in s.get("schemeName", "").lower()]
    return schemes


def get_scheme_nav_history(scheme_code: int, days: int = 90) -> list[dict]:
    """
    Fetch full NAV history for a scheme code.
    Returns: [{date: "DD-MM-YYYY", nav: "123.456"}, ...]
    """
    resp = requests.get(f"{BASE}/{scheme_code}", timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    nav_data = data.get("data", [])
    # data is newest-first; slice to requested window
    cutoff = date.today() - timedelta(days=days)
    result = []
    for entry in nav_data:
        try:
            d, m, y = entry["date"].split("-")
            entry_date = date(int(y), int(m), int(d))
            if entry_date >= cutoff:
                result.append({"date": entry_date.isoformat(), "nav": float(entry["nav"])})
        except (ValueError, KeyError):
            continue
    return sorted(result, key=lambda x: x["date"])


def get_scheme_info(scheme_code: int) -> dict:
    """Fetch scheme metadata: fund house, category, etc."""
    resp = requests.get(f"{BASE}/{scheme_code}", timeout=TIMEOUT)
    resp.raise_for_status()
    meta = resp.json().get("meta", {})
    return meta


# ─── HERDING SIGNAL ───────────────────────────────────────────────────────────

def find_schemes_holding_stock(
    ticker: str,
    categories: list[str] | None = None,
    max_schemes: int = 20,
) -> list[dict]:
    """
    Find MF schemes that contain a stock ticker in their name or description.
    This is a proxy — for actual holdings you need mfdata.in or AMFI portfolio data.

    For actual stock-level holdings, use:
      https://mfdata.in/api/v1/portfolio/{scheme_code}/holdings
    """
    all_schemes = list_schemes(ticker)
    if categories:
        cats = [c.lower() for c in categories]
        all_schemes = [
            s for s in all_schemes
            if any(c in s.get("schemeName", "").lower() for c in cats)
        ]
    return all_schemes[:max_schemes]


def nav_momentum(scheme_code: int, days: int = 30) -> dict:
    """
    Simple NAV momentum: % change over last N days.
    Used to detect funds with unusual inflow/outflow patterns.
    """
    history = get_scheme_nav_history(scheme_code, days=days + 10)
    if len(history) < 2:
        return {"error": "insufficient data"}
    start_nav = history[0]["nav"]
    end_nav   = history[-1]["nav"]
    change_pct = (end_nav - start_nav) / start_nav * 100
    return {
        "scheme_code": scheme_code,
        "from":        history[0]["date"],
        "to":          history[-1]["date"],
        "nav_start":   round(start_nav, 4),
        "nav_end":     round(end_nav, 4),
        "change_pct":  round(change_pct, 2),
        "data_points": len(history),
    }


# ─── DEMO RUNS ────────────────────────────────────────────────────────────────

def demo_large_cap_funds() -> None:
    """Show NAV history for a few well-known large-cap equity funds."""
    SAMPLE_SCHEMES = {
        "Mirae Asset Large Cap Fund - Direct Plan - Growth":   119598,
        "Axis Bluechip Fund - Direct Plan - Growth":           120503,
        "SBI Bluechip Fund - Direct Plan - Growth":            125497,
        "HDFC Top 100 Fund - Direct Plan - Growth":            119533,
    }

    print("\n=== NAV Momentum — Large Cap Funds (30d) ===")
    for name, code in SAMPLE_SCHEMES.items():
        m = nav_momentum(code, days=30)
        if "error" not in m:
            print(f"  {name[:50]:50s} | {m['change_pct']:+6.2f}% | {m['from']} -> {m['to']}")
        else:
            print(f"  {name[:50]:50s} | {m['error']}")


def demo_search_tata_funds() -> None:
    """Find schemes with 'TATA' in name — proxy for funds heavy in Tata group."""
    schemes = list_schemes("tata motors")
    print(f"\n=== Schemes matching 'tata motors' ({len(schemes)} found) ===")
    for s in schemes[:10]:
        print(f"  [{s['schemeCode']}] {s['schemeName']}")


def demo_nav_history(scheme_code: int = 119598) -> None:
    """Show recent NAV history for a specific scheme."""
    info    = get_scheme_info(scheme_code)
    history = get_scheme_nav_history(scheme_code, days=30)
    print(f"\n=== NAV History: [{scheme_code}] {info.get('scheme_name', '')} ===")
    print(f"  Fund House: {info.get('fund_house', 'N/A')} | Category: {info.get('scheme_category', 'N/A')}")
    for entry in history[-10:]:
        print(f"  {entry['date']} | NAV = {entry['nav']:>10.4f}")


def demo_cross_fund_signal(
    tickers: list[str],
    sample_scheme_codes: list[int],
) -> None:
    """
    Check NAV momentum across multiple funds for the same time window.
    High positive momentum across many funds = sector inflow; could signal
    accumulation in underlying stocks.
    """
    print(f"\n=== Cross-Fund NAV Momentum Signal (30d) ===")
    results = []
    for code in sample_scheme_codes:
        m = nav_momentum(code, days=30)
        if "error" not in m:
            results.append(m)

    results.sort(key=lambda x: x["change_pct"], reverse=True)
    for r in results:
        bar = "#" * int(abs(r["change_pct"]) / 0.5)
        sign = "+" if r["change_pct"] >= 0 else ""
        print(f"  [{r['scheme_code']}] {sign}{r['change_pct']:5.2f}% {bar}")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== AMFI Mutual Fund Explorer (no auth required) ===\n")

    # 1. Search for schemes
    demo_search_tata_funds()

    # 2. NAV history for a specific scheme
    demo_nav_history(119598)

    # 3. Large-cap fund momentum (sector signal)
    demo_large_cap_funds()

    # 4. Cross-fund momentum for auto-sector funds
    AUTO_SECTOR_CODES = [
        148620,   # Mirae Asset Nifty Auto ETF
        149075,   # ICICI Prudential Nifty Auto ETF
        148553,   # Nippon India Nifty Auto ETF
    ]
    demo_cross_fund_signal(["TATAMOTORS", "M&M", "BAJAJ-AUTO"], AUTO_SECTOR_CODES)

    print("\n[tip] To get actual holdings per scheme, use mfdata.in:")
    print("  GET https://mfdata.in/api/v1/portfolio/{scheme_code}/holdings")
