"""
core/sectors/infra/registry.py
=============================
Agent registry for the Infrastructure & Construction sector.

Pillar weights:
  business        0.16
  fundamentals    0.18
  valuation       0.14
  technical       0.09
  macro           0.16
  risk            0.12
  management      0.12
  earnings        0.03
            ─────
Total           1.00
"""

from core.sectors.infra.business import InfraBusinessAgent
from core.sectors.infra.fundamentals import InfraFundamentalsAgent
from core.sectors.infra.valuation import InfraValuationAgent
from core.sectors.infra.technical import InfraTechnicalAgent
from core.sectors.infra.macro import InfraMacroAgent
from core.sectors.infra.risk import InfraRiskAgent
from core.sectors.infra.management import InfraManagementAgent
from core.sectors.infra.earnings import InfraEarningsAgent

AGENTS: dict = {
    "business": InfraBusinessAgent(),
    "fundamentals": InfraFundamentalsAgent(),
    "valuation": InfraValuationAgent(),
    "technical": InfraTechnicalAgent(),
    "macro": InfraMacroAgent(),
    "risk": InfraRiskAgent(),
    "management": InfraManagementAgent(),
    "earnings": InfraEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.16,
    "fundamentals": 0.18,
    "valuation": 0.14,
    "technical": 0.09,
    "macro": 0.16,
    "risk": 0.12,
    "management": 0.12,
    "earnings": 0.03,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
