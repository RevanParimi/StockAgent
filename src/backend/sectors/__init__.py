"""
src/backend/sectors/__init__.py
================================
Sector registry: maps ticker symbols to their orchestrator class.
Thin shims over SectorRegistry, which is the single resolution point for
both this (API) path and the RL path (PI task A1). Generic is the default
fallback — unknown tickers and disabled sectors never reach the automobile
graph unless `sectors.generic_fallback_enabled` is turned off.
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
    A1: disabled and unknown sectors degrade to GenericSectorOrchestrator
    with a logged warning.
    """
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.get_handler(sector)
