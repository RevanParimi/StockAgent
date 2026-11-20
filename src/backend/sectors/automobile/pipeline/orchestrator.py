"""
src/backend/sectors/automobile/pipeline/orchestrator.py
========================================================
The automobile analysis path: one data bundle and one analysis call scoring
nine dimensions (prompts/unified.py). Everything else is in
BaseSectorOrchestrator.
"""

from __future__ import annotations

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator


class AutomobileAgentOrchestrator(BaseSectorOrchestrator):
    """
    Entry point for Indian automobile stock analysis.

    Usage:
        report = AutomobileAgentOrchestrator().analyse("MARUTI")
        report = await AutomobileAgentOrchestrator().analyse_async("TATAMOTORS")
    """

    SECTOR_NAME = "automobile"
