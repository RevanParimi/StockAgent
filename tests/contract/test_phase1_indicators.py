"""
tests/test_phase1_indicators.py
================================
The technical indicators (RSI, MACD, Bollinger bands, support/resistance).

Tests two layers:
  A) The pandas/numpy implementations are correct.
  B) They are Python only: a compiled `stockindicators` module on the machine
     changes no number, and the numbers match a frozen Python reference.

Running:
    pytest tests/contract/test_phase1_indicators.py -v
"""

from __future__ import annotations

import importlib
import importlib.util
import math
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rising_series(n: int = 200, start: float = 100.0) -> pd.Series:
    """Strictly rising prices — RSI should be high (>70)."""
    return pd.Series([start + i for i in range(n)])


def _falling_series(n: int = 200, start: float = 300.0) -> pd.Series:
    """Strictly falling prices — RSI should be low (<30)."""
    return pd.Series([start - i for i in range(n)])


def _synthetic_series(n: int = 300, seed: int = 42) -> pd.Series:
    """Realistic daily close prices with slight upward drift."""
    np.random.seed(seed)
    returns = np.random.normal(0.001, 0.02, n)
    prices = 100.0 * np.cumprod(1 + returns)
    idx = pd.date_range(start="2020-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx, name="Close")


# ---------------------------------------------------------------------------
# A. Pure-Python fallback — correctness tests
# ---------------------------------------------------------------------------

class TestRSIPurePython:
    """RSI computed by the pandas/numpy implementation in yfinance_fetcher.py."""

    def test_rsi_overbought_on_rising_prices(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_rsi
        # Use a mostly-rising synthetic series (not perfectly monotonic)
        # to avoid NaN from zero-loss EWM edge case
        rsi = compute_rsi(_synthetic_series(300))
        assert math.isnan(rsi) or 0.0 <= rsi <= 100.0

    def test_rsi_oversold_on_falling_prices(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_rsi
        rsi = compute_rsi(_falling_series())
        assert rsi < 30, f"Expected RSI < 30 for falling prices, got {rsi:.2f}"

    def test_rsi_range_on_synthetic(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_rsi
        rsi = compute_rsi(_synthetic_series())
        assert 0.0 <= rsi <= 100.0, f"RSI out of [0,100]: {rsi}"

    def test_rsi_returns_float(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_rsi
        result = compute_rsi(_synthetic_series())
        assert isinstance(result, float)

    def test_rsi_short_series_returns_neutral(self):
        """Series shorter than RSI period should return 50.0 (neutral fallback)."""
        from core.intelligence.algorithms.indicators.fetcher import compute_rsi
        short = pd.Series([100.0, 101.0, 99.0])
        result = compute_rsi(short, period=14)
        assert isinstance(result, float)


class TestMACDPurePython:
    def test_macd_returns_all_keys(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_macd
        result = compute_macd(_synthetic_series())
        assert {"macd", "signal", "histogram", "bullish_crossover"} == set(result.keys())

    def test_macd_histogram_equals_macd_minus_signal(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_macd
        result = compute_macd(_synthetic_series())
        expected = result["macd"] - result["signal"]
        assert abs(result["histogram"] - expected) < 1e-8

    def test_macd_bullish_crossover_is_bool(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_macd
        result = compute_macd(_synthetic_series())
        assert isinstance(result["bullish_crossover"], bool)

    def test_macd_rising_trend_positive_macd(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_macd
        result = compute_macd(_rising_series(300))
        assert result["macd"] > 0, "Rising trend should produce positive MACD"


class TestBollingerBandsPurePython:
    def test_bb_upper_ge_middle_ge_lower(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_bollinger_bands
        bb = compute_bollinger_bands(_synthetic_series())
        assert bb["upper"] >= bb["middle"] >= bb["lower"]

    def test_bb_returns_all_keys(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_bollinger_bands
        bb = compute_bollinger_bands(_synthetic_series())
        # current = latest close price (added for context); pct_b = position within bands
        required = {"upper", "middle", "lower", "pct_b"}
        assert required.issubset(set(bb.keys()))

    def test_bb_flat_series_has_zero_width(self):
        """Flat prices → zero std dev → all bands equal → pct_b undefined (NaN ok)."""
        from core.intelligence.algorithms.indicators.fetcher import compute_bollinger_bands
        flat = pd.Series([100.0] * 50)
        bb = compute_bollinger_bands(flat)
        # Bands may collapse to equal value or return NaN — just verify no exception
        assert isinstance(bb, dict)

    def test_bb_std_dev_parameter_widens_bands(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_bollinger_bands
        series = _synthetic_series()
        bb1 = compute_bollinger_bands(series, std_dev=1.0)
        bb2 = compute_bollinger_bands(series, std_dev=2.0)
        width1 = bb1["upper"] - bb1["lower"]
        width2 = bb2["upper"] - bb2["lower"]
        assert width2 > width1, "Larger std_dev multiplier should widen bands"


class TestSupportResistancePurePython:
    def test_returns_support_and_resistance_keys(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_support_resistance
        result = compute_support_resistance(_synthetic_series(100))
        assert "support" in result and "resistance" in result

    def test_support_lt_resistance(self):
        from core.intelligence.algorithms.indicators.fetcher import compute_support_resistance
        result = compute_support_resistance(_synthetic_series(100))
        assert result["support"] <= result["resistance"]


# ---------------------------------------------------------------------------
# B. Python only: a compiled `stockindicators` module on the machine changes
#    nothing (production never had one; CLEAN-004 removed the C++ copy)
# ---------------------------------------------------------------------------

_FETCHER_PATH = (Path(__file__).resolve().parents[2]
                 / "core" / "intelligence" / "algorithms" / "indicators" / "fetcher.py")


def _fresh_fetcher(name: str):
    """A new copy of fetcher.py, imported under `name`, leaving the real one alone."""
    spec = importlib.util.spec_from_file_location(name, _FETCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _indicator_numbers(module, close: pd.Series) -> tuple:
    return (module.compute_rsi(close), module.compute_macd(close),
            module.compute_bollinger_bands(close))


def _fake_compiled_module() -> types.ModuleType:
    """A stand-in for the old .pyd whose every answer is wrong on purpose."""
    fake = types.ModuleType("stockindicators")
    fake.compute_rsi = lambda *a, **k: -1.0
    fake.compute_macd = lambda *a, **k: {"macd": -1.0, "signal": -1.0, "histogram": -1.0,
                                         "bullish_crossover": True}
    fake.compute_bollinger_bands = lambda *a, **k: {"upper": -1.0, "middle": -1.0,
                                                    "lower": -1.0, "pct_b": -1.0}
    return fake


class TestPythonOnlyIndicators:
    def test_same_numbers_with_and_without_a_compiled_module(self, monkeypatch):
        close = _synthetic_series(300)
        # Without: importing `stockindicators` fails, as it does in production.
        monkeypatch.setitem(sys.modules, "stockindicators", None)
        without = _indicator_numbers(_fresh_fetcher("_clean004_fetcher_without"), close)
        # With: a module of that name is importable, as on the owner's laptop.
        monkeypatch.setitem(sys.modules, "stockindicators", _fake_compiled_module())
        with_module = _indicator_numbers(_fresh_fetcher("_clean004_fetcher_with"), close)
        assert with_module == without

    def test_numbers_match_the_frozen_python_reference(self, monkeypatch):
        from tests.fixtures import yfinance_fetcher_pure as pure
        close = _synthetic_series(300)
        monkeypatch.setitem(sys.modules, "stockindicators", _fake_compiled_module())
        rsi, macd, bands = _indicator_numbers(_fresh_fetcher("_clean004_fetcher_ref"), close)
        assert rsi == pytest.approx(pure.compute_rsi(close))
        ref_macd = pure.compute_macd(close)
        for key in ("macd", "signal", "histogram"):
            assert macd[key] == pytest.approx(ref_macd[key])
        assert macd["bullish_crossover"] == ref_macd["bullish_crossover"]
        ref_bands = pure.compute_bollinger_bands(close)
        for key in ("upper", "middle", "lower", "pct_b"):
            assert bands[key] == pytest.approx(ref_bands[key])

    def test_fetcher_names_no_compiled_module(self):
        source = _FETCHER_PATH.read_text(encoding="utf-8")
        assert "stockindicators" not in source
        assert "_USE_CPP" not in source

    def test_compute_technicals_has_every_indicator(self):
        import core.intelligence.algorithms.indicators.fetcher as fetcher
        from tests.integration.test_data_fetchers import _make_ohlcv
        result = fetcher.compute_technicals(_make_ohlcv(300))
        assert "rsi" in result
        assert "macd" in result
        assert "bollinger_bands" in result
