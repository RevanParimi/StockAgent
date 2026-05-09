"""
core/sectors/fmcg/registry.py
============================
Agent registry for the FMCG & Consumer Staples sector.

Pillar weights:
  business        0.19
  fundamentals    0.16
  valuation       0.18
  technical       0.09
  macro           0.12
  risk            0.07
  management      0.12
  earnings        0.07
            ─────
Total           1.00
"""

from core.sectors.fmcg.business import FMCGBusinessAgent
from core.sectors.fmcg.fundamentals import FMCGFundamentalsAgent
from core.sectors.fmcg.valuation import FMCGValuationAgent
from core.sectors.fmcg.technical import FMCGTechnicalAgent
from core.sectors.fmcg.macro import FMCGMacroAgent
from core.sectors.fmcg.risk import FMCGRiskAgent
from core.sectors.fmcg.management import FMCGManagementAgent
from core.sectors.fmcg.earnings import FMCGEarningsAgent

AGENTS: dict = {
    "business": FMCGBusinessAgent(),
    "fundamentals": FMCGFundamentalsAgent(),
    "valuation": FMCGValuationAgent(),
    "technical": FMCGTechnicalAgent(),
    "macro": FMCGMacroAgent(),
    "risk": FMCGRiskAgent(),
    "management": FMCGManagementAgent(),
    "earnings": FMCGEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.19,
    "fundamentals": 0.16,
    "valuation": 0.18,
    "technical": 0.09,
    "macro": 0.12,
    "risk": 0.07,
    "management": 0.12,
    "earnings": 0.07,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
