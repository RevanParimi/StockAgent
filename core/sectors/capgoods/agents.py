"""
sectors/capgoods/agents.py
=====================
Backward-compatibility shim for the Capital Goods sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.capgoods.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.capgoods.business import CapGoodsBusinessAgent
from core.sectors.capgoods.fundamentals import CapGoodsFundamentalsAgent
from core.sectors.capgoods.valuation import CapGoodsValuationAgent
from core.sectors.capgoods.technical import CapGoodsTechnicalAgent
from core.sectors.capgoods.macro import CapGoodsMacroAgent
from core.sectors.capgoods.risk import CapGoodsRiskAgent
from core.sectors.capgoods.management import CapGoodsManagementAgent
from core.sectors.capgoods.earnings import CapGoodsEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "CapGoodsBusinessAgent",
    "CapGoodsFundamentalsAgent",
    "CapGoodsValuationAgent",
    "CapGoodsTechnicalAgent",
    "CapGoodsMacroAgent",
    "CapGoodsRiskAgent",
    "CapGoodsManagementAgent",
    "CapGoodsEarningsAgent",
]
