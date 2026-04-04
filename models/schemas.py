"""
models/schemas.py
=================
Pydantic v2 data models for all structured inputs and outputs
flowing through the Automobile Agent pipeline.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class StockQuery(BaseModel):
    """User request passed to the orchestrator."""
    ticker: str = Field(..., description="NSE/BSE ticker symbol, e.g. 'MARUTI'")
    company_name: str = Field(default="", description="Full company name (auto-resolved if empty)")
    exchange: str = Field(default="NSE")
    analysis_date: date = Field(default_factory=date.today)

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------------------------------------
# Per-agent sub-scores (shared structure)
# ---------------------------------------------------------------------------

class SubScores(BaseModel):
    """Generic 5-dimension sub-score container."""
    dim1: float = Field(ge=0.0, le=1.0)
    dim2: float = Field(ge=0.0, le=1.0)
    dim3: float = Field(ge=0.0, le=1.0)
    dim4: float = Field(ge=0.0, le=1.0)
    dim5: float = Field(ge=0.0, le=1.0)


class SalesDemandSubScores(BaseModel):
    fada_siam_dispatch: float = Field(ge=0.0, le=1.0)
    ev_segment_vahan: float = Field(ge=0.0, le=1.0)
    dealer_inventory: float = Field(ge=0.0, le=1.0)
    export_import: float = Field(ge=0.0, le=1.0)
    used_car_price_index: float = Field(ge=0.0, le=1.0)


class FundamentalsSubScores(BaseModel):
    revenue_ebitda_delta: float = Field(ge=0.0, le=1.0)
    margin_vs_peers: float = Field(ge=0.0, le=1.0)
    order_book_pipeline: float = Field(ge=0.0, le=1.0)
    attrition_headcount: float = Field(ge=0.0, le=1.0)
    promoter_fii_dii_flow: float = Field(ge=0.0, le=1.0)


class PatternAnalysisSubScores(BaseModel):
    price_cycle_position: float = Field(ge=0.0, le=1.0)
    seasonal_pattern: float = Field(ge=0.0, le=1.0)
    rsi_macd_bb: float = Field(ge=0.0, le=1.0)
    breakout_support_zone: float = Field(ge=0.0, le=1.0)
    peer_correlation: float = Field(ge=0.0, le=1.0)


class SentimentSubScores(BaseModel):
    news_nlp: float = Field(ge=0.0, le=1.0)
    management_tone: float = Field(ge=0.0, le=1.0)
    twitter_reddit_sentiment: float = Field(ge=0.0, le=1.0)
    youtube_view_spikes: float = Field(ge=0.0, le=1.0)
    dealer_consumer_feedback: float = Field(ge=0.0, le=1.0)


class RiskMacroSubScores(BaseModel):
    inr_usd_crude_exposure: float = Field(ge=0.0, le=1.0)
    commodity_prices: float = Field(ge=0.0, le=1.0)
    rbi_repo_emi_impact: float = Field(ge=0.0, le=1.0)
    emission_policy_risk: float = Field(ge=0.0, le=1.0)
    geopolitical_china_risk: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Individual agent outputs
# ---------------------------------------------------------------------------

class AgentOutput(BaseModel):
    """Base class for all sub-agent outputs."""
    agent: str
    ticker: str
    overall_score: float = Field(ge=0.0, le=1.0)
    key_positives: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    summary: str = ""
    data_freshness: str = ""
    raw_llm_response: str = Field(default="", exclude=True)  # not serialised in reports
    error: str | None = None


class SalesDemandOutput(AgentOutput):
    agent: str = "sales_demand"
    sub_scores: SalesDemandSubScores | None = None


class FundamentalsOutput(AgentOutput):
    agent: str = "fundamentals"
    sub_scores: FundamentalsSubScores | None = None


class PatternAnalysisOutput(AgentOutput):
    agent: str = "pattern_analysis"
    sub_scores: PatternAnalysisSubScores | None = None


class SentimentOutput(AgentOutput):
    agent: str = "sentiment"
    sub_scores: SentimentSubScores | None = None


class RiskMacroOutput(AgentOutput):
    agent: str = "risk_macro"
    sub_scores: RiskMacroSubScores | None = None


# ---------------------------------------------------------------------------
# Signal Aggregator output
# ---------------------------------------------------------------------------

class WeightedAgentScore(BaseModel):
    raw: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    weighted: float = Field(ge=0.0, le=1.0)


class FinalReport(BaseModel):
    """Top-level output of the entire Automobile Agent pipeline."""
    ticker: str
    company_name: str
    final_score: float = Field(ge=0.0, le=1.0)
    verdict: str  # STRONG BUY | BUY | NEUTRAL | SELL | STRONG SELL
    weighted_agent_scores: dict[str, WeightedAgentScore]
    conflicts_resolved: list[str] = Field(default_factory=list)
    conviction_drivers: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    investment_thesis: str = ""
    report_date: str = ""

    # Raw agent outputs attached for drill-down
    agent_outputs: dict[str, Any] = Field(default_factory=dict, exclude=False)

    def verdict_emoji(self) -> str:
        mapping = {
            "STRONG BUY": "🟢",
            "BUY": "🟩",
            "NEUTRAL": "🟡",
            "SELL": "🟧",
            "STRONG SELL": "🔴",
        }
        return mapping.get(self.verdict, "⚪")


# ---------------------------------------------------------------------------
# Pipeline run metadata
# ---------------------------------------------------------------------------

class PipelineRun(BaseModel):
    """Metadata envelope wrapping a full pipeline execution."""
    run_id: str
    query: StockQuery
    report: FinalReport | None = None
    status: str = "pending"   # pending | running | completed | failed
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)
