"""
tests/conftest.py
=================
Shared pytest fixtures used across all test modules.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import (
    AgentOutput,
    FundamentalsOutput,
    FundamentalsSubScores,
    PatternAnalysisOutput,
    PatternAnalysisSubScores,
    RiskMacroOutput,
    RiskMacroSubScores,
    SalesDemandOutput,
    SalesDemandSubScores,
    SentimentOutput,
    SentimentSubScores,
    StockQuery,
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
        analysis_date=date(2026, 4, 3),
    )


@pytest.fixture
def tatamotors_query() -> StockQuery:
    return StockQuery(
        ticker="TATAMOTORS",
        company_name="Tata Motors Ltd",
        exchange="NSE",
        analysis_date=date(2026, 4, 3),
    )


# ---------------------------------------------------------------------------
# Mock LLM response factories
# ---------------------------------------------------------------------------

def make_sales_demand_json(score: float = 0.72) -> str:
    import json
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


def make_fundamentals_json(score: float = 0.68) -> str:
    import json
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
    import json
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
        "data_freshness": "2026-04-01",
    })


def make_sentiment_json(score: float = 0.70) -> str:
    import json
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
        "key_positives": ["Positive earnings call tone", "Strong YouTube engagement on Brezza launch"],
        "key_risks": ["Minor social media noise on CNG wait times"],
        "summary": "Sentiment is broadly positive across channels.",
        "data_freshness": "April 2026",
    })


def make_risk_macro_json(score: float = 0.58) -> str:
    import json
    return json.dumps({
        "agent": "risk_macro",
        "ticker": "MARUTI",
        "overall_score": score,
        "sub_scores": {
            "inr_usd_crude_exposure": 0.55,
            "commodity_prices": 0.60,
            "rbi_repo_emi_impact": 0.65,
            "emission_policy_risk": 0.58,
            "geopolitical_china_risk": 0.50,
        },
        "key_positives": ["Stable INR", "Commodity prices softening"],
        "key_risks": ["China semiconductor risk", "Elevated crude oil"],
        "summary": "Moderate macro risk environment with some commodity relief.",
        "data_freshness": "April 2026",
    })


def make_aggregator_json(score: float = 0.66) -> str:
    import json
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
        "report_date": "2026-04-03",
    })


# ---------------------------------------------------------------------------
# Pre-built agent output fixtures (bypass LLM)
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
    return {
        "sales_demand": mock_sales_demand_output,
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
        "risk_macro": RiskMacroOutput(
            ticker="MARUTI", overall_score=0.58,
            sub_scores=RiskMacroSubScores(
                inr_usd_crude_exposure=0.55, commodity_prices=0.60,
                rbi_repo_emi_impact=0.65, emission_policy_risk=0.58,
                geopolitical_china_risk=0.50,
            ),
        ),
    }
