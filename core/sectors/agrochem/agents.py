"""
sectors/agrochem/agents.py
=====================
Backward-compatibility shim for the Agrochemicals & Fertilizers sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.agrochem.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.agrochem.business import AgroChemBusinessAgent
from core.sectors.agrochem.fundamentals import AgroChemFundamentalsAgent
from core.sectors.agrochem.valuation import AgroChemValuationAgent
from core.sectors.agrochem.technical import AgroChemTechnicalAgent
from core.sectors.agrochem.macro import AgroChemMacroAgent
from core.sectors.agrochem.risk import AgroChemRiskAgent
from core.sectors.agrochem.management import AgroChemManagementAgent
from core.sectors.agrochem.earnings import AgroChemEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "AgroChemBusinessAgent",
    "AgroChemFundamentalsAgent",
    "AgroChemValuationAgent",
    "AgroChemTechnicalAgent",
    "AgroChemMacroAgent",
    "AgroChemRiskAgent",
    "AgroChemManagementAgent",
    "AgroChemEarningsAgent",
]
