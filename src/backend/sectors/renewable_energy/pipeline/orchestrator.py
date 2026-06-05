"""Orchestrator for renewable_energy."""
from __future__ import annotations
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.sectors.renewable_energy.config.registry import AGENTS

class RenewableAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for renewable_energy stock analysis."""
    SECTOR_NAME = "renewable_energy"

    def __init__(self) -> None:
        self._sub_agents = AGENTS
        super().__init__()

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
