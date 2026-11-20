"""
pipeline/orchestrator.py — GenericSectorOrchestrator (Compass Phase B).

Sector-agnostic path for tickers whose sector has no native one: one data
bundle and one analysis call scoring eight dimensions (prompts/unified.py),
with the generic weights. When that call scores nothing there is no analysis
(CLEAN-005), never a second method.
"""
from __future__ import annotations

from backend.shared.config import settings
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator


class GenericSectorOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "generic"

    def _get_default_weights(self) -> dict[str, float]:
        return dict(settings.GENERIC_AGENT_WEIGHTS)
