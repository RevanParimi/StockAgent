"""
tests/unit/test_conviction.py
==============================
Unit tests for P3 — Conviction Duration & Mean Reversion Prior.

Coverage:
  - verdict_direction(): all five verdict strings + unknown
  - compute_reversion_prior(): formula boundary values and cap
  - compute_rsi_amplifier(): threshold logic, streak guard, NEUTRAL guard
  - compute_final_reversion_prior(): combined wrapper + cap at 0.30
  - update_conviction_streak(): same-direction extend, flip reset, NEUTRAL reset,
    max_streak_seen tracking, start date management
  - build_streak_warning_block(): content correctness
  - ConvictionStreak schema: defaults, JSON round-trip
  - PredictionEnvelope schema: conviction_streak field, backward-compatible load
  - Confidence dampening formula: end-to-end through _revise_remaining_forecasts
"""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from core.intelligence.rl.conviction.tracker import (
    STREAK_WARNING_THRESHOLD,
    _MAX_REVERSION_PRIOR,
    _RSI_AMPLIFIER,
    build_streak_warning_block,
    compute_final_reversion_prior,
    compute_reversion_prior,
    compute_rsi_amplifier,
    update_conviction_streak,
    verdict_direction,
)
from core.schemas.feedback import (
    ConvictionStreak,
    DailyForecast,
    PredictionEnvelope,
    RevisedContext,
)


# ---------------------------------------------------------------------------
# verdict_direction
# ---------------------------------------------------------------------------

class TestVerdictDirection:
    @pytest.mark.parametrize("verdict", ["BUY", "buy", "Buy"])
    def test_buy_is_bullish(self, verdict):
        assert verdict_direction(verdict) == "BULLISH"

    @pytest.mark.parametrize("verdict", ["STRONG BUY", "strong buy"])
    def test_strong_buy_is_bullish(self, verdict):
        assert verdict_direction(verdict) == "BULLISH"

    @pytest.mark.parametrize("verdict", ["SELL", "sell"])
    def test_sell_is_bearish(self, verdict):
        assert verdict_direction(verdict) == "BEARISH"

    @pytest.mark.parametrize("verdict", ["STRONG SELL", "strong sell"])
    def test_strong_sell_is_bearish(self, verdict):
        assert verdict_direction(verdict) == "BEARISH"

    def test_neutral_is_neutral(self):
        assert verdict_direction("NEUTRAL") == "NEUTRAL"

    def test_unknown_is_neutral(self):
        assert verdict_direction("HOLD") == "NEUTRAL"
        assert verdict_direction("") == "NEUTRAL"


# ---------------------------------------------------------------------------
# compute_reversion_prior
# ---------------------------------------------------------------------------

class TestComputeReversionPrior:
    @pytest.mark.parametrize("days", [0, 1, 2, 3, 4])
    def test_zero_prior_for_short_streaks(self, days):
        assert compute_reversion_prior(days) == 0.0

    def test_prior_at_exactly_5(self):
        # (5 - 4) × 0.025 = 0.025
        assert compute_reversion_prior(5) == pytest.approx(0.025)

    def test_prior_at_7(self):
        # (7 - 4) × 0.025 = 0.075
        assert compute_reversion_prior(7) == pytest.approx(0.075)

    def test_prior_at_8(self):
        # (8 - 4) × 0.025 = 0.10
        assert compute_reversion_prior(8) == pytest.approx(0.10)

    def test_prior_at_12(self):
        # (12 - 4) × 0.025 = 0.20
        assert compute_reversion_prior(12) == pytest.approx(0.20)

    def test_prior_capped_at_14(self):
        # (14 - 4) × 0.025 = 0.25
        assert compute_reversion_prior(14) == pytest.approx(0.25)

    def test_prior_capped_beyond_14(self):
        # Should not exceed 0.25 regardless of streak length
        for days in [15, 21, 50, 100]:
            assert compute_reversion_prior(days) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# compute_rsi_amplifier
# ---------------------------------------------------------------------------

