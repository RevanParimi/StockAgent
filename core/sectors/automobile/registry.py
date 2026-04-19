"""
core/sectors/automobile/registry.py
=====================================
Imports the canonical agent registry from core/pipeline/orchestrator so the
LangGraph path and the direct orchestrator path share the same instances.
"""

from core.pipeline.orchestrator import _SUB_AGENTS

AGENTS: dict = _SUB_AGENTS

WEIGHTS: dict[str, float] = {
    "sales_demand":       0.16,
    "raw_materials":      0.09,
    "fundamentals":       0.18,
    "pattern_analysis":   0.12,
    "sentiment":          0.04,
    "policy_regulatory":  0.09,
    "competitive_intel":  0.09,
    "risk_macro":         0.13,
    "valuation_catalyst": 0.10,
}
