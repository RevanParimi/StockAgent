"""
Test NSE symbol lookup and verify TATAMOTORS resolution.
Also test the full announcements pipeline for the resolved symbol.
"""
import tempfile, pathlib, time, json
from nse import NSE

dl  = pathlib.Path(tempfile.mkdtemp())
nse = NSE(download_folder=dl)

def safe(s):
    return str(s).encode("ascii", "replace").decode("ascii")

# ── 1. lookup() ─────────────────────────────────────────────────────────────
print("="*55)
print("1. nse.lookup() for Tata Motors variants")
print("="*55)
for query in ["Tata Motors", "TATAMOTORS", "tata motors"]:
    time.sleep(0.8)
    try:
        result = nse.lookup(query)
        rtype  = type(result).__name__
        rlen   = len(result) if hasattr(result, "__len__") else "?"
        print(f"\n  lookup({query!r}) -> type={rtype} len={rlen}")
        if result:
            sample = result if isinstance(result, list) else [result]
            for item in sample[:3]:
                if isinstance(item, dict):
                    print(f"    symbol={item.get('symbol','?')} | name={safe(str(item.get('name',item.get('companyName','?'))))[:50]}")
                else:
                    print(f"    {safe(str(item))[:80]}")
    except Exception as e:
        print(f"  lookup({query!r}) -> ERROR: {safe(str(e))[:100]}")

# ── 2. Try common Tata Motors symbol variants ────────────────────────────────
print("\n" + "="*55)
print("2. announcements() for symbol variants")
print("="*55)
for sym in ["TATAMOTORS", "TATAMTRDVR", "TATAMOTOR", "TTM"]:
    time.sleep(1.0)
    try:
        raw   = nse.announcements(symbol=sym)
        count = len(raw) if hasattr(raw, "__len__") else "?"
        print(f"  announcements({sym!r}) -> {count} items")
        if raw:
            print(f"    sample desc: {safe(str(raw[0].get('desc','?')))[:60]}")
            print(f"    sample date: {raw[0].get('an_dt','?')}")
    except Exception as e:
        print(f"  announcements({sym!r}) -> ERROR: {safe(str(e))[:80]}")

# ── 3. equityMetaInfo() to get canonical symbol ─────────────────────────────
print("\n" + "="*55)
print("3. equityMetaInfo() for TATAMOTORS")
print("="*55)
time.sleep(1.0)
try:
    meta = nse.equityMetaInfo(symbol="TATAMOTORS")
    print(f"  type={type(meta).__name__}")
    if isinstance(meta, dict):
        print(f"  symbol    : {meta.get('symbol','?')}")
        print(f"  companyName: {safe(str(meta.get('companyName','?')))[:60]}")
        print(f"  isin      : {meta.get('isin','?')}")
        print(f"  industry  : {safe(str(meta.get('industry','?')))}")
except Exception as e:
    print(f"  ERROR: {safe(str(e))[:100]}")

# ── 4. Combined Serper + NseIndiaApi pipeline simulation ─────────────────────
print("\n" + "="*55)
print("4. Combined pipeline: recent announcements formatted for LLM")
print("="*55)
time.sleep(1.0)
for ticker in ["MARUTI", "HDFCBANK", "TCS"]:
    try:
        raw = nse.announcements(symbol=ticker)
        # Filter last 7 days
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=7)
        recent = []
        for item in (raw or []):
            try:
                dt = datetime.strptime(item.get("sort_date",""), "%Y-%m-%d %H:%M:%S")
                if dt >= cutoff:
                    recent.append(item)
            except Exception:
                pass

        print(f"\n  [{ticker}] Recent announcements (last 7 days): {len(recent)}")
        for item in recent[:4]:
            desc = item.get("desc","")
            text = item.get("attchmntText","")
            dt   = item.get("an_dt","")
            print(f"    [{safe(dt)}] {safe(desc)}: {safe(str(text))[:80]}")
    except Exception as e:
        print(f"  [{ticker}] ERROR: {safe(str(e))[:80]}")
    time.sleep(0.8)

nse.exit()
print("\nDone.")
