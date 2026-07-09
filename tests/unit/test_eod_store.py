"""Compass Phase B — per-day parquet EOD store."""
from datetime import date

import pandas as pd
import pytest

from services.data.stores.eod_store import EodStore


def _day_frame(iso: str, symbols=("AAA", "BBB")) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(symbols):
        rows.append({"symbol": s, "series": "EQ", "date": iso,
                     "prev_close": 99.0 + i, "open": 100.0 + i, "high": 102.0 + i,
                     "low": 99.0 + i, "close": 101.0 + i, "volume": 1000.0 * (i + 1),
                     "traded_value_cr": 6.0 + i, "delivery_qty": 400.0,
                     "delivery_pct": 40.0 + i})
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path):
    return EodStore(base_dir=str(tmp_path))


def test_save_and_has_day(store):
    d = date(2026, 7, 3)
    path = store.save_day(d, _day_frame("2026-07-03"))
    assert path.name == "2026-07-03.parquet"
    assert store.has_day(d) is True
    assert store.has_day(date(2026, 7, 4)) is False
    assert store.latest_day() == d


def test_load_window_concats_and_sorts(store):
    store.save_day(date(2026, 7, 1), _day_frame("2026-07-01"))
    store.save_day(date(2026, 7, 2), _day_frame("2026-07-02"))
    store.save_day(date(2026, 7, 3), _day_frame("2026-07-03"))
    win = store.load_window(end=date(2026, 7, 3), sessions=2)
    assert sorted(win["date"].unique()) == ["2026-07-02", "2026-07-03"]
    assert set(win.columns) >= {"symbol", "series", "date", "close",
                                "volume", "traded_value_cr", "delivery_pct"}


def test_load_window_empty_store(store):
    win = store.load_window(end=date(2026, 7, 3), sessions=10)
    assert win.empty


def test_prune_keeps_newest(store):
    for d in (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)):
        store.save_day(d, _day_frame(d.isoformat()))
    removed = store.prune(keep_sessions=2)
    assert removed == 1
    assert store.has_day(date(2026, 7, 1)) is False
    assert store.latest_day() == date(2026, 7, 3)
