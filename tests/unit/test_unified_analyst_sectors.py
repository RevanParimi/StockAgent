"""Tests for the sector spec registry in unified_analyst.py (sector rollout).

src/backend/shared/pipeline/unified_analyst.py — SECTOR_SPECS, SectorSpec, DIMENSIONS

Covers:
- SECTOR_SPECS has all 4 sectors (automobile, banking_bfsi, it_sector, renewable_energy)
- DIMENSIONS[sector] matches each sector's AGENT_WEIGHTS keys exactly (set AND order)
- valuation extras flag only set for automobile
- registered sector with missing prompts module -> run() returns {} (never raises)
- automobile behaviour unchanged (existing tests in test_unified_analyst.py stay green)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.schemas.pipeline import StockQuery, AgentOutput
from services.data.context.bundle_builder import SectorDataBundle
from backend.shared.pipeline.unified_analyst import (
    UnifiedAnalyst,
    DIMENSIONS,
    SECTOR_SPECS,
    SectorSpec,
)

from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS as BFSI_WEIGHTS
from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS as IT_WEIGHTS
from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS as RE_WEIGHTS
from backend.sectors.automobile.config.settings import AGENT_WEIGHTS as AUTO_WEIGHTS


ALL_SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]


def _make_query(ticker: str = "HDFCBANK") -> StockQuery:
    return StockQuery(ticker=ticker, company_name="Test Company", nse_data={})


def _make_bundle() -> SectorDataBundle:
    return SectorDataBundle(
        sections={"company_news": "some live data"},
        has_real_data=True,
        api_calls_made={"serper": 3, "tavily": 1},
    )


# ---------------------------------------------------------------------------
# SECTOR_SPECS registry shape
# ---------------------------------------------------------------------------

class TestSectorSpecsRegistry:
    def test_all_four_sectors_registered(self):
        assert set(SECTOR_SPECS.keys()) == set(ALL_SECTORS)
        for sector in ALL_SECTORS:
            assert isinstance(SECTOR_SPECS[sector], SectorSpec)

    def test_dimensions_keys_match_sector_specs_keys(self):
        assert set(DIMENSIONS.keys()) == set(SECTOR_SPECS.keys())

    @pytest.mark.parametrize(
        "sector,weights",
        [
            ("automobile", AUTO_WEIGHTS),
            ("banking_bfsi", BFSI_WEIGHTS),
            ("it_sector", IT_WEIGHTS),
            ("renewable_energy", RE_WEIGHTS),
        ],
    )
    def test_dimensions_match_agent_weights_keys_and_order(self, sector, weights):
        # Set equality
        assert set(DIMENSIONS[sector]) == set(weights.keys())
        # Order-of-classes consistency: SectorSpec.classes dict order ==
        # DIMENSIONS[sector] order (DIMENSIONS is derived from classes order).
        assert DIMENSIONS[sector] == list(SECTOR_SPECS[sector].classes.keys())

    def test_valuation_extras_only_automobile(self):
        assert SECTOR_SPECS["automobile"].has_valuation_extras is True
        assert SECTOR_SPECS["banking_bfsi"].has_valuation_extras is False
        assert SECTOR_SPECS["it_sector"].has_valuation_extras is False
        assert SECTOR_SPECS["renewable_energy"].has_valuation_extras is False

    @pytest.mark.parametrize("sector", ALL_SECTORS)
    def test_prompts_module_is_importable_string(self, sector):
        spec = SECTOR_SPECS[sector]
        assert isinstance(spec.prompts_module, str)
        assert spec.prompts_module.startswith("backend.sectors.")
        assert spec.prompts_module.endswith(".prompts.unified")

    @pytest.mark.parametrize("sector", ALL_SECTORS)
    def test_all_output_classes_are_agent_output_subclasses(self, sector):
        spec = SECTOR_SPECS[sector]
        for dim, output_cls in spec.classes.items():
            assert issubclass(output_cls, AgentOutput), f"{sector}/{dim} not AgentOutput subclass"


# ---------------------------------------------------------------------------
# New sectors: output class fidelity to legacy UniversalAgent / custom agents
# ---------------------------------------------------------------------------

class TestNewSectorOutputClassParsing:
    """The unified path must produce a working AgentOutput subclass per
    dimension that can be instantiated with agent=<dimension>, ticker,
    overall_score and (if sub_scores model declared) the right sub_scores
    field names."""

    @pytest.mark.parametrize(
        "sector,dim",
        [
            ("banking_bfsi", "fundamentals"),
            ("banking_bfsi", "risk"),
            ("banking_bfsi", "macro_policy"),
            ("banking_bfsi", "institutional"),
            ("banking_bfsi", "pattern_analysis"),
            ("banking_bfsi", "universe_setup"),
            ("it_sector", "fundamentals"),
            ("it_sector", "global_macro"),
            ("it_sector", "risk_macro"),
            ("it_sector", "peer_benchmark"),
            ("it_sector", "pattern_analysis"),
            ("it_sector", "sentiment"),
            ("it_sector", "transcript_nlp"),
            ("it_sector", "insider_smart_money"),
            ("renewable_energy", "fundamentals"),
            ("renewable_energy", "business"),
            ("renewable_energy", "valuation"),
            ("renewable_energy", "sentiment_policy"),
            ("renewable_energy", "technical"),
            ("renewable_energy", "risk"),
        ],
    )
    def test_output_class_agent_default_matches_dimension(self, sector, dim):
        output_cls = SECTOR_SPECS[sector].classes[dim]
        agent_default = output_cls.model_fields["agent"].default
        assert agent_default == dim

    @pytest.mark.parametrize(
        "sector,dim",
        [
            ("banking_bfsi", "fundamentals"),
            ("it_sector", "transcript_nlp"),
            ("renewable_energy", "business"),
        ],
    )
    def test_output_class_instantiates_with_required_fields(self, sector, dim):
        output_cls = SECTOR_SPECS[sector].classes[dim]
        out = output_cls(agent=dim, ticker="TEST", overall_score=0.5)
        assert out.agent == dim
        assert out.ticker == "TEST"


# ---------------------------------------------------------------------------
# Missing prompts module -> run() returns {} (never raises)
# ---------------------------------------------------------------------------

class TestMissingPromptsModule:
    @pytest.mark.parametrize("sector", ["banking_bfsi", "it_sector", "renewable_energy"])
    def test_registered_sector_missing_prompts_module_returns_empty_dict(self, sector):
        """The 3 new prompts modules don't exist yet (later task). A sector
        registered in SECTOR_SPECS but whose prompts_module cannot be
        imported must hit the existing never-raises path: run() returns {}
        with an error log, NOT an exception."""
        analyst = UnifiedAnalyst.__new__(UnifiedAnalyst)
        analyst._client = MagicMock()

        outs = analyst.run(_make_query(), _make_bundle(), sector)

        assert outs == {}
        analyst._client.chat.completions.create.assert_not_called()

    def test_unknown_sector_still_returns_empty_dict(self):
        analyst = UnifiedAnalyst.__new__(UnifiedAnalyst)
        analyst._client = MagicMock()

        outs = analyst.run(_make_query(), _make_bundle(), "totally_unknown_sector")

        assert outs == {}
        analyst._client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Automobile path unaffected by the registry refactor
# ---------------------------------------------------------------------------

class TestAutomobileUnaffected:
    def test_automobile_dimensions_unchanged(self):
        assert DIMENSIONS["automobile"] == [
            "sales_demand",
            "raw_materials",
            "fundamentals",
            "pattern_analysis",
            "sentiment",
            "policy_regulatory",
            "competitive_intel",
            "risk_macro",
            "valuation_catalyst",
        ]

    def test_automobile_full_run_still_works(self):
        from core.schemas.pipeline import SalesDemandOutput

        analyst = UnifiedAnalyst.__new__(UnifiedAnalyst)

        payload = {}
        for dim in DIMENSIONS["automobile"]:
            payload[dim] = {
                "score": 0.7,
                "confidence": 0.8,
                "summary": "ok",
                "key_positives": [],
                "key_risks": [],
            }

        mock_client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = json.dumps(payload)
        response.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
        mock_client.chat.completions.create.return_value = response
        analyst._client = mock_client

        outs = analyst.run(_make_query("MARUTI"), _make_bundle(), "automobile")

        assert set(outs.keys()) == set(DIMENSIONS["automobile"])
        assert isinstance(outs["sales_demand"], SalesDemandOutput)
        assert outs["sales_demand"].overall_score == pytest.approx(0.7)
