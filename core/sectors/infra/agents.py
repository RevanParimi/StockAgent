"""
sectors/infra/agents.py
==================
Backward-compatibility shim for the Infrastructure & Construction sector.
All agent classes now live in per-agent files; this re-exports them.
"""

from core.sectors.infra.registry import AGENTS, WEIGHTS, LEGACY_AGENT_ALIASES

from core.sectors.infra.business import InfraBusinessAgent
from core.sectors.infra.fundamentals import InfraFundamentalsAgent
from core.sectors.infra.valuation import InfraValuationAgent
from core.sectors.infra.technical import InfraTechnicalAgent
from core.sectors.infra.macro import InfraMacroAgent
from core.sectors.infra.risk import InfraRiskAgent
from core.sectors.infra.management import InfraManagementAgent
from core.sectors.infra.earnings import InfraEarningsAgent

__all__ = [
    "AGENTS",
    "WEIGHTS",
    "LEGACY_AGENT_ALIASES",
    "InfraBusinessAgent",
    "InfraFundamentalsAgent",
    "InfraValuationAgent",
    "InfraTechnicalAgent",
    "InfraMacroAgent",
    "InfraRiskAgent",
    "InfraManagementAgent",
    "InfraEarningsAgent",
]
