"""
sectors/metals/agents.py
===================
Backward-compatibility shim for the Metals & Mining sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.metals.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.metals.business import MetalBusinessAgent
from core.sectors.metals.fundamentals import MetalFundamentalsAgent
from core.sectors.metals.valuation import MetalValuationAgent
from core.sectors.metals.technical import MetalTechnicalAgent
from core.sectors.metals.macro import MetalMacroAgent
from core.sectors.metals.risk import MetalRiskAgent
from core.sectors.metals.management import MetalManagementAgent
from core.sectors.metals.earnings import MetalEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "MetalBusinessAgent",
    "MetalFundamentalsAgent",
    "MetalValuationAgent",
    "MetalTechnicalAgent",
    "MetalMacroAgent",
    "MetalRiskAgent",
    "MetalManagementAgent",
    "MetalEarningsAgent",
]
