"""
core/sectors/defence/registry.py
===============================
Agent registry for the Defence & Aerospace sector.

Pillar weights:
  business        0.12
  fundamentals    0.22
  valuation       0.15
  technical       0.09
  macro           0.15
  risk            0.1
  management      0.12
  earnings        0.05
            ─────
Total           1.00
"""

from core.sectors.defence.business import DefBusinessAgent
from core.sectors.defence.fundamentals import DefFundamentalsAgent
from core.sectors.defence.valuation import DefValuationAgent
from core.sectors.defence.technical import DefTechnicalAgent
from core.sectors.defence.macro import DefMacroAgent
from core.sectors.defence.risk import DefRiskAgent
from core.sectors.defence.management import DefManagementAgent
from core.sectors.defence.earnings import DefEarningsAgent

AGENTS: dict = {
    "business": DefBusinessAgent(),
    "fundamentals": DefFundamentalsAgent(),
    "valuation": DefValuationAgent(),
    "technical": DefTechnicalAgent(),
    "macro": DefMacroAgent(),
    "risk": DefRiskAgent(),
    "management": DefManagementAgent(),
    "earnings": DefEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.12,
    "fundamentals": 0.22,
    "valuation": 0.15,
    "technical": 0.09,
    "macro": 0.15,
    "risk": 0.1,
    "management": 0.12,
    "earnings": 0.05,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
