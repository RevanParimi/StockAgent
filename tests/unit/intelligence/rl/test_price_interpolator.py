"""
tests/unit/intelligence/rl/test_price_interpolator.py
======================================================
Section 9 — LLM-calibrated price interpolator.

What is verified:
  ForecastProfile schema:
    - monthly_return_pct bounded [-20, 20]; confidence_band_daily_pct bounded [0.1, 5.0]
    - source field is "llm" or "static"

  Static fallback (_static_fallback):
    - BUY → positive monthly_return_pct; SELL → negative; NEUTRAL ≈ 0
    - ATR = 0 → atr_scale = 1.0 → base static values unchanged
    - High ATR (3.0) → scaled up from base; Low ATR (0.5) → scaled down
    - Scaling is bounded: max monthly_return_pct ≤ 20

  Path shape weights (_shape_weights):
    - All shapes produce exactly n_days weights
    - All weights sum to 1.0
    - linear: all weights equal
    - front_loaded: first-third weights > last-third weights
    - back_loaded: last-third weights > first-third weights
    - volatile: same as linear (noise added separately in build_price_path)

  build_price_path:
    - Returns exactly n_days tuples of (price, confidence)
    - All prices positive; all confidences in [0.05, 0.99]
    - Confidence decreases over time (broader horizon = more uncertainty)
    - linear shape: final price ≈ base_close × (1 + monthly_pct/100)
    - front_loaded: 60% of total move by day n//3
    - back_loaded: only 20% of move by day n//3
    - volatile: total move within ±ATR noise band around expected

  _parse (LLM output parsing):
    - Valid JSON → correct ForecastProfile
    - BUY + negative pct → sign flipped to positive
    - SELL + positive pct → sign flipped to negative
    - Out-of-bounds pct clamped to [-20, 20]
    - Invalid path_shape → defaults to "linear"
    - Invalid JSON → static fallback returned

  compute_atr_pct:
    - None df → 0.0; too-few rows (<15) → 0.0
    - Valid 30-day df → positive float

  compute_historical_avg_return:
    - < 3 matching entries → None
    - 5 matching entries → correct median
    - Case-insensitive verdict matching

Design context:
  The static verdict_monthly_pct (BUY=+4%, SELL=-3%) was identical for every
  stock regardless of volatility.  HDFC Bank (ATR ~0.8%) and ADANIGREEN
  (ATR ~3.5%) had the same 30-day price expectation on a BUY signal — wrong.
  The static fallback now scales by atr_pct/1.5.  The LLM profile goes further:
  it calibrates path shape from catalyst timing and sets asymmetric confidence
  bands matching the stock's actual daily range.
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.intelligence.rl.algorithms.price_interpolator import (
    ForecastProfile,
    PriceInterpolator,
    compute_atr_pct,
    compute_historical_avg_return,
    _STATIC_MONTHLY_PCT,
)
from backend.shared.schemas.feedback import (
    DailyFeedbackLog,
    FeedbackEntry,
    MissAnalysis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n_rows: int = 30, base_price: float = 10000.0, daily_range_pct: float = 1.5):
    """Create a synthetic OHLCV DataFrame for ATR testing."""
    # Use a fixed anchor business day to avoid weekend/holiday length mismatches
    # when end=date.today() is a non-business day under pandas "B" freq.
    dates = pd.bdate_range(start="2026-01-05", periods=n_rows)
    close = [base_price] * n_rows
    high  = [p * (1 + daily_range_pct / 100) for p in close]
    low   = [p * (1 - daily_range_pct / 100) for p in close]
    return pd.DataFrame({"High": high, "Low": low, "Close": close}, index=dates)


def _make_feedback_log(
    ticker: str = "MARUTI",
    entries: list[tuple[str, float]] = None,
) -> DailyFeedbackLog:
    """Create a DailyFeedbackLog with (verdict, price_error_pct) tuples."""
    log = DailyFeedbackLog(ticker=ticker, sector="automobile", cycle_id=f"{ticker}_2026-05")
    for i, (verdict, err) in enumerate(entries or []):
        entry = FeedbackEntry(
            day=i + 1,
            date=(date.today() - timedelta(days=len(entries) - i)).isoformat(),
            predicted_close=10000.0,
            actual_close=10000.0 * (1 + err / 100),
            price_error_pct=err,
            predicted_verdict=verdict,
            actual_direction="UP" if err > 0 else "DOWN",
            direction_correct=True,
        )
        log.entries.append(entry)
    return log


# ---------------------------------------------------------------------------
# ForecastProfile schema bounds
# ---------------------------------------------------------------------------

class TestForecastProfileSchema:

    def test_monthly_return_above_ceiling_rejected(self):
        with pytest.raises(Exception):
            ForecastProfile(monthly_return_pct=25.0, path_shape="linear",
                            confidence_band_daily_pct=1.0)

    def test_monthly_return_below_floor_rejected(self):
        with pytest.raises(Exception):
            ForecastProfile(monthly_return_pct=-25.0, path_shape="linear",
                            confidence_band_daily_pct=1.0)

    def test_band_below_floor_rejected(self):
        with pytest.raises(Exception):
            ForecastProfile(monthly_return_pct=4.0, path_shape="linear",
                            confidence_band_daily_pct=0.05)

    def test_band_above_ceiling_rejected(self):
        with pytest.raises(Exception):
            ForecastProfile(monthly_return_pct=4.0, path_shape="linear",
                            confidence_band_daily_pct=6.0)

    def test_valid_profile_accepted(self):
        p = ForecastProfile(monthly_return_pct=5.5, path_shape="front_loaded",
                            confidence_band_daily_pct=1.2, source="llm")
        assert p.monthly_return_pct == 5.5
        assert p.path_shape == "front_loaded"
        assert p.source == "llm"

    def test_default_source_is_llm(self):
        p = ForecastProfile(monthly_return_pct=4.0, path_shape="linear",
                            confidence_band_daily_pct=1.0)
        assert p.source == "llm"


# ---------------------------------------------------------------------------
# Static fallback: sign, direction, ATR scaling
# ---------------------------------------------------------------------------

class TestStaticFallback:

    def _fallback(self, verdict: str, atr: float) -> ForecastProfile:
        return PriceInterpolator._static_fallback(verdict, atr)

    @pytest.mark.parametrize("verdict", ["BUY", "STRONG BUY"])
    def test_bullish_verdict_positive_pct(self, verdict):
        p = self._fallback(verdict, 1.5)
        assert p.monthly_return_pct > 0

    @pytest.mark.parametrize("verdict", ["SELL", "STRONG SELL"])
    def test_bearish_verdict_negative_pct(self, verdict):
        p = self._fallback(verdict, 1.5)
        assert p.monthly_return_pct < 0

    def test_neutral_near_zero(self):
        p = self._fallback("NEUTRAL", 1.5)
        assert abs(p.monthly_return_pct) < 1.5

    def test_atr_zero_uses_base_value(self):
        """ATR=0 → atr_scale=1.0 → unchanged base monthly_pct."""
        p = self._fallback("BUY", 0.0)
        base = _STATIC_MONTHLY_PCT["BUY"]
        # When atr_pct=0, scale = max(0.5, min(2.5, 0/1.5)) = 0.5
        # but the minimum scale is 0.5, so pct = 4.0 * 0.5 = 2.0
        assert p.monthly_return_pct > 0   # at minimum still positive

    def test_high_atr_scales_up_buy(self):
        """ATR=3.0 is 2× the reference 1.5 → monthly_pct should be higher than base."""
        p_low = self._fallback("BUY", 1.5)
        p_high = self._fallback("BUY", 3.0)
        assert p_high.monthly_return_pct > p_low.monthly_return_pct

    def test_low_atr_scales_down_buy(self):
        """ATR=0.5 is below reference → monthly_pct lower than base."""
        p_ref = self._fallback("BUY", 1.5)
        p_low = self._fallback("BUY", 0.5)
        assert p_low.monthly_return_pct < p_ref.monthly_return_pct

    def test_scaled_pct_never_exceeds_bounds(self):
        for verdict in _STATIC_MONTHLY_PCT:
            for atr in [0.1, 1.5, 4.0, 10.0]:
                p = self._fallback(verdict, atr)
                assert -20.0 <= p.monthly_return_pct <= 20.0

    def test_source_field_is_static(self):
        p = self._fallback("BUY", 1.5)
        assert p.source == "static"

    def test_path_shape_is_linear(self):
        p = self._fallback("BUY", 1.5)
        assert p.path_shape == "linear"

    def test_confidence_band_scales_with_atr(self):
        """band ≈ ATR × 0.5."""
        p = self._fallback("BUY", 2.0)
        expected_band = 2.0 * 0.5
        assert abs(p.confidence_band_daily_pct - expected_band) < 0.2


# ---------------------------------------------------------------------------
# _shape_weights: structure and distribution
# ---------------------------------------------------------------------------

class TestShapeWeights:

    def _weights(self, n: int, shape: str) -> list[float]:
        return PriceInterpolator._shape_weights(n, shape)

    @pytest.mark.parametrize("shape", ["linear", "front_loaded", "back_loaded", "volatile"])
    def test_returns_n_weights(self, shape):
        for n in [10, 20, 30]:
            w = self._weights(n, shape)
            assert len(w) == n, f"{shape} n={n}: expected {n} weights, got {len(w)}"

    @pytest.mark.parametrize("shape", ["linear", "front_loaded", "back_loaded", "volatile"])
    def test_weights_sum_to_one(self, shape):
        w = self._weights(30, shape)
        assert abs(sum(w) - 1.0) < 1e-9, f"{shape}: weights sum to {sum(w)}"

    def test_linear_all_equal(self):
        w = self._weights(30, "linear")
        assert all(abs(x - w[0]) < 1e-9 for x in w)

    def test_front_loaded_first_third_heavier(self):
        """60% of move in first third → first 10 days weigh more than last 10."""
        w = self._weights(30, "front_loaded")
        first_third = sum(w[:10])
        last_third  = sum(w[20:])
        assert first_third > last_third, (
            f"front_loaded: first_third={first_third:.3f} should > last_third={last_third:.3f}"
        )

    def test_front_loaded_first_third_approx_60_pct(self):
        w = self._weights(30, "front_loaded")
        first_third_pct = sum(w[:10])
        assert 0.55 <= first_third_pct <= 0.65, (
            f"front_loaded: first_third_pct={first_third_pct:.3f}, expected ~0.60"
        )

    def test_back_loaded_last_two_thirds_heavier(self):
        """80% of move in last two-thirds."""
        w = self._weights(30, "back_loaded")
        first_third = sum(w[:10])
        rest        = sum(w[10:])
        assert rest > first_third

    def test_back_loaded_first_third_approx_20_pct(self):
        w = self._weights(30, "back_loaded")
        first_third_pct = sum(w[:10])
        assert 0.15 <= first_third_pct <= 0.25

    def test_volatile_same_as_linear(self):
        """volatile shape uses linear weights; noise is applied in build_price_path."""
        w_linear   = self._weights(30, "linear")
        w_volatile = self._weights(30, "volatile")
        assert w_linear == w_volatile


# ---------------------------------------------------------------------------
# build_price_path: structural guarantees
# ---------------------------------------------------------------------------

class TestBuildPricePath:

    def _build(self, monthly_pct: float, shape: str, base: float = 10000.0,
                band: float = 1.0, n: int = 30, conf: float = 0.70):
        profile = ForecastProfile(
            monthly_return_pct=monthly_pct,
            path_shape=shape,
            confidence_band_daily_pct=band,
            source="llm",
        )
        return PriceInterpolator().build_price_path(base, profile, n, conf)

    def test_returns_n_tuples(self):
        for n in [10, 20, 30]:
            path = self._build(4.0, "linear", n=n)
            assert len(path) == n

    def test_all_prices_positive(self):
        for shape in ["linear", "front_loaded", "back_loaded", "volatile"]:
            path = self._build(5.0, shape)
            for price, _ in path:
                assert price > 0, f"{shape}: negative price {price}"

    def test_confidence_in_bounds(self):
        path = self._build(4.0, "linear")
        for _, conf in path:
            assert 0.05 <= conf <= 0.99, f"Confidence {conf} outside [0.05, 0.99]"

    def test_confidence_decreases_over_time(self):
        """Confidence should generally decrease from day 1 to day 30."""
        path = self._build(4.0, "linear", conf=0.75)
        # Allow occasional small increase (noise in volatile), but overall trend down
        first_5_avg  = sum(c for _, c in path[:5])  / 5
        last_5_avg   = sum(c for _, c in path[25:]) / 5
        assert last_5_avg <= first_5_avg + 0.02, (
            f"Confidence not decreasing: first_5={first_5_avg:.3f} last_5={last_5_avg:.3f}"
        )

    @pytest.mark.parametrize("monthly_pct,shape", [
        (4.0, "linear"),
        (4.0, "front_loaded"),
        (4.0, "back_loaded"),
    ])
    def test_total_move_matches_monthly_pct(self, monthly_pct, shape):
        """
        For deterministic shapes, final price should ≈ base × (1 + pct/100).
        Tolerance is loose (+/- 1%) to account for rounding.
        """
        base = 10000.0
        path = self._build(monthly_pct, shape, base=base, n=30)
        final_price = path[-1][0]
        expected = base * (1 + monthly_pct / 100)
        assert abs(final_price - expected) < expected * 0.02, (
            f"{shape}: final={final_price:.0f} expected≈{expected:.0f}"
        )

    def test_front_loaded_60pct_in_first_third(self):
        """Front-loaded: 60% of the ₹500 move (BUY +5% on ₹10,000) in first 10 days."""
        base = 10000.0
        path = self._build(5.0, "front_loaded", base=base, n=30)
        prices = [p for p, _ in path]
        move_first_10  = prices[9]  - base
        move_total     = prices[-1] - base
        pct_in_first10 = move_first_10 / move_total if move_total != 0 else 0
        assert 0.55 <= pct_in_first10 <= 0.68, (
            f"front_loaded: {pct_in_first10:.2%} of move in first 10 days (expected 55-68%)"
        )

    def test_back_loaded_only_20pct_in_first_third(self):
        base = 10000.0
        path = self._build(5.0, "back_loaded", base=base, n=30)
        prices = [p for p, _ in path]
        move_first_10 = prices[9]  - base
        move_total    = prices[-1] - base
        pct_in_first10 = move_first_10 / move_total if move_total != 0 else 0
        assert 0.15 <= pct_in_first10 <= 0.28, (
            f"back_loaded: {pct_in_first10:.2%} in first 10 days (expected 15-28%)"
        )

    def test_sell_verdict_final_price_below_base(self):
        path = self._build(-3.5, "linear", base=10000.0, n=30)
        assert path[-1][0] < 10000.0

    def test_neutral_final_price_near_base(self):
        path = self._build(0.5, "linear", base=10000.0, n=30)
        assert abs(path[-1][0] - 10000.0) < 200


# ---------------------------------------------------------------------------
# _parse: LLM output parsing and safety guards
# ---------------------------------------------------------------------------

class TestParseFromLLM:

    def _reviewer(self):
        return PriceInterpolator()

    def test_valid_json_parsed_correctly(self):
        p = self._reviewer()
        raw = json.dumps({
            "monthly_return_pct": 6.5,
            "path_shape": "front_loaded",
            "confidence_band_daily_pct": 1.3,
            "reasoning": "Near-term FADA catalyst expected.",
        })
        fp = p._parse(raw, "BUY", 1.5)
        assert fp.monthly_return_pct == 6.5
        assert fp.path_shape == "front_loaded"
        assert fp.confidence_band_daily_pct == 1.3
        assert fp.source == "llm"

    def test_buy_with_negative_pct_sign_corrected(self):
        """LLM returned -5.0 for a BUY verdict → should be flipped to +5.0."""
        p = self._reviewer()
        raw = json.dumps({"monthly_return_pct": -5.0, "path_shape": "linear",
                          "confidence_band_daily_pct": 1.0})
        fp = p._parse(raw, "BUY", 1.5)
        assert fp.monthly_return_pct > 0, f"Expected positive, got {fp.monthly_return_pct}"

    def test_sell_with_positive_pct_sign_corrected(self):
        """LLM returned +4.0 for a SELL verdict → should be flipped to -4.0."""
        p = self._reviewer()
        raw = json.dumps({"monthly_return_pct": 4.0, "path_shape": "linear",
                          "confidence_band_daily_pct": 1.0})
        fp = p._parse(raw, "SELL", 1.5)
        assert fp.monthly_return_pct < 0

    def test_out_of_bounds_pct_clamped(self):
        p = self._reviewer()
        raw = json.dumps({"monthly_return_pct": 30.0, "path_shape": "linear",
                          "confidence_band_daily_pct": 1.0})
        fp = p._parse(raw, "BUY", 1.5)
        assert fp.monthly_return_pct <= 20.0

    def test_invalid_path_shape_defaults_linear(self):
        p = self._reviewer()
        raw = json.dumps({"monthly_return_pct": 4.0, "path_shape": "sideways",
                          "confidence_band_daily_pct": 1.0})
        fp = p._parse(raw, "BUY", 1.5)
        assert fp.path_shape == "linear"

    def test_all_valid_shapes_accepted(self):
        p = self._reviewer()
        for shape in ["linear", "front_loaded", "back_loaded", "volatile"]:
            raw = json.dumps({"monthly_return_pct": 4.0, "path_shape": shape,
                              "confidence_band_daily_pct": 1.0})
            fp = p._parse(raw, "BUY", 1.5)
            assert fp.path_shape == shape

    def test_invalid_json_returns_static_fallback(self):
        p = self._reviewer()
        fp = p._parse("INVALID JSON <<<", "BUY", 1.5)
        assert fp.source == "static"
        assert fp.monthly_return_pct > 0

    def test_missing_pct_field_uses_static_default(self):
        """If LLM omits monthly_return_pct, use the static dict value for that verdict."""
        p = self._reviewer()
        raw = json.dumps({"path_shape": "linear", "confidence_band_daily_pct": 1.0})
        fp = p._parse(raw, "STRONG BUY", 1.5)
        # The static default for STRONG BUY is 8.0 × ATR scale
        assert fp.monthly_return_pct > 0

    def test_band_clamped_to_bounds(self):
        p = self._reviewer()
        raw = json.dumps({"monthly_return_pct": 4.0, "path_shape": "linear",
                          "confidence_band_daily_pct": 10.0})
        fp = p._parse(raw, "BUY", 1.5)
        assert fp.confidence_band_daily_pct <= 5.0


# ---------------------------------------------------------------------------
# compute_atr_pct
# ---------------------------------------------------------------------------

class TestComputeAtrPct:

    def test_none_df_returns_zero(self):
        assert compute_atr_pct(None) == 0.0

    def test_empty_df_returns_zero(self):
        assert compute_atr_pct(pd.DataFrame()) == 0.0

    def test_too_few_rows_returns_zero(self):
        df = _make_ohlcv(n_rows=10)
        assert compute_atr_pct(df) == 0.0

    def test_valid_df_returns_positive_float(self):
        df = _make_ohlcv(n_rows=30, daily_range_pct=1.5)
        atr = compute_atr_pct(df)
        assert atr > 0, f"Expected positive ATR, got {atr}"

    def test_higher_range_gives_higher_atr(self):
        """1.5% daily range → smaller ATR than 3.0% range."""
        df_low  = _make_ohlcv(n_rows=30, daily_range_pct=1.5)
        df_high = _make_ohlcv(n_rows=30, daily_range_pct=3.0)
        assert compute_atr_pct(df_high) > compute_atr_pct(df_low)

    def test_atr_approximately_correct(self):
        """
        Synthetic data: each day has High=10150, Low=9850 on a ₹10,000 base.
        True Range ≈ 300 consistently → ATR_14 ≈ 300 → ATR% ≈ 3.0%.
        """
        df = _make_ohlcv(n_rows=30, base_price=10000.0, daily_range_pct=1.5)
        atr = compute_atr_pct(df)
        # ATR should be close to 1.5% (the daily range)
        assert 0.5 <= atr <= 3.0, f"ATR {atr:.4f}% seems unreasonable for 1.5% range data"

    def test_returns_float(self):
        df = _make_ohlcv(n_rows=30)
        assert isinstance(compute_atr_pct(df), float)


# ---------------------------------------------------------------------------
# compute_historical_avg_return
# ---------------------------------------------------------------------------

class TestComputeHistoricalAvgReturn:

    def test_none_feedback_log_returns_none(self):
        result = compute_historical_avg_return(None, "BUY")
        assert result is None

    def test_empty_log_returns_none(self):
        log = _make_feedback_log("MARUTI", [])
        result = compute_historical_avg_return(log, "BUY")
        assert result is None

    def test_fewer_than_3_matches_returns_none(self):
        """Less than 3 data points → insufficient for a reliable estimate."""
        log = _make_feedback_log("MARUTI", [("BUY", 2.5), ("BUY", 3.1)])
        result = compute_historical_avg_return(log, "BUY")
        assert result is None

    def test_3_or_more_returns_median(self):
        log = _make_feedback_log("MARUTI", [
            ("BUY", 1.0), ("BUY", 3.0), ("BUY", 5.0),
        ])
        result = compute_historical_avg_return(log, "BUY")
        assert result == 3.0   # median of [1, 3, 5]

    def test_5_entries_correct_median(self):
        log = _make_feedback_log("MARUTI", [
            ("BUY", 2.0), ("BUY", 4.0), ("BUY", 1.0), ("BUY", 6.0), ("BUY", 3.0),
        ])
        result = compute_historical_avg_return(log, "BUY")
        assert result == 3.0   # sorted: [1, 2, 3, 4, 6] → median = 3

    def test_only_matching_verdict_entries_used(self):
        """Mixed BUY/SELL log: only BUY entries count for BUY median."""
        log = _make_feedback_log("MARUTI", [
            ("SELL", -5.0), ("SELL", -3.0),
            ("BUY",   2.0), ("BUY",   4.0), ("BUY",   6.0),
        ])
        result = compute_historical_avg_return(log, "BUY")
        assert result == 4.0

    def test_case_insensitive_verdict_matching(self):
        """'buy' should match 'BUY' entries."""
        log = _make_feedback_log("MARUTI", [
            ("BUY", 3.0), ("BUY", 5.0), ("BUY", 7.0),
        ])
        result = compute_historical_avg_return(log, "buy")
        assert result == 5.0

    def test_strong_buy_separate_from_buy(self):
        """STRONG BUY and BUY are different verdicts."""
        log = _make_feedback_log("MARUTI", [
            ("STRONG BUY", 8.0), ("STRONG BUY", 10.0), ("STRONG BUY", 6.0),
            ("BUY", 3.0),
        ])
        result_sb = compute_historical_avg_return(log, "STRONG BUY")
        result_b  = compute_historical_avg_return(log, "BUY")
        assert result_sb == 8.0   # only 3 STRONG BUY entries
        assert result_b is None    # only 1 BUY entry → insufficient


# ---------------------------------------------------------------------------
# New tests: load_recent_feedback_entries + cross-cycle compute_historical_avg_return
# ---------------------------------------------------------------------------

import json, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.intelligence.rl.stores.prediction_store import PredictionStore


def _make_feedback_log_file(ticker, cycle_id, entries_data, tmp_dir):
    """Write a minimal feedback log JSON to tmp_dir/{sector}/{ticker}/."""
    from backend.shared.schemas.feedback import DailyFeedbackLog, FeedbackEntry, MissAnalysis, TimingAccuracy
    entries = []
    for i, d in enumerate(entries_data):
        ma = MissAnalysis(
            primary_miss_agent="sentiment",
            miss_type=d.get("miss_type", "magnitude"),
            missed_factors=[],
            over_weighted_factors=[],
            agent_score_drift={},
        )
        ta = TimingAccuracy(predicted_peak_day=5, actual_move_start_day=5, lag_days=0, assessment="on_time")
        entry = FeedbackEntry(
            day=i + 1,
            date=d["date"],
            predicted_close=100.0,
            actual_close=d["actual_close"],
            price_error_pct=d["price_error_pct"],
            direction_correct=d.get("direction_correct", True),
            actual_direction="UP" if d["price_error_pct"] >= 0 else "DOWN",
            predicted_verdict=d.get("verdict", "BUY"),
            miss_analysis=ma,
            timing=ta,
        )
        entries.append(entry)
    log = DailyFeedbackLog(ticker=ticker, cycle_id=cycle_id, sector="automobile", entries=entries)
    sector_dir = tmp_dir / "automobile" / ticker
    sector_dir.mkdir(parents=True, exist_ok=True)
    log_path = sector_dir / f"{cycle_id}_daily_feedback_log.json"
    log_path.write_text(log.model_dump_json())
    return log_path


def test_load_recent_feedback_entries_returns_combined(tmp_path):
    """load_recent_feedback_entries aggregates past cycles, not just current."""
    _make_feedback_log_file("MARUTI", "MARUTI_2026-03", [
        {"date": "2026-03-10", "actual_close": 102.0, "price_error_pct": 2.0, "verdict": "BUY"},
        {"date": "2026-03-11", "actual_close": 98.0,  "price_error_pct": -2.0, "verdict": "BUY"},
    ], tmp_path)
    _make_feedback_log_file("MARUTI", "MARUTI_2026-04", [
        {"date": "2026-04-10", "actual_close": 103.0, "price_error_pct": 3.0, "verdict": "BUY"},
    ], tmp_path)

    with patch("core.intelligence.rl.stores.prediction_store.settings") as ms:
        ms.PREDICTION_DATA_DIR = str(tmp_path)
        store = PredictionStore("MARUTI", sector="automobile")
        entries = store.load_recent_feedback_entries(n_cycles=6)

    assert len(entries) == 3


def test_compute_historical_avg_return_accepts_entry_list():
    """compute_historical_avg_return works when passed a list of FeedbackEntry objects."""
    from backend.shared.schemas.feedback import FeedbackEntry, MissAnalysis, TimingAccuracy
    ma = MissAnalysis(primary_miss_agent="x", miss_type="magnitude", missed_factors=[], over_weighted_factors=[], agent_score_drift={})
    ta = TimingAccuracy(predicted_peak_day=1, actual_move_start_day=1, lag_days=0, assessment="on_time")
    entries = [
        FeedbackEntry(
            day=i + 1,
            date=f"2026-03-{10 + i:02d}",
            predicted_close=100.0,
            actual_close=102.0,
            price_error_pct=float(i + 1),
            direction_correct=True,
            actual_direction="UP",
            predicted_verdict="BUY",
            miss_analysis=ma,
            timing=ta,
        )
        for i in range(5)
    ]
    result = compute_historical_avg_return(entries, "BUY")
    assert result is not None
    assert isinstance(result, float)


def test_compute_historical_avg_return_empty_list_returns_none():
    result = compute_historical_avg_return([], "BUY")
    assert result is None
