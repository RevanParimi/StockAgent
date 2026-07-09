"""
Compass Phase B — NSE delivery-bhavcopy fetcher (spec §8: bhavcopy ARCHIVES
are the reliable backbone; delivery % is included in sec_bhavdata_full).

fetch_day(day)    -> canonical EOD DataFrame (EodStore.COLUMNS) | None
sync_recent(...)  -> top-up the EodStore for recent trading days; resumable
                     (skips days already stored) and non-fatal per day.

House pattern mirrors corporate_events.py: isolated _make_nse_client factory
(tests monkeypatch it), never raises, degraded days are reported not thrown.
"""
from __future__ import annotations

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
        path = nse.deliveryBhavcopy(
            datetime(day.year, day.month, day.day),
            folder=pathlib.Path(tempfile.mkdtemp()),
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
        try:
            nse.exit()
        except Exception:
            pass


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
