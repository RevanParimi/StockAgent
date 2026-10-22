"""
Compass Phase B — NSE delivery-bhavcopy fetcher (spec §8: bhavcopy ARCHIVES
are the reliable backbone; delivery % is included in sec_bhavdata_full).

fetch_day(day)    -> canonical EOD DataFrame (EodStore.COLUMNS) | None
sync_recent(...)  -> top-up the EodStore for recent trading days; resumable
                     (skips days already stored) and non-fatal per day.
fetch_listing(day)   -> {symbol: {"series", "isin"}} from the day's UDiFF
                        bhavcopy | None
refresh_listing(end) -> the latest listing on or before `end`, cached in
                        {DISCOVERY_DATA_DIR}/listing.json; the cache on failure
load_listing()       -> the cached listing's securities | None

The delivery bhavcopy carries no ISIN. The UDiFF CM bhavcopy, from the same
archive, carries one per security, and the ISIN is what tells a company's
shares (INE…) from a mutual-fund scheme's units (INF…: every ETF, index fund
and liquid fund). Probed 2026-10-16: 2,337 EQ rows INE, 353 EQ rows INF
(LIQUID1, CASHIETF, GOLDBEES among them); REITs trade as series RR, InvITs as
IV. NSE's per-symbol equity-meta-info API answers 404, so it cannot say.

House pattern mirrors corporate_events.py: isolated _make_nse_client factory
(tests monkeypatch it), never raises, degraded days are reported not thrown.
"""
from __future__ import annotations

import json
import logging
import pathlib
import tempfile
import time
from datetime import date, datetime, timedelta

import pandas as pd

from core.config import settings
from core.intelligence.rl.nse_calendar import is_trading_day
from services.data.stores.eod_store import COLUMNS, EodStore

logger = logging.getLogger(__name__)

_SLEEP_BETWEEN_CALLS = 0.5   # same safe margin as nse_announcements.py

# sec_bhavdata_full CSV column -> canonical column
_COLMAP = {
    "SYMBOL": "symbol",
    "SERIES": "series",
    "DATE1": "date",
    "PREV_CLOSE": "prev_close",
    "OPEN_PRICE": "open",
    "HIGH_PRICE": "high",
    "LOW_PRICE": "low",
    "CLOSE_PRICE": "close",
    "TTL_TRD_QNTY": "volume",
    "TURNOVER_LACS": "traded_value_cr",   # ÷100 below (lakh -> crore)
    "DELIV_QTY": "delivery_qty",
    "DELIV_PER": "delivery_pct",
}
_NUMERIC = ["prev_close", "open", "high", "low", "close", "volume",
            "traded_value_cr", "delivery_qty", "delivery_pct"]


def _make_nse_client():
    """Isolated factory so tests can monkeypatch it."""
    from nse import NSE
    return NSE(download_folder=pathlib.Path(tempfile.mkdtemp()))


def fetch_day(day: date) -> pd.DataFrame | None:
    """Download + normalise one day's delivery bhavcopy. None on any failure."""
    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[bhavcopy] NSE client unavailable: %s", exc)
        return None
    try:
        # Download into the client's own download_folder (default) so
        # close_nse() cleans it up — no separate orphaned mkdtemp (AUD-017).
        path = nse.deliveryBhavcopy(
            datetime(day.year, day.month, day.day),
        )
        raw = pd.read_csv(path, skipinitialspace=True)
        raw.columns = [c.strip() for c in raw.columns]
        df = raw[list(_COLMAP)].rename(columns=_COLMAP)
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["series"] = df["series"].astype(str).str.strip().str.upper()
        for col in _NUMERIC:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.strip().str.replace(",", ""),
                errors="coerce",
            )
        df["traded_value_cr"] = df["traded_value_cr"] / 100.0   # lakh -> crore
        df["date"] = day.isoformat()
        return df[COLUMNS]
    except Exception as exc:
        logger.warning("[bhavcopy] fetch failed for %s: %s", day, exc)
        return None
    finally:
        from services.data.fetchers.nse_client import close_nse
        close_nse(nse)  # exit() + rmtree(download_folder) — AUD-017


