"""Compass Phase B — delivery-bhavcopy fetcher -> canonical EOD frame."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import services.data.fetchers.bhavcopy as bc
from services.data.stores.eod_store import EodStore

# sec_bhavdata_full CSV as NSE ships it: padded values, ' -' for missing.
_CSV = (
    "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,"
    " LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,"
    " NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
    "AAA, EQ, 03-Jul-2026, 99.0, 100.0, 102.0, 99.0, 101.0, 101.0, 100.5,"
    " 10000, 600.00, 500, 4000, 40.00\n"
    "BBB, BE, 03-Jul-2026, 50.0, 50.0, 52.0, 49.0, 51.0, 51.0, 50.5,"
    " 2000, 101.00, 80, -, -\n"
)


@pytest.fixture
def fake_nse(tmp_path, monkeypatch):
    csv_path = tmp_path / "sec_bhavdata_full_03072026.csv"
    csv_path.write_text(_CSV, encoding="utf-8")

    class _FakeNSE:
        def deliveryBhavcopy(self, dt, folder=None):
            return csv_path
        def exit(self):
            pass

    monkeypatch.setattr(bc, "_make_nse_client", lambda: _FakeNSE())
    return csv_path


def test_fetch_day_normalises_columns(fake_nse):
    df = bc.fetch_day(date(2026, 7, 3))
    assert df is not None
    aaa = df[df["symbol"] == "AAA"].iloc[0]
    assert aaa["series"] == "EQ"
    assert aaa["date"] == "2026-07-03"
    assert aaa["close"] == 101.0
    assert aaa["traded_value_cr"] == pytest.approx(6.0)    # TURNOVER_LACS 600.00 lakh = ₹6.0 cr
    assert aaa["delivery_pct"] == 40.0
    # ' -' missing markers parse to NaN, not crash
    bbb = df[df["symbol"] == "BBB"].iloc[0]
    assert pd.isna(bbb["delivery_pct"])


def test_fetch_day_failure_returns_none(monkeypatch):
    class _Boom:
        def deliveryBhavcopy(self, dt, folder=None):
            raise RuntimeError("403")
        def exit(self):
            pass
    monkeypatch.setattr(bc, "_make_nse_client", lambda: _Boom())
    assert bc.fetch_day(date(2026, 7, 3)) is None


def test_sync_recent_skips_existing_and_records_failures(tmp_path, monkeypatch, fake_nse):
    store = EodStore(base_dir=str(tmp_path / "eod"))
    monkeypatch.setattr(bc, "EodStore", lambda: store)
    monkeypatch.setattr(bc, "is_trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(bc.time, "sleep", lambda s: None)

    result = bc.sync_recent(end=date(2026, 7, 3), days_back=3)  # Wed 1st..Fri 3rd
    assert result["synced"] == 3 and result["skipped"] == 0

    result2 = bc.sync_recent(end=date(2026, 7, 3), days_back=3)
    assert result2["synced"] == 0 and result2["skipped"] == 3
