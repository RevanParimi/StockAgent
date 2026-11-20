"""The it_sector analysis path: one data bundle and one analysis call
(prompts/unified.py)."""
from __future__ import annotations

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator


class ITAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for it_sector stock analysis."""
    SECTOR_NAME = "it_sector"

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