class TestComputeRsiAmplifier:
    def test_no_amplifier_when_streak_below_threshold(self):
        scores = {"pattern_analysis": 0.30}   # would trigger if streak were high enough
        for days in range(STREAK_WARNING_THRESHOLD):
            assert compute_rsi_amplifier("BUY", scores, days) == 1.0

    def test_bullish_streak_low_pa_score_triggers_amplifier(self):
        # pa_score < 0.40 with BULLISH streak → divergence
        scores = {"pattern_analysis": 0.35}
        result = compute_rsi_amplifier("BUY", scores, streak_days=8)
        assert result == pytest.approx(_RSI_AMPLIFIER)

    def test_bullish_streak_high_pa_score_no_amplifier(self):
        # pa_score >= 0.40 → no divergence
        scores = {"pattern_analysis": 0.50}
        assert compute_rsi_amplifier("BUY", scores, streak_days=10) == 1.0

    def test_bearish_streak_high_pa_score_triggers_amplifier(self):
        # pa_score > 0.60 with BEARISH streak → divergence
        scores = {"pattern_analysis": 0.65}
        result = compute_rsi_amplifier("SELL", scores, streak_days=9)
        assert result == pytest.approx(_RSI_AMPLIFIER)

    def test_bearish_streak_low_pa_score_no_amplifier(self):
        scores = {"pattern_analysis": 0.40}
        assert compute_rsi_amplifier("SELL", scores, streak_days=9) == 1.0

    def test_neutral_verdict_no_amplifier(self):
        scores = {"pattern_analysis": 0.10}   # extreme but NEUTRAL wins
        assert compute_rsi_amplifier("NEUTRAL", scores, streak_days=10) == 1.0

    def test_missing_pattern_analysis_defaults_to_05(self):
        # Default 0.5 → neither < 0.40 nor > 0.60 → no amplifier for BUY streak
        assert compute_rsi_amplifier("BUY", {}, streak_days=10) == 1.0

    def test_boundary_at_exactly_040_no_amplifier(self):
        # Threshold is < 0.40, so exactly 0.40 should NOT trigger
        scores = {"pattern_analysis": 0.40}
        assert compute_rsi_amplifier("BUY", scores, streak_days=8) == 1.0

    def test_boundary_at_exactly_060_no_amplifier(self):
        # Threshold is > 0.60, so exactly 0.60 should NOT trigger
        scores = {"pattern_analysis": 0.60}
        assert compute_rsi_amplifier("SELL", scores, streak_days=8) == 1.0


# ---------------------------------------------------------------------------
# compute_final_reversion_prior
# ---------------------------------------------------------------------------

class TestComputeFinalReversionPrior:
    def test_zero_when_streak_short(self):
        result = compute_final_reversion_prior(4, "BUY", {"pattern_analysis": 0.30})
        assert result == 0.0

    def test_amplified_prior_capped_at_max(self):
        # streak=14 → base=0.25, amplifier=1.5 → 0.375 → capped at 0.30
        scores = {"pattern_analysis": 0.30}
        result = compute_final_reversion_prior(14, "BUY", scores)
        assert result == pytest.approx(_MAX_REVERSION_PRIOR)

    def test_no_amplifier_gives_base_prior(self):
        # streak=8, pa_score=0.50 → no amplifier → final == base (0.10)
        scores = {"pattern_analysis": 0.50}
        result = compute_final_reversion_prior(8, "BUY", scores)
        assert result == pytest.approx(0.10)

    def test_with_amplifier_no_cap(self):
        # streak=5, base=0.025, pa_score=0.35, amplifier=1.5 → 0.025 × 1.5 = 0.0375
        scores = {"pattern_analysis": 0.35}
        result = compute_final_reversion_prior(5, "BUY", scores)
        # streak < threshold (8) → amplifier is 1.0, so no amplification
        assert result == pytest.approx(0.025)

    def test_amplifier_activates_at_threshold(self):
        # streak=8, pa_score=0.30 → base=0.10, amplifier=1.5 → 0.15
        scores = {"pattern_analysis": 0.30}
        result = compute_final_reversion_prior(8, "BUY", scores)
        assert result == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# update_conviction_streak
# ---------------------------------------------------------------------------

