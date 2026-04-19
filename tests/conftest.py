"""
tests/conftest.py
=================
Shared pytest fixtures used across all test modules.
Covers all 9 agents: sales_demand, raw_materials, fundamentals,
pattern_analysis, sentiment, policy_regulatory, competitive_intel, risk_macro,
valuation_catalyst.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from core.schemas.pipeline import (
    AgentOutput,
    CompetitiveIntelOutput,
    CompetitiveIntelSubScores,
    FundamentalsOutput,
    FundamentalsSubScores,
    PatternAnalysisOutput,
    PatternAnalysisSubScores,
    PolicyRegulatoryOutput,
    PolicyRegulatorySubScores,
    RawMaterialsOutput,
    RawMaterialsSubScores,
    RiskMacroOutput,
    RiskMacroSubScores,
    SalesDemandOutput,
    SalesDemandSubScores,
    SentimentOutput,
    SentimentSubScores,
    ValuationCatalystOutput,
    ValuationCatalystSubScores,
    StockQuery,
    WeightedAgentScore,
    FinalReport,
)


# ---------------------------------------------------------------------------
# Stock query fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def maruti_query() -> StockQuery:
    return StockQuery(
        ticker="MARUTI",
        company_name="Maruti Suzuki India Ltd",
        exchange="NSE",
        analysis_date=date(2026, 4, 16),
    )


@pytest.fixture
def tatamotors_query() -> StockQuery:
    return StockQuery(
        ticker="TATAMOTORS",
        company_name="Tata Motors Ltd",
        exchange="NSE",
        analysis_date=date(2026, 4, 16),
    )


# ---------------------------------------------------------------------------
# Mock LLM response factories — one per agent
# ---------------------------------------------------------------------------

def make_sales_demand_json(score: float = 0.72) -> str:
    return json.dumps({
        "agent": "sales_demand",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "fada_siam_dispatch": 0.75,
            "ev_segment_vahan": 0.60,
            "dealer_inventory": 0.80,
            "export_import": 0.65,
            "used_car_price_index": 0.78,
        },
        "key_positives": ["Strong retail offtake", "Healthy inventory days"],
        "key_risks": ["Slow EV transition"],
        "summary": "Maruti shows strong demand momentum driven by festive season.",
        "data_freshness": "March 2026",
    })


def make_raw_materials_json(score: float = 0.60) -> str:
    return json.dumps({
        "agent": "raw_materials",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "steel_aluminium": 0.58,
            "platinum_palladium": 0.62,
            "crude_oil_polymer": 0.55,
            "power_tariff": 0.65,
            "commodities_trend": 0.60,
        },
        "key_positives": ["Steel prices softening", "Stable power tariff"],
        "key_risks": ["Crude oil spike risk"],
        "summary": "Raw material environment is moderately favourable.",
        "data_freshness": "April 2026",
    })


def make_fundamentals_json(score: float = 0.68) -> str:
    return json.dumps({
        "agent": "fundamentals",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "revenue_ebitda_delta": 0.70,
            "margin_vs_peers": 0.65,
            "order_book_pipeline": 0.55,
            "attrition_headcount": 0.72,
            "promoter_fii_dii_flow": 0.75,
        },
        "key_positives": ["Revenue growing 12% YoY", "FII buying"],
        "key_risks": ["Margin pressure from input costs"],
        "summary": "Fundamentals remain solid with improving EBITDA margins.",
        "data_freshness": "Q3 FY26",
    })


def make_pattern_json(score: float = 0.55) -> str:
    return json.dumps({
        "agent": "pattern_analysis",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "price_cycle_position": 0.60,
            "seasonal_pattern": 0.65,
            "rsi_macd_bb": 0.50,
            "breakout_support_zone": 0.45,
            "peer_correlation": 0.55,
        },
        "key_positives": ["Festive season tailwind (Q2/Q3)"],
        "key_risks": ["RSI approaching overbought"],
        "summary": "Technical picture is neutral with mild seasonal support.",
        "data_freshness": "2026-04-16",
    })


def make_sentiment_json(score: float = 0.70) -> str:
    return json.dumps({
        "agent": "sentiment",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "news_nlp": 0.72,
            "management_tone": 0.75,
            "twitter_reddit_sentiment": 0.65,
            "youtube_view_spikes": 0.68,
            "dealer_consumer_feedback": 0.70,
        },
        "key_positives": ["Positive earnings call tone"],
        "key_risks": ["Minor social media noise on CNG wait times"],
        "summary": "Sentiment is broadly positive across channels.",
        "data_freshness": "April 2026",
    })


def make_policy_regulatory_json(score: float = 0.65) -> str:
    return json.dumps({
        "agent": "policy_regulatory",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "fame_ev_subsidy": 0.70,
            "emission_norms": 0.60,
            "union_budget_duties": 0.65,
            "pli_scheme": 0.68,
            "state_ev_incentives": 0.62,
        },
        "key_positives": ["FAME II subsidy continuity", "PLI scheme benefit"],
        "key_risks": ["CAFE norms tightening timeline"],
        "summary": "Policy environment is broadly supportive for ICE and hybrid.",
        "data_freshness": "April 2026",
    })


def make_competitive_intel_json(score: float = 0.62) -> str:
    return json.dumps({
        "agent": "competitive_intel",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "ev_market_share": 0.45,
            "new_model_pipeline": 0.70,
            "jv_acquisitions": 0.65,
            "adas_safety_ratings": 0.60,
            "competitive_position": 0.68,
        },
        "key_positives": ["Strong new model pipeline (Jimny, Invicto)"],
        "key_risks": ["EV market share laggard vs Tata"],
        "summary": "Maruti leads in volume but trails on EV competitiveness.",
        "data_freshness": "April 2026",
    })


def make_risk_macro_json(score: float = 0.58) -> str:
    return json.dumps({
        "agent": "risk_macro",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "inr_usd_crude_exposure": 0.55,
            "commodity_prices": 0.60,
            "rbi_repo_emi_impact": 0.65,
            "emission_policy_risk": 0.58,
            "global_geopolitical_risk": 0.50,
        },
        "key_positives": ["Stable INR", "Commodity prices softening"],
        "key_risks": ["China semiconductor risk", "Elevated crude oil"],
        "summary": "Moderate macro risk environment with some commodity relief.",
        "data_freshness": "April 2026",
    })


def make_aggregator_json(score: float = 0.66) -> str:
    return json.dumps({
        "ticker": "MARUTI",
        "company_name": "Maruti Suzuki India Ltd",
        "final_score": score,
        "verdict": "BUY",
        "weighted_agent_scores": {},
        "conflicts_resolved": [],
        "conviction_drivers": [
            "Strong retail offtake and dealer inventory",
            "Positive management tone on earnings call",
            "FII buying trend continuing",
        ],
        "top_risks": [
            "EV transition risk",
            "Elevated crude oil and INR volatility",
            "China semiconductor supply dependency",
        ],
        "investment_thesis": (
            "Maruti remains India's dominant passenger vehicle OEM with strong brand equity "
            "and distribution. Near-term demand is healthy with festive momentum intact. "
            "The key risk is the pace of EV transition where the company is a laggard."
        ),
        "report_date": "2026-04-16",
    })


# ---------------------------------------------------------------------------
# Pre-built agent output fixtures — all 8 agents
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sales_demand_output() -> SalesDemandOutput:
    return SalesDemandOutput(
        ticker="MARUTI",
        overall_score=0.72,
        sub_scores=SalesDemandSubScores(
            fada_siam_dispatch=0.75,
            ev_segment_vahan=0.60,
            dealer_inventory=0.80,
            export_import=0.65,
            used_car_price_index=0.78,
        ),
        key_positives=["Strong retail offtake"],
        key_risks=["Slow EV transition"],
        summary="Demand momentum strong.",
        data_freshness="March 2026",
    )


@pytest.fixture
def mock_all_agent_outputs(mock_sales_demand_output) -> dict:
    """All 9 agent outputs with realistic scores for MARUTI."""
    return {
        "sales_demand": mock_sales_demand_output,
        "raw_materials": RawMaterialsOutput(
            ticker="MARUTI", overall_score=0.60,
            sub_scores=RawMaterialsSubScores(
                steel_aluminium=0.58, platinum_palladium=0.62,
                crude_oil_polymer=0.55, power_tariff=0.65,
                commodities_trend=0.60,
            ),
        ),
        "fundamentals": FundamentalsOutput(
            ticker="MARUTI", overall_score=0.68,
            sub_scores=FundamentalsSubScores(
                revenue_ebitda_delta=0.70, margin_vs_peers=0.65,
                order_book_pipeline=0.55, attrition_headcount=0.72,
                promoter_fii_dii_flow=0.75,
            ),
        ),
        "pattern_analysis": PatternAnalysisOutput(
            ticker="MARUTI", overall_score=0.55,
            sub_scores=PatternAnalysisSubScores(
                price_cycle_position=0.60, seasonal_pattern=0.65,
                rsi_macd_bb=0.50, breakout_support_zone=0.45,
                peer_correlation=0.55,
            ),
        ),
        "sentiment": SentimentOutput(
            ticker="MARUTI", overall_score=0.70,
            sub_scores=SentimentSubScores(
                news_nlp=0.72, management_tone=0.75,
                twitter_reddit_sentiment=0.65, youtube_view_spikes=0.68,
                dealer_consumer_feedback=0.70,
            ),
        ),
        "policy_regulatory": PolicyRegulatoryOutput(
            ticker="MARUTI", overall_score=0.65,
            sub_scores=PolicyRegulatorySubScores(
                fame_ev_subsidy=0.70, emission_norms=0.60,
                union_budget_duties=0.65, pli_scheme=0.68,
                state_ev_incentives=0.62,
            ),
        ),
        "competitive_intel": CompetitiveIntelOutput(
            ticker="MARUTI", overall_score=0.62,
            sub_scores=CompetitiveIntelSubScores(
                ev_market_share=0.45, new_model_pipeline=0.70,
                jv_acquisitions=0.65, adas_safety_ratings=0.60,
                competitive_position=0.68,
            ),
        ),
        "risk_macro": RiskMacroOutput(
            ticker="MARUTI", overall_score=0.58,
            sub_scores=RiskMacroSubScores(
                inr_usd_crude_exposure=0.55, commodity_prices=0.60,
                rbi_repo_emi_impact=0.65, emission_policy_risk=0.58,
                global_geopolitical_risk=0.50,
            ),
        ),
        "valuation_catalyst": ValuationCatalystOutput(
            ticker="MARUTI", overall_score=0.72,
            sub_scores=ValuationCatalystSubScores(
                pe_discount_vs_peers=0.70, technical_trend=0.75,
                mean_reversion_potential=0.68, support_zone_strength=0.65,
                recovery_signal_confidence=0.72,
            ),
            fair_value_estimate=11500.0,
            current_discount_pct=-18.5,
            discount_reason="MACRO_SHOCK",
            recovery_catalysts=["Oil price normalisation", "FII return to EMs", "Strong Q1 results"],
            price_target=11000.0,
            recovery_timeline_quarters=3,
        ),
    }


@pytest.fixture
def mock_final_report() -> FinalReport:
    """A complete FinalReport fixture for contract/serialization tests."""
    ws = WeightedAgentScore(raw=0.66, weight=1.0, weighted=0.66)
    return FinalReport(
        ticker="MARUTI",
        company_name="Maruti Suzuki India Ltd",
        final_score=0.66,
        verdict="BUY",
        weighted_agent_scores={"fundamentals": ws},
        conviction_drivers=["Strong demand", "FII buying"],
        top_risks=["EV transition lag", "Crude oil"],
        investment_thesis="Maruti remains dominant with solid near-term momentum.",
        report_date="2026-04-16",
    )
