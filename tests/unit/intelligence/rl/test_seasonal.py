"""
tests/unit/test_seasonal.py
============================
Unit tests for the SeasonalCalendar and SeasonalValidator.

Coverage:
  - Seed loading from YAML for all 4 sectors
  - Pattern activation logic (month, day_range, lunar_dependency)
  - Agent adjustment merging and capping
  - Confidence modifier calculation
  - Narrative construction
  - Neutral context when no patterns active
  - Validator: hit/miss tracking, thresholds, persistence
  - Schema: SeasonalPattern and SeasonalContext Pydantic models
"""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from core.intelligence.seasonal.calendar import SeasonalCalendar, MAX_AGENT_DELTA
from core.intelligence.seasonal.validator import (
    SeasonalValidator,
    PatternValidationRecord,
)
from core.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackEntry,
    LearningLedger,
    Lesson,
    MissAnalysis,
    SeasonalContext,
    SeasonalPattern,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_seed_cache():
    """Clear the class-level seed cache before every test."""
    SeasonalCalendar.clear_cache()
    yield
    SeasonalCalendar.clear_cache()


@pytest.fixture
def auto_calendar():
    return SeasonalCalendar("automobile")


@pytest.fixture
def empty_ledger():
    return LearningLedger(ticker="MARUTI", last_updated="2026-01-01")


@pytest.fixture
def ledger_with_seasonal_lesson():
    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-01-01")
    ledger.lessons.append(Lesson(
        lesson_id="L001",
        date_learned="2026-01-01",
        category="seasonal",
        pattern="december_oem_discounts_confirmed",
        observation="December discounts drove margin miss",
        rule="Discount fundamentals in December",
        confidence=0.70,
        occurrences=2,
        still_valid=True,
        scope="stock_specific",
        last_seen="2026-01-01",
    ))
    return ledger


# ---------------------------------------------------------------------------
# 1. Seed loading
# ---------------------------------------------------------------------------

class TestSeedLoading:
    def test_automobile_seeds_load(self, auto_calendar):
        assert len(auto_calendar._patterns) > 0, "automobile seeds must load"

    def test_all_sectors_load_without_error(self):
        for sector in ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]:
            cal = SeasonalCalendar(sector)
            # Seeds exist for all sectors; no sector should be empty
            assert len(cal._patterns) > 0, f"{sector} seeds must not be empty"

    def test_unknown_sector_returns_empty(self):
        cal = SeasonalCalendar("unknown_sector")
        assert cal._patterns == []

    def test_patterns_are_seasonal_pattern_instances(self, auto_calendar):
        for p in auto_calendar._patterns:
            assert isinstance(p, SeasonalPattern)

    def test_automobile_has_december_pattern(self, auto_calendar):
        ids = [p.id for p in auto_calendar._patterns]
        assert "SEA_AUTO_001" in ids

    def test_automobile_has_festive_pattern(self, auto_calendar):
        ids = [p.id for p in auto_calendar._patterns]
        assert "SEA_AUTO_002" in ids

    def test_seed_cache_is_reused(self):
        cal1 = SeasonalCalendar("automobile")
        cal2 = SeasonalCalendar("automobile")
        assert cal1._patterns is cal2._patterns, "cache must return same list object"

    def test_confidence_values_in_bounds(self, auto_calendar):
        for p in auto_calendar._patterns:
            assert 0.0 <= p.confidence <= 1.0, f"{p.id} confidence out of bounds"

    def test_agent_deltas_within_max(self, auto_calendar):
        for p in auto_calendar._patterns:
            for agent, delta in p.agents_affected.items():
                assert abs(delta) <= MAX_AGENT_DELTA, (
                    f"{p.id}.{agent} delta {delta} exceeds ±{MAX_AGENT_DELTA}"
                )


# ---------------------------------------------------------------------------
# 2. Pattern activation — month and day_range
# ---------------------------------------------------------------------------

