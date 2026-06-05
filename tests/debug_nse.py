"""Quick debug script to inspect raw NseIndiaApi responses."""
import tempfile, pathlib, time, json
from nse import NSE

dl = pathlib.Path(tempfile.mkdtemp())
nse = NSE(download_folder=dl)

def safe(s):
    return str(s).encode("ascii", "replace").decode("ascii")

for ticker in ["TATAMOTORS", "MARUTI", "HDFCBANK"]:
    print(f"\n{'='*50}")
    print(f"  {ticker}")
    print(f"{'='*50}")
    time.sleep(1.5)
    try:
        raw = nse.announcements(symbol=ticker)
        count = len(raw) if hasattr(raw, "__len__") else "?"
        print(f"  type={type(raw).__name__}  count={count}")
        if raw:
            first = raw[0] if isinstance(raw, list) else raw
            print(f"  keys: {list(first.keys())}")
            print(f"  sample:\n{json.dumps(first, indent=4, default=str)[:600]}")
        else:
            print(f"  EMPTY - raw repr: {repr(raw)[:200]}")
    except Exception as e:
        print(f"  ERROR: {safe(str(e))[:150]}")

nse.exit()
