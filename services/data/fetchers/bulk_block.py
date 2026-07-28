"""
Compass Phase B — NSE bulk/block deals over a trailing window (spec §6.1:
"repeated same-side bulk/block deals" = institutional accumulation).

Degraded mode (spec §8): on fetch failure the previous cache is kept and
flagged degraded — the screen treats the signal as live-but-stale, and the
weekly job logs it.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DEFAULT_CACHE = "data/market_cache/bulk_block.json"

# NSE bulk/block rows use several key spellings across report vintages.
_SYMBOL_KEYS = ("BD_SYMBOL", "symbol", "SYMBOL")
_SIDE_KEYS = ("BD_BUY_SELL", "buySell", "BUY_SELL")
_QTY_KEYS = ("BD_QTY_TRD", "qty", "QTY_TRADED", "noOfShareTraded")
_DATE_KEYS = ("BD_DT_DATE", "date", "DEAL_DATE", "mDate")

_NSE_DATE_FMTS = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d")


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _first(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _parse_date(raw: str) -> str:
    for fmt in _NSE_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _normalise(rows: list[dict], kind: str) -> list[dict]:
    out: list[dict] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        symbol = _first(item, _SYMBOL_KEYS).upper()
        side = _first(item, _SIDE_KEYS).upper()
        qty_raw = _first(item, _QTY_KEYS).replace(",", "")
        deal_date = _parse_date(_first(item, _DATE_KEYS))
        try:
            qty = float(qty_raw)
        except ValueError:
            continue
        if not symbol or side not in ("BUY", "SELL"):
            continue
        out.append({"symbol": symbol, "side": side, "qty": qty,
                    "kind": kind, "date": deal_date})
    return out


def load_bulk_block(cache_path: str | None = None) -> dict:
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    if not path.exists():
        return {"fetched_at": "", "degraded": True, "deals": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[bulk_block] cache unreadable %s: %s", path, exc)
        return {"fetched_at": "", "degraded": True, "deals": []}


def refresh_bulk_block(weeks: int = 4, cache_path: str | None = None) -> dict:
    """Fetch trailing `weeks` of bulk + block deals. Never raises."""
    path = pathlib.Path(cache_path or _DEFAULT_CACHE)
    previous = load_bulk_block(cache_path=str(path))

    todate = datetime.now()
    fromdate = todate - timedelta(weeks=weeks)
    deals: list[dict] = []
    degraded = False
    try:
        nse = _make_nse_client()
        try:
            deals += _normalise(nse.bulkdeals("bulk_deals", fromdate, todate), "bulk")
            deals += _normalise(nse.bulkdeals("block_deals", fromdate, todate), "block")
        finally:
            from services.data.fetchers.nse_client import close_nse
            close_nse(nse)  # exit() + rmtree(download_folder) — AUD-017
    except Exception as exc:
        logger.warning("[bulk_block] fetch failed — keeping stale cache: %s", exc)
        degraded = True
        deals = list(previous.get("deals", []))

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "degraded": degraded,
        "deals": deals,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[bulk_block] cache write failed %s: %s", path, exc)
    return result


def net_accumulation(cache: dict) -> dict[str, float]:
    """Per-symbol net BUY quantity over the cached window, floored at 0.
    (Spec §6.1 wants same-side ACCUMULATION — net sellers are simply 0.)"""
    net: dict[str, float] = {}
    for d in cache.get("deals", []):
        sign = 1.0 if d.get("side") == "BUY" else -1.0
        net[d["symbol"]] = net.get(d["symbol"], 0.0) + sign * float(d.get("qty", 0.0))
    return {s: max(0.0, q) for s, q in net.items()}
