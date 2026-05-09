"""
core/sectors/telecom/registry.py
===============================
Agent registry for the Telecommunications sector.

Pillar weights:
  business        0.15
  fundamentals    0.16
  valuation       0.15
  technical       0.07
  macro           0.19
  risk            0.12
  management      0.1
  earnings        0.06
            ─────
Total           1.00
"""

from core.sectors.telecom.business import TelecomBusinessAgent
from core.sectors.telecom.fundamentals import TelecomFundamentalsAgent
from core.sectors.telecom.valuation import TelecomValuationAgent
from core.sectors.telecom.technical import TelecomTechnicalAgent
from core.sectors.telecom.macro import TelecomMacroAgent
from core.sectors.telecom.risk import TelecomRiskAgent
from core.sectors.telecom.management import TelecomManagementAgent
from core.sectors.telecom.earnings import TelecomEarningsAgent

AGENTS: dict = {
    "business": TelecomBusinessAgent(),
    "fundamentals": TelecomFundamentalsAgent(),
    "valuation": TelecomValuationAgent(),
    "technical": TelecomTechnicalAgent(),
    "macro": TelecomMacroAgent(),
    "risk": TelecomRiskAgent(),
    "management": TelecomManagementAgent(),
    "earnings": TelecomEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.15,
    "fundamentals": 0.16,
    "valuation": 0.15,
    "technical": 0.07,
    "macro": 0.19,
    "risk": 0.12,
    "management": 0.1,
    "earnings": 0.06,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
