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


from datetime import date


def _patched_detector(monkeypatch, *, vix=17.0, fii=0.0, rsi=50.0,
                      brent=None, usdinr=None, spx=None):
    d = RegimeDetector()
    monkeypatch.setattr(RegimeDetector, "_get_vix", lambda self, a: vix)
    monkeypatch.setattr(RegimeDetector, "_get_fii_proxy", lambda self, a: fii)
    monkeypatch.setattr(RegimeDetector, "_get_sector_rsi", lambda self, s, a: rsi)
    monkeypatch.setattr(RegimeDetector, "_get_5d_pct",
                        lambda self, t: {"BZ=F": brent, "INR=X": usdinr}.get(t))
    monkeypatch.setattr(RegimeDetector, "_get_last_session_pct", lambda self, t: spx)
    return d


def test_detect_escalates_normal_to_risk_off_on_two_signals(monkeypatch):
    d = _patched_detector(monkeypatch, brent=9.0, usdinr=1.8)
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "RISK_OFF"
    assert snap.global_stress_signals == ["brent_shock", "usdinr_stress"]
    assert snap.brent_5d_pct == 9.0
    assert "brent" in snap.narrative.lower()


def test_detect_single_signal_no_escalation(monkeypatch):
    d = _patched_detector(monkeypatch, brent=9.0)
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "NORMAL"
    assert snap.global_stress_signals == ["brent_shock"]


def test_detect_fetch_failure_degrades_to_current_behavior(monkeypatch):
    d = _patched_detector(monkeypatch)          # all three None
    snap = d.detect(date(2026, 7, 27), "automobile")
    assert snap.regime_label == "NORMAL"
    assert snap.global_stress_signals == []


def test_detect_multipliers_follow_escalated_label(monkeypatch):
    from core.config import settings
    d = _patched_detector(monkeypatch, vix=23.0, fii=-1.5, brent=9.0, spx=-3.0)
    snap = d.detect(date(2026, 7, 27), "automobile")   # MACRO_CRISIS base...
    # base label with vix 23 & fii -1.5 is MACRO_CRISIS; escalation keeps it
    assert snap.regime_label == "MACRO_CRISIS"
    assert snap.multipliers == settings.REGIME_MULTIPLIERS["MACRO_CRISIS"]
