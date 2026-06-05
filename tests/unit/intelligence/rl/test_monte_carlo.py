"""
tests/unit/intelligence/rl/test_monte_carlo.py
===============================================
G1+G3: Regime-conditioned GBM Monte Carlo price bands.

What is verified:
  build_monte_carlo_paths():
    - Returns exactly n_days tuples of (p50, p10, p90, confidence)
    - P10 < P50 < P90 on every day (percentile invariant)
    - MACRO_CRISIS produces wider P10-P90 band than RISK_ON
    - seed=42 reproducibility: identical inputs → identical outputs
    - n_simulations parameter is respected (different n_sims accepted)
    - REGIME_SIGMA_SCALE: all 6 labels produce valid paths

  DailyForecast schema (G1+G3 integration):
    - price_lower and price_upper fields exist and accept float | None
"""

import pytest

from core.intelligence.rl.algorithms.price_interpolator import (
    ForecastProfile,
    PriceInterpolator,
    REGIME_SIGMA_SCALE,
)
from backend.shared.schemas.feedback import DailyForecast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(monthly_pct: float = 4.0, band: float = 1.5) -> ForecastProfile:
    return ForecastProfile(
        monthly_return_pct=monthly_pct,
        path_shape="linear",
        confidence_band_daily_pct=band,
        source="static",
    )


def _mc(regime: str = "NORMAL", n_days: int = 10, n_sims: int = 500):
    interp = PriceInterpolator()
    return interp.build_monte_carlo_paths(
        base_close=1000.0,
        profile=_profile(),
        n_days=n_days,
        base_confidence=0.75,
        n_simulations=n_sims,
        regime_label=regime,
    )


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

def test_returns_n_days_tuples():
    result = _mc(n_days=15)
    assert len(result) == 15
    for tup in result:
        assert len(tup) == 4, "Each tuple must be (p50, p10, p90, confidence)"


def test_all_prices_positive():
    result = _mc(n_days=20)
    for p50, p10, p90, _ in result:
        assert p50 > 0
        assert p10 > 0
        assert p90 > 0


def test_confidence_in_bounds():
    result = _mc(n_days=20)
    for _, _, _, conf in result:
        assert 0.05 <= conf <= 0.99


# ---------------------------------------------------------------------------
# Percentile invariant: P10 < P50 < P90 every day
# ---------------------------------------------------------------------------

def test_percentile_ordering():
    result = _mc(n_days=30)
    for i, (p50, p10, p90, _) in enumerate(result):
        assert p10 < p50, f"Day {i}: P10={p10} not < P50={p50}"
        assert p50 < p90, f"Day {i}: P50={p50} not < P90={p90}"


# ---------------------------------------------------------------------------
# Regime conditioning: MACRO_CRISIS band > RISK_ON band
# ---------------------------------------------------------------------------

def test_macro_crisis_wider_than_risk_on():
    crisis = _mc(regime="MACRO_CRISIS", n_days=15)
    risk_on = _mc(regime="RISK_ON", n_days=15)

    # Compare average band width across all days
    def avg_band(paths):
        return sum((p90 - p10) for p50, p10, p90, _ in paths) / len(paths)

    crisis_band = avg_band(crisis)
    risk_on_band = avg_band(risk_on)
    assert crisis_band > risk_on_band, (
        f"MACRO_CRISIS avg band {crisis_band:.2f} should exceed RISK_ON {risk_on_band:.2f}"
    )


def test_regime_sigma_scale_monotonic():
    """Higher REGIME_SIGMA_SCALE → wider band. Test: NORMAL > RISK_ON, MACRO_CRISIS > OVERSOLD."""
    def avg_band(regime):
        paths = _mc(regime=regime, n_days=10)
        return sum((p90 - p10) for _, p10, p90, _ in paths) / len(paths)

    assert avg_band("MACRO_CRISIS") > avg_band("RISK_OFF")
    assert avg_band("RISK_OFF") > avg_band("NORMAL")
    assert avg_band("NORMAL") > avg_band("RISK_ON")


# ---------------------------------------------------------------------------
# Seed=42 reproducibility
# ---------------------------------------------------------------------------

def test_seed42_reproducibility():
    r1 = _mc(regime="NORMAL", n_days=10)
    r2 = _mc(regime="NORMAL", n_days=10)
    assert r1 == r2, "Identical inputs must yield identical MC outputs (seed=42)"


def test_different_regime_different_output():
    normal = _mc(regime="NORMAL", n_days=10)
    crisis = _mc(regime="MACRO_CRISIS", n_days=10)
    assert normal != crisis, "Different regimes must produce different paths"


# ---------------------------------------------------------------------------
# n_simulations parameter
# ---------------------------------------------------------------------------

def test_small_n_sims_still_works():
    result = _mc(n_sims=50, n_days=5)
    assert len(result) == 5
    for p50, p10, p90, _ in result:
        assert p10 < p50 < p90


def test_large_n_sims_accepted():
    result = _mc(n_sims=1000, n_days=5)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# All 6 regime labels are valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("regime", list(REGIME_SIGMA_SCALE.keys()))
def test_all_regime_labels_produce_valid_paths(regime):
    result = _mc(regime=regime, n_days=5)
    assert len(result) == 5
    for p50, p10, p90, conf in result:
        assert p10 < p50 < p90
        assert 0.05 <= conf <= 0.99


def test_unknown_regime_label_falls_back_to_normal():
    """Unknown regime → REGIME_SIGMA_SCALE.get(label, 1.0) → same as NORMAL."""
    unknown = _mc(regime="NONEXISTENT", n_days=10)
    normal = _mc(regime="NORMAL", n_days=10)
    assert unknown == normal, "Unknown regime label should fall back to sigma_scale=1.0 (same as NORMAL)"


# ---------------------------------------------------------------------------
# DailyForecast schema: price_lower and price_upper fields exist
# ---------------------------------------------------------------------------

def test_daily_forecast_has_price_bands():
    df = DailyForecast(
        day=1,
        date="2026-05-26",
        predicted_close=1050.0,
        predicted_verdict="BUY",
        confidence=0.75,
        price_lower=980.0,
        price_upper=1120.0,
    )
    assert df.price_lower == 980.0
    assert df.price_upper == 1120.0


def test_daily_forecast_price_bands_optional():
    df = DailyForecast(
        day=1,
        date="2026-05-26",
        predicted_close=1050.0,
        predicted_verdict="BUY",
        confidence=0.75,
    )
    assert df.price_lower is None
    assert df.price_upper is None
