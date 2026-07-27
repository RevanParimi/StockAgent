"""Piece C (spec 2026-07-27): global-stress detection + escalation notch."""
from core.intelligence.regime.detector import RegimeDetector


def test_stress_signal_thresholds():
    f = RegimeDetector._global_stress_signals
    assert f(9.0, 0.0, 0.0) == ["brent_shock"]          # brent >= +8
    assert f(0.0, 1.6, 0.0) == ["usdinr_stress"]        # usdinr >= +1.5
    assert f(0.0, 0.0, -2.5) == ["spx_drop"]            # spx <= -2
    assert f(9.0, 1.6, -2.5) == ["brent_shock", "usdinr_stress", "spx_drop"]
    assert f(7.9, 1.4, -1.9) == []


def test_none_inputs_never_fire():
    assert RegimeDetector._global_stress_signals(None, None, None) == []
    assert RegimeDetector._global_stress_signals(None, 1.6, None) == ["usdinr_stress"]


def test_escalation_ladder():
    esc = RegimeDetector._escalate_label
    for base in ("NORMAL", "RISK_ON", "MOMENTUM_EXTENDED", "OVERSOLD"):
        assert esc(base, 2) == "RISK_OFF"
    assert esc("RISK_OFF", 2) == "MACRO_CRISIS"
    assert esc("MACRO_CRISIS", 3) == "MACRO_CRISIS"


def test_below_min_signals_never_escalates():
    for base in ("NORMAL", "RISK_OFF", "MACRO_CRISIS"):
        assert RegimeDetector._escalate_label(base, 0) == base
        assert RegimeDetector._escalate_label(base, 1) == base


def test_snapshot_schema_has_optional_stress_fields():
    from core.schemas.feedback import RegimeSnapshot
    s = RegimeSnapshot()          # old callers construct with no new args
    assert s.brent_5d_pct is None
    assert s.global_stress_signals == []
