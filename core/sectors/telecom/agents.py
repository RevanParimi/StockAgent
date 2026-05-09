"""
sectors/telecom/agents.py
====================
Backward-compatibility shim for the Telecommunications sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.telecom.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.telecom.business import TelecomBusinessAgent
from core.sectors.telecom.fundamentals import TelecomFundamentalsAgent
from core.sectors.telecom.valuation import TelecomValuationAgent
from core.sectors.telecom.technical import TelecomTechnicalAgent
from core.sectors.telecom.macro import TelecomMacroAgent
from core.sectors.telecom.risk import TelecomRiskAgent
from core.sectors.telecom.management import TelecomManagementAgent
from core.sectors.telecom.earnings import TelecomEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "TelecomBusinessAgent",
    "TelecomFundamentalsAgent",
    "TelecomValuationAgent",
    "TelecomTechnicalAgent",
    "TelecomMacroAgent",
    "TelecomRiskAgent",
    "TelecomManagementAgent",
    "TelecomEarningsAgent",
]
