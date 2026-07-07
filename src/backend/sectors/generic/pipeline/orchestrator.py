"""
pipeline/orchestrator.py — GenericSectorOrchestrator (Compass Phase B).

Sector-agnostic orchestrator for tickers whose sector has no native graph.
Primary path: the Unified Analyst ("generic" is in UNIFIED_ANALYST_SECTORS,
so BaseSectorOrchestrator._run_agents dispatches to _run_unified — one
reasoning-model call for all 8 dimensions). Fallback path: 8 UniversalAgents
built from prompts/dimensions.py (only on unified total failure with
UNIFIED_ANALYST_FALLBACK_LEGACY=true).
"""
from __future__ import annotations

from backend.shared.config import settings
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.agents.universal import UniversalAgent
from backend.sectors.generic.prompts import dimensions as D


class GenericSectorOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "generic"

    def __init__(self) -> None:
        self._sub_agents = {
            dim: UniversalAgent(dim, D.PROMPTS[dim], sector="generic")
            for dim in D.DIMENSIONS
        }
        super().__init__()

    def _get_default_weights(self) -> dict[str, float]:
        return dict(settings.GENERIC_AGENT_WEIGHTS)
