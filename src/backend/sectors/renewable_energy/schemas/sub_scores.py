"""Sector-specific sub-score Pydantic models."""
from pydantic import BaseModel, Field


class REFundamentalsAgentSubScores(BaseModel):
    capacity_utilisation: float = Field(ge=0.0, le=1.0)
    ebitda_quality: float = Field(ge=0.0, le=1.0)
    debt_serviceability: float = Field(ge=0.0, le=1.0)
    receivables: float = Field(ge=0.0, le=1.0)
    leverage: float = Field(ge=0.0, le=1.0)

class REBusinessAgentSubScores(BaseModel):
    subsector_mix: float = Field(ge=0.0, le=1.0)
    ppa_quality: float = Field(ge=0.0, le=1.0)
    pipeline_cred: float = Field(ge=0.0, le=1.0)
    customer_divers: float = Field(ge=0.0, le=1.0)
    geography_spread: float = Field(ge=0.0, le=1.0)

class REValuationAgentSubScores(BaseModel):
    ev_per_mw: float = Field(ge=0.0, le=1.0)
    ev_ebitda: float = Field(ge=0.0, le=1.0)
    tariff_vs_auction: float = Field(ge=0.0, le=1.0)
    pipeline_dcf: float = Field(ge=0.0, le=1.0)
    implied_irr: float = Field(ge=0.0, le=1.0)

class RESentimentPolicyAgentSubScores(BaseModel):
    mnre_auction_health: float = Field(ge=0.0, le=1.0)
    budget_allocation: float = Field(ge=0.0, le=1.0)
    policy_tailwinds: float = Field(ge=0.0, le=1.0)
    green_hydrogen: float = Field(ge=0.0, le=1.0)
    news_sentiment: float = Field(ge=0.0, le=1.0)

class RETechnicalAgentSubScores(BaseModel):
    moving_averages: float = Field(ge=0.0, le=1.0)
    rsi_signal: float = Field(ge=0.0, le=1.0)
    macd_weekly: float = Field(ge=0.0, le=1.0)
    volume_catalyst: float = Field(ge=0.0, le=1.0)
    accumulation_zone: float = Field(ge=0.0, le=1.0)

class RERiskAgentSubScores(BaseModel):
    discom_credit: float = Field(ge=0.0, le=1.0)
    regulatory_change: float = Field(ge=0.0, le=1.0)
    weather_resource: float = Field(ge=0.0, le=1.0)
    grid_integration: float = Field(ge=0.0, le=1.0)
    commodity_input: float = Field(ge=0.0, le=1.0)
