"""
core/sectors/power/registry.py
=============================
Agent registry for the Power & Utilities sector.

Pillar weights:
  business        0.1
  fundamentals    0.19
  valuation       0.16
  technical       0.08
  macro           0.18
  risk            0.12
  management      0.11
  earnings        0.06
            ─────
Total           1.00
"""

from core.sectors.power.business import PowerBusinessAgent
from core.sectors.power.fundamentals import PowerFundamentalsAgent
from core.sectors.power.valuation import PowerValuationAgent
from core.sectors.power.technical import PowerTechnicalAgent
from core.sectors.power.macro import PowerMacroAgent
from core.sectors.power.risk import PowerRiskAgent
from core.sectors.power.management import PowerManagementAgent
from core.sectors.power.earnings import PowerEarningsAgent

AGENTS: dict = {
    "business": PowerBusinessAgent(),
    "fundamentals": PowerFundamentalsAgent(),
    "valuation": PowerValuationAgent(),
    "technical": PowerTechnicalAgent(),
    "macro": PowerMacroAgent(),
    "risk": PowerRiskAgent(),
    "management": PowerManagementAgent(),
    "earnings": PowerEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.1,
    "fundamentals": 0.19,
    "valuation": 0.16,
    "technical": 0.08,
    "macro": 0.18,
    "risk": 0.12,
    "management": 0.11,
    "earnings": 0.06,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
