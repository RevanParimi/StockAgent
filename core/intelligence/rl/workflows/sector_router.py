"""
core/intelligence/rl/workflows/sector_router.py
================================================
Maps sector strings to the correct orchestrator and weight config.

Used by generate_forecast and daily_review so both use the same routing
logic — a single place to add new sectors.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# sector → dotted path to orchestrator class
_ORCHESTRATORS: dict[str, str] = {
    "automobile":       "core.pipeline.orchestrator.AutomobileAgentOrchestrator",
    "renewable_energy": "backend.sectors.renewable_energy.pipeline.orchestrator.RenewableAgentOrchestrator",
    "banking_bfsi":     "backend.sectors.banking_bfsi.pipeline.orchestrator.BankingAgentOrchestrator",
    "it_sector":        "backend.sectors.it_sector.pipeline.orchestrator.ITAgentOrchestrator",
}

# sector → dotted module path that contains AGENT_WEIGHTS
_WEIGHT_MODULES: dict[str, str] = {
    "automobile":       "core.config.settings",
    "renewable_energy": "backend.sectors.renewable_energy.config.settings",
    "banking_bfsi":     "backend.sectors.banking_bfsi.config.settings",
    "it_sector":        "backend.sectors.it_sector.config.settings",
}


def get_orchestrator(sector: str):
    """Return a freshly instantiated orchestrator for the given sector."""
    dotted = _ORCHESTRATORS.get(sector)
    if dotted is None:
        logger.warning(
            "[sector_router] Unknown sector '%s' — falling back to automobile orchestrator", sector
        )
        dotted = _ORCHESTRATORS["automobile"]

    module_path, cls_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    logger.debug("[sector_router] Resolved '%s' → %s", sector, cls_name)
    return cls()


def get_sector_weights(sector: str) -> dict[str, float]:
    """
    Return the sector-specific AGENT_WEIGHTS dict.
    Used to initialise WeightMemory with the right baseline instead of
    always defaulting to automobile weights.
    """
    mod_path = _WEIGHT_MODULES.get(sector)
    if mod_path is None:
        logger.warning(
            "[sector_router] No weight module for sector '%s' — using automobile weights", sector
        )
        mod_path = _WEIGHT_MODULES["automobile"]

    try:
        mod = importlib.import_module(mod_path)
        return dict(mod.AGENT_WEIGHTS)
    except Exception as exc:
        logger.warning(
            "[sector_router] Could not load AGENT_WEIGHTS from '%s': %s — using automobile fallback",
            mod_path, exc,
        )
        from core.config import settings
        return dict(settings.AGENT_WEIGHTS)
