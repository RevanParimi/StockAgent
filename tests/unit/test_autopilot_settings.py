from core.config import settings


def test_autopilot_settings_defaults():
    assert settings.AUTOPILOT_ENABLED is True
    assert settings.AUTOPILOT_ADD_TRANCHE_PCT == 25.0
    assert settings.AUTOPILOT_TRIM_PCT == 25.0
    assert settings.AUTOPILOT_MIN_CASH_FLOOR == 10000.0
    assert settings.AUTOPILOT_ADD_COOLDOWN_TD == 5
