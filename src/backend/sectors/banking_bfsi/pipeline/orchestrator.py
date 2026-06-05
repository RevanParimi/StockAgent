"""Orchestrator for banking_bfsi."""
from __future__ import annotations
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.sectors.banking_bfsi.config.registry import AGENTS

class BankingAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for banking_bfsi stock analysis."""
    SECTOR_NAME = "banking_bfsi"

    def __init__(self) -> None:
        self._sub_agents = AGENTS
        super().__init__()

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
