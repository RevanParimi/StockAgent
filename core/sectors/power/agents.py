"""
sectors/power/agents.py
==================
Backward-compatibility shim for the Power & Utilities sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.power.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.power.business import PowerBusinessAgent
from core.sectors.power.fundamentals import PowerFundamentalsAgent
from core.sectors.power.valuation import PowerValuationAgent
from core.sectors.power.technical import PowerTechnicalAgent
from core.sectors.power.macro import PowerMacroAgent
from core.sectors.power.risk import PowerRiskAgent
from core.sectors.power.management import PowerManagementAgent
from core.sectors.power.earnings import PowerEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "PowerBusinessAgent",
    "PowerFundamentalsAgent",
    "PowerValuationAgent",
    "PowerTechnicalAgent",
    "PowerMacroAgent",
    "PowerRiskAgent",
    "PowerManagementAgent",
    "PowerEarningsAgent",
]
