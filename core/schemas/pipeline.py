# ── MIGRATION SHIM ────────────────────────────────────────────────────────────
# Real module: src/backend/shared/schemas/pipeline.py
# This shim keeps all existing `from core.schemas.pipeline import ...` working
# unchanged during the migration.  Remove once every import is updated to the
# new path.
from backend.shared.schemas.pipeline import *  # noqa: F401, F403
from backend.shared.schemas.pipeline import (   # explicit re-exports for IDEs
    StockQuery,
    AgentOutput,
    SalesDemandSubScores, SalesDemandOutput,
    FundamentalsSubScores, FundamentalsOutput,
    PatternAnalysisSubScores, PatternAnalysisOutput,
    SentimentSubScores, SentimentOutput,
    RiskMacroSubScores, RiskMacroOutput,
    RawMaterialsSubScores, RawMaterialsOutput,
    PolicyRegulatorySubScores, PolicyRegulatoryOutput,
    CompetitiveIntelSubScores, CompetitiveIntelOutput,
    ValuationCatalystSubScores, ValuationCatalystOutput,
    WeightedAgentScore,
    FinalReport,
    PipelineRun,
)
