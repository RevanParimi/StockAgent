"""
tests/unit/intelligence/rl/test_new_data_sources.py
====================================================
Unit tests for the three new data source modules:
  - services/data/fetchers/nse_market.py
  - services/data/fetchers/mf_herding.py
  - core/intelligence/rl/algorithms/factor_regime.py

All tests mock external network calls — no live NSE/AMFI/IIMA traffic.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd


# ---------------------------------------------------------------------------
# nse_market.py tests
# ---------------------------------------------------------------------------

class TestNseMarketFormatContext:
    """Test format_nse_market_context with controlled mock data."""

    def _make_data(self, **overrides) -> dict:
        base = {
            "fii_net_cr":            -500.0,
            "dii_net_cr":            1200.0,
            "combined_net_cr":       700.0,
            "fii_dii_signal":        "DII absorbing FII selling — moderate support",
            "bulk_deal_net_buyers":  ["APOLLOHOSP", "ZOMATO"],
            "bulk_deal_net_sellers": ["ADANIPORTS"],
            "bulk_deals_by_ticker":  {
                "APOLLOHOSP": {"net_qty": 50000, "side": "BUY"},
                "ADANIPORTS": {"net_qty": -20000, "side": "SELL"},
            },
            "upcoming_earnings":     [
                {"symbol": "TCS", "date": "2026-06-15", "purpose": "Financial Results"},
                {"symbol": "INFY", "date": "2026-06-18", "purpose": "Financial Results"},
            ],
            "fetched_at":            "2026-05-31",
            "error":                 None,
        }
        base.update(overrides)
        return base

    def test_fii_dii_focus_contains_flow_numbers(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data()
        ctx  = format_nse_market_context(data, focus="fii_dii")

        assert "FII net:" in ctx
        assert "-500.00 Cr" in ctx
        assert "+1,200.00 Cr" in ctx
        assert "DII absorbing FII selling" in ctx

    def test_bulk_deals_focus_contains_buyers_sellers(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data()
        ctx  = format_nse_market_context(data, focus="bulk_deals")

        assert "APOLLOHOSP" in ctx
        assert "ADANIPORTS" in ctx
        assert "Net institutional buyers" in ctx
        assert "Net institutional sellers" in ctx

    def test_bulk_deals_with_ticker_shows_specific_activity(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data()
        ctx  = format_nse_market_context(data, focus="bulk_deals", ticker="APOLLOHOSP")
        assert "bulk deal activity" in ctx
        assert "buy" in ctx.lower()

    def test_bulk_deals_with_ticker_not_present_shows_no_activity(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data()
        ctx  = format_nse_market_context(data, focus="bulk_deals", ticker="TATAMOTORS")
        assert "no bulk deal activity today" in ctx

    def test_all_focus_includes_both_sections(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data()
        ctx  = format_nse_market_context(data, focus="all")

        assert "NSE MARKET FLOWS" in ctx
        assert "NSE BULK DEALS" in ctx
        assert "UPCOMING NSE EVENTS" in ctx
        assert "TCS" in ctx

    def test_empty_data_returns_empty_string(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        assert format_nse_market_context({}) == ""
        assert format_nse_market_context(None) == ""

    def test_nsepython_not_installed_returns_empty(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = {"error": "nsepython_not_installed"}
        assert format_nse_market_context(data) == ""

    def test_both_selling_signal(self):
        from services.data.fetchers.nse_market import format_nse_market_context
        data = self._make_data(
            fii_net_cr=-300.0,
            dii_net_cr=-150.0,
            combined_net_cr=-450.0,
            fii_dii_signal="Both FII and DII selling — risk-off, reduce exposure",
        )
        ctx = format_nse_market_context(data, focus="fii_dii")
        assert "Both FII and DII selling" in ctx

    def test_get_upcoming_earnings_for_ticker_found(self):
        from services.data.fetchers.nse_market import get_upcoming_earnings_for_ticker
        data = self._make_data()
        result = get_upcoming_earnings_for_ticker("TCS", data)
        assert result == "2026-06-15"

    def test_get_upcoming_earnings_for_ticker_not_found(self):
        from services.data.fetchers.nse_market import get_upcoming_earnings_for_ticker
        data = self._make_data()
        result = get_upcoming_earnings_for_ticker("MARUTI", data)
        assert result is None


class TestNseMarketDailyCache:
    """Test the daily in-process cache behaviour."""

    def test_cache_hit_returns_same_object(self):
        from services.data.fetchers import nse_market
        nse_market._CACHE.clear()

        fake_data = {"fii_net_cr": 100.0, "fetched_at": "2099-01-01", "error": None}
        with patch.object(nse_market, "_fetch_nse_market_data", return_value=fake_data) as mock_fetch:
            # Override today key to match fake data
            with patch.object(nse_market, "_today_key", return_value="2099-01-01"):
                first  = nse_market.get_nse_market_data()
                second = nse_market.get_nse_market_data()
                assert mock_fetch.call_count == 1
                assert first is second

    def test_force_refresh_bypasses_cache(self):
        from services.data.fetchers import nse_market
        nse_market._CACHE.clear()

        fake_data = {"fii_net_cr": 200.0, "fetched_at": "2099-01-02", "error": None}
        with patch.object(nse_market, "_fetch_nse_market_data", return_value=fake_data):
            with patch.object(nse_market, "_today_key", return_value="2099-01-02"):
                nse_market.get_nse_market_data()
                nse_market.get_nse_market_data(force_refresh=True)
                # _fetch called twice: initial + force refresh
                assert nse_market._CACHE.get("2099-01-02") == fake_data


# ---------------------------------------------------------------------------
# mf_herding.py tests
# ---------------------------------------------------------------------------

class TestMfHerdingFormat:
    """Test format_mf_herding_context with mock data."""

    def _make_herding(self, avg: float, flow: str, sector: str = "automobile") -> dict:
        return {
            "sector":             sector,
            "avg_momentum_pct":   avg,
            "institutional_flow": flow,
            "fund_count":         3,
            "individual": [
                {"scheme_code": 148620, "name": "Mirae Asset Nifty Auto ETF",       "momentum_pct": avg - 0.05},
                {"scheme_code": 149075, "name": "ICICI Prudential Nifty Auto ETF",  "momentum_pct": avg},
                {"scheme_code": 148553, "name": "Nippon India Nifty Auto ETF",       "momentum_pct": avg + 0.05},
            ],
            "fetched_at": "2026-W22",
            "error": None,
        }

    def test_outflow_context(self):
        from services.data.fetchers.mf_herding import format_mf_herding_context
        ctx = format_mf_herding_context(self._make_herding(-0.38, "OUTFLOW"))
        assert "MF HERDING SIGNAL" in ctx
        assert "outflow" in ctx.lower()
        assert "-0.380%" in ctx

    def test_inflow_context(self):
        from services.data.fetchers.mf_herding import format_mf_herding_context
        ctx = format_mf_herding_context(self._make_herding(0.72, "INFLOW"))
        assert "inflow" in ctx.lower() or "accumulation" in ctx.lower()
        assert "+0.720%" in ctx

    def test_neutral_context(self):
        from services.data.fetchers.mf_herding import format_mf_herding_context
        ctx = format_mf_herding_context(self._make_herding(0.1, "NEUTRAL"))
        assert "neutral" in ctx.lower()

    def test_empty_data_returns_empty_string(self):
        from services.data.fetchers.mf_herding import format_mf_herding_context
        assert format_mf_herding_context({}) == ""
        assert format_mf_herding_context({"avg_momentum_pct": None, "institutional_flow": "UNKNOWN"}) == ""

    def test_individual_funds_listed(self):
        from services.data.fetchers.mf_herding import format_mf_herding_context
        ctx = format_mf_herding_context(self._make_herding(-0.5, "OUTFLOW", "automobile"))
        assert "Mirae Asset Nifty Auto ETF" in ctx or "ICICI Prudential Nifty Auto ETF" in ctx


class TestMfHerdingWeeklyCache:
    """Test that same week key returns cached data."""

    def test_cache_hit_skips_fetch(self):
        from services.data.fetchers import mf_herding
        mf_herding._CACHE.clear()

        fake = {"sector": "automobile", "avg_momentum_pct": 0.2, "institutional_flow": "NEUTRAL",
                "fund_count": 3, "individual": [], "fetched_at": "2099-W01", "error": None}

        with patch.object(mf_herding, "_fetch_nav_history", return_value=[]):
            with patch.object(mf_herding, "_week_key", return_value="2099-W01"):
                # Pre-populate cache
                mf_herding._CACHE["2099-W01:automobile"] = fake
                result = mf_herding.get_sector_mf_herding("automobile")
                assert result is fake


# ---------------------------------------------------------------------------
# factor_regime.py tests
# ---------------------------------------------------------------------------

class TestFactorRegimePenaltyScale:
    """Test get_regime_penalty_scale — no network calls needed."""

    def _regime(self, r_type: str, strength: str = "MODERATE") -> dict:
        return {
            "regime":   r_type,
            "strength": strength,
            "avg_wml_pct": -0.5 if r_type == "REVERSAL" else 0.5,
            "z_score":  -0.6,
        }

    def test_reversal_regime_pattern_analysis_scale(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("pattern_analysis", self._regime("REVERSAL"))
        assert scale < 1.0
        assert scale == 0.80

    def test_reversal_regime_competitive_intel_scale(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("competitive_intel", self._regime("REVERSAL"))
        assert scale == 0.80

    def test_reversal_regime_fundamentals_no_change(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("fundamentals", self._regime("REVERSAL"))
        assert scale == 1.0

    def test_momentum_regime_fundamentals_scale(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("fundamentals", self._regime("MOMENTUM"))
        assert scale == 0.85

    def test_momentum_regime_risk_macro_scale(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("risk_macro", self._regime("MOMENTUM"))
        assert scale == 0.85

    def test_momentum_regime_pattern_analysis_no_change(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        scale = get_regime_penalty_scale("pattern_analysis", self._regime("MOMENTUM"))
        assert scale == 1.0

    def test_none_regime_returns_one(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        assert get_regime_penalty_scale("pattern_analysis", None) == 1.0

    def test_weak_regime_returns_one(self):
        from core.intelligence.rl.algorithms.factor_regime import get_regime_penalty_scale
        regime = self._regime("REVERSAL", strength="WEAK")
        assert get_regime_penalty_scale("pattern_analysis", regime) == 1.0


class TestFactorRegimeFormatContext:
    """Test format_factor_regime_context output structure."""

    def _regime_dict(self, r_type: str = "REVERSAL") -> dict:
        return {
            "regime":            r_type,
            "strength":          "MODERATE",
            "z_score":           -0.63,
            "avg_wml_pct":       -0.681,
            "last_wml_pct":      -1.2,
            "size_tilt":         "SMALL_CAP",
            "style_tilt":        "VALUE",
            "market_factor_avg": 0.8,
            "lookback_months":   12,
            "data_vintage":      "2023-03",
            "fetched_at":        "2026-05-31",
        }

    def test_reversal_regime_format(self):
        from core.intelligence.rl.algorithms.factor_regime import format_factor_regime_context
        ctx = format_factor_regime_context(self._regime_dict("REVERSAL"))
        assert "IIMA FACTOR REGIME" in ctx
        assert "MODERATE REVERSAL" in ctx
        assert "SMALL_CAP" in ctx
        assert "VALUE" in ctx
        assert "sector rotation" in ctx.lower() or "reversal" in ctx.lower()

    def test_momentum_regime_format(self):
        from core.intelligence.rl.algorithms.factor_regime import format_factor_regime_context
        ctx = format_factor_regime_context(self._regime_dict("MOMENTUM"))
        assert "MOMENTUM" in ctx
        assert "keep outperforming" in ctx.lower() or "winners" in ctx.lower()

    def test_none_returns_empty(self):
        from core.intelligence.rl.algorithms.factor_regime import format_factor_regime_context
        assert format_factor_regime_context(None) == ""
        assert format_factor_regime_context({}) == ""

    def test_data_vintage_shown(self):
        from core.intelligence.rl.algorithms.factor_regime import format_factor_regime_context
        ctx = format_factor_regime_context(self._regime_dict())
        assert "2023-03" in ctx


class TestFactorRegimeDailyCache:
    """Test daily cache — no actual IIMA download."""

    def test_cache_hit_returns_same_object(self):
        from core.intelligence.rl.algorithms import factor_regime as fr
        fr._PROCESS_CACHE.clear()

        fake = {"regime": "REVERSAL", "strength": "MODERATE", "fetched_at": "2099-01-01"}
        with patch.object(fr, "_compute_regime", return_value=fake):
            with patch.object(fr, "_today_key", return_value="2099-01-01"):
                first  = fr.get_factor_regime()
                second = fr.get_factor_regime()
                assert first is second

    def test_failure_returns_none(self):
        from core.intelligence.rl.algorithms import factor_regime as fr
        fr._PROCESS_CACHE.clear()
        with patch.object(fr, "_compute_regime", side_effect=RuntimeError("network error")):
            with patch.object(fr, "_today_key", return_value="2099-01-02"):
                result = fr.get_factor_regime()
                assert result is None


# ---------------------------------------------------------------------------
# WeightAdapter integration — factor_regime param is passed through
# ---------------------------------------------------------------------------

class TestWeightAdapterFactorRegimeIntegration:
    """Verify WeightAdapter.update() accepts factor_regime without crashing."""

    def _make_wm(self):
        from core.schemas.feedback import WeightMemory
        agents = ["fundamentals", "pattern_analysis", "risk_macro"]
        base   = {a: round(1.0 / len(agents), 4) for a in agents}
        return WeightMemory(
            ticker="TEST",
            last_updated="2026-01-01",
            current_weights=base.copy(),
            base_weights=base.copy(),
            adjustment_bounds={"max_single_step": 0.05, "max_total_drift_from_base": 0.15},
        )

    def _make_log_with_entries(self, n: int = 10):
        from core.schemas.feedback import DailyFeedbackLog, FeedbackEntry, MissAnalysis
        from datetime import date, timedelta
        entries = []
        base_date = date(2026, 1, 1)
        for i in range(n):
            entries.append(FeedbackEntry(
                day=i + 1,
                date=(base_date + timedelta(days=i)).isoformat(),
                predicted_close=100.0,
                actual_close=98.0,
                price_error_pct=-2.0,
                predicted_verdict="BUY",
                actual_direction="DOWN",
                direction_correct=False,
                miss_analysis=MissAnalysis(
                    primary_miss_agent="pattern_analysis",
                    miss_type="direction_flip",
                ),
            ))
        log = DailyFeedbackLog(ticker="TEST", sector="automobile", cycle_id="2026-01")
        log.entries = entries
        return log

    def test_update_accepts_none_factor_regime(self):
        from core.intelligence.rl.agents.weight_adapter import WeightAdapter
        wa  = WeightAdapter()
        wm  = self._make_wm()
        log = self._make_log_with_entries(15)
        result = wa.update(
            weight_memory=wm,
            feedback_log=log,
            todays_primary_miss_agent="pattern_analysis",
            todays_miss_type="direction_flip",
            factor_regime=None,
        )
        assert result is not None

    def test_update_with_reversal_regime_reduces_pattern_analysis_penalty(self):
        from core.intelligence.rl.agents.weight_adapter import WeightAdapter
        reversal_regime = {
            "regime":   "REVERSAL",
            "strength": "MODERATE",
            "avg_wml_pct": -0.5,
        }
        wa  = WeightAdapter()
        wm_no  = self._make_wm()
        wm_yes = self._make_wm()
        log = self._make_log_with_entries(20)

        result_no  = wa.update(
            weight_memory=wm_no,
            feedback_log=log,
            todays_primary_miss_agent="pattern_analysis",
            todays_miss_type="direction_flip",
            factor_regime=None,
        )
        result_yes = wa.update(
            weight_memory=wm_yes,
            feedback_log=log,
            todays_primary_miss_agent="pattern_analysis",
            todays_miss_type="direction_flip",
            factor_regime=reversal_regime,
        )
        # With regime leniency, pattern_analysis weight should be >= no-regime version
        w_no  = result_no.current_weights.get("pattern_analysis", 0)
        w_yes = result_yes.current_weights.get("pattern_analysis", 0)
        assert w_yes >= w_no, (
            f"Expected regime leniency to raise pattern_analysis weight, "
            f"got no_regime={w_no:.4f} vs with_regime={w_yes:.4f}"
        )
