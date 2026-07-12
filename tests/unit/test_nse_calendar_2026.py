"""Audit Wave 1 (AUD-023) — 2026 NSE holiday calendar correctness.

Official 2026 NSE equity trading holidays (exchange circular; verified
2026-07-12): Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3, Apr 14, May 1,
May 28, Jun 26, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25
(+ Aug 15 falls on a Saturday; Nov 8 Muhurat session is a Sunday).
"""
import json
from datetime import date

import pytest

import core.intelligence.rl.nse_calendar as cal


OFFICIAL_2026_WEEKDAY_HOLIDAYS = [
    date(2026, 1, 15), date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 5, 28), date(2026, 6, 26), date(2026, 9, 14), date(2026, 10, 2),
    date(2026, 10, 20), date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
]

# The old preliminary fallback wrongly marked these REAL trading days as holidays.
FALSE_HOLIDAYS_REMOVED = [date(2026, 3, 4), date(2026, 3, 20)]


@pytest.fixture
def _isolated_holiday_file(tmp_path, monkeypatch):
    """Point the module at a temp holiday file and restore the real set after."""
    monkeypatch.setattr(cal, "_HOLIDAY_FILE", tmp_path / "nse_holidays.json")
    yield tmp_path / "nse_holidays.json"
    monkeypatch.undo()
    cal.reload_holidays()


def test_official_2026_weekday_holidays_are_holidays(_isolated_holiday_file):
    cal.reload_holidays()          # no file → hardcoded fallback only
    for d in OFFICIAL_2026_WEEKDAY_HOLIDAYS:
        assert not cal.is_trading_day(d), f"{d} must be an NSE holiday"


def test_false_preliminary_holidays_are_trading_days(_isolated_holiday_file):
    cal.reload_holidays()
    for d in FALSE_HOLIDAYS_REMOVED:
        assert cal.is_trading_day(d), f"{d} was a real trading session"


def test_file_and_hardcoded_merge_as_union(_isolated_holiday_file):
    """A yfinance-built file year only knows holidays up to its creation date —
    hardcoded FUTURE dates must survive the merge (union, not file-wins)."""
    _isolated_holiday_file.write_text(
        json.dumps({"2026": ["2026-01-15", "2026-01-26"]}), encoding="utf-8")
    cal.reload_holidays()
    assert not cal.is_trading_day(date(2026, 11, 24)), \
        "hardcoded Guru Nanak holiday lost to a partial file year"
    assert not cal.is_trading_day(date(2026, 1, 15))


def test_loader_skips_meta_and_malformed_keys(_isolated_holiday_file):
    _isolated_holiday_file.write_text(
        json.dumps({"_meta": {"source": "test"}, "2026": ["2026-01-15"],
                    "2027": "not-a-list"}), encoding="utf-8")
    cal.reload_holidays()          # must not raise
    assert not cal.is_trading_day(date(2026, 1, 15))
