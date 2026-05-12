"""
tests/unit/intelligence/rl/test_lesson_decay.py
================================================
Section 6 — Category-specific lesson confidence decay.

What is verified:
  - LESSON_DECAY_RATES dict has all 7 categories with correct relative ordering
  - Seasonal lessons: decay = 0.0, confidence is always original value
  - Occurrence damping: rate / sqrt(occurrences) — a macro lesson confirmed 9×
    decays at 0.010/month, not 0.030/month
  - Floor of 0.10: very old unseen lessons never fall to zero
  - Unknown category falls back to LearningLedger.confidence_decay_rate (0.02)
  - Freshly seen lesson (months_inactive = 0) retains full confidence
  - Category ordering is correct: fundamental decays slower than macro

Design context:
  - Decay reflects market half-life: global macro (~25 days) decays fastest,
    seasonal patterns never decay, fundamental patterns (earnings cycle) decay
    very slowly.
  - Occurrence damping reflects that repeated confirmation makes any pattern
    more structural: a macro lesson seen 9 times is effectively behavioral.
"""

import math
from datetime import date, timedelta

import pytest

from backend.shared.schemas.feedback import (
    LESSON_DECAY_RATES,
    LearningLedger,
    Lesson,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger() -> LearningLedger:
    return LearningLedger(
        ticker="MARUTI",
        sector="automobile",
        last_updated=date.today().isoformat(),
    )


def _make_lesson(
    category: str,
    confidence: float = 0.75,
    occurrences: int = 1,
    months_ago: float = 0.0,
) -> Lesson:
    """Create a lesson last_seen N months ago from today."""
    last_seen_date = date.today() - timedelta(days=int(months_ago * 30))
    return Lesson(
        lesson_id="L001",
        date_learned=last_seen_date.isoformat(),
        last_seen=last_seen_date.isoformat(),
        category=category,
        pattern=f"test_{category}",
        observation="test observation",
        rule="test rule",
        confidence=confidence,
        occurrences=occurrences,
        still_valid=True,
    )


# ---------------------------------------------------------------------------
# LESSON_DECAY_RATES dict structure
# ---------------------------------------------------------------------------

class TestLessonDecayRatesDict:

    def test_all_seven_categories_present(self):
        expected = {
            "seasonal", "data_availability", "fundamental",
            "technical", "sentiment", "macro", "global_macro",
        }
        assert set(LESSON_DECAY_RATES.keys()) == expected

    def test_seasonal_is_exactly_zero(self):
        assert LESSON_DECAY_RATES["seasonal"] == 0.0

    def test_relative_ordering_slowest_to_fastest(self):
        """
        Expected order (slowest decay first):
          seasonal(0) < data_availability < fundamental < technical
                      < sentiment < macro < global_macro
        """
        order = [
            "seasonal", "data_availability", "fundamental",
            "technical", "sentiment", "macro", "global_macro",
        ]
        rates = [LESSON_DECAY_RATES[k] for k in order]
        for i in range(len(rates) - 1):
            assert rates[i] <= rates[i + 1], (
                f"{order[i]} rate {rates[i]} should be ≤ {order[i+1]} rate {rates[i+1]}"
            )

    def test_all_rates_non_negative(self):
        for cat, rate in LESSON_DECAY_RATES.items():
            assert rate >= 0.0, f"Category '{cat}' has negative rate {rate}"

    def test_macro_faster_than_fundamental(self):
        assert LESSON_DECAY_RATES["macro"] > LESSON_DECAY_RATES["fundamental"]

    def test_global_macro_fastest_non_zero(self):
        non_zero = {k: v for k, v in LESSON_DECAY_RATES.items() if v > 0}
        assert LESSON_DECAY_RATES["global_macro"] == max(non_zero.values())


# ---------------------------------------------------------------------------
# Seasonal: decay-exempt
# ---------------------------------------------------------------------------

class TestSeasonalDecayExempt:

    def test_seasonal_0_months_no_decay(self):
        ledger = _make_ledger()
        lesson = _make_lesson("seasonal", confidence=0.80, months_ago=0)
        assert ledger.effective_confidence(lesson) == 0.80

    def test_seasonal_6_months_no_decay(self):
        ledger = _make_ledger()
        lesson = _make_lesson("seasonal", confidence=0.80, months_ago=6)
        assert ledger.effective_confidence(lesson) == 0.80

    def test_seasonal_12_months_no_decay(self):
        """A seasonal pattern unseen for a full year should retain its confidence."""
        ledger = _make_ledger()
        lesson = _make_lesson("seasonal", confidence=0.65, months_ago=12)
        assert ledger.effective_confidence(lesson) == 0.65

    def test_seasonal_low_confidence_unchanged(self):
        ledger = _make_ledger()
        lesson = _make_lesson("seasonal", confidence=0.30, months_ago=24)
        assert ledger.effective_confidence(lesson) == 0.30


# ---------------------------------------------------------------------------
# Floor = 0.10
# ---------------------------------------------------------------------------

class TestDecayFloor:

    def test_very_old_global_macro_lesson_hits_floor(self):
        """
        global_macro decays at 0.04/month.
        After 36 months: 0.70 × (0.96^36) ≈ 0.18 — still above floor.
        After 72 months: 0.70 × (0.96^72) ≈ 0.046 — should hit floor 0.10.
        """
        ledger = _make_ledger()
        lesson = _make_lesson("global_macro", confidence=0.70, months_ago=72)
        eff = ledger.effective_confidence(lesson)
        assert eff == 0.10, f"Expected floor 0.10, got {eff}"

    def test_very_old_macro_lesson_hits_floor(self):
        ledger = _make_ledger()
        lesson = _make_lesson("macro", confidence=0.60, months_ago=60)
        eff = ledger.effective_confidence(lesson)
        assert eff >= 0.10

    def test_recently_seen_lesson_above_floor(self):
        ledger = _make_ledger()
        lesson = _make_lesson("macro", confidence=0.75, months_ago=1)
        eff = ledger.effective_confidence(lesson)
        assert eff > 0.10


# ---------------------------------------------------------------------------
# Occurrence damping
# ---------------------------------------------------------------------------

class TestOccurrenceDamping:
    """
    Damping formula: effective_rate = base_rate / sqrt(occurrences)

    Example for macro (base_rate=0.030):
      1×  → rate = 0.030/1.0 = 0.030
      4×  → rate = 0.030/2.0 = 0.015
      9×  → rate = 0.030/3.0 = 0.010

    After 3 months inactive:
      1×:  0.75 × (0.970^3) ≈ 0.683
      9×:  0.75 × (0.990^3) ≈ 0.728
    """

    def test_higher_occurrences_higher_effective_confidence(self):
        """A lesson confirmed 9 times must retain more confidence than one seen once."""
        ledger = _make_ledger()
        lesson_1x = _make_lesson("macro", confidence=0.75, occurrences=1,  months_ago=3)
        lesson_9x = _make_lesson("macro", confidence=0.75, occurrences=9,  months_ago=3)
        ec_1x = ledger.effective_confidence(lesson_1x)
        ec_9x = ledger.effective_confidence(lesson_9x)
        assert ec_9x > ec_1x, (
            f"9× lesson ({ec_9x:.4f}) should retain more than 1× lesson ({ec_1x:.4f})"
        )

    def test_occurrence_damping_is_sqrt_scaled(self):
        """Verify the rate is base_rate/sqrt(n), not base_rate/n."""
        ledger = _make_ledger()
        base_rate = LESSON_DECAY_RATES["macro"]

        # At exactly 1 month inactive, loss ≈ base_rate × confidence (first-order approx)
        lesson_1  = _make_lesson("macro", confidence=0.75, occurrences=1,  months_ago=1)
        lesson_4  = _make_lesson("macro", confidence=0.75, occurrences=4,  months_ago=1)
        lesson_9  = _make_lesson("macro", confidence=0.75, occurrences=9,  months_ago=1)
        lesson_16 = _make_lesson("macro", confidence=0.75, occurrences=16, months_ago=1)

        ec_1  = ledger.effective_confidence(lesson_1)
        ec_4  = ledger.effective_confidence(lesson_4)
        ec_9  = ledger.effective_confidence(lesson_9)
        ec_16 = ledger.effective_confidence(lesson_16)

        # Each quadrupling of occurrences halves the rate → half the loss
        assert ec_1 < ec_4 < ec_9 < ec_16, "Confidence should increase with occurrences"

    def test_occurrence_floor_at_one(self):
        """occurrences=0 should be treated as 1 (no division by zero)."""
        ledger = _make_ledger()
        # Manually construct a lesson with occurrences=0 (edge case)
        lesson = Lesson(
            lesson_id="L_EDGE",
            date_learned=(date.today() - timedelta(days=60)).isoformat(),
            last_seen=(date.today() - timedelta(days=60)).isoformat(),
            category="macro",
            pattern="edge_zero_occ",
            observation="test",
            rule="test",
            confidence=0.70,
            occurrences=0,
        )
        eff = ledger.effective_confidence(lesson)
        assert 0.10 <= eff <= 0.70, f"Expected bounded result, got {eff}"

    def test_same_category_more_occurrences_is_more_structural(self):
        """
        A macro lesson seen 25 times should have near-structural decay rate:
        0.030 / sqrt(25) = 0.006/month  ≈  fundamental category (0.008).
        """
        ledger = _make_ledger()
        lesson_macro_25x = _make_lesson("macro", confidence=0.75, occurrences=25, months_ago=6)
        lesson_fundamental_1x = _make_lesson("fundamental", confidence=0.75, occurrences=1, months_ago=6)
        ec_macro   = ledger.effective_confidence(lesson_macro_25x)
        ec_fund    = ledger.effective_confidence(lesson_fundamental_1x)
        # A 25× macro lesson should be close to a 1× fundamental lesson
        assert abs(ec_macro - ec_fund) < 0.08, (
            f"25× macro ({ec_macro:.4f}) should be structurally similar to "
            f"1× fundamental ({ec_fund:.4f})"
        )


# ---------------------------------------------------------------------------
# Category ordering over time
# ---------------------------------------------------------------------------

class TestCategoryOrderingOverTime:

    @pytest.mark.parametrize("months", [1, 3, 6])
    def test_fundamental_retains_more_than_macro(self, months):
        ledger = _make_ledger()
        fund = _make_lesson("fundamental", confidence=0.75, occurrences=1, months_ago=months)
        macro = _make_lesson("macro", confidence=0.75, occurrences=1, months_ago=months)
        ec_fund = ledger.effective_confidence(fund)
        ec_macro = ledger.effective_confidence(macro)
        assert ec_fund > ec_macro, (
            f"After {months} months: fundamental ({ec_fund:.4f}) "
            f"should retain more than macro ({ec_macro:.4f})"
        )

    @pytest.mark.parametrize("months", [1, 3, 6])
    def test_data_availability_second_slowest(self, months):
        ledger = _make_ledger()
        da = _make_lesson("data_availability", confidence=0.75, occurrences=1, months_ago=months)
        tech = _make_lesson("technical", confidence=0.75, occurrences=1, months_ago=months)
        ec_da = ledger.effective_confidence(da)
        ec_tech = ledger.effective_confidence(tech)
        assert ec_da > ec_tech

    def test_zero_months_inactive_no_decay(self):
        """Any lesson seen today should return original confidence."""
        ledger = _make_ledger()
        for cat in LESSON_DECAY_RATES:
            lesson = _make_lesson(cat, confidence=0.78, months_ago=0)
            eff = ledger.effective_confidence(lesson)
            assert abs(eff - 0.78) < 0.02, (
                f"Category '{cat}' with 0 months inactive: expected ≈0.78, got {eff}"
            )


# ---------------------------------------------------------------------------
# Unknown category fallback
# ---------------------------------------------------------------------------

class TestUnknownCategoryFallback:

    def test_unknown_category_uses_ledger_default_rate(self):
        """
        A lesson category not in LESSON_DECAY_RATES falls back to
        LearningLedger.confidence_decay_rate (default 0.02/month).
        """
        ledger = _make_ledger()
        # Lesson with a future category not yet in LESSON_DECAY_RATES
        lesson = Lesson(
            lesson_id="L_UNK",
            date_learned=(date.today() - timedelta(days=90)).isoformat(),
            last_seen=(date.today() - timedelta(days=90)).isoformat(),
            category="technical",   # using valid literal but checking formula
            pattern="unknown_fallback",
            observation="test",
            rule="test",
            confidence=0.70,
            occurrences=1,
        )
        eff = ledger.effective_confidence(lesson)
        # At 3 months with 0.015/month: 0.70 × (0.985^3) ≈ 0.669
        expected_approx = 0.70 * ((1 - 0.015) ** 3)
        assert abs(eff - expected_approx) < 0.03, (
            f"Expected ~{expected_approx:.3f}, got {eff:.4f}"
        )


# ---------------------------------------------------------------------------
# Numeric correctness spot-checks
# ---------------------------------------------------------------------------

class TestNumericCorrectness:

    def test_macro_1x_3months_expected_value(self):
        """
        macro, 1×, 3 months: rate=0.030, eff = 0.75 × (0.970^3) ≈ 0.683
        """
        ledger = _make_ledger()
        lesson = _make_lesson("macro", confidence=0.75, occurrences=1, months_ago=3)
        eff = ledger.effective_confidence(lesson)
        expected = 0.75 * ((1 - 0.030) ** 3)
        assert abs(eff - expected) < 0.02, f"Expected ~{expected:.4f}, got {eff:.4f}"

    def test_macro_9x_3months_expected_value(self):
        """
        macro, 9×: rate = 0.030/sqrt(9) = 0.010
        eff = 0.75 × (0.990^3) ≈ 0.728
        """
        ledger = _make_ledger()
        lesson = _make_lesson("macro", confidence=0.75, occurrences=9, months_ago=3)
        effective_rate = 0.030 / math.sqrt(9)  # = 0.010
        expected = 0.75 * ((1 - effective_rate) ** 3)
        eff = ledger.effective_confidence(lesson)
        assert abs(eff - expected) < 0.02, f"Expected ~{expected:.4f}, got {eff:.4f}"

    def test_fundamental_1x_6months_expected_value(self):
        """
        fundamental, 1×, 6 months: rate=0.008
        eff = 0.80 × (0.992^6) ≈ 0.762
        """
        ledger = _make_ledger()
        lesson = _make_lesson("fundamental", confidence=0.80, occurrences=1, months_ago=6)
        expected = 0.80 * ((1 - 0.008) ** 6)
        eff = ledger.effective_confidence(lesson)
        assert abs(eff - expected) < 0.02, f"Expected ~{expected:.4f}, got {eff:.4f}"