class TestPatternActivation:
    def test_december_pattern_active_in_december(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 12, 15))
        ids = [p.id for p in active]
        assert "SEA_AUTO_001" in ids

    def test_december_pattern_not_active_in_november(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 11, 15))
        ids = [p.id for p in active]
        assert "SEA_AUTO_001" not in ids

    def test_festive_pattern_active_in_october(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 10, 20))
        ids = [p.id for p in active]
        assert "SEA_AUTO_002" in ids

    def test_festive_pattern_active_in_november(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 11, 5))
        ids = [p.id for p in active]
        assert "SEA_AUTO_002" in ids

    def test_budget_week_pattern_only_in_day_range(self, auto_calendar):
        # SEA_AUTO_005: months=[1], day_range=[22, 31]
        active_in_range = auto_calendar.active_patterns_on(date(2026, 1, 25))
        active_out_range = auto_calendar.active_patterns_on(date(2026, 1, 10))
        in_ids  = [p.id for p in active_in_range]
        out_ids = [p.id for p in active_out_range]
        assert "SEA_AUTO_005" in in_ids
        assert "SEA_AUTO_005" not in out_ids

    def test_day_range_boundary_inclusive(self, auto_calendar):
        # day_range=[22, 31] — test both boundaries
        start = auto_calendar.active_patterns_on(date(2026, 1, 22))
        end   = auto_calendar.active_patterns_on(date(2026, 1, 31))
        assert any(p.id == "SEA_AUTO_005" for p in start)
        assert any(p.id == "SEA_AUTO_005" for p in end)

    def test_march_pattern_active_in_march(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 3, 10))
        ids = [p.id for p in active]
        assert "SEA_AUTO_004" in ids

    def test_shravan_pattern_active_in_july(self, auto_calendar):
        active = auto_calendar.active_patterns_on(date(2026, 7, 20))
        ids = [p.id for p in active]
        assert "SEA_AUTO_003" in ids

    def test_no_patterns_in_april(self, auto_calendar):
        """April has no automobile seed patterns."""
        active = auto_calendar.active_patterns_on(date(2026, 4, 15))
        assert active == []

    def test_patterns_for_month_returns_correct_subset(self, auto_calendar):
        dec_patterns = auto_calendar.patterns_for_month(12)
        assert all(12 in p.months for p in dec_patterns)
        assert len(dec_patterns) >= 1


# ---------------------------------------------------------------------------
# 3. SeasonalContext assembly
# ---------------------------------------------------------------------------

