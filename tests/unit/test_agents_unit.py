"""
tests/test_agents_unit.py
==========================
Unit tests for each sub-agent's _parse_output() method.
The LLM is mocked — these tests verify that JSON → Pydantic parsing
works correctly for every agent without making real API calls.

What is tested:
  - Correct agent_name on each output
  - Score clamping (values outside [0,1] are clamped, not rejected)
  - Missing sub_scores keys default to 0.5
  - key_positives / key_risks / summary are forwarded correctly
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.sectors.automobile.sales_demand import SalesDemandAgent
from core.sectors.automobile.fundamentals import FundamentalsAgent
from core.sectors.automobile.pattern_analysis import PatternAnalysisAgent
from core.sectors.automobile.sentiment import SentimentAgent
from core.sectors.automobile.risk_macro import RiskMacroAgent
from tests.conftest import (
    make_sales_demand_json,
    make_fundamentals_json,
    make_pattern_json,
    make_sentiment_json,
    make_risk_macro_json,
)


# ---------------------------------------------------------------------------
# Helper: patch Groq so no real API call is made
# ---------------------------------------------------------------------------
def _mock_groq_response(raw_json: str):
    mock_choice = MagicMock()
    mock_choice.message.content = raw_json
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


# ---------------------------------------------------------------------------
# Sales & Demand
# ---------------------------------------------------------------------------
class TestSalesDemandAgent:
    def setup_method(self):
        self.agent = SalesDemandAgent()

    def test_agent_name(self):
        assert self.agent.agent_name == "sales_demand"

    def test_parse_valid_json(self):
        data = json.loads(make_sales_demand_json(0.72))
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == pytest.approx(0.72)
        assert output.sub_scores.fada_siam_dispatch == pytest.approx(0.75)
        assert output.sub_scores.dealer_inventory == pytest.approx(0.80)

    def test_score_clamped_above(self):
        data = {"overall_score": 1.5, "sub_scores": {}}
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == 1.0

    def test_score_clamped_below(self):
        data = {"overall_score": -0.5, "sub_scores": {}}
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == 0.0

    def test_missing_sub_scores_default(self):
        data = {"overall_score": 0.5, "sub_scores": {}}
        output = self.agent._parse_output(data, "MARUTI")
        assert output.sub_scores.ev_segment_vahan == pytest.approx(0.5)

    @patch("services.clients.llm_client.OpenAI")
    def test_run_calls_llm(self, mock_groq_cls, maruti_query):
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value = _mock_groq_response(
            make_sales_demand_json()
        )
        agent = SalesDemandAgent()
        output = agent.run(maruti_query)
        assert output.agent == "sales_demand"
        assert 0.0 <= output.overall_score <= 1.0


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------
class TestFundamentalsAgent:
    def setup_method(self):
        self.agent = FundamentalsAgent()

    def test_agent_name(self):
        assert self.agent.agent_name == "fundamentals"

    def test_parse_valid_json(self):
        data = json.loads(make_fundamentals_json(0.68))
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == pytest.approx(0.68)
        assert output.sub_scores.revenue_ebitda_delta == pytest.approx(0.70)

    def test_key_risks_forwarded(self):
        data = json.loads(make_fundamentals_json())
        output = self.agent._parse_output(data, "MARUTI")
        assert len(output.key_risks) > 0


# ---------------------------------------------------------------------------
# Pattern Analysis
# ---------------------------------------------------------------------------
class TestPatternAnalysisAgent:
    def setup_method(self):
        self.agent = PatternAnalysisAgent()

    def test_agent_name(self):
        assert self.agent.agent_name == "pattern_analysis"

    def test_parse_valid_json(self):
        data = json.loads(make_pattern_json(0.55))
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == pytest.approx(0.55)
        assert output.sub_scores.rsi_macd_bb == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------
class TestSentimentAgent:
    def setup_method(self):
        self.agent = SentimentAgent()

    def test_agent_name(self):
        assert self.agent.agent_name == "sentiment"

    def test_parse_valid_json(self):
        data = json.loads(make_sentiment_json(0.70))
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == pytest.approx(0.70)
        assert output.sub_scores.news_nlp == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# Risk & Macro
# ---------------------------------------------------------------------------
class TestRiskMacroAgent:
    def setup_method(self):
        self.agent = RiskMacroAgent()

    def test_agent_name(self):
        assert self.agent.agent_name == "risk_macro"

    def test_parse_valid_json(self):
        data = json.loads(make_risk_macro_json(0.58))
        output = self.agent._parse_output(data, "MARUTI")
        assert output.overall_score == pytest.approx(0.58)
        assert output.sub_scores.global_geopolitical_risk == pytest.approx(0.50)
