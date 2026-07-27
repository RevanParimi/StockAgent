"""Piece B (spec 2026-07-27): peak-close signal + trailing_stop_breach rule."""
from datetime import date

import pandas as pd

from core.portfolio.advisor import peak_close_since


def _ohlcv(closes_by_day: dict[str, float]) -> pd.DataFrame:
    idx = pd.to_datetime(list(closes_by_day)).tz_localize("Asia/Kolkata")
    return pd.DataFrame({"Close": list(closes_by_day.values())}, index=idx)


def test_peak_is_max_close_on_or_after_buy_date():
    df = _ohlcv({"2026-07-01": 100.0, "2026-07-10": 140.0, "2026-07-20": 120.0})
    assert peak_close_since(df, date(2026, 7, 5)) == 140.0


def test_closes_before_buy_date_are_ignored():
    df = _ohlcv({"2026-07-01": 999.0, "2026-07-10": 140.0})
    assert peak_close_since(df, date(2026, 7, 5)) == 140.0


def test_none_when_no_data_in_window_or_no_df():
    df = _ohlcv({"2026-07-01": 100.0})
    assert peak_close_since(df, date(2026, 7, 5)) is None
    assert peak_close_since(None, date(2026, 7, 5)) is None


def test_setting_exists():
    from core.config import settings
    assert settings.ADVISOR_TRAIL_ARM_PCT == 10.0