class TestSeasonalContext:
    def test_context_is_seasonal_in_december(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 12, 10), empty_ledger)
        assert ctx.is_seasonal_period is True

    def test_context_not_seasonal_in_april(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 4, 15), empty_ledger)
        assert ctx.is_seasonal_period is False
        assert ctx.agent_adjustments == {}
        assert ctx.narrative == ""

    def test_neutral_context_returns_zero_adjustments(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 4, 15), empty_ledger)
        assert ctx.confidence_modifier == 0.0

    def test_december_adjustments_correct_direction(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 12, 10), empty_ledger)
        # SEA_AUTO_001: sales_demand +0.06, fundamentals -0.08
        assert "sales_demand" in ctx.agent_adjustments
        assert "fundamentals" in ctx.agent_adjustments
        assert ctx.agent_adjustments["sales_demand"] > 0
        assert ctx.agent_adjustments["fundamentals"] < 0

    def test_adjustments_capped_at_max_delta(self, auto_calendar, empty_ledger):
        # Even if multiple patterns stack, no agent exceeds ±MAX_AGENT_DELTA
        ctx = auto_calendar.get_context(date(2026, 11, 5), empty_ledger)
        for agent, delta in ctx.agent_adjustments.items():
            assert abs(delta) <= MAX_AGENT_DELTA, (
                f"{agent} delta {delta} exceeds cap on Nov 5"
            )

    def test_lunar_dependency_halves_delta(self, auto_calendar, empty_ledger):
        # SEA_AUTO_003 (Shravan, Jul-Aug) has lunar_dependency=True → 0.5× multiplier
        ctx_jul = auto_calendar.get_context(date(2026, 7, 15), empty_ledger)
        # Expect sales_demand to be -0.07 × 0.5 = -0.035
        if "sales_demand" in ctx_jul.agent_adjustments:
            assert abs(ctx_jul.agent_adjustments["sales_demand"]) <= 0.04, (
                "Lunar-dependent pattern should apply at half delta"
            )

    def test_narrative_is_non_empty_in_seasonal_period(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 12, 10), empty_ledger)
        assert len(ctx.narrative) > 0

    def test_active_pattern_ids_populated(self, auto_calendar, empty_ledger):
        ctx = auto_calendar.get_context(date(2026, 12, 10), empty_ledger)
        assert "SEA_AUTO_001" in ctx.active_pattern_ids

    def test_rl_lesson_merged_into_context(self, auto_calendar, ledger_with_seasonal_lesson):
        ctx = auto_calendar.get_context(date(2026, 12, 10), ledger_with_seasonal_lesson)
        assert "L001" in ctx.active_rl_lesson_ids
        assert "[RL lesson L001]" in ctx.narrative

    def test_rl_lesson_not_added_if_not_seasonal(self, auto_calendar):
        """Non-seasonal lessons should not appear in seasonal context."""
        ledger = LearningLedger(ticker="MARUTI", last_updated="2026-01-01")
        ledger.lessons.append(Lesson(
            lesson_id="L002",
            date_learned="2026-01-01",
            category="macro",  # not seasonal
            pattern="rbi_policy_day",
            observation="RBI surprise",
            rule="Boost risk_macro on RBI days",
            confidence=0.80,
            occurrences=3,
            still_valid=True,
            scope="sector_wide",
            last_seen="2026-01-01",
        ))
        ctx = auto_calendar.get_context(date(2026, 12, 10), ledger)
        assert "L002" not in ctx.active_rl_lesson_ids

    def test_context_without_ledger_still_works(self, auto_calendar):
        ctx = auto_calendar.get_context(date(2026, 12, 10), None)
        assert ctx.is_seasonal_period is True
        assert ctx.active_rl_lesson_ids == []

    def test_confidence_modifier_negative_for_bearish_period(self, auto_calendar, empty_ledger):
        # March (SEA_AUTO_004): net delta on sales_demand is -0.07 → bearish net
        ctx = auto_calendar.get_context(date(2026, 3, 15), empty_ledger)
        if ctx.is_seasonal_period:
            # Net effect depends on whether fundamentals +0.04 outweighs sales_demand -0.07
            # net = -0.07 + 0.04 = -0.03 → negative → conf_modifier should be <= 0
            assert ctx.confidence_modifier <= 0.0

    def test_confidence_modifier_bounded(self, auto_calendar, empty_ledger):
        # Test across all months to ensure modifier never exceeds ±0.10
        for month in range(1, 13):
            ctx = auto_calendar.get_context(date(2026, month, 15), empty_ledger)
            assert -0.10 <= ctx.confidence_modifier <= 0.10, (
                f"confidence_modifier {ctx.confidence_modifier} out of bounds in month {month}"
            )


# ---------------------------------------------------------------------------
# 4. Banking, IT, Renewable — smoke tests
# ---------------------------------------------------------------------------

