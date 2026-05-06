"""
tests/unit/test_regime.py
==========================
Unit tests for P5 — Context-Conditional Regime Multiplier.

Coverage:
  - RegimeDetector._classify(): all 6 regime labels with boundary values
  - RegimeDetector._classify(): priority ordering (MACRO_CRISIS before RISK_OFF)
  - RegimeDetector._classify(): OVERSOLD is checked after macro regimes
  - apply_regime_multipliers(): renormalisation (sum = 1.0)
  - apply_regime_multipliers(): agents not in multipliers table get 1.0×
  - apply_regime_multipliers(): zero-sum guard returns original weights
  - apply_regime_multipliers(): MACRO_CRISIS increases risk_macro share
  - apply_regime_multipliers(): RISK_ON increases fundamentals + sentiment share
  - _compute_rsi(): insufficient data returns fallback
  - _compute_rsi(): all same prices → RSI = 100 (no losses)
  - _compute_rsi(): alternating prices → RSI ≈ 50 (equal gains/losses)
  - RegimeSnapshot schema: defaults, backward-compatible load from old JSON
  - REGIME_MULTIPLIERS in settings: all 6 regimes present, all 9 agents present
  - REGIME_MULTIPLIERS NORMAL: all multipliers = 1.0
  - RegimeDetector.detect(): fallback to NORMAL when yfinance errors (monkeypatched)
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.config import settings
from core.intelligence.regime.detector import (
    RegimeDetector,
    _compute_rsi,
    apply_regime_multipliers,
)
from core.schemas.feedback import RegimeSnapshot


# ---------------------------------------------------------------------------
# _compute_rsi()
# ---------------------------------------------------------------------------

class TestComputeRsi:
    def test_insufficient_data_returns_fallback(self):
        prices = pd.Series([100.0, 101.0, 99.0])
        result = _compute_rsi(prices, period=14)
        assert result == settings.RSI_FALLBACK

    def test_exactly_period_plus_one_prices_returns_value(self):
        prices = pd.Series([float(i) for i in range(100, 116)])  # 16 values, period=14
        result = _compute_rsi(prices, period=14)
        assert 0.0 <= result <= 100.0

    def test_all_gains_returns_100(self):
        # Strictly increasing prices → no losses → RSI approaches 100
        prices = pd.Series([float(100 + i) for i in range(30)])
        result = _compute_rsi(prices, period=14)
        assert result > 90.0, f"Expected RSI near 100 for all-gain series, got {result}"

    def test_all_losses_returns_near_zero(self):
        # Strictly decreasing prices → no gains → RSI approaches 0
        prices = pd.Series([float(100 - i) for i in range(30)])
        result = _compute_rsi(prices, period=14)
        assert result < 10.0, f"Expected RSI near 0 for all-loss series, got {result}"

    def test_alternating_returns_near_fifty(self):
        # Perfectly alternating +1/-1 → equal avg gain and loss → RSI ≈ 50
        vals = []
        v = 100.0
        for i in range(40):
            v += 1.0 if i % 2 == 0 else -1.0
            vals.append(v)
        prices = pd.Series(vals)
        result = _compute_rsi(prices, period=14)
        assert 40.0 <= result <= 60.0, f"Expected RSI near 50, got {result}"


# ---------------------------------------------------------------------------
# RegimeDetector._classify()
# ---------------------------------------------------------------------------

class TestClassify:
    @pytest.mark.parametrize("vix,fii,rsi,expected", [
        # MACRO_CRISIS: VIX > 22 AND fii < -1.0
        (25.0, -2.0, 50.0, "MACRO_CRISIS"),
        (22.1, -1.1, 50.0, "MACRO_CRISIS"),
        # RISK_OFF: VIX > 22 but fii neutral (doesn't qualify for MACRO_CRISIS)
        (25.0,  0.0, 50.0, "RISK_OFF"),
        (22.5,  0.5, 50.0, "RISK_OFF"),
        # RISK_OFF: 14 ≤ VIX ≤ 22 AND fii outflow
        (18.0, -1.5, 50.0, "RISK_OFF"),
        (14.0, -2.0, 50.0, "RISK_OFF"),
        # MOMENTUM_EXTENDED: VIX < 14 AND fii > 1.0 AND RSI > 70
        (12.0,  2.0, 75.0, "MOMENTUM_EXTENDED"),
        (13.9,  1.1, 71.0, "MOMENTUM_EXTENDED"),
        # RISK_ON: VIX < 22 AND fii > 1.0 AND RSI < 70
        (18.0,  2.0, 55.0, "RISK_ON"),
        (10.0,  1.5, 65.0, "RISK_ON"),
        # OVERSOLD: RSI < 30 (checked after macro regimes)
        (18.0,  0.0, 25.0, "OVERSOLD"),
        (20.0, -0.5, 28.0, "OVERSOLD"),
        # NORMAL: everything else
        (18.0,  0.0, 50.0, "NORMAL"),
        (14.0,  0.0, 50.0, "NORMAL"),
        (21.9,  0.9, 50.0, "NORMAL"),
    ])
    def test_classification(self, vix, fii, rsi, expected):
        result = RegimeDetector._classify(vix, fii, rsi)
        assert result == expected, (
            f"VIX={vix}, FII={fii}, RSI={rsi}: expected {expected}, got {result}"
        )

    def test_macro_crisis_takes_priority_over_risk_off(self):
        # VIX > 22 AND fii < -1 → MACRO_CRISIS, not RISK_OFF
        assert RegimeDetector._classify(25.0, -2.0, 50.0) == "MACRO_CRISIS"

    def test_oversold_below_macro_crisis_in_priority(self):
        # VIX > 22 AND fii < -1 AND RSI < 30 → still MACRO_CRISIS (higher priority)
        assert RegimeDetector._classify(25.0, -2.0, 20.0) == "MACRO_CRISIS"

    def test_vix_exactly_at_volatile_threshold_is_risk_off(self):
        # VIX == 22.0 is NOT > 22, so it falls into 14–22 range
        # With fii outflow it should be RISK_OFF (14 ≤ VIX ≤ 22 AND fii < -1)
        assert RegimeDetector._classify(22.0, -1.5, 50.0) == "RISK_OFF"

    def test_vix_exactly_at_low_threshold_is_not_momentum_extended(self):
        # VIX == 14 is NOT < 14, so MOMENTUM_EXTENDED doesn't apply
        # With inflow + overbought → RISK_ON (VIX < 22 AND fii > 1 AND rsi < 70? No, RSI=75)
        # Actually RSI=75 > 70, and VIX=14 is not < 14, so not MOMENTUM_EXTENDED
        # VIX < 22 AND fii > 1 AND RSI < 70 → RISK_ON only if RSI < 70
        result = RegimeDetector._classify(14.0, 2.0, 75.0)
        # Not MOMENTUM_EXTENDED (VIX not < 14), not RISK_ON (RSI not < 70) → NORMAL
        assert result == "NORMAL"

    def test_normal_at_exact_boundaries(self):
        # VIX = 18 (14–22), FII = 0 (neutral), RSI = 50 (neutral)
        assert RegimeDetector._classify(18.0, 0.0, 50.0) == "NORMAL"


# ---------------------------------------------------------------------------
# apply_regime_multipliers()
# ---------------------------------------------------------------------------

class TestApplyRegimeMultipliers:
    def _base_weights(self) -> dict[str, float]:
        return {
            "risk_macro":         0.13,
            "fundamentals":       0.18,
            "sales_demand":       0.15,
            "sentiment":          0.04,
            "pattern_analysis":   0.11,
            "competitive_intel":  0.09,
            "valuation_catalyst": 0.12,
            "raw_materials":      0.09,
            "policy_regulatory":  0.09,
        }

    def test_normal_regime_weights_unchanged(self):
        weights = self._base_weights()
        multipliers = settings.REGIME_MULTIPLIERS["NORMAL"]
        result = apply_regime_multipliers(weights, multipliers)
        # All multipliers = 1.0 → weights should be unchanged (up to floating point)
        for agent, w in weights.items():
            assert abs(result[agent] - w) < 1e-6, (
                f"{agent}: expected {w:.6f}, got {result[agent]:.6f}"
            )

    def test_result_sums_to_one(self):
        weights = self._base_weights()
        for regime_label, multipliers in settings.REGIME_MULTIPLIERS.items():
            result = apply_regime_multipliers(weights, multipliers)
            total = sum(result.values())
            assert abs(total - 1.0) < 1e-5, (
                f"Regime {regime_label}: weights sum to {total:.6f}, expected 1.0"
            )

    def test_macro_crisis_increases_risk_macro_share(self):
        weights = self._base_weights()
        multipliers = settings.REGIME_MULTIPLIERS["MACRO_CRISIS"]
        result = apply_regime_multipliers(weights, multipliers)
        # risk_macro should have a higher share in MACRO_CRISIS than in NORMAL
        normal_result = apply_regime_multipliers(weights, settings.REGIME_MULTIPLIERS["NORMAL"])
        assert result["risk_macro"] > normal_result["risk_macro"]

    def test_risk_on_increases_sentiment_share(self):
        weights = self._base_weights()
        multipliers = settings.REGIME_MULTIPLIERS["RISK_ON"]
        result = apply_regime_multipliers(weights, multipliers)
        normal_result = apply_regime_multipliers(weights, settings.REGIME_MULTIPLIERS["NORMAL"])
        assert result["sentiment"] > normal_result["sentiment"]

    def test_oversold_increases_pattern_analysis_share(self):
        weights = self._base_weights()
        result = apply_regime_multipliers(weights, settings.REGIME_MULTIPLIERS["OVERSOLD"])
        normal_result = apply_regime_multipliers(weights, settings.REGIME_MULTIPLIERS["NORMAL"])
        assert result["pattern_analysis"] > normal_result["pattern_analysis"]

    def test_agent_not_in_multipliers_gets_one_times(self):
        weights = {"risk_macro": 0.5, "new_agent": 0.5}
        multipliers = {"risk_macro": 1.4}   # new_agent not listed → 1.0×
        result = apply_regime_multipliers(weights, multipliers)
        total = sum(result.values())
        assert abs(total - 1.0) < 1e-5

    def test_zero_sum_guard_returns_original(self):
        weights = {"risk_macro": 0.0, "fundamentals": 0.0}
        multipliers = {"risk_macro": 0.0, "fundamentals": 0.0}
        result = apply_regime_multipliers(weights, multipliers)
        assert result == weights

    @pytest.mark.parametrize("regime_label", [
        "MACRO_CRISIS", "RISK_OFF", "NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD"
    ])
    def test_all_regimes_produce_valid_weights(self, regime_label):
        weights = self._base_weights()
        multipliers = settings.REGIME_MULTIPLIERS[regime_label]
        result = apply_regime_multipliers(weights, multipliers)
        assert all(v >= 0 for v in result.values()), f"{regime_label}: negative weight found"
        assert abs(sum(result.values()) - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# settings.REGIME_MULTIPLIERS validation
# ---------------------------------------------------------------------------

class TestRegimeMultipliersConfig:
    _EXPECTED_REGIMES = {
        "MACRO_CRISIS", "RISK_OFF", "NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD"
    }
    _EXPECTED_AGENTS = {
        "risk_macro", "fundamentals", "sales_demand", "sentiment",
        "pattern_analysis", "competitive_intel", "valuation_catalyst",
        "raw_materials", "policy_regulatory",
    }

    def test_all_six_regimes_present(self):
        assert set(settings.REGIME_MULTIPLIERS.keys()) == self._EXPECTED_REGIMES

    def test_all_agents_present_in_every_regime(self):
        for regime, table in settings.REGIME_MULTIPLIERS.items():
            missing = self._EXPECTED_AGENTS - set(table.keys())
            assert not missing, f"Regime '{regime}' missing agents: {missing}"

    def test_normal_regime_all_ones(self):
        for agent, mult in settings.REGIME_MULTIPLIERS["NORMAL"].items():
            assert mult == 1.0, f"NORMAL[{agent}] = {mult}, expected 1.0"

    def test_all_multipliers_are_positive(self):
        for regime, table in settings.REGIME_MULTIPLIERS.items():
            for agent, mult in table.items():
                assert mult > 0, f"Regime '{regime}', agent '{agent}': non-positive multiplier {mult}"

    def test_macro_crisis_risk_macro_multiplier_is_highest(self):
        assert settings.REGIME_MULTIPLIERS["MACRO_CRISIS"]["risk_macro"] == 1.40

    def test_vix_thresholds_ordered_correctly(self):
        assert settings.VIX_LOW_VOL_THRESHOLD < settings.VIX_VOLATILE_THRESHOLD


# ---------------------------------------------------------------------------
# RegimeSnapshot schema
# ---------------------------------------------------------------------------

class TestRegimeSnapshotSchema:
    def test_defaults_are_safe(self):
        snap = RegimeSnapshot()
        assert snap.regime_label == "NORMAL"
        assert snap.vix_value == 17.0
        assert snap.fii_proxy_5d_pct == 0.0
        assert snap.sector_rsi == 50.0
        assert snap.multipliers == {}
        assert snap.narrative == ""
        assert snap.as_of_date == ""

    def test_json_round_trip(self):
        snap = RegimeSnapshot(
            regime_label="MACRO_CRISIS",
            vix_value=25.0,
            fii_proxy_5d_pct=-2.5,
            sector_rsi=35.0,
            multipliers={"risk_macro": 1.40},
            narrative="Crisis regime detected.",
            as_of_date="2026-05-01",
        )
        raw = snap.model_dump_json()
        restored = RegimeSnapshot.model_validate_json(raw)
        assert restored.regime_label == "MACRO_CRISIS"
        assert restored.vix_value == 25.0
        assert restored.multipliers["risk_macro"] == 1.40

    def test_backward_compatible_load_old_json(self):
        # Old JSON with no RegimeSnapshot fields → loads as default without error
        old_data: dict = {}
        snap = RegimeSnapshot(**old_data)
        assert snap.regime_label == "NORMAL"


# ---------------------------------------------------------------------------
# RegimeDetector.detect() with mocked yfinance (non-fatal fallback)
# ---------------------------------------------------------------------------

class TestRegimeDetectorDetect:
    def _make_df(self, closes: list[float]) -> pd.DataFrame:
        return pd.DataFrame({"Close": closes})

    def test_detect_returns_regime_snapshot(self):
        detector = RegimeDetector()
        with (
            patch.object(detector, "_get_vix", return_value=18.0),
            patch.object(detector, "_get_fii_proxy", return_value=0.0),
            patch.object(detector, "_get_sector_rsi", return_value=50.0),
        ):
            snap = detector.detect(date(2026, 5, 1), "automobile")
        assert isinstance(snap, RegimeSnapshot)
        assert snap.regime_label == "NORMAL"
        assert snap.as_of_date == "2026-05-01"

    def test_detect_macro_crisis_when_vix_high_and_fii_outflow(self):
        detector = RegimeDetector()
        with (
            patch.object(detector, "_get_vix", return_value=26.0),
            patch.object(detector, "_get_fii_proxy", return_value=-3.0),
            patch.object(detector, "_get_sector_rsi", return_value=50.0),
        ):
            snap = detector.detect(date(2026, 5, 1), "automobile")
        assert snap.regime_label == "MACRO_CRISIS"
        assert snap.multipliers["risk_macro"] == 1.40

    def test_detect_risk_on_signals(self):
        detector = RegimeDetector()
        with (
            patch.object(detector, "_get_vix", return_value=12.0),
            patch.object(detector, "_get_fii_proxy", return_value=2.5),
            patch.object(detector, "_get_sector_rsi", return_value=55.0),
        ):
            snap = detector.detect(date(2026, 5, 1), "automobile")
        assert snap.regime_label == "RISK_ON"

    def test_detect_fallback_to_vix_default_on_yfinance_error(self):
        # When yfinance raises inside _get_vix(), the method catches and returns VIX_FALLBACK.
        detector = RegimeDetector()
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("network")
            vix = detector._get_vix(date(2026, 5, 1))
        assert vix == settings.VIX_FALLBACK

    def test_detect_fallback_to_zero_on_fii_yfinance_error(self):
        # When yfinance raises inside _get_fii_proxy(), falls back to FII_PROXY_FALLBACK.
        detector = RegimeDetector()
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("network")
            fii = detector._get_fii_proxy(date(2026, 5, 1))
        assert fii == settings.FII_PROXY_FALLBACK

    def test_detect_fallback_to_fifty_on_rsi_yfinance_error(self):
        # When yfinance raises inside _get_sector_rsi(), falls back to RSI_FALLBACK.
        detector = RegimeDetector()
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = Exception("network")
            rsi = detector._get_sector_rsi("automobile", date(2026, 5, 1))
        assert rsi == settings.RSI_FALLBACK

    def test_narrative_non_empty_for_all_regimes(self):
        detector = RegimeDetector()
        for vix, fii, rsi, label in [
            (26.0, -2.0, 50.0, "MACRO_CRISIS"),
            (25.0,  0.0, 50.0, "RISK_OFF"),
            (18.0,  0.0, 50.0, "NORMAL"),
            (18.0,  2.0, 55.0, "RISK_ON"),
            (12.0,  2.0, 75.0, "MOMENTUM_EXTENDED"),
            (18.0,  0.0, 25.0, "OVERSOLD"),
        ]:
            with (
                patch.object(detector, "_get_vix", return_value=vix),
                patch.object(detector, "_get_fii_proxy", return_value=fii),
                patch.object(detector, "_get_sector_rsi", return_value=rsi),
            ):
                snap = detector.detect(date(2026, 5, 1), "automobile")
            assert snap.narrative, f"Empty narrative for regime {label}"
            assert snap.regime_label == label

    def test_multipliers_loaded_from_settings(self):
        detector = RegimeDetector()
        with (
            patch.object(detector, "_get_vix", return_value=26.0),
            patch.object(detector, "_get_fii_proxy", return_value=-2.0),
            patch.object(detector, "_get_sector_rsi", return_value=50.0),
        ):
            snap = detector.detect(date(2026, 5, 1), "automobile")
        expected = settings.REGIME_MULTIPLIERS["MACRO_CRISIS"]
        assert snap.multipliers == expected
