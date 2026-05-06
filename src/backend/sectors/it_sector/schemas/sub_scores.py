"""Sector-specific sub-score Pydantic models — IT Sector."""
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
    attrition_rank: float = Field(ge=0.0, le=1.0)      # was return_metrics_rank
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
    sector_narrative: float = Field(ge=0.0, le=1.0)    # was media_coverage
    news_volume: float = Field(ge=0.0, le=1.0)          # was social_buzz (LinkedIn/Reddit dropped)


class ITTranscriptNLPAgentSubScores(BaseModel):
    guidance_delta: float = Field(ge=0.0, le=1.0)       # was guidance_tone
    vertical_mix: float = Field(ge=0.0, le=1.0)         # was demand_signals
    geography_colour: float = Field(ge=0.0, le=1.0)     # was margin_commentary
    ai_deal_count: float = Field(ge=0.0, le=1.0)        # was ai_deal_mentions
    analyst_pushback: float = Field(ge=0.0, le=1.0)     # was analyst_qa_tone


class ITInsiderAgentSubScores(BaseModel):
    promoter_activity: float = Field(ge=0.0, le=1.0)
    director_trades: float = Field(ge=0.0, le=1.0)
    amfi_mf_flow: float = Field(ge=0.0, le=1.0)         # was smart_money_flow
    fii_futures: float = Field(ge=0.0, le=1.0)          # was short_interest (PCR/OI dropped)
    block_deals: float = Field(ge=0.0, le=1.0)
