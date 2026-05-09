"""
sectors/hospitality/agents.py
========================
Backward-compatibility shim for the Hospitality & Travel sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.hospitality.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.hospitality.business import HospBusinessAgent
from core.sectors.hospitality.fundamentals import HospFundamentalsAgent
from core.sectors.hospitality.valuation import HospValuationAgent
from core.sectors.hospitality.technical import HospTechnicalAgent
from core.sectors.hospitality.macro import HospMacroAgent
from core.sectors.hospitality.risk import HospRiskAgent
from core.sectors.hospitality.management import HospManagementAgent
from core.sectors.hospitality.earnings import HospEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "HospBusinessAgent",
    "HospFundamentalsAgent",
    "HospValuationAgent",
    "HospTechnicalAgent",
    "HospMacroAgent",
    "HospRiskAgent",
    "HospManagementAgent",
    "HospEarningsAgent",
]
