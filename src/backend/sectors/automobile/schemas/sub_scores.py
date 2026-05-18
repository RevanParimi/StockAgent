"""
src/backend/sectors/automobile/schemas/sub_scores.py
=====================================================
Automobile-sector sub-score Pydantic models — one per agent.

Each model defines the granular dimensions that the corresponding agent
scores (0.0–1.0 each).  They are attached to the AgentOutput subclass as
`sub_scores` and serialised into the full FinalReport.

These models live here (not in shared/schemas/pipeline.py) because they are
automobile-specific signals.  The output classes (SalesDemandOutput, etc.)
and the shared FinalReport still live in backend.shared.schemas.pipeline;
they import from here to attach the automobile-specific sub-score payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SalesDemandSubScores(BaseModel):
    fada_siam_dispatch:      float = Field(ge=0.0, le=1.0)
    ev_segment_vahan:        float = Field(ge=0.0, le=1.0)
    dealer_inventory:        float = Field(ge=0.0, le=1.0)
    export_import:           float = Field(ge=0.0, le=1.0)
    used_car_price_index:    float = Field(ge=0.0, le=1.0)
    waiting_period_booking:  float = Field(ge=0.0, le=1.0)


class FundamentalsSubScores(BaseModel):
    revenue_ebitda_delta:    float = Field(ge=0.0, le=1.0)
    margin_vs_peers:         float = Field(ge=0.0, le=1.0)
    order_book_pipeline:     float = Field(ge=0.0, le=1.0)
    attrition_headcount:     float = Field(ge=0.0, le=1.0)
    promoter_fii_dii_flow:   float = Field(ge=0.0, le=1.0)
    cash_flow_balance_sheet: float = Field(ge=0.0, le=1.0)


class PatternAnalysisSubScores(BaseModel):
    multi_timeframe_trend: float = Field(ge=0.0, le=1.0)
    seasonal_pattern:      float = Field(ge=0.0, le=1.0)
    rsi_macd_bb:           float = Field(ge=0.0, le=1.0)
    breakout_support_zone: float = Field(ge=0.0, le=1.0)
    peer_correlation:      float = Field(ge=0.0, le=1.0)
    volume_confirmation:   float = Field(ge=0.0, le=1.0)


class SentimentSubScores(BaseModel):
    news_nlp:                 float = Field(ge=0.0, le=1.0)
    management_tone:          float = Field(ge=0.0, le=1.0)
    twitter_reddit_sentiment: float = Field(ge=0.0, le=1.0)
    youtube_view_spikes:      float = Field(ge=0.0, le=1.0)
    dealer_consumer_feedback: float = Field(ge=0.0, le=1.0)
    institutional_sentiment:  float = Field(ge=0.0, le=1.0)


class RiskMacroSubScores(BaseModel):
    inr_usd_crude_exposure:      float = Field(ge=0.0, le=1.0)
    commodity_prices:            float = Field(ge=0.0, le=1.0)
    rbi_repo_emi_impact:         float = Field(ge=0.0, le=1.0)
    emission_policy_risk:        float = Field(ge=0.0, le=1.0)
    global_geopolitical_risk:    float = Field(ge=0.0, le=1.0)
    consumer_demand_sensitivity: float = Field(ge=0.0, le=1.0)


class RawMaterialsSubScores(BaseModel):
    steel_aluminium:           float = Field(ge=0.0, le=1.0)
    platinum_palladium:        float = Field(ge=0.0, le=1.0)
    crude_oil_polymer:         float = Field(ge=0.0, le=1.0)
    power_tariff:              float = Field(ge=0.0, le=1.0)
    commodities_trend:         float = Field(ge=0.0, le=1.0)
    pricing_power_passthrough: float = Field(ge=0.0, le=1.0)


class PolicyRegulatorySubScores(BaseModel):
    fame_ev_subsidy:        float = Field(ge=0.0, le=1.0)
    emission_norms:         float = Field(ge=0.0, le=1.0)
    union_budget_duties:    float = Field(ge=0.0, le=1.0)
    pli_scheme:             float = Field(ge=0.0, le=1.0)
    state_ev_incentives:    float = Field(ge=0.0, le=1.0)
    localisation_readiness: float = Field(ge=0.0, le=1.0)


class CompetitiveIntelSubScores(BaseModel):
    ev_market_share:      float = Field(ge=0.0, le=1.0)
    new_model_pipeline:   float = Field(ge=0.0, le=1.0)
    jv_acquisitions:      float = Field(ge=0.0, le=1.0)
    adas_safety_ratings:  float = Field(ge=0.0, le=1.0)
    competitive_position: float = Field(ge=0.0, le=1.0)
    future_readiness:     float = Field(ge=0.0, le=1.0)


class ValuationCatalystSubScores(BaseModel):
    pe_discount_vs_peers:           float = Field(ge=0.0, le=1.0)
    risk_adjusted_return_potential: float = Field(ge=0.0, le=1.0)
    mean_reversion_potential:       float = Field(ge=0.0, le=1.0)
    catalyst_timing:                float = Field(ge=0.0, le=1.0)
    recovery_signal_confidence:     float = Field(ge=0.0, le=1.0)
    sector_rotation_momentum:       float = Field(ge=0.0, le=1.0)
    valuation_trap_risk:            float = Field(ge=0.0, le=1.0)
