"""Orchestrator for it_sector."""
from __future__ import annotations
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.sectors.it_sector.config.registry import AGENTS

class ITAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for it_sector stock analysis."""
    SECTOR_NAME = "it_sector"

    def __init__(self) -> None:
        self._sub_agents = AGENTS
        super().__init__()

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
