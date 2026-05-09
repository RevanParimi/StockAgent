"""
core/sectors/realestate/registry.py
==================================
Agent registry for the Real Estate & REITs sector.

Pillar weights:
  business        0.14
  fundamentals    0.11
  valuation       0.18
  technical       0.09
  macro           0.18
  risk            0.11
  management      0.12
  earnings        0.07
            ─────
Total           1.00
"""

from core.sectors.realestate.business import RealEstBusinessAgent
from core.sectors.realestate.fundamentals import RealEstFundamentalsAgent
from core.sectors.realestate.valuation import RealEstValuationAgent
from core.sectors.realestate.technical import RealEstTechnicalAgent
from core.sectors.realestate.macro import RealEstMacroAgent
from core.sectors.realestate.risk import RealEstRiskAgent
from core.sectors.realestate.management import RealEstManagementAgent
from core.sectors.realestate.earnings import RealEstEarningsAgent

AGENTS: dict = {
    "business": RealEstBusinessAgent(),
    "fundamentals": RealEstFundamentalsAgent(),
    "valuation": RealEstValuationAgent(),
    "technical": RealEstTechnicalAgent(),
    "macro": RealEstMacroAgent(),
    "risk": RealEstRiskAgent(),
    "management": RealEstManagementAgent(),
    "earnings": RealEstEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.14,
    "fundamentals": 0.11,
    "valuation": 0.18,
    "technical": 0.09,
    "macro": 0.18,
    "risk": 0.11,
    "management": 0.12,
    "earnings": 0.07,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
