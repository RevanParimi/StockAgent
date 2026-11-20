"""Tests for Unified Sector Analyst settings (2026-06-12 redesign)."""

from core.config import settings


def test_unified_analyst_settings_defaults():
    assert settings.UNIFIED_ANALYST_MAX_TOKENS == 6000
    assert settings.UNIFIED_SECTION_MAX_CHARS == 2500
    assert settings.UNIFIED_BUNDLE_MAX_CHARS == 18000


def test_no_setting_can_route_an_analysis_elsewhere():
    """CLEAN-005: the per-sector switch and the backup switch are gone, so no
    value in the environment or config.yaml can send a path to another
    method. Every path has its one-call spec."""
    from backend.shared.pipeline.unified_analyst import SECTOR_SPECS

    for name in ("UNIFIED_ANALYST_SECTORS", "UNIFIED_ANALYST_FALLBACK_LEGACY",
                 "unified_analyst_sectors"):
        assert not hasattr(settings, name)
    assert set(SECTOR_SPECS) == {
        "automobile", "banking_bfsi", "it_sector", "renewable_energy", "generic",
    }
