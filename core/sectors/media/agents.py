"""
sectors/media/agents.py
==================
Backward-compatibility shim for the Media & Entertainment sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.media.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.media.business import MediaBusinessAgent
from core.sectors.media.fundamentals import MediaFundamentalsAgent
from core.sectors.media.valuation import MediaValuationAgent
from core.sectors.media.technical import MediaTechnicalAgent
from core.sectors.media.macro import MediaMacroAgent
from core.sectors.media.risk import MediaRiskAgent
from core.sectors.media.management import MediaManagementAgent
from core.sectors.media.earnings import MediaEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "MediaBusinessAgent",
    "MediaFundamentalsAgent",
    "MediaValuationAgent",
    "MediaTechnicalAgent",
    "MediaMacroAgent",
    "MediaRiskAgent",
    "MediaManagementAgent",
    "MediaEarningsAgent",
]
