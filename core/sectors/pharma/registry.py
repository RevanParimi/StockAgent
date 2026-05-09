"""
core/sectors/pharma/registry.py
==============================
Agent registry for the Pharmaceuticals sector.

Pillar weights:
  business        0.18
  fundamentals    0.16
  valuation       0.15
  technical       0.1
  macro           0.08
  risk            0.16
  management      0.11
  earnings        0.06
            ─────
Total           1.00
"""

from core.sectors.pharma.business import PharmaBusinessAgent
from core.sectors.pharma.fundamentals import PharmaFundamentalsAgent
from core.sectors.pharma.valuation import PharmaValuationAgent
from core.sectors.pharma.technical import PharmaTechnicalAgent
from core.sectors.pharma.macro import PharmaMacroAgent
from core.sectors.pharma.risk import PharmaRiskAgent
from core.sectors.pharma.management import PharmaManagementAgent
from core.sectors.pharma.earnings import PharmaEarningsAgent

AGENTS: dict = {
    "business": PharmaBusinessAgent(),
    "fundamentals": PharmaFundamentalsAgent(),
    "valuation": PharmaValuationAgent(),
    "technical": PharmaTechnicalAgent(),
    "macro": PharmaMacroAgent(),
    "risk": PharmaRiskAgent(),
    "management": PharmaManagementAgent(),
    "earnings": PharmaEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.18,
    "fundamentals": 0.16,
    "valuation": 0.15,
    "technical": 0.1,
    "macro": 0.08,
    "risk": 0.16,
    "management": 0.11,
    "earnings": 0.06,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
