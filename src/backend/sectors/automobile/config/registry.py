"""
src/backend/sectors/automobile/config/registry.py
===================================================
Automobile sector agent registry.

AGENTS — dict[str, BaseAgent]  — all 9 agent instances (stateless, shared).
WEIGHTS — dict[str, float]     — normalized agent weights (sum to 1.0).
"""

from __future__ import annotations

from backend.sectors.automobile.agents.sales_demand       import SalesDemandAgent
from backend.sectors.automobile.agents.fundamentals        import FundamentalsAgent
from backend.sectors.automobile.agents.raw_materials       import RawMaterialsAgent
from backend.sectors.automobile.agents.pattern_analysis    import PatternAnalysisAgent
from backend.sectors.automobile.agents.sentiment           import SentimentAgent
from backend.sectors.automobile.agents.policy_regulatory   import PolicyRegulatoryAgent
from backend.sectors.automobile.agents.competitive_intel   import CompetitiveIntelAgent
from backend.sectors.automobile.agents.risk_macro          import RiskMacroAgent
from backend.sectors.automobile.agents.valuation_catalyst  import ValuationCatalystAgent
from backend.sectors.automobile.config.settings            import AGENT_WEIGHTS

AGENTS: dict = {
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

WEIGHTS: dict[str, float] = AGENT_WEIGHTS
