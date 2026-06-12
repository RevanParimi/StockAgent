"""
tests/unit/test_unified_e2e_parity.py
======================================
End-to-end FinalReport contract parity for the Unified Sector Analyst
(Task 7, 2026-06-12 redesign).

Runs the REAL AutomobileAgentOrchestrator + REAL SignalAggregator code with
UNIFIED_ANALYST_SECTORS="automobile". Only LLM calls and fetchers are
mocked (no network):
  - _resolve_ticker            -> StockQuery(ticker="MARUTI", ...)
  - _prefetch_nse_data          -> no-op
  - build_sector_bundle          -> a tiny SectorDataBundle (patched at the
                                     source module so the call-time
                                     `from services.data.context.bundle_builder
                                     import build_sector_bundle` inside
                                     _run_unified resolves to the mock)
  - UnifiedAnalyst._call_llm     -> JSON for all 9 dimensions, score 0.65,
                                     valuation_catalyst.price_target=14000.0
  - SignalAggregator._call_llm   -> verdict JSON (BUY)

Asserts FinalReport keeps the same shape as the legacy 9-agent path:
  - weighted_agent_scores / agent_outputs keys == the 9 automobile dimensions
  - verdict in the 5-value enum
  - price_target == 14000.0 (proves valuation extras survive end-to-end
    through extract_valuation_fields)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.pipeline import base_orchestrator as bo_mod
from backend.shared.pipeline.unified_analyst import DIMENSIONS, UnifiedAnalyst
from backend.shared.pipeline.signal_aggregator import SignalAggregator
from core.schemas.pipeline import StockQuery
from services.data.context.bundle_builder import SectorDataBundle

VALID_VERDICTS = {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}

SUB_SCORE_FIELDS = {
    "sales_demand": ["fada_siam_dispatch", "ev_segment_vahan", "dealer_inventory",
                     "export_import", "used_car_price_index"],
    "raw_materials": ["steel_aluminium", "platinum_palladium", "crude_oil_polymer",
                      "power_tariff", "commodities_trend"],
    "fundamentals": ["revenue_ebitda_delta", "margin_vs_peers", "order_book_pipeline",
                     "attrition_headcount", "promoter_fii_dii_flow"],
    "pattern_analysis": ["price_cycle_position", "seasonal_pattern", "rsi_macd_bb",
                          "breakout_support_zone", "peer_correlation"],
    "sentiment": ["news_nlp", "management_tone", "twitter_reddit_sentiment",
                  "youtube_view_spikes", "dealer_consumer_feedback"],
    "policy_regulatory": ["fame_ev_subsidy", "emission_norms", "union_budget_duties",
                           "pli_scheme", "state_ev_incentives"],
    "competitive_intel": ["ev_market_share", "new_model_pipeline", "jv_acquisitions",
                           "adas_safety_ratings", "competitive_position"],
    "risk_macro": ["inr_usd_crude_exposure", "commodity_prices", "rbi_repo_emi_impact",
                   "emission_policy_risk", "global_geopolitical_risk"],
    "valuation_catalyst": ["pe_discount_vs_peers", "technical_trend", "mean_reversion_potential",
                            "support_zone_strength", "recovery_signal_confidence"],
}


def _unified_analyst_payload(score: float = 0.65) -> dict:
    payload: dict = {}
    for dim in DIMENSIONS["automobile"]:
        block = {
            "score": score,
            "confidence": 0.8,
            "summary": f"{dim} summary for MARUTI.",
            "key_positives": ["positive driver"],
            "key_risks": ["some risk"],
            "sub_scores": {field: score for field in SUB_SCORE_FIELDS[dim]},
            "ticker_vs_peers": "MARUTI vs peers",
            "bull_case_if": "bull case",
            "bear_case_if": "bear case",
            "what_changed": "no major change",
        }
        if dim == "valuation_catalyst":
            block.update({
                "price_target": 14000.0,
                "recovery_timeline_quarters": 2,
                "discount_reason": "SECTOR_ROTATION",
                "recovery_catalysts": ["earnings beat"],
                "fair_value_estimate": 13500.0,
                "current_discount_pct": -8.0,
            })
        payload[dim] = block
    return payload


def _aggregator_verdict_payload() -> dict:
    return {
        "final_score": 0.65,
        "verdict": "BUY",
        "conflicts_resolved": [],
        "conviction_drivers": ["Strong demand", "Improving fundamentals"],
        "top_risks": ["EV transition risk"],
        "executive_summary": "Maruti looks healthy near-term.",
        "investment_thesis": "Maruti remains a solid OEM pick with festive tailwinds.",
        "report_date": "2026-06-12",
    }


def _make_llm_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize("run_mode", ["sync", "async"])
async def test_unified_e2e_final_report_contract_parity(monkeypatch, run_mode):
    monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "automobile")
    monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_FALLBACK_LEGACY", True)

    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator

    orchestrator = AutomobileAgentOrchestrator()

    query = StockQuery(ticker="MARUTI", company_name="Maruti")
    bundle = SectorDataBundle(
        sections={"company_news": "Maruti reported strong Q4 sales."},
        has_real_data=True,
        api_calls_made={"serper": 3, "tavily": 1},
    )

    unified_response = _make_llm_response(json.dumps(_unified_analyst_payload(0.65)))
    aggregator_response = _make_llm_response(json.dumps(_aggregator_verdict_payload()))

    with patch.object(orchestrator, "_resolve_ticker", return_value=query), \
         patch.object(orchestrator, "_prefetch_nse_data"), \
         patch("services.data.context.bundle_builder.build_sector_bundle", return_value=bundle), \
         patch.object(UnifiedAnalyst, "_call_llm", return_value=unified_response.choices[0].message.content) as mock_unified_llm, \
         patch.object(SignalAggregator, "_call_llm", return_value=aggregator_response.choices[0].message.content) as mock_agg_llm:

        if run_mode == "sync":
            report = orchestrator.analyse("maruti")
        else:
            report = await orchestrator.analyse_async("maruti")

    # Exactly one unified-analyst LLM call, one aggregator LLM call.
    mock_unified_llm.assert_called_once()
    mock_agg_llm.assert_called_once()

    expected_dims = set(DIMENSIONS["automobile"])
    assert set(report.weighted_agent_scores) == expected_dims
    assert set(report.agent_outputs) == expected_dims

    assert report.verdict in VALID_VERDICTS
    assert report.verdict == "BUY"

    # Valuation extras survive end-to-end through extract_valuation_fields.
    assert report.price_target == 14000.0
    assert report.recovery_timeline_quarters == 2
    assert report.discount_reason == "SECTOR_ROTATION"
    assert report.recovery_catalysts == ["earnings beat"]
    assert report.undervalued_by_pct == 8.0
