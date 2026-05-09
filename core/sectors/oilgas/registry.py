"""
core/sectors/oilgas/registry.py
==============================
Agent registry for the Oil & Gas sector.

Pillar weights:
  business        0.1
  fundamentals    0.14
  valuation       0.14
  technical       0.1
  macro           0.22
  risk            0.12
  management      0.1
  earnings        0.08
            ─────
Total           1.00
"""

from core.sectors.oilgas.business import OilGasBusinessAgent
from core.sectors.oilgas.fundamentals import OilGasFundamentalsAgent
from core.sectors.oilgas.valuation import OilGasValuationAgent
from core.sectors.oilgas.technical import OilGasTechnicalAgent
from core.sectors.oilgas.macro import OilGasMacroAgent
from core.sectors.oilgas.risk import OilGasRiskAgent
from core.sectors.oilgas.management import OilGasManagementAgent
from core.sectors.oilgas.earnings import OilGasEarningsAgent

AGENTS: dict = {
    "business": OilGasBusinessAgent(),
    "fundamentals": OilGasFundamentalsAgent(),
    "valuation": OilGasValuationAgent(),
    "technical": OilGasTechnicalAgent(),
    "macro": OilGasMacroAgent(),
    "risk": OilGasRiskAgent(),
    "management": OilGasManagementAgent(),
    "earnings": OilGasEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.1,
    "fundamentals": 0.14,
    "valuation": 0.14,
    "technical": 0.1,
    "macro": 0.22,
    "risk": 0.12,
    "management": 0.1,
    "earnings": 0.08,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
