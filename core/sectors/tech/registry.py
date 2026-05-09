"""
core/sectors/tech/registry.py
============================
Agent registry for the Information Technology sector.

Pillar weights:
  business        0.2
  fundamentals    0.16
  valuation       0.2
  technical       0.1
  macro           0.08
  risk            0.08
  management      0.11
  earnings        0.07
            ─────
Total           1.00
"""

from core.sectors.tech.business import ITBusinessAgent
from core.sectors.tech.fundamentals import ITFundamentalsAgent
from core.sectors.tech.valuation import ITValuationAgent
from core.sectors.tech.technical import ITTechnicalAgent
from core.sectors.tech.macro import ITMacroAgent
from core.sectors.tech.risk import ITRiskAgent
from core.sectors.tech.management import ITManagementAgent
from core.sectors.tech.earnings import ITEarningsAgent

AGENTS: dict = {
    "business": ITBusinessAgent(),
    "fundamentals": ITFundamentalsAgent(),
    "valuation": ITValuationAgent(),
    "technical": ITTechnicalAgent(),
    "macro": ITMacroAgent(),
    "risk": ITRiskAgent(),
    "management": ITManagementAgent(),
    "earnings": ITEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.2,
    "fundamentals": 0.16,
    "valuation": 0.2,
    "technical": 0.1,
    "macro": 0.08,
    "risk": 0.08,
    "management": 0.11,
    "earnings": 0.07,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
