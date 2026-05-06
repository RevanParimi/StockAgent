"""Sector-specific sub-score Pydantic models."""
from pydantic import BaseModel, Field


class BFSIFundamentalsAgentSubScores(BaseModel):
    asset_quality: float = Field(ge=0.0, le=1.0)
    net_interest: float = Field(ge=0.0, le=1.0)
    capital_adequacy: float = Field(ge=0.0, le=1.0)
    profitability: float = Field(ge=0.0, le=1.0)
    loan_mix: float = Field(ge=0.0, le=1.0)

class BFSIRiskAgentSubScores(BaseModel):
    asset_quality_trend: float = Field(ge=0.0, le=1.0)
    concentration_risk: float = Field(ge=0.0, le=1.0)
    deposit_stability: float = Field(ge=0.0, le=1.0)
    regulatory_risk: float = Field(ge=0.0, le=1.0)
    macro_sensitivity: float = Field(ge=0.0, le=1.0)

class BFSIMacroPolicyAgentSubScores(BaseModel):
    rbi_rate_cycle: float = Field(ge=0.0, le=1.0)
    system_credit: float = Field(ge=0.0, le=1.0)
    liquidity_conditions: float = Field(ge=0.0, le=1.0)
    regulatory_actions: float = Field(ge=0.0, le=1.0)
    fiscal_policy: float = Field(ge=0.0, le=1.0)

class BFSIInstitutionalAgentSubScores(BaseModel):
    fii_dii_flow: float = Field(ge=0.0, le=1.0)
    promoter_holding: float = Field(ge=0.0, le=1.0)
    insider_trades: float = Field(ge=0.0, le=1.0)
    analyst_changes: float = Field(ge=0.0, le=1.0)
    institutional_conc: float = Field(ge=0.0, le=1.0)

class BFSIPatternAgentSubScores(BaseModel):
    price_cycle: float = Field(ge=0.0, le=1.0)
    momentum: float = Field(ge=0.0, le=1.0)
    breakout_zones: float = Field(ge=0.0, le=1.0)
    relative_strength: float = Field(ge=0.0, le=1.0)
    volume_pattern: float = Field(ge=0.0, le=1.0)

class BFSIUniverseAgentSubScores(BaseModel):
    index_weight: float = Field(ge=0.0, le=1.0)
    peer_positioning: float = Field(ge=0.0, le=1.0)
    market_cap_tier: float = Field(ge=0.0, le=1.0)
    corporate_actions: float = Field(ge=0.0, le=1.0)
    rebalancing_risk: float = Field(ge=0.0, le=1.0)
