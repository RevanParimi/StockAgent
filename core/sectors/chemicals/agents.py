"""
sectors/chemicals/agents.py
======================
Backward-compatibility shim for the Specialty Chemicals sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.chemicals.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.chemicals.business import ChemBusinessAgent
from core.sectors.chemicals.fundamentals import ChemFundamentalsAgent
from core.sectors.chemicals.valuation import ChemValuationAgent
from core.sectors.chemicals.technical import ChemTechnicalAgent
from core.sectors.chemicals.macro import ChemMacroAgent
from core.sectors.chemicals.risk import ChemRiskAgent
from core.sectors.chemicals.management import ChemManagementAgent
from core.sectors.chemicals.earnings import ChemEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "ChemBusinessAgent",
    "ChemFundamentalsAgent",
    "ChemValuationAgent",
    "ChemTechnicalAgent",
    "ChemMacroAgent",
    "ChemRiskAgent",
    "ChemManagementAgent",
    "ChemEarningsAgent",
]