def sync_recent(end: date | None = None, days_back: int | None = None) -> dict:
    """Fetch any missing trading days in (end - days_back, end] into the store.

    Resumable: days already stored are skipped. Failed days are recorded and
    retried on the next sync (the daily job passes days_back=7 so transient
    NSE outages self-heal). Prunes beyond DISCOVERY_HISTORY_DAYS at the end.
    """
    end = end or date.today()
    days_back = days_back or settings.DISCOVERY_HISTORY_DAYS
    store = EodStore()

    synced = skipped = 0
    failed: list[str] = []
    day = end
    scanned = 0
    while scanned < days_back:
        if is_trading_day(day):
            if store.has_day(day):
                skipped += 1
            else:
                df = fetch_day(day)
                if df is not None and not df.empty:
                    store.save_day(day, df)
                    synced += 1
                else:
                    failed.append(day.isoformat())
                time.sleep(_SLEEP_BETWEEN_CALLS)
        day -= timedelta(days=1)
        scanned += 1

    pruned = store.prune(keep_sessions=settings.DISCOVERY_HISTORY_DAYS)
    result = {"synced": synced, "skipped": skipped, "failed": failed, "pruned": pruned}
    logger.info("[bhavcopy] sync_recent end=%s days_back=%d -> %s", end, days_back, result)
    return result


# -- Instrument listing (PR-004) -------------------------------------------------

# A symbol can appear in several series (a company's shares and its NCDs share
# the ticker), so one row is kept per symbol, preferring its equity series.
_SERIES_PREFERENCE = ("EQ", "BE", "BZ", "SM", "ST")


def _listing_path() -> pathlib.Path:
    return pathlib.Path(settings.DISCOVERY_DATA_DIR) / "listing.json"


def fetch_listing(day: date) -> dict[str, dict] | None:
    """{symbol: {"series", "isin"}} for every security in the day's UDiFF CM
    bhavcopy. None on any failure (holiday, archive down, format change)."""
    try:
        nse = _make_nse_client()
    except Exception as exc:
        logger.warning("[bhavcopy] NSE client unavailable for the listing: %s", exc)
        return None
    try:
        path = nse.equityBhavcopy(datetime(day.year, day.month, day.day))
        raw = pd.read_csv(path, dtype=str, skipinitialspace=True)
        raw.columns = [c.strip() for c in raw.columns]
        rank = {s: i for i, s in enumerate(_SERIES_PREFERENCE)}
        out: dict[str, dict] = {}
        for sym, series, isin in zip(raw["TckrSymb"], raw["SctySrs"], raw["ISIN"]):
            sym = str(sym).strip().upper() if pd.notna(sym) else ""
            if not sym:
                continue
            row = {"series": str(series).strip().upper() if pd.notna(series) else "",
                   "isin": str(isin).strip().upper() if pd.notna(isin) else ""}
            held = out.get(sym)
            if held is None or (rank.get(row["series"], 99) < rank.get(held["series"], 99)):
                out[sym] = row
        return out or None
    except Exception as exc:
        logger.warning("[bhavcopy] listing fetch failed for %s: %s", day, exc)
        return None
    finally:
        from services.data.fetchers.nse_client import close_nse
        close_nse(nse)


def load_listing() -> dict[str, dict] | None:
    """The cached listing's securities, or None when there is no readable cache."""
    path = _listing_path()
    if not path.exists():
        return None
    try:
        securities = json.loads(path.read_text(encoding="utf-8")).get("securities")
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("[bhavcopy] listing cache unreadable %s: %s", path, exc)
        return None
    return securities if isinstance(securities, dict) and securities else None


def refresh_listing(end: date | None = None, tries: int = 5) -> dict:
    """Fetch the listing of the latest trading day on or before `end` (trying
    up to `tries` trading days back) and cache it. On failure the cached
    listing stands: what a symbol is never changes, only new listings are
    missed. Never raises.

    Returns {"as_of": ISO date | None, "fresh": bool, "securities": int}."""
    end = end or date.today()
    day, tried = end, 0
    while tried < tries and (end - day).days < 15:
        if is_trading_day(day):
            tried += 1
            securities = fetch_listing(day)
            if securities:
                path = _listing_path()
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"as_of": day.isoformat(),
                                               "securities": securities}), encoding="utf-8")
                    tmp.replace(path)
                except OSError as exc:
                    logger.error("[bhavcopy] listing cache write failed %s: %s", path, exc)
                logger.info("[bhavcopy] listing as of %s: %d securities", day, len(securities))
                return {"as_of": day.isoformat(), "fresh": True, "securities": len(securities)}
            time.sleep(_SLEEP_BETWEEN_CALLS)
        day -= timedelta(days=1)
    cached = load_listing()
    as_of = None
    if cached:
        try:
            as_of = json.loads(_listing_path().read_text(encoding="utf-8")).get("as_of")
        except (OSError, ValueError) as exc:
            logger.warning("[bhavcopy] listing cache date unreadable: %s", exc)
    logger.warning("[bhavcopy] listing not refreshed (end=%s); cached as of %s", end, as_of)
    return {"as_of": as_of, "fresh": False, "securities": len(cached or {})}
