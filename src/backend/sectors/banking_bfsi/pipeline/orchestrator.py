"""The banking_bfsi analysis path: one data bundle and one analysis call
(prompts/unified.py)."""
from __future__ import annotations

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator


class BankingAgentOrchestrator(BaseSectorOrchestrator):
    """Entry point for banking_bfsi stock analysis."""
    SECTOR_NAME = "banking_bfsi"

    def _get_default_weights(self) -> dict[str, float]:
        from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS
        return AGENT_WEIGHTS
