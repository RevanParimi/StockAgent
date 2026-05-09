"""
sectors/oilgas/agents.py
===================
Backward-compatibility shim for the Oil & Gas sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.oilgas.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.oilgas.business import OilGasBusinessAgent
from core.sectors.oilgas.fundamentals import OilGasFundamentalsAgent
from core.sectors.oilgas.valuation import OilGasValuationAgent
from core.sectors.oilgas.technical import OilGasTechnicalAgent
from core.sectors.oilgas.macro import OilGasMacroAgent
from core.sectors.oilgas.risk import OilGasRiskAgent
from core.sectors.oilgas.management import OilGasManagementAgent
from core.sectors.oilgas.earnings import OilGasEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "OilGasBusinessAgent",
    "OilGasFundamentalsAgent",
    "OilGasValuationAgent",
    "OilGasTechnicalAgent",
    "OilGasMacroAgent",
    "OilGasRiskAgent",
    "OilGasManagementAgent",
    "OilGasEarningsAgent",
]
