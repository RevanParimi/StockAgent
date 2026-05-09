"""
sectors/tech/agents.py
=================
Backward-compatibility shim for the Information Technology sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.tech.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.tech.business import ITBusinessAgent
from core.sectors.tech.fundamentals import ITFundamentalsAgent
from core.sectors.tech.valuation import ITValuationAgent
from core.sectors.tech.technical import ITTechnicalAgent
from core.sectors.tech.macro import ITMacroAgent
from core.sectors.tech.risk import ITRiskAgent
from core.sectors.tech.management import ITManagementAgent
from core.sectors.tech.earnings import ITEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "ITBusinessAgent",
    "ITFundamentalsAgent",
    "ITValuationAgent",
    "ITTechnicalAgent",
    "ITMacroAgent",
    "ITRiskAgent",
    "ITManagementAgent",
    "ITEarningsAgent",
]
