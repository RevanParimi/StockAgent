"""
core/sectors/retail/registry.py
==============================
Agent registry for the Retail & Consumer Discretionary sector.

Pillar weights:
  business        0.22
  fundamentals    0.12
  valuation       0.2
  technical       0.11
  macro           0.12
  risk            0.07
  management      0.11
  earnings        0.05
            ─────
Total           1.00
"""

from core.sectors.retail.business import RetailBusinessAgent
from core.sectors.retail.fundamentals import RetailFundamentalsAgent
from core.sectors.retail.valuation import RetailValuationAgent
from core.sectors.retail.technical import RetailTechnicalAgent
from core.sectors.retail.macro import RetailMacroAgent
from core.sectors.retail.risk import RetailRiskAgent
from core.sectors.retail.management import RetailManagementAgent
from core.sectors.retail.earnings import RetailEarningsAgent

AGENTS: dict = {
    "business": RetailBusinessAgent(),
    "fundamentals": RetailFundamentalsAgent(),
    "valuation": RetailValuationAgent(),
    "technical": RetailTechnicalAgent(),
    "macro": RetailMacroAgent(),
    "risk": RetailRiskAgent(),
    "management": RetailManagementAgent(),
    "earnings": RetailEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.22,
    "fundamentals": 0.12,
    "valuation": 0.2,
    "technical": 0.11,
    "macro": 0.12,
    "risk": 0.07,
    "management": 0.11,
    "earnings": 0.05,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
