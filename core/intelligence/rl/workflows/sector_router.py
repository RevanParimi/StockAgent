"""
core/intelligence/rl/workflows/sector_router.py
================================================
Maps sector strings to the correct orchestrator and weight config.

Used by generate_forecast and daily_review so both use the same routing
logic — a single place to add new sectors.

PI task A1: routing itself now lives in `backend.sectors.registry`. This
module used to keep its OWN sector → orchestrator map, and the two drifted:
the registry degraded every disabled sector to the automobile graph while
this module sent it to the generic graph, so the same stock got two different
analyses depending on which entry point ran it (spec §2.1). That divergence
is what minted the duplicate prediction stores. There is one map now, in the
registry; this module keeps only the weight-module lookup, which is genuinely
RL-specific.

Sectors WITHOUT a native graph (pharma, fmcg, metals, …) route to the GENERIC
sector graph (sector-agnostic unified analyst + neutral weights). The
PredictionStore keeps using the REAL sector name for its directory layout
(data/predictions/pharma/SUNPHARMA/…) — only the analysis graph is generic.
"""
from __future__ import annotations

import importlib
import logging

from backend.sectors.registry import (  # single source — do not re-declare
    GENERIC_SECTOR,
    NATIVE_SECTORS,
    SectorRegistry,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GENERIC_SECTOR",
    "NATIVE_SECTORS",
    "get_orchestrator",
    "get_orchestrator_class",
    "get_sector_weights",
]

# sector → dotted module path that contains AGENT_WEIGHTS
_WEIGHT_MODULES: dict[str, str] = {
    "automobile":       "core.config.settings",
    "renewable_energy": "backend.sectors.renewable_energy.config.settings",
    "banking_bfsi":     "backend.sectors.banking_bfsi.config.settings",
    "it_sector":        "backend.sectors.it_sector.config.settings",
}


def get_orchestrator_class(sector: str):
    """Return the orchestrator class for a sector, without building it."""
    cls = SectorRegistry.get_handler(sector)
    logger.debug("[sector_router] Resolved '%s' → %s", sector, cls.__name__)
    return cls


def get_orchestrator(sector: str):
    """Return a freshly instantiated orchestrator for the given sector."""
    return get_orchestrator_class(sector)()


def get_sector_weights(sector: str) -> dict[str, float]:
    """
    Return the sector-specific AGENT_WEIGHTS dict.
    Used to initialise WeightMemory with the right baseline. Sectors without
    a native graph get the neutral generic weights (config generic_graph.*).

    Keyed off the sector whose GRAPH runs, not the requested sector, so the
    weights can never describe a different agent set than the graph that
    produced the scores.
    """
    graph_sector = SectorRegistry.get_graph_sector(sector)
    mod_path = _WEIGHT_MODULES.get(graph_sector)
    if mod_path is None:
        from core.config import settings
        logger.info(
            "[sector_router] Sector '%s' has no native weight module — using generic weights",
            sector,
        )
        return dict(settings.GENERIC_AGENT_WEIGHTS)

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
