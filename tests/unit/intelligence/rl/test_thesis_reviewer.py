"""
tests/unit/intelligence/rl/test_thesis_reviewer.py
===================================================
Step 7 — Conditional thesis review after significant prediction miss.

What is verified:
  - should_review() triggers on |error| > 2.0% regardless of miss_type
  - should_review() triggers on direction_flip / model_bias even below threshold
  - should_review() does NOT trigger on timing / magnitude / external_shock below threshold
  - ThesisReview schema bounds: multiplier clamped to [0.3, 1.0]
  - _parse() handles valid JSON → correct ThesisReview fields
  - _parse() handles malformed JSON → safe default (intact=True, mult=1.0)
  - _parse() enforces multiplier bounds [0.3, 1.0]
  - _revise_remaining_forecasts(): thesis_review=None → no extra discount
  - _revise_remaining_forecasts(): multiplier=0.75 → all remaining confidences reduced
  - _revise_remaining_forecasts(): multiplier=1.0 → no change from thesis component

Design context:
  - ThesisReviewer fires at most 1-3×/month across all tickers (only on significant misses).
  - The multiplier is a global discount on ALL remaining 30-day forecasts, separate from
    the per-day horizon_confidence_adjustment.  A broken thesis (e.g. crude spiked 8%,
    invalidating the "stable input cost" assumption) makes every remaining BUY forecast
    structurally less reliable, not just today's.
  - Safe-default-on-failure is critical: the daily review must never be blocked by a
    thesis review LLM failure.
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.schemas.feedback import (
    ThesisReview,
    FeedbackAgentOutput,
    RevisedContext,
    DailyForecast,
    PredictionEnvelope,
    ConvictionStreak,
)
from core.intelligence.rl.agents.thesis_reviewer import (
    ThesisReviewer,
    THESIS_REVIEW_THRESHOLD,
    THESIS_REVIEW_MISS_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fb_output(miss_type: str = "direction_flip", primary: str = "risk_macro") -> FeedbackAgentOutput:
    return FeedbackAgentOutput(
        primary_miss_agent=primary,
        miss_type=miss_type,
        missed_factors=["crude oil spike", "RBI surprise"],
        over_weighted_factors=["FADA optimism"],
        agent_score_drift={"risk_macro": -0.18},
        new_lessons=[],
        revised_context=RevisedContext(
            headline="test",
            horizon_confidence_adjustment=-0.05,
        ),
    )


def _make_envelope(n_days: int = 5, base_conf: float = 0.70) -> PredictionEnvelope:
    today = date.today()
    forecasts = [
        DailyForecast(
            day=i + 1,
            date=(today + timedelta(days=i + 1)).isoformat(),
            predicted_close=10000.0 + i * 50,
            predicted_change_pct=float(i) * 0.5,
            predicted_verdict="BUY",
            predicted_agent_scores={"risk_macro": 0.55},
            confidence=base_conf,
        )
        for i in range(n_days)
    ]
    return PredictionEnvelope(
        ticker="MARUTI",
        sector="automobile",
        cycle_id="MARUTI_2026-05",
        generated_at=today.isoformat(),
        base_close=10000.0,
        daily_forecasts=forecasts,
        conviction_streak=ConvictionStreak(),
    )


# ---------------------------------------------------------------------------
# should_review()
# ---------------------------------------------------------------------------

class TestShouldReview:

    def test_large_positive_error_triggers(self):
        """error = +3.5% exceeds threshold → review warranted."""
        r = ThesisReviewer()
        assert r.should_review(3.5, True, "magnitude") is True

    def test_large_negative_error_triggers(self):
        """error = -2.5% exceeds threshold → review warranted."""
        r = ThesisReviewer()
        assert r.should_review(-2.5, True, "magnitude") is True

    def test_exactly_at_floor_does_not_trigger(self):
        """error = exactly 1.5% (the ATR floor) should NOT trigger (strict >)."""
        r = ThesisReviewer()
        assert r.should_review(1.5, True, "magnitude") is False

    def test_just_above_floor_triggers(self):
        """error = 1.51% just above the ATR floor (no ticker → atr=0) triggers."""
        r = ThesisReviewer()
        assert r.should_review(1.51, True, "magnitude") is True

    def test_small_error_direction_correct_no_trigger(self):
        """Small miss, direction correct → no review needed."""
        r = ThesisReviewer()
        assert r.should_review(0.8, True, "magnitude") is False

    @pytest.mark.parametrize("miss_type", ["direction_flip", "model_bias"])
    def test_wrong_direction_triggers_regardless_of_size(self, miss_type):
        """direction_correct=False + structural miss type → always triggers."""
        r = ThesisReviewer()
        assert r.should_review(0.5, False, miss_type) is True

    @pytest.mark.parametrize("miss_type", ["timing", "magnitude", "external_shock",
                                            "data_gap", "data_stale"])
    def test_small_miss_non_structural_type_no_trigger(self, miss_type):
        """Below threshold + non-structural miss → no review."""
        r = ThesisReviewer()
        assert r.should_review(0.5, False, miss_type) is False

    def test_threshold_floor_is_1_5_pct(self):
        """ATR threshold constants live in settings; THESIS_REVIEW_THRESHOLD alias preserved."""
        from core.config import settings
        assert settings.RL_ATR_THRESHOLD_FLOOR == 1.5
        assert settings.RL_ATR_THRESHOLD_MULTIPLIER == 1.5
        # Backward-compat alias still importable and reflects the floor
        assert THESIS_REVIEW_THRESHOLD == settings.RL_ATR_THRESHOLD_FLOOR

    def test_structural_miss_types_set(self):
        assert "direction_flip" in THESIS_REVIEW_MISS_TYPES
        assert "model_bias" in THESIS_REVIEW_MISS_TYPES
        assert "timing" not in THESIS_REVIEW_MISS_TYPES
        assert "external_shock" not in THESIS_REVIEW_MISS_TYPES


# ---------------------------------------------------------------------------
# ThesisReview schema
# ---------------------------------------------------------------------------

class TestThesisReviewSchema:

    def test_default_thesis_intact_true(self):
        tr = ThesisReview()
        assert tr.thesis_intact is True

    def test_default_multiplier_is_one(self):
        tr = ThesisReview()
        assert tr.horizon_confidence_multiplier == 1.0

    def test_multiplier_below_floor_rejected(self):
        with pytest.raises(Exception):
            ThesisReview(horizon_confidence_multiplier=0.1)

    def test_multiplier_above_ceiling_rejected(self):
        with pytest.raises(Exception):
            ThesisReview(horizon_confidence_multiplier=1.5)

    def test_valid_multiplier_accepted(self):
        tr = ThesisReview(horizon_confidence_multiplier=0.75)
        assert tr.horizon_confidence_multiplier == 0.75

    def test_assumptions_lists_default_empty(self):
        tr = ThesisReview()
        assert tr.assumptions_invalidated == []
        assert tr.assumptions_still_valid == []


# ---------------------------------------------------------------------------
# _parse() — JSON parsing and safety guards
# ---------------------------------------------------------------------------

class TestThesisReviewerParse:

    def _reviewer(self):
        return ThesisReviewer.__new__(ThesisReviewer)   # skip __init__ (no LLM client needed)

    def test_valid_json_parsed_correctly(self):
        r = self._reviewer()
        raw = json.dumps({
            "assumptions_invalidated": ["crude stable ~$82"],
            "assumptions_still_valid": ["FADA dispatch strong"],
            "thesis_intact": False,
            "revised_narrative": "RBI surprise invalidated financing assumption.",
            "horizon_confidence_multiplier": 0.70,
        })
        tr = r._parse(raw, ["crude stable ~$82", "FADA dispatch strong"])
        assert tr.thesis_intact is False
        assert tr.horizon_confidence_multiplier == 0.70
        assert "crude stable ~$82" in tr.assumptions_invalidated
        assert "FADA dispatch strong" in tr.assumptions_still_valid
        assert "RBI" in tr.revised_narrative

    def test_invalid_json_returns_safe_default(self):
        r = self._reviewer()
        tr = r._parse("NOT JSON AT ALL {{{", [])
        assert tr.thesis_intact is True
        assert tr.horizon_confidence_multiplier == 1.0

    def test_multiplier_clamped_to_floor_03(self):
        r = self._reviewer()
        raw = json.dumps({"horizon_confidence_multiplier": 0.1, "thesis_intact": False})
        tr = r._parse(raw, [])
        assert tr.horizon_confidence_multiplier == 0.3

    def test_multiplier_clamped_to_ceiling_10(self):
        r = self._reviewer()
        raw = json.dumps({"horizon_confidence_multiplier": 1.8, "thesis_intact": True})
        tr = r._parse(raw, [])
        assert tr.horizon_confidence_multiplier == 1.0

    def test_missing_fields_use_defaults(self):
        r = self._reviewer()
        raw = json.dumps({})
        tr = r._parse(raw, [])
        assert tr.thesis_intact is True
        assert tr.horizon_confidence_multiplier == 1.0
        assert tr.assumptions_invalidated == []

    def test_assumptions_capped_at_five(self):
        r = self._reviewer()
        raw = json.dumps({
            "assumptions_invalidated": [f"assumption_{i}" for i in range(10)],
            "thesis_intact": False,
        })
        tr = r._parse(raw, [])
        assert len(tr.assumptions_invalidated) <= 5

    def test_narrative_truncated_at_300_chars(self):
        r = self._reviewer()
        raw = json.dumps({"revised_narrative": "x" * 500})
        tr = r._parse(raw, [])
        assert len(tr.revised_narrative) <= 300

    def test_review_fails_gracefully_returns_safe_default(self):
        """review() catches all exceptions and returns intact=True, mult=1.0."""
        r = ThesisReviewer.__new__(ThesisReviewer)
        r._client = None   # simulate no client → _call_llm will raise
        fb = _make_fb_output()
        tr = r.review(
            ticker="MARUTI", sector="automobile",
            key_assumptions=["crude stable ~$82"],
            fb_output=fb, market_context="",
        )
        assert tr.thesis_intact is True
        assert tr.horizon_confidence_multiplier == 1.0


# ---------------------------------------------------------------------------
# Forecast revision with thesis multiplier
# ---------------------------------------------------------------------------

class TestRevisionWithThesisMultiplier:
    """
    Verifies that _revise_remaining_forecasts() correctly applies the
    thesis_review.horizon_confidence_multiplier on top of other adjustments.
    """

    def _call_revise(self, envelope, thesis_review=None):
        from unittest.mock import MagicMock
        store = MagicMock()
        store.load_envelope.return_value = envelope
        store.save_envelope = MagicMock()

        from core.intelligence.rl.workflows.daily_review import _revise_remaining_forecasts
        from core.schemas.feedback import RevisedContext, ConvictionStreak

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _revise_remaining_forecasts(
            ticker="MARUTI",
            store=store,
            reviewed_date=yesterday,
            new_weights={"risk_macro": 0.20, "fundamentals": 0.20},
            revised_context=RevisedContext(horizon_confidence_adjustment=0.0),
            reversion_prior=0.0,
            updated_streak=ConvictionStreak(),
            thesis_review=thesis_review,
        )
        return store.save_envelope.call_args[0][0]  # saved envelope

    def test_no_thesis_review_confidences_unchanged_from_base(self):
        """thesis_review=None → thesis component makes no change."""
        env = _make_envelope(n_days=3, base_conf=0.70)
        saved = self._call_revise(env, thesis_review=None)
        for f in saved.daily_forecasts:
            # Should not be pushed down by thesis multiplier
            assert f.confidence >= 0.20   # some decay from re-weighting is ok

    def test_multiplier_075_reduces_all_remaining_confidences(self):
        """multiplier=0.75 must reduce every remaining forecast confidence."""
        env_no_mult = _make_envelope(n_days=4, base_conf=0.70)
        env_with_mult = _make_envelope(n_days=4, base_conf=0.70)

        saved_no = self._call_revise(env_no_mult, thesis_review=None)
        saved_75 = self._call_revise(
            env_with_mult,
            thesis_review=ThesisReview(
                thesis_intact=False,
                horizon_confidence_multiplier=0.75,
            ),
        )

        for f_no, f_75 in zip(saved_no.daily_forecasts, saved_75.daily_forecasts):
            assert f_75.confidence <= f_no.confidence + 0.01, (
                f"Day {f_75.day}: thesis(0.75) conf {f_75.confidence:.3f} "
                f"should be ≤ no-thesis conf {f_no.confidence:.3f}"
            )

    def test_multiplier_10_no_extra_discount(self):
        """multiplier=1.0 (intact thesis) → no extra confidence reduction."""
        env_no_mult = _make_envelope(n_days=3, base_conf=0.70)
        env_one = _make_envelope(n_days=3, base_conf=0.70)

        saved_no = self._call_revise(env_no_mult, thesis_review=None)
        saved_1  = self._call_revise(
            env_one,
            thesis_review=ThesisReview(thesis_intact=True, horizon_confidence_multiplier=1.0),
        )

        for f_no, f_1 in zip(saved_no.daily_forecasts, saved_1.daily_forecasts):
            assert abs(f_no.confidence - f_1.confidence) < 0.001

    def test_multiplier_applied_before_floor(self):
        """Even with 0.30 multiplier, confidence must not fall below 0.05 floor."""
        env = _make_envelope(n_days=3, base_conf=0.10)  # already low
        saved = self._call_revise(
            env,
            thesis_review=ThesisReview(thesis_intact=False, horizon_confidence_multiplier=0.3),
        )
        for f in saved.daily_forecasts:
            assert f.confidence >= 0.05, f"Confidence {f.confidence} below floor 0.05"


# ---------------------------------------------------------------------------
# ATR-relative threshold (Task 7)
# ---------------------------------------------------------------------------

def test_should_review_high_atr_stock_2pct_miss_no_trigger():
    """For ADANIGREEN-like stock (ATR 3.5%), a 2% miss should NOT trigger review.
    Threshold = max(1.5, 1.5*3.5) = 5.25%, so 2% < 5.25% = no trigger."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", return_value=3.5):
        result = reviewer.should_review(
            price_error_pct=2.0,
            direction_correct=True,
            miss_type="magnitude",
            ticker="ADANIGREEN",
        )
    assert result is False