class TestOtherSectors:
    def test_banking_mpc_months_active(self):
        cal = SeasonalCalendar("banking_bfsi")
        # MPC months: Feb, Apr, Jun, Aug, Oct, Dec — first 10 days
        ctx = cal.get_context(date(2026, 4, 5))
        assert ctx.is_seasonal_period is True
        assert "SEA_BFSI_002" in ctx.active_pattern_ids

    def test_banking_mpc_not_active_mid_month(self):
        cal = SeasonalCalendar("banking_bfsi")
        ctx = cal.get_context(date(2026, 4, 20))  # day 20 outside [1,10]
        ids = ctx.active_pattern_ids
        assert "SEA_BFSI_002" not in ids

    def test_it_us_earnings_active_in_april(self):
        cal = SeasonalCalendar("it_sector")
        ctx = cal.get_context(date(2026, 4, 15))  # within [8,25]
        assert ctx.is_seasonal_period is True
        assert "SEA_IT_001" in ctx.active_pattern_ids

    def test_it_salary_hike_active_in_may(self):
        cal = SeasonalCalendar("it_sector")
        ctx = cal.get_context(date(2026, 5, 10))
        assert "SEA_IT_002" in ctx.active_pattern_ids

    def test_renewable_monsoon_active_in_july(self):
        cal = SeasonalCalendar("renewable_energy")
        ctx = cal.get_context(date(2026, 7, 15))
        assert ctx.is_seasonal_period is True
        assert "SEA_RE_001" in ctx.active_pattern_ids

    def test_renewable_peak_solar_active_in_april(self):
        cal = SeasonalCalendar("renewable_energy")
        ctx = cal.get_context(date(2026, 4, 20))
        assert "SEA_RE_002" in ctx.active_pattern_ids

    def test_all_sector_adjustments_bounded(self):
        for sector in ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]:
            cal = SeasonalCalendar(sector)
            for month in range(1, 13):
                ctx = cal.get_context(date(2026, month, 15))
                for agent, delta in ctx.agent_adjustments.items():
                    assert abs(delta) <= MAX_AGENT_DELTA, (
                        f"{sector} month={month} {agent} delta={delta} exceeds cap"
                    )


# ---------------------------------------------------------------------------
# 5. SeasonalValidator
# ---------------------------------------------------------------------------