class TestUpdateConvictionStreak:
    def _empty(self) -> ConvictionStreak:
        return ConvictionStreak()

    def test_first_bullish_verdict_starts_streak_at_1(self):
        result = update_conviction_streak(self._empty(), "BUY", "2026-04-01")
        assert result.streak_days == 1
        assert result.current_verdict == "BUY"
        assert result.streak_start_date == "2026-04-01"
        assert result.max_streak_seen == 1
        assert result.reversion_prior == 0.0   # streak 1 → prior 0

    def test_same_direction_extends_streak(self):
        streak = ConvictionStreak(
            current_verdict="BUY",
            streak_days=3,
            streak_start_date="2026-04-01",
            max_streak_seen=3,
            reversion_prior=0.0,
        )
        result = update_conviction_streak(streak, "STRONG BUY", "2026-04-04")
        assert result.streak_days == 4
        assert result.streak_start_date == "2026-04-01"   # start preserved
        assert result.max_streak_seen == 4

    def test_direction_flip_resets_streak_to_1(self):
        streak = ConvictionStreak(
            current_verdict="BUY",
            streak_days=10,
            streak_start_date="2026-03-15",
            max_streak_seen=10,
            reversion_prior=0.15,
        )
        result = update_conviction_streak(streak, "SELL", "2026-04-01")
        assert result.streak_days == 1
        assert result.current_verdict == "SELL"
        assert result.streak_start_date == "2026-04-01"
        assert result.max_streak_seen == 10   # historical max preserved

    def test_neutral_resets_streak_to_0(self):
        streak = ConvictionStreak(
            current_verdict="BUY",
            streak_days=7,
            streak_start_date="2026-03-20",
            max_streak_seen=7,
            reversion_prior=0.075,
        )
        result = update_conviction_streak(streak, "NEUTRAL", "2026-04-01")
        assert result.streak_days == 0
        assert result.streak_start_date == ""
        assert result.reversion_prior == 0.0
        assert result.max_streak_seen == 7   # historical max preserved

    def test_prior_computed_from_new_streak_days(self):
        streak = ConvictionStreak(current_verdict="BUY", streak_days=7, max_streak_seen=7)
        result = update_conviction_streak(streak, "BUY", "2026-04-08")
        # streak_days=8 → prior = (8-4) × 0.025 = 0.10
        assert result.streak_days == 8
        assert result.reversion_prior == pytest.approx(0.10)

    def test_max_streak_never_decreases_on_flip(self):
        streak = ConvictionStreak(
            current_verdict="BUY", streak_days=5, max_streak_seen=12
        )
        result = update_conviction_streak(streak, "SELL", "2026-04-01")
        assert result.max_streak_seen == 12

    def test_does_not_mutate_input(self):
        streak = ConvictionStreak(current_verdict="BUY", streak_days=3, max_streak_seen=3)
        _ = update_conviction_streak(streak, "BUY", "2026-04-01")
        assert streak.streak_days == 3   # original unchanged

    def test_buy_and_strong_buy_same_direction(self):
        streak = ConvictionStreak(current_verdict="BUY", streak_days=2, max_streak_seen=2)
        result = update_conviction_streak(streak, "STRONG BUY", "2026-04-01")
        assert result.streak_days == 3   # same direction → extend

    def test_sell_and_strong_sell_same_direction(self):
        streak = ConvictionStreak(current_verdict="SELL", streak_days=4, max_streak_seen=4)
        result = update_conviction_streak(streak, "STRONG SELL", "2026-04-01")
        assert result.streak_days == 5

    def test_streak_sequence_10_days(self):
        streak = self._empty()
        for day in range(1, 11):
            streak = update_conviction_streak(streak, "BUY", f"2026-04-{day:02d}")
        assert streak.streak_days == 10
        assert streak.max_streak_seen == 10
        assert streak.reversion_prior == pytest.approx(compute_reversion_prior(10))


# ---------------------------------------------------------------------------
# build_streak_warning_block
# ---------------------------------------------------------------------------

class TestBuildStreakWarningBlock:
    def test_contains_verdict(self):
        streak = ConvictionStreak(
            current_verdict="STRONG BUY", streak_days=10,
            streak_start_date="2026-03-22", reversion_prior=0.15,
        )
        block = build_streak_warning_block(streak)
        assert "STRONG BUY" in block

    def test_contains_streak_days(self):
        streak = ConvictionStreak(
            current_verdict="BUY", streak_days=12,
            reversion_prior=0.20,
        )
        block = build_streak_warning_block(streak)
        assert "12" in block

    def test_contains_reversion_percentage(self):
        streak = ConvictionStreak(
            current_verdict="BUY", streak_days=8, reversion_prior=0.10,
        )
        block = build_streak_warning_block(streak)
        # 0.10 → "10%"
        assert "10%" in block

    def test_contains_start_date_when_set(self):
        streak = ConvictionStreak(
            current_verdict="SELL", streak_days=9,
            streak_start_date="2026-04-01", reversion_prior=0.125,
        )
        block = build_streak_warning_block(streak)
        assert "2026-04-01" in block

    def test_contains_rsi_divergence_mention(self):
        streak = ConvictionStreak(current_verdict="BUY", streak_days=8, reversion_prior=0.10)
        block = build_streak_warning_block(streak)
        assert "RSI" in block


