"""Tests for Unified Sector Analyst settings (2026-06-12 redesign)."""

from core.config import settings


def test_unified_analyst_settings_defaults():
    assert settings.UNIFIED_ANALYST_SECTORS == "automobile,banking_bfsi,it_sector,renewable_energy,generic"
    assert settings.UNIFIED_ANALYST_FALLBACK_LEGACY is True
    assert settings.UNIFIED_ANALYST_MAX_TOKENS == 6000
    assert settings.UNIFIED_SECTION_MAX_CHARS == 2500
    assert settings.UNIFIED_BUNDLE_MAX_CHARS == 18000


def test_unified_sectors_helper():
    from core.config.settings import unified_analyst_sectors

    assert unified_analyst_sectors() == {
        "automobile", "banking_bfsi", "it_sector", "renewable_energy", "generic",
    }
