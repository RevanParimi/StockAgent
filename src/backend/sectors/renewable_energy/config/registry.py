"""
src/backend/sectors/renewable_energy/config/registry.py
=========================================================
Renewable Energy sector agent registry — Phase 2 refactor.

5 of 6 agents replaced with UniversalAgent.
1 sector-specific agent kept:
  - REBusinessAgent : custom capacity/PLF/PPA data assembly + operational metrics
"""
from __future__ import annotations

from backend.shared.agents.universal                              import UniversalAgent
from backend.shared.agents.prompts.technical                      import RE_TECHNICAL
from backend.sectors.renewable_energy.agents.business             import REBusinessAgent
from backend.sectors.renewable_energy.prompts import (
    fundamentals     as _fund,
    valuation        as _val,
    sentiment_policy as _pol,
    risk             as _risk,
)
from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS

_S = "renewable_energy"

AGENTS: dict = {
    "fundamentals":    UniversalAgent("fundamentals",    _fund,       sector=_S),
    "business":        REBusinessAgent(),
    "valuation":       UniversalAgent("valuation",       _val,        sector=_S),
    "sentiment_policy":UniversalAgent("sentiment_policy",_pol,        sector=_S),
    "technical":       UniversalAgent("technical",       RE_TECHNICAL,sector=_S),
    "risk":            UniversalAgent("risk",            _risk,       sector=_S),
}

WEIGHTS: dict[str, float] = AGENT_WEIGHTS
