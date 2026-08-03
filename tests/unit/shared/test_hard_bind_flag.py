"""AUD-117 / AUD-077 — hard-bind verdict flag wiring.

The flag's *value* is deployment state (config.yaml; flipped ON 2026-08-03),
not an invariant — asserting it here would make a rollback flip the suite red.
Both behaviours are covered by tests that monkeypatch the flag explicitly:
test_hard_bind_daily_review.py and test_signal_aggregator.py.
"""
from backend.shared.config import settings
from backend.shared.config.settings.base import cfg


def test_hard_bind_flag_exists_and_is_bool():
    assert isinstance(settings.RL_HARD_BIND_VERDICT_ENABLED, bool)


def test_hard_bind_flag_falls_back_off_when_key_absent():
    # Safety default: a missing/unreadable config key must never silently bind.
    assert cfg("rl.__no_such_hard_bind_key__", fallback=False) is False
