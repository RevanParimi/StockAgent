"""
sectors/logistics/agents.py
======================
Backward-compatibility shim for the Logistics & Supply Chain sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.logistics.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.logistics.business import LogistBusinessAgent
from core.sectors.logistics.fundamentals import LogistFundamentalsAgent
from core.sectors.logistics.valuation import LogistValuationAgent
from core.sectors.logistics.technical import LogistTechnicalAgent
from core.sectors.logistics.macro import LogistMacroAgent
from core.sectors.logistics.risk import LogistRiskAgent
from core.sectors.logistics.management import LogistManagementAgent
from core.sectors.logistics.earnings import LogistEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "LogistBusinessAgent",
    "LogistFundamentalsAgent",
    "LogistValuationAgent",
    "LogistTechnicalAgent",
    "LogistMacroAgent",
    "LogistRiskAgent",
    "LogistManagementAgent",
    "LogistEarningsAgent",
]
