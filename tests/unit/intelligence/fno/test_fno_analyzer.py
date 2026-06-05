"""
tests/unit/intelligence/fno/test_fno_analyzer.py
================================================
G7b: F&O Options Chain Analyzer.

What is verified:
  FnOAnalyzer.analyze():
    - Returns FnOSnapshot with correct ticker/date fields
    - Empty chain_data returns FnOSnapshot with all signals None
    - PCR computed as total_put_OI / total_call_OI
    - PCR is None when total_call_OI is 0

  _compute_pcr():
    - Correct ratio from known OI values
    - None when call OI is zero

  _compute_max_pain():
    - Returns the strike with minimum total option buyer payoff
    - Verified against manually computed value for 3-strike chain

  _compute_oi_buildup():
    - Returns LONG when near-ATM call_OI >> put_OI (ratio > 1.3)
    - Returns SHORT when near-ATM put_OI >> call_OI
    - Returns NEUTRAL when balanced or no near-ATM OI

  _find_atm_strike():
    - Returns strike nearest to current price

  FnOSnapshot.to_context_string():
    - Returns empty string when pcr is None
    - Includes "bearish" when PCR > 1.5
    - Includes "bullish" when PCR < 0.7
    - Includes max pain price
    - Includes OI buildup direction
"""

import pytest

from core.intelligence.fno.analyzer import FnOAnalyzer
from core.schemas.feedback import FnOSnapshot


# ---------------------------------------------------------------------------
# Helpers: synthetic option chain builder
# ---------------------------------------------------------------------------

def _row(strike: float, call_oi: int = 0, put_oi: int = 0) -> dict:
    """Build a synthetic chain row in NSE optionChain format."""
    return {
        "strikePrice": strike,
        "expiryDate": "28-May-2026",
        "CE": {"openInterest": call_oi},
        "PE": {"openInterest": put_oi},
    }


def _chain_3strikes():
    """
    3-strike chain for deterministic max-pain computation:
      Strike 900: CE OI=0, PE OI=1000
      Strike 1000: CE OI=500, PE OI=500
      Strike 1100: CE OI=1000, PE OI=0
    Current price: 1000

    Max pain = argmin_K Σ[max(0,K-s)×CE_OI + max(0,s-K)×PE_OI]
    At K=900: CE loss=0, PE loss=sum(max(0,s-900)*PE_OI) = max(0,1000-900)*500=50000 + max(0,1100-900)*0=0 → 50000
              Actually: Σ_s [max(0,K-s)×CE_OI(s) + max(0,s-K)×PE_OI(s)]
              At K=900:
                s=900:  max(0,900-900)×0 + max(0,900-900)×1000 = 0
                s=1000: max(0,900-1000)×500 + max(0,1000-900)×500 = 0 + 50000 = 50000
                s=1100: max(0,900-1100)×1000 + max(0,1100-900)×0 = 0 + 0 = 0
              Total at K=900: 50000
    At K=1000:
                s=900:  max(0,1000-900)×0 + max(0,900-1000)×1000 = 0
                s=1000: max(0,1000-1000)×500 + max(0,1000-1000)×500 = 0
                s=1100: max(0,1000-1100)×1000 + max(0,1100-1000)×0 = 0
              Total at K=1000: 0
    At K=1100:
                s=900:  max(0,1100-900)×0 + max(0,900-1100)×1000 = 0
                s=1000: max(0,1100-1000)×500 + max(0,1000-1100)×500 = 50000
                s=1100: max(0,1100-1100)×1000 + max(0,1100-1100)×0 = 0
              Total at K=1100: 50000
    → Min pain is at K=1000 → max_pain_price = 1000
    """
    return [
        _row(900,  call_oi=0,    put_oi=1000),
        _row(1000, call_oi=500,  put_oi=500),
        _row(1100, call_oi=1000, put_oi=0),
    ]


def _chain_with_pcr(call_total: int, put_total: int):
    """Single-strike chain with known OI for PCR testing."""
    return [_row(1000, call_oi=call_total, put_oi=put_total)]


# ---------------------------------------------------------------------------
# FnOAnalyzer.analyze() — top-level integration
# ---------------------------------------------------------------------------

