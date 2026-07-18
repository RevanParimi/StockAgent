"""
tests/unit/test_close_verifier.py
==================================
Data-integrity cross-check: services/data/fetchers/close_verifier.get_verified_close()

Covers:
  - agree-within-tolerance -> (yfinance_close, "agree"), no warning logged
  - disagree beyond tolerance -> (nse_close, "nse") + WARNING log naming both values
    (the symbol-cache-poisoning detector — e.g. yfinance returns 131 instead of
    MARUTI's real ~13022)
  - yfinance close is None -> falls back to NSE close, source "nse"
  - NSE client raises -> falls back to yfinance close, source "yfinance"; never raises
  - both sources unavailable -> (None, "none")
  - CLOSE_VERIFY_ENABLED=False -> pure yfinance passthrough, NSE never called
  - tolerance boundary: exactly CLOSE_VERIFY_TOLERANCE_PCT -> still "agree"
  - generate_forecast._fetch_actual_close routes through get_verified_close
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from services.data.fetchers import close_verifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_settings(monkeypatch, *, enabled: bool = True, tolerance_pct: float = 1.0):
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_ENABLED", enabled, raising=False)
    monkeypatch.setattr(close_verifier.settings, "CLOSE_VERIFY_TOLERANCE_PCT", tolerance_pct, raising=False)


@pytest.fixture(autouse=True)
def _clear_nse_cache():
    """The NSE close is day-cached in-process — reset between tests."""
    close_verifier._NSE_CLOSE_CACHE.clear()
    yield
    close_verifier._NSE_CLOSE_CACHE.clear()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

class TestGetVerifiedClose:
    def test_agree_within_tolerance_returns_yfinance_value_no_warning(self, monkeypatch, caplog):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=13022.0), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=13050.0):
            with caplog.at_level(logging.WARNING, logger=close_verifier.logger.name):
                close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13022.0
        assert source == "agree"
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_disagree_beyond_tolerance_returns_nse_value_with_warning(self, monkeypatch, caplog):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        # Symbol-cache-poisoning scenario: yfinance returns a wildly wrong
        # value (131) vs NSE's correct ~13022.
        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=131.0), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=13022.0):
            with caplog.at_level(logging.WARNING, logger=close_verifier.logger.name):
                close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13022.0
        assert source == "nse"
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "expected a WARNING log on disagreement"
        msg = warnings[0].getMessage()
        assert "131" in msg
        assert "13022" in msg

    def test_yfinance_none_falls_back_to_nse(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=None), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=13050.0):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13050.0
        assert source == "nse"

    def test_nse_missing_falls_back_to_yfinance(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=13022.0), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=None):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13022.0
        assert source == "yfinance"

    def test_nse_raises_falls_back_to_yfinance_never_raises(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        def _boom(ticker):
            raise ConnectionError("NSE 403: Forbidden")

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=13022.0), \
             patch.object(close_verifier, "_fetch_nse_close", side_effect=_boom):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13022.0
        assert source == "yfinance"

    def test_both_dead_returns_none_none(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=None), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=None):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close is None
        assert source == "none"

    def test_yfinance_raises_does_not_propagate(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        def _boom(ticker):
            raise RuntimeError("yfinance rate-limited")

        with patch.object(close_verifier, "_fetch_yfinance_close", side_effect=_boom), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=13050.0):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13050.0
        assert source == "nse"

    def test_flag_off_pure_yfinance_passthrough_no_nse_call(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=False, tolerance_pct=1.0)

        nse_mock_calls = []

        def _nse_spy(ticker):
            nse_mock_calls.append(ticker)
            return 99999.0  # would be wildly different — must never be used

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=13022.0), \
             patch.object(close_verifier, "_fetch_nse_close", side_effect=_nse_spy):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close == 13022.0
        assert source == "yfinance"
        assert nse_mock_calls == [], "NSE must never be called when CLOSE_VERIFY_ENABLED=False"

    def test_flag_off_both_none_returns_none_none(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=False, tolerance_pct=1.0)

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=None), \
             patch.object(close_verifier, "_fetch_nse_close") as nse_fn:
            close, source = close_verifier.get_verified_close("MARUTI")

        assert close is None
        assert source == "none"
        nse_fn.assert_not_called()

    def test_tolerance_boundary_exactly_at_limit_is_agree(self, monkeypatch):
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        yf_close = 13000.0
        # Exactly 1.0% difference
        nse_close = yf_close * 1.01

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=yf_close), \
             patch.object(close_verifier, "_fetch_nse_close", return_value=nse_close):
            close, source = close_verifier.get_verified_close("MARUTI")

        assert source == "agree"
        assert close == yf_close

    def test_nse_in_process_day_cache(self, monkeypatch):
        """NSE close is fetched at most once per ticker per process (day-cache)."""
        _patch_settings(monkeypatch, enabled=True, tolerance_pct=1.0)

        # Pre-seed the cache as get_verified_close's first call would, then
        # verify a second call doesn't re-invoke the underlying NSE client.
        nse_calls = []

        class _FakeNSE:
            def __init__(self, download_folder=None):
                pass

            def fetch_equity_historical_data(self, ticker, from_date=None, to_date=None):
                nse_calls.append(ticker)
                return [{"mtimestamp": "12-Jun-2026", "chClosingPrice": 13050.0}]

            def exit(self):
                pass

        fake_nse_module = type("module", (), {"NSE": _FakeNSE})

        with patch.object(close_verifier, "_fetch_yfinance_close", return_value=13022.0), \
             patch.dict("sys.modules", {"nse": fake_nse_module}):
            close_verifier.get_verified_close("MARUTI")
            close_verifier.get_verified_close("MARUTI")

        assert len(nse_calls) == 1


# ---------------------------------------------------------------------------
# Integration: generate_forecast._fetch_actual_close routes through verifier
# ---------------------------------------------------------------------------

class TestGenerateForecastIntegration:
    def test_fetch_actual_close_routes_through_verifier(self, monkeypatch):
        from core.intelligence.rl.workflows import generate_forecast as gf

        called_with = {}

        def _fake_get_verified_close(ticker):
            called_with["ticker"] = ticker
            return (13022.0, "agree")

        monkeypatch.setattr(gf, "get_verified_close", _fake_get_verified_close)

        result = gf._fetch_actual_close("MARUTI")

        assert result == 13022.0
        assert called_with["ticker"] == "MARUTI"


class TestNanSanitization:
    """A NaN yfinance close (RISHABH 2026-07-18) passed `is None` guards and
    was saved into an envelope as base_close=nan. Non-finite / non-positive
    closes must be treated as missing data."""

    def test_sanitize_rejects_nan_inf_zero_negative(self):
        assert close_verifier._sanitize(float("nan")) is None
        assert close_verifier._sanitize(float("inf")) is None
        assert close_verifier._sanitize(0.0) is None
        assert close_verifier._sanitize(-13022.0) is None
        assert close_verifier._sanitize(None) is None
        assert close_verifier._sanitize(13022.0) == 13022.0

    def test_cross_check_nan_yf_close_nse_dead_returns_none_none(self):
        with patch.object(close_verifier, "_fetch_nse_close", return_value=None):
            close, source = close_verifier.cross_check_close("RISHABH", float("nan"))
        assert close is None
        assert source == "none"

    def test_cross_check_nan_yf_close_falls_back_to_nse(self):
        with patch.object(close_verifier, "_fetch_nse_close", return_value=310.65):
            close, source = close_verifier.cross_check_close("RISHABH", float("nan"))
        assert close == 310.65
        assert source == "nse"
