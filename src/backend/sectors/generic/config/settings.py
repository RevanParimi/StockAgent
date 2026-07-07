"""
Generic sector graph — Compass Phase B (spec §4.3 reality check).

Neutral config for tickers whose sector has no native orchestrator.
AGENT_WEIGHTS re-exports the config.yaml-tunable generic weights so
sector_router.get_sector_weights() and WeightMemory initialisation read
one source of truth. TICKERS is empty by design: generic-graph names are
auto-promoted portfolio/discovery symbols, never a hardcoded universe
(BaseSectorOrchestrator._managed_tickers tolerates the empty list).
"""
from __future__ import annotations

from backend.shared.config import settings as _settings

AGENT_WEIGHTS: dict[str, float] = dict(_settings.GENERIC_AGENT_WEIGHTS)

TICKERS: list[str] = []
