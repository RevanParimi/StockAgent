"""
core/sectors/media/registry.py
=============================
Agent registry for the Media & Entertainment sector.

Pillar weights:
  business        0.2
  fundamentals    0.16
  valuation       0.16
  technical       0.11
  macro           0.14
  risk            0.07
  management      0.11
  earnings        0.05
            ─────
Total           1.00
"""

from core.sectors.media.business import MediaBusinessAgent
from core.sectors.media.fundamentals import MediaFundamentalsAgent
from core.sectors.media.valuation import MediaValuationAgent
from core.sectors.media.technical import MediaTechnicalAgent
from core.sectors.media.macro import MediaMacroAgent
from core.sectors.media.risk import MediaRiskAgent
from core.sectors.media.management import MediaManagementAgent
from core.sectors.media.earnings import MediaEarningsAgent

AGENTS: dict = {
    "business": MediaBusinessAgent(),
    "fundamentals": MediaFundamentalsAgent(),
    "valuation": MediaValuationAgent(),
    "technical": MediaTechnicalAgent(),
    "macro": MediaMacroAgent(),
    "risk": MediaRiskAgent(),
    "management": MediaManagementAgent(),
    "earnings": MediaEarningsAgent(),
}

WEIGHTS: dict[str, float] = {
    "business": 0.2,
    "fundamentals": 0.16,
    "valuation": 0.16,
    "technical": 0.11,
    "macro": 0.14,
    "risk": 0.07,
    "management": 0.11,
    "earnings": 0.05,
}

LEGACY_AGENT_ALIASES: dict[str, str] = {}
