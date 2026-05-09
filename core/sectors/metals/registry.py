"""
core/sectors/metals/registry.py
==============================
Agent registry for the Metals & Mining sector.

Pillar weights:
  business        0.1
  fundamentals    0.16
  valuation       0.15
  technical       0.16
  macro           0.18
  risk            0.11
  management      0.09
  earnings        0.05
            ─────
Total           1.00
"""

from core.sectors.metals.business import MetalBusinessAgent
from core.sectors.metals.fundamentals import MetalFundamentalsAgent
from core.sectors.metals.valuation import MetalValuationAgent
from core.sectors.metals.technical import MetalTechnicalAgent
from core.sectors.metals.macro import MetalMacroAgent
from core.sectors.metals.risk import MetalRiskAgent
from core.sectors.metals.management import MetalManagementAgent
from core.sectors.metals.earnings import MetalEarningsAgent

AGENTS: dict = {
    "business": MetalBusinessAgent(),
    "fundamentals": MetalFundamentalsAgent(),
    "valuation": MetalValuationAgent(),
    "technical": MetalTechnicalAgent(),
    "macro": MetalMacroAgent(),
    "risk": MetalRiskAgent(),
    "management": MetalManagementAgent(),
    "earnings": MetalEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.1,
    "fundamentals": 0.16,
    "valuation": 0.15,
    "technical": 0.16,
    "macro": 0.18,
    "risk": 0.11,
    "management": 0.09,
    "earnings": 0.05,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
