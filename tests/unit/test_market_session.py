"""Unit tests for the IST-aware NSE market session resolver.

2026 reference dates used below:
    2026-06-03  Wednesday  — normal trading day
    2026-05-30  Saturday   — weekend
    2026-05-31  Sunday     — weekend
    2026-01-26  Monday     — Republic Day (NSE holiday)
"""
from datetime import datetime

import pytest

from core.intelligence.rl.nse_calendar import market_session


@pytest.mark.parametrize(
    "label, dt, exp_state, exp_live",
    [
        ("pre-market",  datetime(2026, 6, 3, 8, 30), "PRE_MARKET", False),
        ("pre-open",    datetime(2026, 6, 3, 9, 5),  "PRE_OPEN",   False),
        ("just opened", datetime(2026, 6, 3, 9, 16), "OPEN",       True),
        ("midday",      datetime(2026, 6, 3, 13, 0), "OPEN",       True),
        ("after close", datetime(2026, 6, 3, 15, 45),"CLOSED",     False),
        ("at 09:15",    datetime(2026, 6, 3, 9, 15), "OPEN",       True),
        ("at 15:30",    datetime(2026, 6, 3, 15, 30),"CLOSED",     False),
        ("saturday",    datetime(2026, 5, 30, 11, 0),"HOLIDAY",    False),
        ("sunday",      datetime(2026, 5, 31, 11, 0),"HOLIDAY",    False),
        ("republic day",datetime(2026, 1, 26, 11, 0),"HOLIDAY",    False),
    ],
)
def test_session_state(label, dt, exp_state, exp_live):
    s = market_session(dt)
    assert s["state"] == exp_state, f"{label}: {s['state']}"
    assert s["is_live"] is exp_live, f"{label}: live={s['is_live']}"


def test_last_close_day_before_open_is_prior_trading_day():
    # Wednesday pre-market → last settled close is Tuesday 2026-06-02
    s = market_session(datetime(2026, 6, 3, 8, 30))
    assert s["last_close_day"].isoformat() == "2026-06-02"


def test_last_close_day_after_close_is_today():
    s = market_session(datetime(2026, 6, 3, 16, 0))
    assert s["last_close_day"].isoformat() == "2026-06-03"


def test_weekend_last_close_is_friday():
    # Saturday 2026-05-30 → last trading day is Friday 2026-05-29
    s = market_session(datetime(2026, 5, 30, 11, 0))
    assert s["last_close_day"].isoformat() == "2026-05-29"


def test_naive_datetime_treated_as_ist():
    # A naive datetime must be interpreted as IST, not UTC.
    naive = datetime(2026, 6, 3, 13, 0)
    assert market_session(naive)["state"] == "OPEN"
