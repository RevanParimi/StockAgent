"""Compass Phase A — deterministic advisor: EXIT > TRIM > ADD > HOLD."""
from datetime import date

import pytest

from backend.shared.schemas.portfolio import Holding
from core.portfolio.advisor import (
    AdvisorSignals,
    compute_stop_pct,
    decide,
    resolve_cap_bucket,
)

REVIEW_DATE = date(2026, 7, 6)


def _holding(buy_date="2026-01-05") -> Holding:
    return Holding(
        symbol="MARUTI", sector="automobile", qty=10, avg_buy_price=12000.0,
        adj_avg_price=12000.0, adj_qty=10, buy_date=buy_date,
    )


def _signals(**kw) -> AdvisorSignals:
    base = dict(
        symbol="MARUTI", sector="automobile", close=13000.0,
        atr_stop_pct=10.0, unrealised_pnl_pct=8.0, holding_age_days=180,
    )
    base.update(kw)
    return AdvisorSignals(**base)


# ── Stop scaling ────────────────────────────────────────────────────────────

def test_stop_clamped_to_bucket():
    # 3 × 5% ATR = 15% > large-cap cap 12% -> clamped
    assert compute_stop_pct(5.0, "large", "balanced") == 12.0
    # 3 × 1% = 3% < large floor 8% -> floored
    assert compute_stop_pct(1.0, "large", "balanced") == 8.0
    # mid bucket passes through inside band
    assert compute_stop_pct(5.0, "mid", "balanced") == 15.0


def test_conservative_tightens_one_notch():
    # small bucket (15-22) tightened to mid (12-18): 3×7%=21 -> capped 18
    assert compute_stop_pct(7.0, "small", "conservative") == 18.0


def test_cap_bucket_resolution():
    assert resolve_cap_bucket(70000 * 1e7) == "large"     # ₹70,000 cr
    assert resolve_cap_bucket(30000 * 1e7) == "mid"
    assert resolve_cap_bucket(5000 * 1e7) == "small"
    assert resolve_cap_bucket(None) == "mid"


# ── EXIT rules (highest precedence) ────────────────────────────────────────

def test_exit_on_stop_breach():
    rec = decide(_signals(unrealised_pnl_pct=-12.0, atr_stop_pct=10.0), _holding(), "balanced")
    assert rec.verdict == "EXIT"
    assert "stop_breach" in rec.triggers


def test_exit_on_thesis_break_against_position():
    rec = decide(
        _signals(thesis_intact=False, envelope_direction="DOWN"),
        _holding(), "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "thesis_break" in rec.triggers


def test_exit_on_crisis_regime_bearish():
    rec = decide(
        _signals(regime_label="MACRO_CRISIS", envelope_direction="DOWN"),
        _holding(), "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "crisis_regime_bearish" in rec.triggers


def test_exit_outranks_trim_even_with_ltcg_window():
    # 11-month-old profitable position breaching stop: EXIT, never WAIT_FOR_LTCG
    h = _holding(buy_date="2025-08-06")
    rec = decide(
        _signals(unrealised_pnl_pct=-15.0, atr_stop_pct=10.0, holding_age_days=334),
        h, "balanced",
    )
    assert rec.verdict == "EXIT"
    assert "WAIT_FOR_LTCG" not in rec.notes


# ── TRIM rules ──────────────────────────────────────────────────────────────

def test_trim_on_profit_with_confidence_decline():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10),
        _holding(), "balanced",
    )
    assert rec.verdict == "TRIM"
    assert "trim_profit_confidence_decline" in rec.triggers


def test_trim_on_profit_with_elevated_reversion():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, reversion_prior=0.25),
        _holding(), "balanced",
    )
    assert rec.verdict == "TRIM"


def test_no_trim_below_profit_threshold():
    rec = decide(
        _signals(unrealised_pnl_pct=10.0, confidence_trend=-0.10),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


def test_trim_softened_to_wait_for_ltcg():
    # age 320 days (~10.7 months), thesis intact -> HOLD + WAIT_FOR_LTCG note
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10,
                 holding_age_days=320, thesis_intact=True),
        _holding(buy_date="2025-08-20"), "balanced",
    )
    assert rec.verdict == "HOLD"
    assert "WAIT_FOR_LTCG" in rec.notes


def test_trim_not_softened_past_12_months():
    rec = decide(
        _signals(unrealised_pnl_pct=30.0, confidence_trend=-0.10,
                 holding_age_days=400, thesis_intact=True),
        _holding(buy_date="2025-06-01"), "balanced",
    )
    assert rec.verdict == "TRIM"


# ── ADD rules ───────────────────────────────────────────────────────────────

def test_add_when_bullish_and_healthy():
    rec = decide(
        _signals(envelope_direction="UP", regime_label="NORMAL",
                 direction_accuracy_7d=0.7, position_weight_pct=5.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "ADD"
    assert "add_bullish_healthy" in rec.triggers


def test_no_add_when_position_at_max_weight():
    rec = decide(
        _signals(envelope_direction="UP", direction_accuracy_7d=0.7,
                 position_weight_pct=12.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


def test_no_add_in_risk_off_regime():
    rec = decide(
        _signals(envelope_direction="UP", regime_label="RISK_OFF",
                 direction_accuracy_7d=0.7, position_weight_pct=5.0),
        _holding(), "balanced",
    )
    assert rec.verdict == "HOLD"


# ── Annotations ─────────────────────────────────────────────────────────────

def test_earnings_gap_note_on_profitable_position():
    rec = decide(
        _signals(unrealised_pnl_pct=8.0, earnings_in_days=2),
        _holding(), "balanced",
    )
    assert "EARNINGS_GAP_PROTECTION" in rec.notes


def test_no_earnings_note_when_far():
    rec = decide(
        _signals(unrealised_pnl_pct=8.0, earnings_in_days=10),
        _holding(), "balanced",
    )
    assert "EARNINGS_GAP_PROTECTION" not in rec.notes


def test_advice_record_has_hash_and_date():
    rec = decide(_signals(), _holding(), "balanced")
    assert rec.rationale_hash != ""
    assert rec.verdict == "HOLD"
    assert rec.symbol == "MARUTI"
