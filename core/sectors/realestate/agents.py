"""
sectors/realestate/agents.py
=======================
Backward-compatibility shim for the Real Estate & REITs sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.realestate.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.realestate.business import RealEstBusinessAgent
from core.sectors.realestate.fundamentals import RealEstFundamentalsAgent
from core.sectors.realestate.valuation import RealEstValuationAgent
from core.sectors.realestate.technical import RealEstTechnicalAgent
from core.sectors.realestate.macro import RealEstMacroAgent
from core.sectors.realestate.risk import RealEstRiskAgent
from core.sectors.realestate.management import RealEstManagementAgent
from core.sectors.realestate.earnings import RealEstEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "RealEstBusinessAgent",
    "RealEstFundamentalsAgent",
    "RealEstValuationAgent",
    "RealEstTechnicalAgent",
    "RealEstMacroAgent",
    "RealEstRiskAgent",
    "RealEstManagementAgent",
    "RealEstEarningsAgent",
]