class TestFnOAnalyzerAnalyze:
    def _analyzer(self):
        return FnOAnalyzer()

    def test_returns_fno_snapshot(self):
        snap = self._analyzer().analyze(_chain_3strikes(), 1000.0, "MARUTI", "2026-05-26")
        assert isinstance(snap, FnOSnapshot)

    def test_fields_set_correctly(self):
        snap = self._analyzer().analyze(_chain_3strikes(), 1000.0, "MARUTI", "2026-05-26")
        assert snap.ticker == "MARUTI"
        assert snap.date == "2026-05-26"
        assert snap.current_price == 1000.0

    def test_empty_chain_returns_blank_snapshot(self):
        snap = self._analyzer().analyze([], 1000.0, "MARUTI", "2026-05-26")
        assert snap.pcr is None
        assert snap.max_pain_price is None
        assert snap.oi_buildup_direction is None

    def test_pcr_computed_in_full_analysis(self):
        # 2000 put OI, 1000 call OI → PCR = 2.0
        chain = [
            _row(900,  call_oi=0,    put_oi=1000),
            _row(1000, call_oi=1000, put_oi=1000),
        ]
        snap = self._analyzer().analyze(chain, 950.0, "MARUTI", "2026-05-26")
        assert snap.pcr is not None
        assert snap.pcr == pytest.approx(2000 / 1000, rel=0.01)

    def test_atm_strike_set(self):
        snap = self._analyzer().analyze(_chain_3strikes(), 980.0, "MARUTI", "2026-05-26")
        assert snap.atm_strike == 1000.0  # nearest to 980

    def test_max_pain_deviation_computed(self):
        snap = self._analyzer().analyze(_chain_3strikes(), 1000.0, "MARUTI", "2026-05-26")
        # current == max_pain → deviation = 0%
        assert snap.max_pain_deviation_pct == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# _compute_pcr()
# ---------------------------------------------------------------------------

class TestComputePCR:
    def _analyzer(self):
        return FnOAnalyzer()

    def test_known_ratio(self):
        chain = _chain_with_pcr(call_total=1000, put_total=1500)
        pcr = self._analyzer()._compute_pcr(chain)
        assert pcr == pytest.approx(1.5, rel=0.001)

    def test_none_when_no_calls(self):
        chain = _chain_with_pcr(call_total=0, put_total=500)
        pcr = self._analyzer()._compute_pcr(chain)
        assert pcr is None

    def test_zero_pcr_when_no_puts(self):
        chain = _chain_with_pcr(call_total=1000, put_total=0)
        pcr = self._analyzer()._compute_pcr(chain)
        assert pcr == pytest.approx(0.0)

    def test_total_oi_fields_set(self):
        chain = [
            _row(900,  call_oi=300, put_oi=200),
            _row(1000, call_oi=700, put_oi=800),
        ]
        snap = FnOAnalyzer().analyze(chain, 950.0, "MARUTI", "2026-05-26")
        assert snap.total_call_oi == 1000
        assert snap.total_put_oi == 1000


# ---------------------------------------------------------------------------
# _compute_max_pain()
# ---------------------------------------------------------------------------

class TestComputeMaxPain:
    def _analyzer(self):
        return FnOAnalyzer()

    def test_max_pain_at_expected_strike(self):
        """3-strike chain: min pain = 0 at K=1000 (see docstring above)."""
        pain_strike = self._analyzer()._compute_max_pain(_chain_3strikes())
        assert pain_strike == pytest.approx(1000.0)

    def test_none_for_empty_chain(self):
        assert self._analyzer()._compute_max_pain([]) is None

    def test_single_strike_returns_that_strike(self):
        chain = [_row(1000, call_oi=500, put_oi=500)]
        result = self._analyzer()._compute_max_pain(chain)
        assert result == pytest.approx(1000.0)

    def test_asymmetric_chain(self):
        """Heavy call OI at 1100 and put OI at 900 — pain minimised near center."""
        chain = [
            _row(900,  call_oi=0,    put_oi=10000),
            _row(1000, call_oi=5000, put_oi=5000),
            _row(1100, call_oi=10000, put_oi=0),
        ]
        # At K=1000: 0 (same logic as above)
        result = self._analyzer()._compute_max_pain(chain)
        assert result == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# _compute_oi_buildup()
# ---------------------------------------------------------------------------

