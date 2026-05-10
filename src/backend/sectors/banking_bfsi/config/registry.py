"""
src/backend/sectors/banking_bfsi/config/registry.py
=====================================================
Banking BFSI sector agent registry — Phase 2 refactor.

5 of 6 agents replaced with UniversalAgent.
1 sector-specific agent kept:
  - BFSIUniverseAgent : peer universe setup + sector-specific config logic
"""
from __future__ import annotations

from backend.shared.agents.universal                          import UniversalAgent
from backend.shared.agents.prompts.technical                  import BANKING_TECHNICAL
from backend.shared.agents.prompts.institutional_flow         import BANKING_INSTITUTIONAL
from backend.sectors.banking_bfsi.agents.universe_setup       import BFSIUniverseAgent
from backend.sectors.banking_bfsi.prompts import (
    fundamentals as _fund,
    risk         as _risk,
    macro_policy as _mac,
)
from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS

_S = "banking_bfsi"

AGENTS: dict = {
    "fundamentals":    UniversalAgent("fundamentals",    _fund,                sector=_S),
    "risk":            UniversalAgent("risk",            _risk,                sector=_S),
    "macro_policy":    UniversalAgent("macro_policy",    _mac,                 sector=_S),
    "institutional":   UniversalAgent("institutional",   BANKING_INSTITUTIONAL,sector=_S),
    "pattern_analysis":UniversalAgent("pattern_analysis",BANKING_TECHNICAL,   sector=_S),
    "universe_setup":  BFSIUniverseAgent(),
}

WEIGHTS: dict[str, float] = AGENT_WEIGHTS