class TestSeasonalValidator:

    def _make_feedback_log(self, date_str: str, actual_direction: str) -> DailyFeedbackLog:
        entry = FeedbackEntry(
            day=1,
            date=date_str,
            predicted_close=1000.0,
            actual_close=1050.0 if actual_direction == "UP" else 950.0,
            price_error_pct=5.0 if actual_direction == "UP" else -5.0,
            predicted_verdict="BUY",
            actual_direction=actual_direction,
            direction_correct=(actual_direction == "UP"),
        )
        log = DailyFeedbackLog(ticker="MARUTI", cycle_id="MARUTI_2026-12")
        log.entries.append(entry)
        return log

    def _make_pattern(self, net_positive: bool = True) -> SeasonalPattern:
        return SeasonalPattern(
            id="SEA_AUTO_001",
            name="test_pattern",
            evidence="Test only",
            months=[12],
            day_range=None,
            direction_bias="positive" if net_positive else "negative",
            confidence=0.75,
            agents_affected={"sales_demand": 0.06 if net_positive else -0.06},
            narrative="Test narrative",
            scope="sector_wide",
            validated_by_rl=False,
            decay_exempt=True,
            lunar_dependency=False,
        )

    def test_hit_increments_on_direction_match(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path))
        pattern = self._make_pattern(net_positive=True)
        log = self._make_feedback_log("2026-12-10", "UP")
        result = validator.validate_pattern(pattern, date(2026, 12, 10), log)
        assert result.record.hits == 1
        assert result.record.misses == 0
        assert result.direction_matched is True

    def test_miss_increments_on_direction_contradiction(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path))
        pattern = self._make_pattern(net_positive=True)
        log = self._make_feedback_log("2026-12-10", "DOWN")
        result = validator.validate_pattern(pattern, date(2026, 12, 10), log)
        assert result.record.misses == 1
        assert result.record.hits == 0
        assert result.direction_matched is False

    def test_validated_after_min_hits(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path), min_hits=2)
        pattern = self._make_pattern(net_positive=True)
        for day in [10, 11]:
            log = self._make_feedback_log(f"2026-12-{day:02d}", "UP")
            validator.validate_pattern(pattern, date(2026, 12, day), log)
        assert validator.is_validated("SEA_AUTO_001") is True

    def test_not_validated_before_min_hits(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path), min_hits=3)
        pattern = self._make_pattern(net_positive=True)
        log = self._make_feedback_log("2026-12-10", "UP")
        validator.validate_pattern(pattern, date(2026, 12, 10), log)
        assert validator.is_validated("SEA_AUTO_001") is False

    def test_invalidated_after_max_misses(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path), max_misses=3)
        pattern = self._make_pattern(net_positive=True)
        for day in [10, 11, 12]:
            log = self._make_feedback_log(f"2026-12-{day:02d}", "DOWN")
            validator.validate_pattern(pattern, date(2026, 12, day), log)
        assert validator.is_invalidated("SEA_AUTO_001") is True

    def test_confidence_multiplier_invalidated(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path), max_misses=1)
        pattern = self._make_pattern(net_positive=True)
        log = self._make_feedback_log("2026-12-10", "DOWN")
        validator.validate_pattern(pattern, date(2026, 12, 10), log)
        assert validator.confidence_multiplier("SEA_AUTO_001") == 0.5

    def test_confidence_multiplier_validated(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path), min_hits=1)
        pattern = self._make_pattern(net_positive=True)
        log = self._make_feedback_log("2026-12-10", "UP")
        validator.validate_pattern(pattern, date(2026, 12, 10), log)
        assert validator.confidence_multiplier("SEA_AUTO_001") == 1.0

    def test_volatile_pattern_skips_directional_validation(self, tmp_path):
        """Patterns with near-zero net delta should not be directionally validated."""
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path))
        pattern = SeasonalPattern(
            id="SEA_AUTO_VOLATILE",
            name="volatile_test",
            evidence="test",
            months=[2],
            day_range=None,
            direction_bias="volatile",
            confidence=0.60,
            agents_affected={"sentiment": -0.01, "policy_regulatory": +0.01},  # net ~0
            narrative="volatile",
            scope="sector_wide",
            validated_by_rl=False,
            decay_exempt=True,
            lunar_dependency=False,
        )
        log = self._make_feedback_log("2026-02-01", "DOWN")
        result = validator.validate_pattern(pattern, date(2026, 2, 1), log)
        assert result.direction_matched is None
        assert result.record.hits == 0
        assert result.record.misses == 0

    def test_no_feedback_entry_returns_none_direction(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path))
        pattern = self._make_pattern()
        empty_log = DailyFeedbackLog(ticker="MARUTI", cycle_id="MARUTI_2026-12")
        result = validator.validate_pattern(pattern, date(2026, 12, 10), empty_log)
        assert result.direction_matched is None

    def test_state_persists_across_instances(self, tmp_path):
        # Write state with first instance
        v1 = SeasonalValidator("automobile", base_dir=str(tmp_path), min_hits=1)
        pattern = self._make_pattern()
        log = self._make_feedback_log("2026-12-10", "UP")
        v1.validate_pattern(pattern, date(2026, 12, 10), log)
        v1.save_state()

        # Read state with second instance
        v2 = SeasonalValidator("automobile", base_dir=str(tmp_path))
        assert v2.is_validated("SEA_AUTO_001") is True

    def test_summary_not_empty_after_validation(self, tmp_path):
        validator = SeasonalValidator("automobile", base_dir=str(tmp_path))
        pattern = self._make_pattern()
        log = self._make_feedback_log("2026-12-10", "UP")
        validator.validate_pattern(pattern, date(2026, 12, 10), log)
        summary = validator.summary()
        assert "SEA_AUTO_001" in summary


# ---------------------------------------------------------------------------
# 6. Schema validation
# ---------------------------------------------------------------------------

class TestSchemaModels:
    def test_seasonal_pattern_requires_confidence_in_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SeasonalPattern(
                id="X", name="x", evidence="x", months=[1],
                direction_bias="pos", confidence=1.5,
                agents_affected={}, narrative="x",
            )

    def test_seasonal_context_defaults(self):
        ctx = SeasonalContext(target_date=date(2026, 4, 15))
        assert ctx.is_seasonal_period is False
        assert ctx.agent_adjustments == {}
        assert ctx.narrative == ""
        assert ctx.confidence_modifier == 0.0
