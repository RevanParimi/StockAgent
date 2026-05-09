"""
core/sectors/agrochem/registry.py
================================
Agent registry for the Agrochemicals & Fertilizers sector.

Pillar weights:
  business        0.17
  fundamentals    0.19
  valuation       0.14
  technical       0.1
  macro           0.17
  risk            0.08
  management      0.09
  earnings        0.06
            ─────
Total           1.00
"""

from core.sectors.agrochem.business import AgroChemBusinessAgent
from core.sectors.agrochem.fundamentals import AgroChemFundamentalsAgent
from core.sectors.agrochem.valuation import AgroChemValuationAgent
from core.sectors.agrochem.technical import AgroChemTechnicalAgent
from core.sectors.agrochem.macro import AgroChemMacroAgent
from core.sectors.agrochem.risk import AgroChemRiskAgent
from core.sectors.agrochem.management import AgroChemManagementAgent
from core.sectors.agrochem.earnings import AgroChemEarningsAgent

AGENTS: dict = {
    "business": AgroChemBusinessAgent(),
    "fundamentals": AgroChemFundamentalsAgent(),
    "valuation": AgroChemValuationAgent(),
    "technical": AgroChemTechnicalAgent(),
    "macro": AgroChemMacroAgent(),
    "risk": AgroChemRiskAgent(),
    "management": AgroChemManagementAgent(),
    "earnings": AgroChemEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.17,
    "fundamentals": 0.19,
    "valuation": 0.14,
    "technical": 0.1,
    "macro": 0.17,
    "risk": 0.08,
    "management": 0.09,
    "earnings": 0.06,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
