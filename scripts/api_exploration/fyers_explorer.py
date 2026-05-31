"""
scripts/api_exploration/fyers_explorer.py
=========================================
Fyers API v3 Explorer — Free tier, no data subscription fee.
Tests: live quotes, historical OHLCV, options chain with IV/PCR.

Setup:
  1. Create app at https://myapi.fyers.in/dashboard
  2. pip install fyers-apiv3
  3. Run once to get auth URL, complete login, paste auth_code below.

Docs: https://myapi.fyers.in/docs/
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import requests

# ─── CREDENTIALS ──────────────────────────────────────────────────────────────
APP_ID       = "YOUR_FYERS_APP_ID"       # e.g. "XXXXXXXX-100"
SECRET_KEY   = "YOUR_FYERS_SECRET_KEY"
REDIRECT_URI = "https://trade.fyers.in/api-login/redirect-uri/index.html"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"       # obtained via get_auth_url() → exchange_code()
# ──────────────────────────────────────────────────────────────────────────────

BASE     = "https://api-t1.fyers.in/api/v3"
DATA_URL = "https://api-t2.fyers.in/data"
HEADERS  = {"Authorization": f"{APP_ID}:{ACCESS_TOKEN}"}


# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    """Step 1 — open this URL in a browser, log in, copy the auth_code from redirect."""
    return (
        f"{BASE}/generate-authcode"
        f"?client_id={APP_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&state=StockAgent"
    )


def exchange_code(auth_code: str) -> str:
    """Step 2 — exchange auth_code for access_token. Paste ACCESS_TOKEN at top."""
    app_hash = hashlib.sha256(f"{APP_ID}:{SECRET_KEY}".encode()).hexdigest()
    resp = requests.post(
        f"{BASE}/validate-authcode",
        json={"grant_type": "authorization_code", "appIdHash": app_hash, "code": auth_code},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[auth] access_token: {data['access_token']}")
    return data["access_token"]


# ─── DATA TESTS ───────────────────────────────────────────────────────────────

def test_profile() -> None:
    resp = requests.get(f"{BASE}/profile", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    p = resp.json().get("data", {})
    print(f"\n[profile] name={p.get('name')} | email={p.get('emailId')} | broker={p.get('brokerName')}")


def test_quotes(symbols: list[str]) -> None:
    """Live quotes for NSE equity symbols."""
    fyers_symbols = ",".join(f"NSE:{s}-EQ" for s in symbols)
    resp = requests.get(
        f"{DATA_URL}/quotes",
        headers=HEADERS,
        params={"symbols": fyers_symbols},
        timeout=10,
    )
    resp.raise_for_status()
    print("\n=== Live Quotes ===")
    for item in resp.json().get("d", []):
        v = item.get("v", {})
        print(
            f"  {item['n']:20s} | LTP={v.get('lp'):>8} | "
            f"Open={v.get('op'):>8} | High={v.get('high'):>8} | Low={v.get('low'):>8} | "
            f"Vol={v.get('volume'):>10}"
        )


def test_historical(symbol: str, days: int = 30) -> None:
    """Daily OHLCV candles for NSE equity."""
    end   = date.today()
    start = end - timedelta(days=days)
    resp = requests.get(
        f"{DATA_URL}/history",
        headers=HEADERS,
        params={
            "symbol":      f"NSE:{symbol}-EQ",
            "resolution":  "D",
            "date_format": "1",            # "1" = YYYY-MM-DD strings
            "range_from":  start.isoformat(),
            "range_to":    end.isoformat(),
            "cont_flag":   "1",
        },
        timeout=15,
    )
    resp.raise_for_status()
    candles = resp.json().get("candles", [])
    print(f"\n=== Historical OHLCV: {symbol} (last {days}d, showing first 5) ===")
    for ts, o, h, l, c, v in candles[:5]:
        print(f"  {ts} | O={o:>9.2f}  H={h:>9.2f}  L={l:>9.2f}  C={c:>9.2f}  V={v:>12,}")
    print(f"  ... {len(candles)} total candles")


def test_option_chain(index: str = "NIFTY") -> None:
    """
    Options chain with IV and PCR per strike.
    index: "NIFTY" or "BANKNIFTY"
    """
    symbol_map = {"NIFTY": "NSE:NIFTY50-INDEX", "BANKNIFTY": "NSE:NIFTYBANK-INDEX"}
    resp = requests.get(
        f"{DATA_URL}/options/chain",
        headers=HEADERS,
        params={"symbol": symbol_map.get(index, f"NSE:{index}50-INDEX"), "strikecount": 5},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    spot = data.get("underlyingValue", "N/A")
    print(f"\n=== Options Chain: {index} | Spot={spot} ===")
    print(f"  {'Strike':>10} | {'CE LTP':>8} | {'CE IV':>6} | {'CE OI':>10} | {'PE LTP':>8} | {'PE IV':>6} | {'PE OI':>10} | PCR")
    for strike_data in data.get("optionsChain", [])[:10]:
        strike = strike_data.get("strikePrice", "")
        ce = strike_data.get("CE", {})
        pe = strike_data.get("PE", {})
        pcr = round(pe.get("oi", 0) / max(ce.get("oi", 1), 1), 2)
        print(
            f"  {strike:>10} | {ce.get('ltp', 0):>8.2f} | {ce.get('iv', 0):>6.2f}% | "
            f"{ce.get('oi', 0):>10,} | {pe.get('ltp', 0):>8.2f} | {pe.get('iv', 0):>6.2f}% | "
            f"{pe.get('oi', 0):>10,} | {pcr}"
        )


def test_market_depth(symbol: str = "TATAMOTORS") -> None:
    """Top 5 bid/ask depth."""
    resp = requests.get(
        f"{DATA_URL}/depth",
        headers=HEADERS,
        params={"symbol": f"NSE:{symbol}-EQ", "ohlcv_flag": "1"},
        timeout=10,
    )
    resp.raise_for_status()
    d = resp.json().get("d", {}).get(f"NSE:{symbol}-EQ", {})
    bids = d.get("bids", [])[:3]
    asks = d.get("ask", [])[:3]
    print(f"\n=== Market Depth: {symbol} ===")
    for b, a in zip(bids, asks):
        print(f"  BID {b.get('price'):>9.2f} × {b.get('quantity'):>8,}  |  ASK {a.get('price'):>9.2f} × {a.get('quantity'):>8,}")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN":
        print("=== Fyers API v3 — Auth Setup ===")
        print(f"\nStep 1: Open this URL in your browser:\n  {get_auth_url()}")
        print("\nStep 2: After login, copy the 'auth_code' from the redirect URL.")
        print("\nStep 3: Run:  exchange_code('paste_auth_code_here')")
        print("         Paste the returned token into ACCESS_TOKEN at top of file.")
    else:
        TEST_TICKERS = ["TATAMOTORS", "HDFCBANK", "INFY", "ADANIGREEN", "TATAPOWER"]
        test_profile()
        test_quotes(TEST_TICKERS)
        test_historical("TATAMOTORS", days=30)
        test_option_chain("NIFTY")
        test_option_chain("BANKNIFTY")
        test_market_depth("HDFCBANK")
