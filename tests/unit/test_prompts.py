"""
tests/test_prompts.py
=====================
Tests that all prompt templates are well-formed and format without errors.

What is tested:
  - All ANALYSIS_PROMPT templates accept required format variables
  - SYSTEM_PROMPT is a non-empty string
  - CONTEXT_SEARCH_QUERIES are non-empty lists
  - Signal aggregator aggregation prompt formats correctly
  - Orchestrator ticker resolution prompt formats correctly
"""

import pytest

from backend.sectors.automobile.prompts import sales_demand
from backend.sectors.automobile.prompts import fundamentals
from backend.sectors.automobile.prompts import pattern_analysis
from backend.sectors.automobile.prompts import sentiment
from backend.sectors.automobile.prompts import risk_macro
from core.config.prompts.shared import signal_aggregator
from core.config.prompts.shared import orchestrator


SAMPLE_FORMAT_ARGS = dict(
    ticker="MARUTI",
    company_name="Maruti Suzuki India Ltd",
    context="Sample context for testing.",
    month="April",
    year="2026",
    quarter="Q4 FY26",
    date="2026-04-03",
    business_model_context="TICKER BUSINESS MODEL (MARUTI):\n  Portfolio: 80% PV\n  EV Status: Late to EV\n  Revenue Mix: Domestic 85%\n  Margin Profile: ~19% EBITDA\n  Key Watch: Rural demand\n",
)


class TestPromptFormatting:
    def test_sales_demand_analysis_prompt(self):
        result = sales_demand.ANALYSIS_PROMPT.format(**SAMPLE_FORMAT_ARGS)
        assert "MARUTI" in result
        assert "Sales & Demand" in result

    def test_fundamentals_analysis_prompt(self):
        result = fundamentals.ANALYSIS_PROMPT.format(**SAMPLE_FORMAT_ARGS)
        assert "MARUTI" in result
        assert "EBITDA" in result

    def test_pattern_analysis_prompt(self):
        result = pattern_analysis.ANALYSIS_PROMPT.format(**SAMPLE_FORMAT_ARGS)
        assert "MARUTI" in result
        assert "RSI" in result

    def test_sentiment_analysis_prompt(self):
        result = sentiment.ANALYSIS_PROMPT.format(**SAMPLE_FORMAT_ARGS)
        assert "MARUTI" in result
        assert "NLP" in result

    def test_risk_macro_analysis_prompt(self):
        result = risk_macro.ANALYSIS_PROMPT.format(**SAMPLE_FORMAT_ARGS)
        assert "MARUTI" in result
        assert "repo rate" in result.lower() or "RBI" in result


class TestSystemPrompts:
    @pytest.mark.parametrize("module", [
        sales_demand, fundamentals, pattern_analysis, sentiment,
        risk_macro, signal_aggregator, orchestrator,
    ])
    def test_system_prompt_not_empty(self, module):
        assert module.SYSTEM_PROMPT.strip() != ""

    @pytest.mark.parametrize("module", [
        sales_demand, fundamentals, pattern_analysis, sentiment,
        risk_macro, signal_aggregator, orchestrator,
    ])
    def test_system_prompt_is_string(self, module):
        assert isinstance(module.SYSTEM_PROMPT, str)


class TestSearchQueries:
    @pytest.mark.parametrize("module", [
        sales_demand, fundamentals, pattern_analysis, sentiment, risk_macro,
    ])
    def test_search_queries_non_empty_list(self, module):
        assert isinstance(module.CONTEXT_SEARCH_QUERIES, list)
        assert len(module.CONTEXT_SEARCH_QUERIES) > 0

    @pytest.mark.parametrize("module", [
        sales_demand, fundamentals, pattern_analysis, sentiment, risk_macro,
    ])
    def test_search_queries_contain_ticker_placeholder(self, module):
        has_ticker = any("{ticker}" in q or "{company_name}" in q for q in module.CONTEXT_SEARCH_QUERIES)
        assert has_ticker, f"{module.__name__} queries should reference {{ticker}} or {{company_name}}"


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
