"""
core/sectors/logistics/registry.py
=================================
Agent registry for the Logistics & Supply Chain sector.

Pillar weights:
  business        0.17
  fundamentals    0.2
  valuation       0.15
  technical       0.1
  macro           0.14
  risk            0.08
  management      0.11
  earnings        0.05
            ─────
Total           1.00
"""

from core.sectors.logistics.business import LogistBusinessAgent
from core.sectors.logistics.fundamentals import LogistFundamentalsAgent
from core.sectors.logistics.valuation import LogistValuationAgent
from core.sectors.logistics.technical import LogistTechnicalAgent
from core.sectors.logistics.macro import LogistMacroAgent
from core.sectors.logistics.risk import LogistRiskAgent
from core.sectors.logistics.management import LogistManagementAgent
from core.sectors.logistics.earnings import LogistEarningsAgent

AGENTS: dict = {
    "business": LogistBusinessAgent(),
    "fundamentals": LogistFundamentalsAgent(),
    "valuation": LogistValuationAgent(),
    "technical": LogistTechnicalAgent(),
    "macro": LogistMacroAgent(),
    "risk": LogistRiskAgent(),
    "management": LogistManagementAgent(),
    "earnings": LogistEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.17,
    "fundamentals": 0.2,
    "valuation": 0.15,
    "technical": 0.1,
    "macro": 0.14,
    "risk": 0.08,
    "management": 0.11,
    "earnings": 0.05,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
