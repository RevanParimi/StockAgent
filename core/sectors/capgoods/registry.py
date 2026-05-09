"""
core/sectors/capgoods/registry.py
================================
Agent registry for the Capital Goods sector.

Pillar weights:
  business        0.17
  fundamentals    0.2
  valuation       0.14
  technical       0.09
  macro           0.14
  risk            0.07
  management      0.12
  earnings        0.07
            ─────
Total           1.00
"""

from core.sectors.capgoods.business import CapGoodsBusinessAgent
from core.sectors.capgoods.fundamentals import CapGoodsFundamentalsAgent
from core.sectors.capgoods.valuation import CapGoodsValuationAgent
from core.sectors.capgoods.technical import CapGoodsTechnicalAgent
from core.sectors.capgoods.macro import CapGoodsMacroAgent
from core.sectors.capgoods.risk import CapGoodsRiskAgent
from core.sectors.capgoods.management import CapGoodsManagementAgent
from core.sectors.capgoods.earnings import CapGoodsEarningsAgent

AGENTS: dict = {
    "business": CapGoodsBusinessAgent(),
    "fundamentals": CapGoodsFundamentalsAgent(),
    "valuation": CapGoodsValuationAgent(),
    "technical": CapGoodsTechnicalAgent(),
    "macro": CapGoodsMacroAgent(),
    "risk": CapGoodsRiskAgent(),
    "management": CapGoodsManagementAgent(),
    "earnings": CapGoodsEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.17,
    "fundamentals": 0.2,
    "valuation": 0.14,
    "technical": 0.09,
    "macro": 0.14,
    "risk": 0.07,
    "management": 0.12,
    "earnings": 0.07,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
