"""tests/unit/test_equity_curve_labels.py — AUD-089/008 honest equity-curve labels."""
import logging
from datetime import date

import pytest

from core.portfolio.autopilot import record_value_point
from core.portfolio.store import PortfolioStore

D = date(2026, 7, 17)


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    import core.portfolio.autopilot as _ap
    monkeypatch.setattr(_ap, "_today_ist", lambda: D)


def _store_with_history(tmp_path, points):
    s = PortfolioStore(user_id="t", base_dir=str(tmp_path))
    p = s.load()
    p.cash_deployable = 1000.0
    p.capital_in = 1000.0
    s.save(p)
    for pt in points:
        s.append_value_point(pt)
    return s


def test_value_point_records_change_span_days(tmp_path):
    s = _store_with_history(tmp_path, [
        {"date": "2026-07-14", "market_value": 0.0, "cash": 1000.0,
         "total_equity": 1000.0, "capital_in": 1000.0, "day_change_pct": None},
    ])
    pt = record_value_point(s, s.load(), {}, D)
    assert pt["change_span_days"] == 3          # 7/14 -> 7/17 spans 3 days
    assert pt["day_change_pct"] is not None


def test_first_value_point_has_null_span(tmp_path):
    s = _store_with_history(tmp_path, [])
    pt = record_value_point(s, s.load(), {}, D)
    assert pt["change_span_days"] is None


def test_out_of_order_skip_logs(tmp_path, caplog):
    s = _store_with_history(tmp_path, [
        {"date": "2026-07-16", "market_value": 0.0, "cash": 1000.0,
         "total_equity": 1000.0, "capital_in": 1000.0, "day_change_pct": None},
    ])
    with caplog.at_level(logging.INFO):
        assert record_value_point(s, s.load(), {}, date(2026, 7, 15)) is None
    assert any("out-of-order" in r.message for r in caplog.records)
