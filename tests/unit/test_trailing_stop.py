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


from core.portfolio.advisor import AdvisorSignals, decide
from backend.shared.schemas.portfolio import Holding


def _h(**over):
    d = dict(symbol="SUZLON", sector="renewable_energy", qty=100.0,
             avg_buy_price=100.0, adj_avg_price=100.0, adj_qty=100.0,
             buy_date="2026-01-10")
    d.update(over)
    return Holding(**d)


def _sig(**over):
    d = dict(symbol="SUZLON", sector="renewable_energy", close=100.0,
             atr_stop_pct=10.0, unrealised_pnl_pct=0.0, holding_age_days=30)
    d.update(over)
    return AdvisorSignals(**d)


def test_armed_and_giveback_breached_fires_exit():
    # peak 140 (peak_pnl +40% >= arm 10%); close 120 → drawdown 14.3% >= stop 10%
    rec = decide(_sig(close=120.0, unrealised_pnl_pct=20.0,
                      peak_close_since_entry=140.0), _h(), "balanced")
    assert rec.verdict == "EXIT"
    assert "trailing_stop_breach" in rec.triggers


def test_not_armed_below_arm_threshold():
    # peak 105 → peak_pnl +5% < arm 10% → inactive even though drawdown huge
    rec = decide(_sig(close=90.0, unrealised_pnl_pct=-10.0,
                      atr_stop_pct=25.0, peak_close_since_entry=105.0),
                 _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers


def test_armed_but_giveback_within_budget_holds():
    # peak 140; close 133 → drawdown 5% < stop 10%
    rec = decide(_sig(close=133.0, unrealised_pnl_pct=33.0,
                      peak_close_since_entry=140.0), _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers
    assert rec.verdict in ("HOLD", "TRIM", "ADD")


def test_missing_peak_rule_inactive():
    rec = decide(_sig(close=50.0, unrealised_pnl_pct=-50.0,
                      atr_stop_pct=60.0, peak_close_since_entry=None),
                 _h(), "balanced")
    assert "trailing_stop_breach" not in rec.triggers


def test_ltcg_never_softens_trailing_exit():
    # holding ~11 months old (inside the LTCG wait window) — EXIT must survive
    rec = decide(_sig(close=120.0, unrealised_pnl_pct=20.0,
                      peak_close_since_entry=140.0, holding_age_days=340,
                      thesis_intact=True), _h(), "balanced")
    assert rec.verdict == "EXIT"


def test_narrator_has_text_for_trigger():
    from core.portfolio.narrator import _TRIGGER_TEXT
    assert "trailing_stop_breach" in _TRIGGER_TEXT
