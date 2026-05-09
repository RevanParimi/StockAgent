"""
sectors/retail/agents.py
===================
Backward-compatibility shim for the Retail & Consumer Discretionary sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.retail.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.retail.business import RetailBusinessAgent
from core.sectors.retail.fundamentals import RetailFundamentalsAgent
from core.sectors.retail.valuation import RetailValuationAgent
from core.sectors.retail.technical import RetailTechnicalAgent
from core.sectors.retail.macro import RetailMacroAgent
from core.sectors.retail.risk import RetailRiskAgent
from core.sectors.retail.management import RetailManagementAgent
from core.sectors.retail.earnings import RetailEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "RetailBusinessAgent",
    "RetailFundamentalsAgent",
    "RetailValuationAgent",
    "RetailTechnicalAgent",
    "RetailMacroAgent",
    "RetailRiskAgent",
    "RetailManagementAgent",
    "RetailEarningsAgent",
]
