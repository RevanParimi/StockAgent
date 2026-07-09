"""
Compass Phase B — per-day parquet EOD store (spec §8 data plan).

One parquet file per trading day under data/market_cache/bhavcopy/
(YYYY-MM-DD.parquet). Per-day files make the initial ~550-session backfill
resumable (a crashed sync just skips days already on disk) and pruning
trivial. ~2yr of NSE mainboard EOD ≈ 200MB — fits the Railway volume.

Canonical columns (all consumers depend on these exact names):
  symbol, series, date (ISO str), prev_close, open, high, low, close,
  volume, traded_value_cr, delivery_qty, delivery_pct
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)

_DAY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.parquet$")

COLUMNS: list[str] = [
    "symbol", "series", "date", "prev_close", "open", "high", "low",
    "close", "volume", "traded_value_cr", "delivery_qty", "delivery_pct",
]


class EodStore:
    def __init__(self, base_dir: str | None = None) -> None:
        self._dir = Path(base_dir or settings.DISCOVERY_BHAVCOPY_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.parquet"

    def _day_files(self) -> list[Path]:
        return sorted(
            p for p in self._dir.glob("*.parquet") if _DAY_FILE_RE.match(p.name)
        )

    def save_day(self, day: date, df: pd.DataFrame) -> Path:
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"EodStore.save_day: missing columns {missing}")
        path = self._path(day)
        tmp = path.with_suffix(".tmp")
        df[COLUMNS].to_parquet(tmp, index=False)
        tmp.replace(path)
        return path

    def has_day(self, day: date) -> bool:
        return self._path(day).exists()

    def latest_day(self) -> date | None:
        files = self._day_files()
        if not files:
            return None
        return date.fromisoformat(files[-1].stem)

    def load_window(self, end: date, sessions: int) -> pd.DataFrame:
        """Concatenate the newest `sessions` day-files with date <= end."""
        files = [
            p for p in self._day_files() if date.fromisoformat(p.stem) <= end
        ][-sessions:]
        if not files:
            return pd.DataFrame(columns=COLUMNS)
        frames = []
        for p in files:
            try:
                frames.append(pd.read_parquet(p))
            except Exception as exc:                      # corrupt file: skip, log
                logger.warning("[eod_store] unreadable %s: %s", p.name, exc)
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        return pd.concat(frames, ignore_index=True).sort_values(
            ["date", "symbol"], ignore_index=True
        )

    def prune(self, keep_sessions: int) -> int:
        files = self._day_files()
        stale = files[:-keep_sessions] if keep_sessions > 0 else files
        for p in stale:
            try:
                p.unlink()
            except OSError as exc:
                logger.warning("[eod_store] prune failed for %s: %s", p.name, exc)
        return len(stale)
