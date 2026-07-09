"""Compass Phase B — discovery + generic-graph tunables exposed via settings."""
from core.config import settings


def test_discovery_settings_present():
    assert settings.DISCOVERY_ENABLED is True          # yaml true; base.py fallback False
    assert settings.DISCOVERY_HISTORY_DAYS == 550
    assert settings.DISCOVERY_BHAVCOPY_DIR == "data/market_cache/bhavcopy"
    assert settings.DISCOVERY_DATA_DIR == "data/discovery"
    assert settings.PAPER_PREDICTION_DATA_DIR == "data/rl/paper/predictions"
    assert settings.DISCOVERY_LIQUIDITY_FLOOR_CR == 5.0
    assert settings.DISCOVERY_FLOAT_MCAP_FLOOR_CR == 500.0
    assert settings.DISCOVERY_MIN_PRICE == 20.0
    assert settings.DISCOVERY_MAX_PLEDGE_PCT == 25.0
    assert settings.DISCOVERY_CIRCUIT_STREAK_MAX == 3
    assert settings.DISCOVERY_SHORTLIST_SIZE == 80
    assert settings.DISCOVERY_MAX_CANDIDATES == 40
    assert settings.DISCOVERY_DEEP_DIVE_COUNT == 10
    assert settings.DISCOVERY_SHELF_SIZE == 10
    assert settings.DISCOVERY_STALE_DAYS == 60
    assert settings.DISCOVERY_MIN_CONVICTION == 0.55
    assert settings.DISCOVERY_INCLUDE_SME is False


def test_discovery_signal_weights_sum_to_one():
    w = settings.DISCOVERY_SIGNAL_WEIGHTS
    assert set(w) == {"momentum", "delivery_surge", "volume_breakout",
                      "bulk_block", "high_52wk_rs", "insider_buying", "mf_holding"}
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["momentum"] == 0.30


def test_generic_agent_weights_sum_to_one():
    w = settings.GENERIC_AGENT_WEIGHTS
    assert set(w) == {"business", "fundamentals", "valuation", "technical",
                      "macro", "risk", "management", "earnings"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_generic_on_unified_path_and_regime_role_mapped():
    sectors = {s.strip() for s in settings.UNIFIED_ANALYST_SECTORS.split(",")}
    assert "generic" in sectors
    role_map = settings.SECTOR_AGENT_REGIME_ROLE["generic"]
    assert role_map["technical"] == "pattern_analysis"
    assert role_map["macro"] == "risk_macro"
