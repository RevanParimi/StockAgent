"""
scripts/api_exploration/angel_one_explorer.py
==============================================
Angel One SmartAPI v2 Explorer — Free, no monthly fee.
Tests: live quotes, historical OHLCV, WebSocket live tick, Depth-20 bid/ask.

Setup:
  1. Open a Demat account at angelone.in
  2. Register API app at smartapi.angelone.in → get API_KEY
  3. Enable TOTP in the Angel One app (Settings → TOTP)
  4. pip install smartapi-python pyotp

Docs: https://smartapi.angelone.in/docs/
"""

from __future__ import annotations

import time
from datetime import date, timedelta, datetime

# pip install smartapi-python pyotp
try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    import pyotp
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False
    print("[setup] Run: pip install smartapi-python pyotp")

# ─── CREDENTIALS ──────────────────────────────────────────────────────────────
API_KEY      = "YOUR_ANGEL_API_KEY"        # from smartapi.angelone.in
CLIENT_ID    = "YOUR_CLIENT_ID"            # your Angel One login ID
PASSWORD     = "YOUR_MPIN"                 # 4-digit MPIN
TOTP_SECRET  = "YOUR_TOTP_SECRET"          # base32 string from TOTP setup QR code
# ──────────────────────────────────────────────────────────────────────────────

# NSE token map — Angel One uses numeric instrument tokens (not ticker symbols)
# Fetch the full instrument list from: https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json
INSTRUMENT_TOKENS = {
    "TATAMOTORS": "3456",
    "HDFCBANK":   "1333",
    "INFY":       "1594",
    "ADANIGREEN": "25",
    "NIFTY 50":   "26000",   # index
    "BANKNIFTY":  "26009",   # index
}


def _login() -> "SmartConnect":
    """Authenticate and return a connected SmartConnect session."""
    if not _DEPS_OK:
        raise RuntimeError("Install deps first: pip install smartapi-python pyotp")
    totp = pyotp.TOTP(TOTP_SECRET).now()
    obj = SmartConnect(api_key=API_KEY)
    data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
    if data["status"] is False:
        raise RuntimeError(f"Login failed: {data['message']}")
    print(f"[auth] Logged in as {CLIENT_ID} | JWT obtained")
    return obj


def test_profile(obj: "SmartConnect") -> None:
    profile = obj.getProfile(obj.refresh_token)
    print(f"\n[profile] name={profile['data'].get('name')} | "
          f"email={profile['data'].get('email')} | "
          f"broker={profile['data'].get('broker')}")


def test_quotes(obj: "SmartConnect", tokens: list[tuple[str, str]]) -> None:
    """
    Live quotes for multiple symbols.
    tokens: list of (exchange, symboltoken) — e.g. [("NSE", "3456")]
    """
    exchange_tokens = {"NSE": [t for e, t in tokens if e == "NSE"]}
    data = obj.getMarketData("FULL", exchange_tokens)
    print("\n=== Live Quotes (Angel One SmartAPI) ===")
    for item in data.get("data", {}).get("fetched", []):
        print(
            f"  {item.get('symbolName', ''):20s} | "
            f"LTP={item.get('ltp', 0):>9.2f} | "
            f"Open={item.get('open', 0):>9.2f} | "
            f"High={item.get('high', 0):>9.2f} | "
            f"Low={item.get('low', 0):>9.2f} | "
            f"Vol={item.get('tradeVolume', 0):>12,}"
        )


def test_historical(obj: "SmartConnect", symbol: str, token: str, days: int = 30) -> None:
    """Daily OHLCV candles for last N days."""
    end   = datetime.now().strftime("%Y-%m-%d %H:%M")
    start = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d 09:15")
    params = {
        "exchange":    "NSE",
        "symboltoken": token,
        "interval":    "ONE_DAY",
        "fromdate":    start,
        "todate":      end,
    }
    data = obj.getCandleData(params)
    candles = data.get("data", [])
    print(f"\n=== Historical OHLCV: {symbol} (last {days}d, first 5) ===")
    for ts, o, h, l, c, v in candles[:5]:
        print(f"  {ts[:10]} | O={o:>9.2f}  H={h:>9.2f}  L={l:>9.2f}  C={c:>9.2f}  V={v:>12,}")
    print(f"  ... {len(candles)} total candles")


def test_option_chain(obj: "SmartConnect", name: str = "NIFTY") -> None:
    """Full options chain with OI, IV, Greeks from SmartAPI."""
    data = obj.allTradingSession(name, date.today().strftime("%Y-%m-%d"), "")
    print(f"\n=== Options Chain: {name} ===")
    chain = data.get("data", {})
    print(f"  ATM Strike   = {chain.get('atmStrike')}")
    print(f"  Expiry dates = {chain.get('expiryDates', [])[:4]}")
    options = chain.get("options", [])[:3]
    for opt in options:
        print(
            f"  Strike={opt.get('strikePrice'):>8} | "
            f"CE IV={opt.get('CE', {}).get('impliedVolatility', 'N/A'):>6} | "
            f"CE Delta={opt.get('CE', {}).get('delta', 'N/A'):>6} | "
            f"PE IV={opt.get('PE', {}).get('impliedVolatility', 'N/A'):>6} | "
            f"PE Delta={opt.get('PE', {}).get('delta', 'N/A'):>6}"
        )


def test_websocket_ticks(obj: "SmartConnect", tokens: list[str]) -> None:
    """
    Stream live ticks via SmartAPI WebSocket v2 (Depth-20).
    Runs for 10 seconds then stops.
    """
    feed_token  = obj.getfeedToken()
    client_code = CLIENT_ID
    token_list  = [{"exchangeType": 1, "tokens": tokens}]  # 1 = NSE

    def on_data(wsapp, message):
        print(f"  [tick] {message}")

    def on_error(wsapp, error):
        print(f"  [ws error] {error}")

    def on_close(wsapp):
        print("  [ws] connection closed")

    def on_open(wsapp):
        print("  [ws] connected, subscribing...")
        sws.subscribe("depth_20_sub", 4, token_list)   # mode 4 = SNAP_QUOTE with 20-depth

    sws = SmartWebSocketV2(feed_token, API_KEY, client_code, obj.access_token)
    sws.on_open    = on_open
    sws.on_data    = on_data
    sws.on_error   = on_error
    sws.on_close   = on_close

    print(f"\n=== WebSocket Depth-20 (running 10s) ===")
    import threading
    t = threading.Thread(target=sws.connect)
    t.daemon = True
    t.start()
    time.sleep(10)
    sws.close_connection()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if API_KEY == "YOUR_ANGEL_API_KEY":
        print("=== Angel One SmartAPI — Setup Required ===")
        print("1. Create account: https://www.angelone.in/open-demat-account")
        print("2. Register API app: https://smartapi.angelone.in/")
        print("3. Fill API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET at top of file")
        print("4. pip install smartapi-python pyotp")
    else:
        obj = _login()
        test_profile(obj)

        # Build token pairs for getMarketData
        token_pairs = [("NSE", INSTRUMENT_TOKENS[t]) for t in ["TATAMOTORS", "HDFCBANK", "INFY"]]
        test_quotes(obj, token_pairs)
        test_historical(obj, "TATAMOTORS", INSTRUMENT_TOKENS["TATAMOTORS"], days=30)
        test_option_chain(obj, "NIFTY")
        test_websocket_ticks(obj, [INSTRUMENT_TOKENS["NIFTY 50"]])
