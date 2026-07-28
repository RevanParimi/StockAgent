"""AUD-117 / AUD-077 — hard-bind verdict flag defaults OFF (byte-identical deploy)."""
from backend.shared.config import settings


def test_hard_bind_flag_exists_and_is_bool():
    assert isinstance(settings.RL_HARD_BIND_VERDICT_ENABLED, bool)


def test_hard_bind_flag_defaults_off():
    # Merged OFF ⇒ deploy is a byte-identical no-op (spec §3.1).
    assert settings.RL_HARD_BIND_VERDICT_ENABLED is False
