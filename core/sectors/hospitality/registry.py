"""
core/sectors/hospitality/registry.py
===================================
Agent registry for the Hospitality & Travel sector.

Pillar weights:
  business        0.15
  fundamentals    0.16
  valuation       0.15
  technical       0.09
  macro           0.18
  risk            0.12
  management      0.08
  earnings        0.07
            ─────
Total           1.00
"""

from core.sectors.hospitality.business import HospBusinessAgent
from core.sectors.hospitality.fundamentals import HospFundamentalsAgent
from core.sectors.hospitality.valuation import HospValuationAgent
from core.sectors.hospitality.technical import HospTechnicalAgent
from core.sectors.hospitality.macro import HospMacroAgent
from core.sectors.hospitality.risk import HospRiskAgent
from core.sectors.hospitality.management import HospManagementAgent
from core.sectors.hospitality.earnings import HospEarningsAgent

AGENTS: dict = {
    "business": HospBusinessAgent(),
    "fundamentals": HospFundamentalsAgent(),
    "valuation": HospValuationAgent(),
    "technical": HospTechnicalAgent(),
    "macro": HospMacroAgent(),
    "risk": HospRiskAgent(),
    "management": HospManagementAgent(),
    "earnings": HospEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.15,
    "fundamentals": 0.16,
    "valuation": 0.15,
    "technical": 0.09,
    "macro": 0.18,
    "risk": 0.12,
    "management": 0.08,
    "earnings": 0.07,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
