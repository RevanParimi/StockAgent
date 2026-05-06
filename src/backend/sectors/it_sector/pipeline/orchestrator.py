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
