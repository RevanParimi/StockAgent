"""
graphs/automobile/agents.py
============================
Zero-duplication wrapper — exposes the existing agents/ sub-agents as a
plain dict keyed by agent name.  The LangGraph run_agent node picks the
right instance from this registry at runtime.
"""

from agents.sales_demand      import SalesDemandAgent
from agents.raw_materials      import RawMaterialsAgent
from agents.fundamentals       import FundamentalsAgent
from agents.pattern_analysis   import PatternAnalysisAgent
from agents.sentiment          import SentimentAgent
from agents.policy_regulatory  import PolicyRegulatoryAgent
from agents.competitive_intel  import CompetitiveIntelAgent
from agents.risk_macro         import RiskMacroAgent

# Instantiated once — all agents are stateless per .run() call
AGENTS: dict = {
    "sales_demand":      SalesDemandAgent(),
    "raw_materials":     RawMaterialsAgent(),
    "fundamentals":      FundamentalsAgent(),
    "pattern_analysis":  PatternAnalysisAgent(),
    "sentiment":         SentimentAgent(),
    "policy_regulatory": PolicyRegulatoryAgent(),
    "competitive_intel": CompetitiveIntelAgent(),
    "risk_macro":        RiskMacroAgent(),
}

# Weights from Automobile Agent Registry spec
WEIGHTS: dict[str, float] = {
    "sales_demand":      0.18,
    "fundamentals":      0.20,
    "risk_macro":        0.15,
    "pattern_analysis":  0.13,
    "policy_regulatory": 0.10,
    "competitive_intel": 0.10,
    "raw_materials":     0.10,
    "sentiment":         0.04,
}