class TestComputeOIBuildup:
    def _analyzer(self):
        return FnOAnalyzer()

    def _buildup(self, chain, price):
        return self._analyzer()._compute_oi_buildup(chain, price)

    def test_long_when_call_oi_dominates_atm(self):
        # current_price=1000, ATM ±3% = [970, 1030]
        # strike 1000 is within range; call_oi=2000 >> put_oi=500 (ratio > 1.3) → LONG
        chain = [
            _row(1000, call_oi=2000, put_oi=500),
            _row(1300, call_oi=0, put_oi=9000),  # far OTM, outside ±3%
        ]
        assert self._buildup(chain, 1000.0) == "LONG"

    def test_short_when_put_oi_dominates_atm(self):
        chain = [
            _row(1000, call_oi=300, put_oi=2000),
            _row(700,  call_oi=5000, put_oi=0),   # far OTM, outside ±3%
        ]
        assert self._buildup(chain, 1000.0) == "SHORT"

    def test_neutral_when_balanced(self):
        chain = [_row(1000, call_oi=1000, put_oi=1000)]
        assert self._buildup(chain, 1000.0) == "NEUTRAL"

    def test_neutral_when_no_near_atm_strikes(self):
        # All strikes are far from current price
        chain = [
            _row(500,  call_oi=5000, put_oi=0),
            _row(1500, call_oi=0, put_oi=5000),
        ]
        assert self._buildup(chain, 1000.0) == "NEUTRAL"

    def test_long_when_no_puts_at_atm(self):
        chain = [_row(1000, call_oi=500, put_oi=0)]
        assert self._buildup(chain, 1000.0) == "LONG"

    def test_short_when_no_calls_at_atm(self):
        chain = [_row(1000, call_oi=0, put_oi=500)]
        assert self._buildup(chain, 1000.0) == "SHORT"


# ---------------------------------------------------------------------------
# _find_atm_strike()
# ---------------------------------------------------------------------------

class TestFindATMStrike:
    def _analyzer(self):
        return FnOAnalyzer()

    def test_exact_match(self):
        chain = [_row(900), _row(1000), _row(1100)]
        assert self._analyzer()._find_atm_strike(chain, 1000.0) == 1000.0

    def test_nearest_below(self):
        chain = [_row(900), _row(1000), _row(1100)]
        # price=980 → nearest is 1000 (diff=20) vs 900 (diff=80)
        assert self._analyzer()._find_atm_strike(chain, 980.0) == 1000.0

    def test_nearest_above(self):
        chain = [_row(900), _row(1000), _row(1100)]
        # price=1020 → nearest is 1000 (diff=20) vs 1100 (diff=80)
        assert self._analyzer()._find_atm_strike(chain, 1020.0) == 1000.0

    def test_none_for_empty_chain(self):
        assert self._analyzer()._find_atm_strike([], 1000.0) is None


# ---------------------------------------------------------------------------
# FnOSnapshot.to_context_string()
# ---------------------------------------------------------------------------

class TestFnOSnapshotToContextString:
    def test_empty_when_pcr_is_none(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI")
        assert snap.to_context_string() == ""

    def test_includes_pcr_line(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=1.2, oi_buildup_direction="NEUTRAL")
        ctx = snap.to_context_string()
        assert "PCR" in ctx
        assert "1.20" in ctx

    def test_bearish_signal_when_pcr_above_1_5(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=1.8, oi_buildup_direction="SHORT")
        ctx = snap.to_context_string()
        assert "bearish" in ctx

    def test_bullish_signal_when_pcr_below_0_7(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=0.5, oi_buildup_direction="LONG")
        ctx = snap.to_context_string()
        assert "bullish" in ctx

    def test_neutral_signal_when_pcr_in_range(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=1.0, oi_buildup_direction="NEUTRAL")
        ctx = snap.to_context_string()
        assert "neutral" in ctx

    def test_includes_max_pain_when_set(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=1.0, oi_buildup_direction="NEUTRAL",
                           max_pain_price=950.0, current_price=1000.0,
                           max_pain_deviation_pct=-5.0)
        ctx = snap.to_context_string()
        assert "950" in ctx
        assert "Max Pain" in ctx

    def test_includes_oi_buildup_direction(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=0.6, oi_buildup_direction="LONG")
        ctx = snap.to_context_string()
        assert "LONG" in ctx

    def test_includes_date_header(self):
        snap = FnOSnapshot(date="2026-05-26", ticker="MARUTI",
                           pcr=1.0, oi_buildup_direction="NEUTRAL")
        ctx = snap.to_context_string()
        assert "2026-05-26" in ctx
