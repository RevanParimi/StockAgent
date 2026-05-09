"""
sectors/pharma/agents.py
===================
Backward-compatibility shim for the Pharmaceuticals sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.pharma.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.pharma.business import PharmaBusinessAgent
from core.sectors.pharma.fundamentals import PharmaFundamentalsAgent
from core.sectors.pharma.valuation import PharmaValuationAgent
from core.sectors.pharma.technical import PharmaTechnicalAgent
from core.sectors.pharma.macro import PharmaMacroAgent
from core.sectors.pharma.risk import PharmaRiskAgent
from core.sectors.pharma.management import PharmaManagementAgent
from core.sectors.pharma.earnings import PharmaEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "PharmaBusinessAgent",
    "PharmaFundamentalsAgent",
    "PharmaValuationAgent",
    "PharmaTechnicalAgent",
    "PharmaMacroAgent",
    "PharmaRiskAgent",
    "PharmaManagementAgent",
    "PharmaEarningsAgent",
]
