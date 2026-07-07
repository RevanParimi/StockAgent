"""Compass Phase A — portfolio/advisor tunables exposed via settings."""
from core.config import settings


def test_portfolio_settings_present():
    assert settings.PORTFOLIO_DATA_DIR == "data/portfolio"
    assert settings.PORTFOLIO_DEFAULT_USER_ID == "primary"
    assert settings.PORTFOLIO_MAX_MANAGED_TICKERS == 40
    assert settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY == 4


def test_advisor_settings_present():
    assert settings.ADVISOR_ENABLED is True
    assert settings.ADVISOR_NARRATE is True
    assert settings.ADVISOR_ATR_PERIOD == 20
    assert settings.ADVISOR_STOP_ATR_MULT == 3.0
    assert settings.ADVISOR_TRIM_PROFIT_PCT == 25.0
    assert settings.ADVISOR_MAX_POSITION_PCT == 10.0
    assert settings.ADVISOR_LTCG_WAIT_MIN_MONTHS == 10
    assert settings.ADVISOR_EARNINGS_GAP_DAYS == 3
    assert settings.ADVISOR_REVERSION_PRIOR_ELEVATED == 0.20
    assert settings.ADVISOR_CONFIDENCE_DECLINE_THRESHOLD == 0.05
    assert settings.ADVISOR_ENVELOPE_FLAT_BAND_PCT == 1.0
    assert settings.ADVISOR_ADD_MIN_DIRECTION_ACCURACY == 0.60
    assert settings.ADVISOR_SECTOR_CONCENTRATION_WARN_PCT == 30.0


def test_advisor_stop_buckets_are_tuples():
    buckets = settings.ADVISOR_STOP_BUCKETS
    assert set(buckets) == {"large", "mid", "small"}
    assert buckets["large"] == (8.0, 12.0)
    assert buckets["mid"] == (12.0, 18.0)
    assert buckets["small"] == (15.0, 22.0)
    assert settings.ADVISOR_LARGE_CAP_FLOOR_CR == 65000.0
    assert settings.ADVISOR_MID_CAP_FLOOR_CR == 20000.0
