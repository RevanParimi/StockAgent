"""
sectors/defence/agents.py
====================
Backward-compatibility shim for the Defence & Aerospace sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.defence.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.defence.business import DefBusinessAgent
from core.sectors.defence.fundamentals import DefFundamentalsAgent
from core.sectors.defence.valuation import DefValuationAgent
from core.sectors.defence.technical import DefTechnicalAgent
from core.sectors.defence.macro import DefMacroAgent
from core.sectors.defence.risk import DefRiskAgent
from core.sectors.defence.management import DefManagementAgent
from core.sectors.defence.earnings import DefEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "DefBusinessAgent",
    "DefFundamentalsAgent",
    "DefValuationAgent",
    "DefTechnicalAgent",
    "DefMacroAgent",
    "DefRiskAgent",
    "DefManagementAgent",
    "DefEarningsAgent",
]
