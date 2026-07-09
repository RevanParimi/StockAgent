"""
Compass Phase B — per-symbol surveillance/meta + float-mcap guard data
(spec §6.1 threshold gates: ASM/GSM, suspension, free-float mcap floor).

Called only for the post-rank SHORTLIST (~80 symbols), never the full
universe — per-symbol NSE calls at 0.5s spacing stay under a minute.
Per-day JSON cache so a re-run within the day is free.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
import time
from datetime import date

logger = logging.getLogger(__name__)

_CACHE_PATH_DEFAULT = "data/market_cache/symbol_meta.json"
_SLEEP_BETWEEN_CALLS = 0.5


def _make_nse_client():
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def _yf_info(ticker: str) -> dict:
    """yfinance .info with the repo's NSE suffix convention. {} on failure."""
    try:
        import yfinance as yf
        from core.config import settings
        suffix = settings.YFINANCE_SUFFIX
        yf_ticker = settings.YF_SYMBOL_OVERRIDES.get(ticker.upper()) or (
            ticker if ticker.endswith(suffix) else f"{ticker}{suffix}"
        )
        return yf.Ticker(yf_ticker).info or {}
    except Exception as exc:
        logger.debug("[surveillance] yfinance info failed for %s: %s", ticker, exc)
        return {}


def _load_cache(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: pathlib.Path, cache: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("[surveillance] cache write failed %s: %s", path, exc)


def get_symbol_meta(symbol: str) -> dict:
    """NSE meta for one symbol: surveillance flag, suspension, industry.
    Cached per (symbol, day). Never raises — degraded=True on failure."""
    symbol = symbol.strip().upper()
    path = pathlib.Path(_CACHE_PATH_DEFAULT)
    cache = _load_cache(path)
    key = f"{symbol}|{date.today().isoformat()}"
    if key in cache:
        return cache[key]

    result = {"surveillance": None, "suspended": False, "industry": None,
              "degraded": False}
    try:
        nse = _make_nse_client()
        try:
            meta = nse.equityMetaInfo(symbol) or {}
        finally:
            try:
                nse.exit()
            except Exception:
                pass
        surv_block = meta.get("surveillance") or {}
        surv = surv_block.get("surv") if isinstance(surv_block, dict) else None
        result["surveillance"] = (str(surv).strip() or None) if surv else None
        status = str((meta.get("metadata") or {}).get("status", "")).lower()
        result["suspended"] = "suspend" in status or "delist" in status
        info = meta.get("info") or {}
        industry = info.get("industry") or meta.get("industry")
        result["industry"] = str(industry).strip() if industry else None
    except Exception as exc:
        logger.warning("[surveillance] meta fetch failed for %s: %s", symbol, exc)
        result["degraded"] = True

    cache[key] = result
    _save_cache(path, cache)
    time.sleep(_SLEEP_BETWEEN_CALLS)
    return result


def float_mcap_cr(symbol: str) -> float | None:
    """Free-float market cap in ₹ crore via yfinance; None when unknown."""
    info = _yf_info(symbol)
    shares = info.get("floatShares")
    price = info.get("currentPrice") or info.get("regularMarketPrice") \
        or info.get("previousClose")
    if not shares or not price:
        return None
    return float(shares) * float(price) / 1e7
