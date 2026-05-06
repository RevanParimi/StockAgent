"""Sector-specific sub-score Pydantic models."""
from pydantic import BaseModel, Field


class ITFundamentalsAgentSubScores(BaseModel):
    revenue_growth: float = Field(ge=0.0, le=1.0)
    ebit_margins: float = Field(ge=0.0, le=1.0)
    deal_wins: float = Field(ge=0.0, le=1.0)
    attrition: float = Field(ge=0.0, le=1.0)
    valuation: float = Field(ge=0.0, le=1.0)

class ITGlobalMacroAgentSubScores(BaseModel):
    us_tech_spend: float = Field(ge=0.0, le=1.0)
    fed_rate_impact: float = Field(ge=0.0, le=1.0)
    usd_inr: float = Field(ge=0.0, le=1.0)
    geopolitical: float = Field(ge=0.0, le=1.0)
    ma_activity: float = Field(ge=0.0, le=1.0)

class ITRiskMacroAgentSubScores(BaseModel):
    visa_risk: float = Field(ge=0.0, le=1.0)
    ai_disruption: float = Field(ge=0.0, le=1.0)
    client_concentration: float = Field(ge=0.0, le=1.0)
    fx_hedge: float = Field(ge=0.0, le=1.0)
    talent_risk: float = Field(ge=0.0, le=1.0)

class ITPeerBenchmarkAgentSubScores(BaseModel):
    revenue_growth_rank: float = Field(ge=0.0, le=1.0)
    margin_rank: float = Field(ge=0.0, le=1.0)
    deal_momentum_rank: float = Field(ge=0.0, le=1.0)
    return_metrics_rank: float = Field(ge=0.0, le=1.0)
    valuation_gap: float = Field(ge=0.0, le=1.0)

class ITPatternAgentSubScores(BaseModel):
    price_cycle: float = Field(ge=0.0, le=1.0)
    momentum: float = Field(ge=0.0, le=1.0)
    breakout_levels: float = Field(ge=0.0, le=1.0)
    nifty_it_beta: float = Field(ge=0.0, le=1.0)
    volume_quality: float = Field(ge=0.0, le=1.0)

class ITSentimentAgentSubScores(BaseModel):
    ai_narrative: float = Field(ge=0.0, le=1.0)
    layoff_signals: float = Field(ge=0.0, le=1.0)
    management_tone: float = Field(ge=0.0, le=1.0)
    media_coverage: float = Field(ge=0.0, le=1.0)
    social_buzz: float = Field(ge=0.0, le=1.0)

class ITTranscriptNLPAgentSubScores(BaseModel):
    guidance_tone: float = Field(ge=0.0, le=1.0)
    demand_signals: float = Field(ge=0.0, le=1.0)
    margin_commentary: float = Field(ge=0.0, le=1.0)
    ai_deal_mentions: float = Field(ge=0.0, le=1.0)
    analyst_qa_tone: float = Field(ge=0.0, le=1.0)

class ITInsiderAgentSubScores(BaseModel):
    promoter_activity: float = Field(ge=0.0, le=1.0)
    director_trades: float = Field(ge=0.0, le=1.0)
    smart_money_flow: float = Field(ge=0.0, le=1.0)
    short_interest: float = Field(ge=0.0, le=1.0)
    block_deals: float = Field(ge=0.0, le=1.0)
