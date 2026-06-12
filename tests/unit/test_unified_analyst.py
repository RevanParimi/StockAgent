"""Tests for the sector-generic UnifiedAnalyst (Task 4, 2026-06-12).

src/backend/shared/pipeline/unified_analyst.py — UnifiedAnalyst.run()

One LLM call -> all 9 dimension AgentOutput subclasses. NEVER raises;
returns {} on total failure. The LLM client is faked via MagicMock on
`a._client` (mirrors SignalAggregator test conventions).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.schemas.pipeline import (
    StockQuery,
    SalesDemandOutput,
    RawMaterialsOutput,
    FundamentalsOutput,
    PatternAnalysisOutput,
    SentimentOutput,
    PolicyRegulatoryOutput,
    CompetitiveIntelOutput,
    RiskMacroOutput,
    ValuationCatalystOutput,
)
from services.data.context.bundle_builder import SectorDataBundle
from backend.shared.pipeline.unified_analyst import (
    UnifiedAnalyst,
    DIMENSIONS,
    _salvage_truncated_json,
)


DIM_CLASS_MAP = {
    "sales_demand": SalesDemandOutput,
    "raw_materials": RawMaterialsOutput,
    "fundamentals": FundamentalsOutput,
    "pattern_analysis": PatternAnalysisOutput,
    "sentiment": SentimentOutput,
    "policy_regulatory": PolicyRegulatoryOutput,
    "competitive_intel": CompetitiveIntelOutput,
    "risk_macro": RiskMacroOutput,
    "valuation_catalyst": ValuationCatalystOutput,
}

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


def _make_query() -> StockQuery:
    return StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India Ltd", nse_data={})


def _make_bundle() -> SectorDataBundle:
    return SectorDataBundle(
        sections={"company_news": "some live data"},
        has_real_data=True,
        api_calls_made={"serper": 3, "tavily": 1},
    )


def _dimension_block(score: float = 0.7, confidence: float = 0.8, sub_scores: dict | None = None) -> dict:
    block = {
        "score": score,
        "confidence": confidence,
        "summary": "Test summary",
        "key_positives": ["positive 1"],
        "key_risks": ["risk 1"],
        "ticker_vs_peers": "MARUTI vs peers",
        "bull_case_if": "bull case",
        "bear_case_if": "bear case",
        "what_changed": "changed",
    }
    if sub_scores is not None:
        block["sub_scores"] = sub_scores
    return block


def _full_payload(score: float = 0.7, omit: list[str] | None = None, sub_scores_present: bool = True) -> dict:
    omit = omit or []
    payload = {}
    for dim in DIMENSIONS["automobile"]:
        if dim in omit:
            continue
        sub_scores = None
        if sub_scores_present:
            sub_scores = {field: score for field in SUB_SCORE_FIELDS[dim]}
        block = _dimension_block(score=score, sub_scores=sub_scores)
        if dim == "valuation_catalyst":
            block.update({
                "price_target": 12345.0,
                "recovery_timeline_quarters": 2,
                "discount_reason": "SECTOR_ROTATION",
                "recovery_catalysts": ["earnings beat"],
                "fair_value_estimate": 12000.0,
                "current_discount_pct": -10.0,
            })
        payload[dim] = block
    return payload


def _set_llm_response(analyst: UnifiedAnalyst, content: str) -> MagicMock:
    mock_client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
    mock_client.chat.completions.create.return_value = response
    analyst._client = mock_client
    return mock_client


@pytest.fixture
def analyst() -> UnifiedAnalyst:
    a = UnifiedAnalyst.__new__(UnifiedAnalyst)
    return a


class TestGoodPayload:
    def test_all_nine_keys_correct_classes_and_one_call(self, analyst):
        payload = _full_payload(score=0.7)
        mock_client = _set_llm_response(analyst, json.dumps(payload))

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        assert set(outs.keys()) == set(DIMENSIONS["automobile"])
        for dim, cls in DIM_CLASS_MAP.items():
            assert isinstance(outs[dim], cls)
            assert outs[dim].overall_score == pytest.approx(0.7)

        vc = outs["valuation_catalyst"]
        assert isinstance(vc, ValuationCatalystOutput)
        assert vc.price_target == 12345.0
        assert vc.recovery_timeline_quarters == 2
        assert vc.discount_reason == "SECTOR_ROTATION"
        assert vc.recovery_catalysts == ["earnings beat"]
        assert vc.fair_value_estimate == 12000.0
        assert vc.current_discount_pct == -10.0

        assert mock_client.chat.completions.create.call_count == 1


class TestMissingDimension:
    def test_missing_sentiment_gets_neutral_with_error(self, analyst):
        payload = _full_payload(score=0.7, omit=["sentiment"])
        _set_llm_response(analyst, json.dumps(payload))

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        assert "sentiment" in outs
        sentiment = outs["sentiment"]
        assert isinstance(sentiment, SentimentOutput)
        assert sentiment.overall_score == pytest.approx(0.5)
        assert sentiment.error == "missing_in_unified_response"

        # All other dimensions still parsed normally
        assert outs["sales_demand"].overall_score == pytest.approx(0.7)
        assert outs["sales_demand"].error is None


class TestSubScoresOmitted:
    def test_each_sub_score_field_defaults_to_dimension_score(self, analyst):
        payload = _full_payload(score=0.65, sub_scores_present=False)
        _set_llm_response(analyst, json.dumps(payload))

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        for dim, fields in SUB_SCORE_FIELDS.items():
            sub_scores = outs[dim].sub_scores
            assert sub_scores is not None
            for field in fields:
                assert getattr(sub_scores, field) == pytest.approx(0.65)


class TestClientRaisesEveryTime:
    def test_run_returns_empty_dict_never_raises(self, analyst):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")
        analyst._client = mock_client

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        assert outs == {}


class TestNonJsonResponse:
    def test_non_json_response_returns_empty_dict(self, analyst):
        _set_llm_response(analyst, "this is not json")

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        assert outs == {}


class TestScoreClamping:
    def test_score_above_one_is_clamped(self, analyst):
        payload = _full_payload(score=1.0)
        # Manually set one dimension's score to an out-of-range value.
        payload["sales_demand"]["score"] = 1.7
        # sub_scores also out of range to verify clamping there too
        payload["sales_demand"]["sub_scores"] = {
            field: 1.7 for field in SUB_SCORE_FIELDS["sales_demand"]
        }
        _set_llm_response(analyst, json.dumps(payload))

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        sales = outs["sales_demand"]
        assert sales.overall_score == 1.0
        assert sales.sub_scores is not None
        for field in SUB_SCORE_FIELDS["sales_demand"]:
            assert getattr(sales.sub_scores, field) == 1.0


class TestUnknownSector:
    def test_unknown_sector_returns_empty_dict(self, analyst):
        # Should never even reach the LLM client.
        analyst._client = MagicMock()

        outs = analyst.run(_make_query(), _make_bundle(), "bfsi")

        assert outs == {}
        analyst._client.chat.completions.create.assert_not_called()


class TestPerDimensionParseError:
    def test_malformed_dimension_block_isolated(self, analyst):
        payload = _full_payload(score=0.7)
        # Make one dimension's block malformed (score is a non-numeric string
        # that cannot be cast to float).
        payload["fundamentals"]["score"] = "not-a-number"
        _set_llm_response(analyst, json.dumps(payload))

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        # All 9 keys still present.
        assert set(outs.keys()) == set(DIMENSIONS["automobile"])
        fundamentals = outs["fundamentals"]
        assert fundamentals.overall_score == pytest.approx(0.5)
        assert fundamentals.error is not None
        assert fundamentals.error.startswith("parse_error")

        # Other dimensions unaffected.
        assert outs["sales_demand"].overall_score == pytest.approx(0.7)
        assert outs["sales_demand"].error is None


class TestTruncatedResponseSalvage:
    def test_truncated_mid_seventh_block_salvages_first_six(self, analyst):
        payload = _full_payload(score=0.7)
        full_json = json.dumps(payload, indent=2)

        # Locate the 7th dimension block (competitive_intel) and cut the
        # response mid-way through one of its string values, simulating a
        # max_tokens truncation.
        dims = DIMENSIONS["automobile"]
        seventh_dim = dims[6]
        assert seventh_dim == "competitive_intel"

        marker = f'"{seventh_dim}": {{'
        marker_idx = full_json.index(marker)
        # Find a string value inside this block to cut through, e.g. "summary": "Test summary"
        summary_idx = full_json.index('"summary": "Test summary"', marker_idx)
        # Cut partway through the summary's string value, leaving an
        # unterminated string -> json.loads must fail.
        cut_point = summary_idx + len('"summary": "Test sum')
        truncated = full_json[:cut_point]

        # Sanity: this must NOT be valid JSON on its own.
        with pytest.raises(json.JSONDecodeError):
            json.loads(truncated)

        _set_llm_response(analyst, truncated)

        outs = analyst.run(_make_query(), _make_bundle(), "automobile")

        # NO exception, NO empty dict — all 9 keys present.
        assert outs != {}
        assert set(outs.keys()) == set(DIMENSIONS["automobile"])

        # First 6 dimensions (fully present before the cut) parsed normally.
        for dim in dims[:6]:
            out = outs[dim]
            assert out.overall_score == pytest.approx(0.7)
            assert out.error is None

        # Remaining dimensions (lost to truncation) degrade to neutral+error.
        for dim in dims[6:]:
            out = outs[dim]
            assert out.overall_score == pytest.approx(0.5)
            assert out.error is not None


class TestSalvageTruncatedJsonHelper:
    def test_garbage_returns_empty_dict(self):
        assert _salvage_truncated_json("garbage") == {}

    def test_empty_string_returns_empty_dict(self):
        assert _salvage_truncated_json("") == {}

    def test_valid_full_json_still_works_or_empty(self):
        # _salvage_truncated_json is only called on json.loads failure in
        # run(), but it must not raise if called on valid JSON: either it
        # successfully salvages the full object, or returns {}.
        payload = _full_payload(score=0.6)
        full_json = json.dumps(payload)
        result = _salvage_truncated_json(full_json)
        assert isinstance(result, dict)
