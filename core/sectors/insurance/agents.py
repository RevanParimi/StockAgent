"""
sectors/insurance/agents.py
======================
Backward-compatibility shim for the Insurance sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.insurance.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.insurance.business import InsBusinessAgent
from core.sectors.insurance.fundamentals import InsFundamentalsAgent
from core.sectors.insurance.valuation import InsValuationAgent
from core.sectors.insurance.technical import InsTechnicalAgent
from core.sectors.insurance.macro import InsMacroAgent
from core.sectors.insurance.risk import InsRiskAgent
from core.sectors.insurance.management import InsManagementAgent
from core.sectors.insurance.earnings import InsEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "InsBusinessAgent",
    "InsFundamentalsAgent",
    "InsValuationAgent",
    "InsTechnicalAgent",
    "InsMacroAgent",
    "InsRiskAgent",
    "InsManagementAgent",
    "InsEarningsAgent",
]
