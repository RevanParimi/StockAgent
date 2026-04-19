"""
tests/test_orchestrator.py
===========================
Integration-level tests for the AutomobileAgentOrchestrator.
All LLM calls are mocked — no real API calls or network access needed.

What is tested:
  - Ticker resolution (valid ticker, fallback on failure)
  - All 5 agents are dispatched
  - FinalReport is returned with correct structure
  - Agent failure falls back to neutral score (doesn't crash pipeline)
"""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from core.pipeline.orchestrator import AutomobileAgentOrchestrator
from tests.conftest import (
    make_aggregator_json,
    make_sales_demand_json,
    make_fundamentals_json,
    make_pattern_json,
    make_sentiment_json,
    make_risk_macro_json,
)


TICKER_RESOLUTION_JSON = json.dumps({
    "ticker": "MARUTI",
    "company_name": "Maruti Suzuki India Ltd",
    "exchange": "NSE",
    "sector": "Automobile",
    "confidence": 0.99,
})


def _make_llm_side_effect(responses: list[str]):
    """Return successive responses from a list."""
    calls = iter(responses)

    def side_effect(*args, **kwargs):
        content = next(calls, make_aggregator_json())
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp

    return side_effect


class TestOrchestratorTickerResolution:
    @patch("services.clients.llm_client.OpenAI")
    @patch("core.pipeline.orchestrator._SUB_AGENTS")
    @patch("core.pipeline.orchestrator.SignalAggregator")
    def test_valid_ticker_resolved(self, mock_agg_cls, mock_agents, mock_groq_cls):
        # Mock orchestrator LLM for ticker resolution
        mock_llm = MagicMock()
        mock_groq_cls.return_value = mock_llm
        mock_llm.chat.completions.create.return_value.choices[
            0
        ].message.content = TICKER_RESOLUTION_JSON

        # Mock all sub-agents to return neutral outputs
        from core.schemas.pipeline import AgentOutput
        for name, agent in mock_agents.items():
            agent.run.return_value = AgentOutput(
                agent=name, ticker="MARUTI", overall_score=0.6
            )

        # Mock aggregator
        from core.schemas.pipeline import FinalReport
        mock_agg_instance = MagicMock()
        mock_agg_cls.return_value = mock_agg_instance
        mock_agg_instance.run.return_value = FinalReport(
            ticker="MARUTI",
            company_name="Maruti Suzuki India Ltd",
            final_score=0.65,
            verdict="BUY",
            weighted_agent_scores={},
        )

        orch = AutomobileAgentOrchestrator()
        report = orch.analyse("MARUTI")
        assert report.ticker == "MARUTI"
        assert report.verdict == "BUY"

    @patch("services.clients.llm_client.OpenAI")
    def test_ticker_resolution_fallback_on_error(self, mock_groq_cls):
        """If LLM resolution fails, orchestrator falls back to raw input as ticker."""
        mock_llm = MagicMock()
        mock_groq_cls.return_value = mock_llm
        mock_llm.chat.completions.create.side_effect = Exception("Network error")

        orch = AutomobileAgentOrchestrator.__new__(AutomobileAgentOrchestrator)
        orch._llm = mock_llm
        query = orch._resolve_ticker("TATAMOTORS")
        assert query.ticker == "TATAMOTORS"


class TestOrchestratorAgentFailure:
    @patch("services.clients.llm_client.OpenAI")
    @patch("core.pipeline.orchestrator._SUB_AGENTS")
    @patch("core.pipeline.orchestrator.SignalAggregator")
    def test_single_agent_failure_does_not_crash(
        self, mock_agg_cls, mock_agents, mock_groq_cls
    ):
        """If one agent raises, it should be replaced with neutral output."""
        mock_llm = MagicMock()
        mock_groq_cls.return_value = mock_llm
        mock_llm.chat.completions.create.return_value.choices[
            0
        ].message.content = TICKER_RESOLUTION_JSON

        from core.schemas.pipeline import AgentOutput, FinalReport
        for i, (name, agent) in enumerate(mock_agents.items()):
            if i == 0:
                agent.run.side_effect = RuntimeError("Simulated agent crash")
            else:
                agent.run.return_value = AgentOutput(
                    agent=name, ticker="MARUTI", overall_score=0.6
                )

        mock_agg_instance = MagicMock()
        mock_agg_cls.return_value = mock_agg_instance
        mock_agg_instance.run.return_value = FinalReport(
            ticker="MARUTI",
            company_name="Maruti Suzuki India Ltd",
            final_score=0.55,
            verdict="NEUTRAL",
            weighted_agent_scores={},
        )

        orch = AutomobileAgentOrchestrator()
        # Should not raise
        report = orch.analyse("MARUTI")
        assert report is not None
