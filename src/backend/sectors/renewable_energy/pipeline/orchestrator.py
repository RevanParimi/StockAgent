"""The renewable_energy analysis path: one data bundle and one analysis call
(prompts/unified.py)."""
from __future__ import annotations

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator


class RenewableAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for renewable_energy stock analysis."""
    SECTOR_NAME = "renewable_energy"

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