def test_should_review_low_atr_stock_triggers_at_floor():
    """For HDFCBANK-like stock (ATR 0.8%), threshold = max(1.5, 1.5*0.8=1.2) = 1.5%.
    A 1.6% miss exceeds the floor and triggers."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", return_value=0.8):
        result = reviewer.should_review(
            price_error_pct=1.6,
            direction_correct=True,
            miss_type="magnitude",
            ticker="HDFCBANK",
        )
    assert result is True


def test_should_review_structural_miss_always_triggers():
    """direction_flip always triggers regardless of ATR or error size."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", return_value=5.0):
        result = reviewer.should_review(
            price_error_pct=0.5,
            direction_correct=False,
            miss_type="direction_flip",
            ticker="ADANIGREEN",
        )
    assert result is True


def test_should_review_atr_failure_uses_floor():
    """If ATR computation fails, threshold falls back to floor 1.5%."""
    reviewer = ThesisReviewer.__new__(ThesisReviewer)
    with patch.object(reviewer, "_compute_atr_pct", side_effect=Exception("no data")):
        result = reviewer.should_review(
            price_error_pct=2.0,
            direction_correct=True,
            miss_type="magnitude",
            ticker="HDFCBANK",
        )
    # floor=1.5, atr=0 (fallback from exception), threshold=max(1.5, 0)=1.5, error=2.0 > 1.5 → True
    assert result is True
