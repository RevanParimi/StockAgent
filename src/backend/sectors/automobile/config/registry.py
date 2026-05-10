"""
src/backend/sectors/automobile/config/registry.py
===================================================
Automobile sector agent registry — Phase 2 refactor.

7 of 9 agents replaced with UniversalAgent (prompt-driven, no duplication).
2 sector-specific agents kept:
  - SalesDemandAgent  : custom FADA/SIAM/VAHAN data fetching
  - RawMaterialsAgent : commodity price context assembly
"""
from __future__ import annotations

from backend.shared.agents.universal              import UniversalAgent
from backend.sectors.automobile.agents.sales_demand   import SalesDemandAgent
from backend.sectors.automobile.agents.raw_materials  import RawMaterialsAgent
from backend.sectors.automobile.prompts import (
    fundamentals       as _fund,
    pattern_analysis   as _pat,
    sentiment          as _sent,
    risk_macro         as _risk,
    valuation_catalyst as _val,
    policy_regulatory  as _pol,
    competitive_intel  as _comp,
)
from backend.sectors.automobile.config.settings import AGENT_WEIGHTS

_S = "automobile"

AGENTS: dict = {
    "sales_demand":       SalesDemandAgent(),
    "raw_materials":      RawMaterialsAgent(),
    "fundamentals":       UniversalAgent("fundamentals",       _fund, sector=_S),
    "pattern_analysis":   UniversalAgent("pattern_analysis",   _pat,  sector=_S),
    "sentiment":          UniversalAgent("sentiment",          _sent, sector=_S),
    "risk_macro":         UniversalAgent("risk_macro",         _risk, sector=_S),
    "valuation_catalyst": UniversalAgent("valuation_catalyst", _val,  sector=_S),
    "policy_regulatory":  UniversalAgent("policy_regulatory",  _pol,  sector=_S),
    "competitive_intel":  UniversalAgent("competitive_intel",  _comp, sector=_S),
}

WEIGHTS: dict[str, float] = AGENT_WEIGHTS
