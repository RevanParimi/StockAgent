"""
tests/test_orchestrator.py
===========================
Integration-level tests for the AutomobileAgentOrchestrator.
All LLM calls are mocked — no real API calls or network access needed.

What is tested:
  - Ticker resolution falls back to raw input when LLM resolution fails
  - Sync analyse() wiring returns the aggregator's FinalReport
"""

from unittest.mock import MagicMock, patch

from core.pipeline.orchestrator import AutomobileAgentOrchestrator


class TestOrchestratorTickerResolution:
    @patch("backend.shared.pipeline.base_orchestrator.get_llm_client")
    @patch("backend.shared.pipeline.base_orchestrator.SignalAggregator")
    def test_valid_ticker_resolved(self, mock_agg_cls, mock_llm_factory):
        """Sync analyse() end-to-end wiring: resolve → weights → agents →
        aggregate → report. All network/LLM seams on BaseSectorOrchestrator
        are stubbed so only the wiring is exercised."""
        mock_llm_factory.return_value = MagicMock()

        # Mock aggregator — analyse() returns whatever it produces.
        from core.schemas.pipeline import FinalReport, StockQuery
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
        query = StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India Ltd")
        # One scored dimension: a run that scores nothing is "no analysis".
        from core.schemas.pipeline import AgentOutput
        scored = {"fundamentals": AgentOutput(agent="fundamentals", ticker="MARUTI",
                                              overall_score=0.65)}
        with patch.object(orch, "_resolve_ticker", return_value=query), \
             patch.object(orch, "_prefetch_nse_data"), \
             patch.object(orch, "_load_learned_weights", return_value=None), \
             patch.object(orch, "_run_agents", return_value=scored), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_summary"), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_api_usage"), \
             patch("backend.shared.pipeline.base_orchestrator.log_analysis"), \
             patch("backend.shared.pipeline.base_orchestrator.snapshot_usage", return_value={}):
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
