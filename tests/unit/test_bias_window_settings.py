"""tests/unit/test_bias_window_settings.py — Wave I.

The bias-detection windows were the last WeightAdapter constants hardcoded in
code rather than settings. Pin the defaults (unchanged behavior) and that the
adapter reads them from settings.
"""
from backend.shared.config import settings


def test_bias_window_defaults():
    assert settings.RL_BIAS_WINDOWS == [5, 10, 21]
    assert settings.RL_BIAS_WINDOW_WEIGHTS == [0.50, 0.30, 0.20]
    assert len(settings.RL_BIAS_WINDOWS) == len(settings.RL_BIAS_WINDOW_WEIGHTS)


def test_weight_adapter_reads_from_settings():
    import core.intelligence.rl.agents.weight_adapter as wa
    assert wa._BIAS_WINDOWS is settings.RL_BIAS_WINDOWS
    assert wa._BIAS_WINDOW_WEIGHTS is settings.RL_BIAS_WINDOW_WEIGHTS
