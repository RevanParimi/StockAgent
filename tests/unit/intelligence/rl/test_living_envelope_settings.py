"""Tests for Living Envelope (RL Phase 2.5) settings — shock-robust forecasting."""

from core.config import settings


def test_living_envelope_settings_defaults():
    assert settings.RL_REFORECAST_ENABLED is True
    assert settings.RL_REFORECAST_MAX_PER_MONTH == 2
    assert settings.RL_REFORECAST_THESIS_MULT_THRESHOLD == 0.5
    assert settings.RL_REGIME_STICKY_ENABLED is True
    assert settings.RL_REGIME_CALM_DAYS == 3
    assert settings.RL_PREOPEN_CHECK_ENABLED is True
    assert settings.RL_PREOPEN_SHOCK_SEVERITY == 0.7
