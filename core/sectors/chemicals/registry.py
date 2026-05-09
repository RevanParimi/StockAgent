"""
core/sectors/chemicals/registry.py
=================================
Agent registry for the Specialty Chemicals sector.

Pillar weights:
  business        0.2
  fundamentals    0.2
  valuation       0.15
  technical       0.07
  macro           0.12
  risk            0.08
  management      0.12
  earnings        0.06
            ─────
Total           1.00
"""

from core.sectors.chemicals.business import ChemBusinessAgent
from core.sectors.chemicals.fundamentals import ChemFundamentalsAgent
from core.sectors.chemicals.valuation import ChemValuationAgent
from core.sectors.chemicals.technical import ChemTechnicalAgent
from core.sectors.chemicals.macro import ChemMacroAgent
from core.sectors.chemicals.risk import ChemRiskAgent
from core.sectors.chemicals.management import ChemManagementAgent
from core.sectors.chemicals.earnings import ChemEarningsAgent

AGENTS: dict = {
    "business": ChemBusinessAgent(),
    "fundamentals": ChemFundamentalsAgent(),
    "valuation": ChemValuationAgent(),
    "technical": ChemTechnicalAgent(),
    "macro": ChemMacroAgent(),
    "risk": ChemRiskAgent(),
    "management": ChemManagementAgent(),
    "earnings": ChemEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.2,
    "fundamentals": 0.2,
    "valuation": 0.15,
    "technical": 0.07,
    "macro": 0.12,
    "risk": 0.08,
    "management": 0.12,
    "earnings": 0.06,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
