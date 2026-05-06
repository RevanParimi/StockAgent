"""
src/backend/sectors/automobile/pipeline/orchestrator.py
========================================================
Automobile sector orchestrator — 9 specialist agents run in parallel.

Extends BaseSectorOrchestrator which handles ticker resolution, LangGraph
dispatch, RL weight loading, signal aggregation, and all logging.
"""

from __future__ import annotations

from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

from backend.sectors.automobile.agents.sales_demand import SalesDemandAgent
from backend.sectors.automobile.agents.raw_materials import RawMaterialsAgent
from backend.sectors.automobile.agents.fundamentals import FundamentalsAgent
from backend.sectors.automobile.agents.pattern_analysis import PatternAnalysisAgent
from backend.sectors.automobile.agents.sentiment import SentimentAgent
from backend.sectors.automobile.agents.policy_regulatory import PolicyRegulatoryAgent
from backend.sectors.automobile.agents.competitive_intel import CompetitiveIntelAgent
from backend.sectors.automobile.agents.risk_macro import RiskMacroAgent
from backend.sectors.automobile.agents.valuation_catalyst import ValuationCatalystAgent


# Module-level agent instances — stateless, safe to share
_SUB_AGENTS = {
    "sales_demand":       SalesDemandAgent(),
    "raw_materials":      RawMaterialsAgent(),
    "fundamentals":       FundamentalsAgent(),
    "pattern_analysis":   PatternAnalysisAgent(),
    "sentiment":          SentimentAgent(),
    "policy_regulatory":  PolicyRegulatoryAgent(),
    "competitive_intel":  CompetitiveIntelAgent(),
    "risk_macro":         RiskMacroAgent(),
    "valuation_catalyst": ValuationCatalystAgent(),
}


class AutomobileAgentOrchestrator(BaseSectorOrchestrator):
    """
    Entry point for Indian automobile stock analysis.

    Usage:
        report = AutomobileAgentOrchestrator().analyse("MARUTI")
        report = await AutomobileAgentOrchestrator().analyse_async("TATAMOTORS")
    """

    SECTOR_NAME = "automobile"

    def __init__(self) -> None:
        self._sub_agents = _SUB_AGENTS
        super().__init__()
