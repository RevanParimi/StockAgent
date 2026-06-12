"""
src/backend/sectors/__init__.py
================================
Sector registry: maps ticker symbols to their orchestrator class.
Automobile is the default fallback.
"""
from __future__ import annotations


def detect_sector(ticker: str) -> str:
    """
    Resolve ticker → sector key.
    Phase 0+1: routes through SectorRegistry (extended ticker map + toggle awareness).
    Kept backward-compatible — always returns a usable sector string.
    """
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.resolve(ticker)


def get_orchestrator(sector: str):
    """
    Return the orchestrator class for a sector key.
    Phase 0: disabled sectors degrade to AutomobileAgentOrchestrator with a log warning.
    """
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.get_handler(sector)
