"""
scripts/api_exploration/dhan_explorer.py
=========================================
Dhan DhanHQ v2 Explorer — Free API, best options Greeks coverage.
Tests: live quotes, historical OHLCV, options chain with full Greeks (Δ,Θ,Γ,ν,IV), WebSocket.

⚠️  SEBI Mandate (April 2026): Dhan requires a STATIC IP for order placement.
    For read-only data access (what StockAgent needs) a static IP is NOT required.
    Static IP is only enforced at the trading/order API level.

Setup:
  1. Open Dhan account: https://dhan.co
  2. Get access token: Dhan → My Account → Dhan HQ → API Access
  3. pip install dhanhq

Docs: https://dhanhq.co/docs/v2/
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import requests

# pip install dhanhq
try:
    from dhanhq import dhanhq, marketfeed
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False
    print("[setup] Run: pip install dhanhq")

# ─── CREDENTIALS ──────────────────────────────────────────────────────────────
CLIENT_ID    = "YOUR_DHAN_CLIENT_ID"    # numeric string, e.g. "1103XXXXXX"
ACCESS_TOKEN = "YOUR_DHAN_ACCESS_TOKEN" # 24-hour token from Dhan dashboard
# ──────────────────────────────────────────────────────────────────────────────

# Dhan uses numeric security_id. NSE securities list:
# https://images.dhan.co/api-data/api-scrip-master.csv
SECURITY_IDS = {
    "TATAMOTORS": "3456",
    "HDFCBANK":   "1333",
    "INFY":       "1594",
    "ADANIGREEN": "25",
    "TATAPOWER":  "3426",
    "NIFTY":      "13",    # index scrip (for option chain underlying)
    "BANKNIFTY":  "25",    # index scrip
}

# Dhan exchange segment codes
NSE_EQ  = "NSE_EQ"
NSE_FNO = "NSE_FNO"
IDX_I   = "IDX_I"          # index


def _client() -> "dhanhq":
    if not _DEPS_OK:
        raise RuntimeError("Run: pip install dhanhq")
    return dhanhq(CLIENT_ID, ACCESS_TOKEN)


# ─── DATA TESTS ───────────────────────────────────────────────────────────────

def test_ltp(dhan: "dhanhq", symbols: list[str]) -> None:
    """Live Last Traded Price for multiple NSE equities."""
    securities = {NSE_EQ: [SECURITY_IDS[s] for s in symbols if s in SECURITY_IDS]}
    data = dhan.get_market_feed_quote(securities)
    print("\n=== Live Quotes (Dhan) ===")
    for seg, items in data.get("data", {}).items():
        for sec_id, info in items.items():
            name = next((k for k, v in SECURITY_IDS.items() if v == sec_id), sec_id)
            print(
                f"  {name:20s} | LTP={info.get('last_price', 0):>9.2f} | "
                f"Open={info.get('ohlc', {}).get('open', 0):>9.2f} | "
                f"High={info.get('ohlc', {}).get('high', 0):>9.2f} | "
                f"Low={info.get('ohlc', {}).get('low', 0):>9.2f} | "
                f"Vol={info.get('volume', 0):>12,}"
            )


def test_historical(dhan: "dhanhq", symbol: str, days: int = 30) -> None:
    """Daily OHLCV candles."""
    end   = date.today()
    start = end - timedelta(days=days)
    data  = dhan.historical_daily_data(
        symbol=symbol,
        exchange_segment=NSE_EQ,
        instrument_type="EQUITY",
        expiry_code=0,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
    )
    candles = list(zip(
        data.get("data", {}).get("timestamp", []),
        data.get("data", {}).get("open",      []),
        data.get("data", {}).get("high",      []),
        data.get("data", {}).get("low",       []),
        data.get("data", {}).get("close",     []),
        data.get("data", {}).get("volume",    []),
    ))
    print(f"\n=== Historical OHLCV: {symbol} (last {days}d, first 5) ===")
    for ts, o, h, l, c, v in candles[:5]:
        print(f"  {ts} | O={o:>9.2f}  H={h:>9.2f}  L={l:>9.2f}  C={c:>9.2f}  V={v:>12,}")
    print(f"  ... {len(candles)} total candles")


def test_option_chain(dhan: "dhanhq", underlying: str = "NIFTY", expiry: str = "") -> None:
    """
    Full options chain with live Greeks: Delta, Gamma, Theta, Vega, IV.
    This is Dhan's crown jewel — free Greeks per strike in one API call.

    underlying: "NIFTY" or "BANKNIFTY"
    expiry: "YYYY-MM-DD" — leave blank for nearest weekly expiry
    """
    scrip_id = SECURITY_IDS.get(underlying, "13")
    if not expiry:
        # nearest Thursday
        today = date.today()
        days_to_thursday = (3 - today.weekday()) % 7
        if days_to_thursday == 0:
            days_to_thursday = 7
        expiry = (today + timedelta(days=days_to_thursday)).isoformat()

    data = dhan.option_chain(
        UnderlyingScrip=scrip_id,
        UnderlyingSeg=IDX_I,
        Expiry=expiry,
    )

    oc = data.get("data", {}).get("oc", {})
    print(f"\n=== Options Chain: {underlying} | Expiry={expiry} ===")
    print(
        f"  {'Strike':>10} | "
        f"{'CE LTP':>8} {'CE IV%':>7} {'CE Δ':>7} {'CE Θ':>8} {'CE OI':>10} | "
        f"{'PE LTP':>8} {'PE IV%':>7} {'PE Δ':>7} {'PE Θ':>8} {'PE OI':>10}"
    )

    strikes_sorted = sorted(oc.keys(), key=lambda x: float(x))
    # Show 5 strikes above and below ATM
    mid = len(strikes_sorted) // 2
    window = strikes_sorted[max(0, mid-5): mid+6]

    for strike_str in window:
        strike_data = oc[strike_str]
        ce = strike_data.get("ce", {})
        pe = strike_data.get("pe", {})
        print(
            f"  {float(strike_str):>10,.0f} | "
            f"{ce.get('last_price', 0):>8.2f} "
            f"{ce.get('implied_volatility', 0):>7.2f} "
            f"{ce.get('delta', 0):>7.3f} "
            f"{ce.get('theta', 0):>8.3f} "
            f"{ce.get('oi', 0):>10,} | "
            f"{pe.get('last_price', 0):>8.2f} "
            f"{pe.get('implied_volatility', 0):>7.2f} "
            f"{pe.get('delta', 0):>7.3f} "
            f"{pe.get('theta', 0):>8.3f} "
            f"{pe.get('oi', 0):>10,}"
        )

    # PCR and Max Pain
    total_ce_oi = sum(oc[s].get("ce", {}).get("oi", 0) for s in oc)
    total_pe_oi = sum(oc[s].get("pe", {}).get("oi", 0) for s in oc)
    pcr = round(total_pe_oi / max(total_ce_oi, 1), 3)
    print(f"\n  Total CE OI: {total_ce_oi:,} | Total PE OI: {total_pe_oi:,} | PCR: {pcr}")


def test_expiry_list(dhan: "dhanhq", underlying: str = "NIFTY") -> None:
    """List available expiry dates for an underlying."""
    scrip_id = SECURITY_IDS.get(underlying, "13")
    data = dhan.option_chain(UnderlyingScrip=scrip_id, UnderlyingSeg=IDX_I, Expiry="")
    expiries = data.get("data", {}).get("expiry_list", [])
    print(f"\n=== Available Expiries: {underlying} ===")
    for e in expiries[:8]:
        print(f"  {e}")


def test_websocket_ticks(securities: dict | None = None) -> None:
    """
    Stream live market ticks via Dhan WebSocket.
    securities: {exchange_segment: [security_id, ...]}
    """
    if not _DEPS_OK:
        print("[ws] dhanhq not installed")
        return

    import threading

    if securities is None:
        securities = {marketfeed.NSE: [("3456", marketfeed.Quote)]}  # TATAMOTORS Quote mode

    print("\n=== WebSocket Ticks (running 10s) ===")

    def on_ticks(tick):
        print(f"  [tick] {tick}")

    feed = marketfeed.DhanFeed(
        client_id=CLIENT_ID,
        access_token=ACCESS_TOKEN,
        instruments=securities,
        subscription_type=marketfeed.Quote,
        on_ticks=on_ticks,
    )

    import time
    t = threading.Thread(target=feed.run_forever)
    t.daemon = True
    t.start()
    time.sleep(10)
    feed.disconnect()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if CLIENT_ID == "YOUR_DHAN_CLIENT_ID":
        print("=== Dhan DhanHQ v2 — Setup Required ===")
        print("1. Open account: https://dhan.co")
        print("2. Get token: My Account → Dhan HQ → Create Access Token")
        print("3. Fill CLIENT_ID and ACCESS_TOKEN at top of file")
        print("4. pip install dhanhq")
        print("\nNote: access token expires every 24 hours — regenerate daily.")
    else:
        dhan = _client()
        test_ltp(dhan, ["TATAMOTORS", "HDFCBANK", "INFY", "ADANIGREEN"])
        test_historical(dhan, "TATAMOTORS", days=30)
        test_expiry_list(dhan, "NIFTY")
        test_option_chain(dhan, "NIFTY")
        test_option_chain(dhan, "BANKNIFTY")
        test_websocket_ticks()
