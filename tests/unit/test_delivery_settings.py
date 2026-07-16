"""Compass Phase C — delivery + IPO-tracker tunables exposed via settings."""
from core.config import settings


def test_ipo_settings_present():
    assert settings.DISCOVERY_IPO_ENABLED is True       # yaml true; base.py fallback False
    assert settings.DISCOVERY_IPO_LISTING_WINDOW_DAYS == 90
    assert settings.DISCOVERY_IPO_MAX_DEEP_DIVES == 2
    assert settings.DISCOVERY_IPO_LOCKIN_WARN_DAYS == 7
    assert settings.DISCOVERY_IPO_QIB_WEIGHT == 3.0


def test_ipo_budget_within_deep_dive_budget():
    assert settings.DISCOVERY_IPO_MAX_DEEP_DIVES < settings.DISCOVERY_DEEP_DIVE_COUNT


def test_switch_gap_present():
    assert settings.ADVISOR_SWITCH_CONVICTION_GAP == 0.15


def test_delivery_settings_present():
    assert settings.DELIVERY_ENABLED is True            # yaml true; base.py fallback False
    assert settings.DELIVERY_DATA_DIR == "data/delivery"
    # DELIVERY_EMAIL_ENABLED is an env-driven operator switch (flipped on when
    # SMTP went live 2026-07-16) — assert type, not the machine's current value.
    assert isinstance(settings.DELIVERY_EMAIL_ENABLED, bool)
    assert settings.DELIVERY_PUSH_ENABLED is True
    assert "NIFTY 50" in settings.DELIVERY_INDEX_WATCH
    assert len(settings.DELIVERY_INDEX_WATCH) == 4


def test_delivery_secrets_are_env_only_strings():
    # Secrets default empty (they live in .env, never config.yaml)
    assert isinstance(settings.SMTP_HOST, str)
    assert isinstance(settings.SMTP_PORT, int)
    assert isinstance(settings.DELIVERY_EMAIL_TO, str)
    assert isinstance(settings.VAPID_PRIVATE_KEY, str)
    assert isinstance(settings.VAPID_PUBLIC_KEY, str)
    assert settings.VAPID_CLAIM_EMAIL  # non-empty fallback (mailto: claim needs a value)
