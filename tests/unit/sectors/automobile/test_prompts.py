"""
tests/test_prompts.py
=====================
Tests that the shared prompt templates are well-formed and format without errors.

What is tested:
  - The automobile analysis prompt (one call, nine dimensions) formats
  - SYSTEM_PROMPT is a non-empty string
  - Signal aggregator aggregation prompt formats correctly
  - Orchestrator ticker resolution prompt formats correctly

(CLEAN-005 removed the per-analyst prompt files these tests also covered.)
"""

import pytest

from backend.sectors.automobile.prompts import unified
from core.config.prompts.shared import signal_aggregator
from core.config.prompts.shared import orchestrator


class TestPromptFormatting:
    def test_unified_analysis_prompt(self):
        result = unified.ANALYSIS_PROMPT.format(
            ticker="MARUTI", company_name="Maruti Suzuki India Ltd",
            report_date="2026-04-03", bundle="BUNDLE")
        assert "MARUTI" in result and "BUNDLE" in result
        for dim in ("sales_demand", "fundamentals", "pattern_analysis", "sentiment",
                    "risk_macro", "valuation_catalyst"):
            assert dim in result


class TestSystemPrompts:
    @pytest.mark.parametrize("module", [unified, signal_aggregator, orchestrator])
    def test_system_prompt_not_empty(self, module):
        assert module.SYSTEM_PROMPT.strip() != ""

    @pytest.mark.parametrize("module", [unified, signal_aggregator, orchestrator])
    def test_system_prompt_is_string(self, module):
        assert isinstance(module.SYSTEM_PROMPT, str)


class TestSignalAggregatorPrompts:
    def test_aggregation_prompt_formats(self):
        result = signal_aggregator.AGGREGATION_PROMPT.format(
            ticker="MARUTI",
            company_name="Maruti Suzuki India Ltd",
            agent_scores_block="  sales_demand: raw=0.72, weight=0.20",
            agent_narratives="[FUNDAMENTALS] score=0.72\n  Narrative: Strong margins.",
            weighted_score=0.66,
            conflict_flags="None",
            report_date="2026-04-03",
        )
        assert "MARUTI" in result
        assert "0.66" in result


class TestOrchestratorPrompts:
    def test_ticker_resolution_prompt_formats(self):
        result = orchestrator.TICKER_RESOLUTION_PROMPT.format(
            user_input="Maruti Suzuki"
        )
        assert "Maruti Suzuki" in result
        assert "MARUTI" in result  # appears in the known tickers table