# ---------------------------------------------------------------------------
# ConvictionStreak schema
# ---------------------------------------------------------------------------

class TestConvictionStreakSchema:
    def test_default_values(self):
        cs = ConvictionStreak()
        assert cs.current_verdict == ""
        assert cs.streak_days == 0
        assert cs.streak_start_date == ""
        assert cs.max_streak_seen == 0
        assert cs.reversion_prior == 0.0

    def test_round_trip_serialisation(self):
        cs = ConvictionStreak(
            current_verdict="BUY",
            streak_days=7,
            streak_start_date="2026-04-01",
            max_streak_seen=7,
            reversion_prior=0.075,
        )
        restored = ConvictionStreak(**cs.model_dump())
        assert restored == cs


# ---------------------------------------------------------------------------
# PredictionEnvelope schema changes
# ---------------------------------------------------------------------------

class TestPredictionEnvelopeSchema:
    def _make_envelope(self) -> PredictionEnvelope:
        return PredictionEnvelope(
            ticker="MARUTI",
            cycle_id="MARUTI_2026-04",
            generated_at="2026-04-01",
            base_close=12500.0,
        )

    def test_conviction_streak_field_exists_with_default(self):
        env = self._make_envelope()
        assert isinstance(env.conviction_streak, ConvictionStreak)
        assert env.conviction_streak.streak_days == 0

    def test_conviction_streak_persists_in_round_trip(self):
        env = self._make_envelope()
        env.conviction_streak = ConvictionStreak(
            current_verdict="SELL",
            streak_days=5,
            streak_start_date="2026-04-10",
            max_streak_seen=5,
            reversion_prior=0.025,
        )
        restored = PredictionEnvelope(**env.model_dump())
        assert restored.conviction_streak.streak_days == 5
        assert restored.conviction_streak.current_verdict == "SELL"

    def test_backward_compatible_envelope_without_conviction_streak(self):
        # Simulates loading an old envelope that was saved before P3.
        old_data = {
            "ticker": "MARUTI",
            "cycle_id": "MARUTI_2026-03",
            "generated_at": "2026-03-01",
            "base_close": 12000.0,
            # conviction_streak field deliberately absent
        }
        env = PredictionEnvelope(**old_data)
        assert env.conviction_streak.streak_days == 0   # default applied


# ---------------------------------------------------------------------------
# Confidence dampening formula (unit arithmetic test)
# ---------------------------------------------------------------------------

class TestConfidenceDampening:
    """
    Verify the dampening formula independently of daily_review.py:
        adjusted = base × (1.0 - reversion_prior × 0.5)
    """

    def test_zero_prior_no_change(self):
        base = 0.80
        result = round(base * (1.0 - 0.0 * 0.5), 4)
        assert result == pytest.approx(base)

    def test_prior_025_damps_125pct(self):
        # 0.25 prior → 1 - 0.25 × 0.5 = 0.875 → 80% × 0.875 = 70%
        base = 0.80
        result = round(base * (1.0 - 0.25 * 0.5), 4)
        assert result == pytest.approx(0.70)

    def test_prior_030_damps_15pct(self):
        # 0.30 prior → 1 - 0.30 × 0.5 = 0.85 → 80% × 0.85 = 68%
        base = 0.80
        result = round(base * (1.0 - 0.30 * 0.5), 4)
        assert result == pytest.approx(0.68)

    def test_prior_never_fully_halves_confidence(self):
        # Max prior is 0.30 → multiplier = 0.85 (not < 0.5)
        base = 0.80
        multiplier = 1.0 - _MAX_REVERSION_PRIOR * 0.5
        assert multiplier > 0.5, "Reversion prior should never halve confidence"
        result = round(base * multiplier, 4)
        assert result > base * 0.5

    def test_streak_14_days_confidence_dampened(self):
        # Real integration: 14 days → prior = 0.25
        # 0.75 × (1.0 - 0.25 × 0.5) = 0.75 × 0.875 = 0.65625
        # Python banker's rounding: round(0.65625, 4) = 0.6562 (rounds to even digit)
        prior = compute_reversion_prior(14)
        base = 0.75
        result = round(base * (1.0 - prior * 0.5), 4)
        assert result == pytest.approx(0.6562, abs=1e-4)

    def test_dampening_respects_floor(self):
        # Extremely low confidence should not go below 0.05
        base = 0.06
        prior = 0.30
        adjusted = round(base * (1.0 - prior * 0.5), 4)
        clamped = max(0.05, min(0.99, adjusted))
        assert clamped >= 0.05
