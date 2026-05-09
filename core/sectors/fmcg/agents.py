"""
sectors/fmcg/agents.py
=================
Backward-compatibility shim for the FMCG & Consumer Staples sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.fmcg.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.fmcg.business import FMCGBusinessAgent
from core.sectors.fmcg.fundamentals import FMCGFundamentalsAgent
from core.sectors.fmcg.valuation import FMCGValuationAgent
from core.sectors.fmcg.technical import FMCGTechnicalAgent
from core.sectors.fmcg.macro import FMCGMacroAgent
from core.sectors.fmcg.risk import FMCGRiskAgent
from core.sectors.fmcg.management import FMCGManagementAgent
from core.sectors.fmcg.earnings import FMCGEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "FMCGBusinessAgent",
    "FMCGFundamentalsAgent",
    "FMCGValuationAgent",
    "FMCGTechnicalAgent",
    "FMCGMacroAgent",
    "FMCGRiskAgent",
    "FMCGManagementAgent",
    "FMCGEarningsAgent",
]
