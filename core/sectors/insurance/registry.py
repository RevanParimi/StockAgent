"""
core/sectors/insurance/registry.py
=================================
Agent registry for the Insurance sector.

Pillar weights:
  business        0.12
  fundamentals    0.14
  valuation       0.2
  technical       0.05
  macro           0.12
  risk            0.16
  management      0.13
  earnings        0.08
            ─────
Total           1.00
"""

from core.sectors.insurance.business import InsBusinessAgent
from core.sectors.insurance.fundamentals import InsFundamentalsAgent
from core.sectors.insurance.valuation import InsValuationAgent
from core.sectors.insurance.technical import InsTechnicalAgent
from core.sectors.insurance.macro import InsMacroAgent
from core.sectors.insurance.risk import InsRiskAgent
from core.sectors.insurance.management import InsManagementAgent
from core.sectors.insurance.earnings import InsEarningsAgent

AGENTS: dict = {
    "business": InsBusinessAgent(),
    "fundamentals": InsFundamentalsAgent(),
    "valuation": InsValuationAgent(),
    "technical": InsTechnicalAgent(),
    "macro": InsMacroAgent(),
    "risk": InsRiskAgent(),
    "management": InsManagementAgent(),
    "earnings": InsEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.12,
    "fundamentals": 0.14,
    "valuation": 0.2,
    "technical": 0.05,
    "macro": 0.12,
    "risk": 0.16,
    "management": 0.13,
    "earnings": 0.08,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
