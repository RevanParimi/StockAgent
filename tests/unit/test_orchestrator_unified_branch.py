"""
tests/unit/test_orchestrator_unified_branch.py
===============================================
The orchestrator's one analysis method (CLEAN-005).

Every path runs one data bundle and one analysis call (`_run_unified`).
There is no per-sector switch back to the per-analyst worker pool and no
backup when the call fails: an empty result stays empty here, and
`analyse` / `analyse_async` turn it into "no analysis"
(tests/unit/test_no_analysis_clean005.py).

No network: _resolve_ticker, _prefetch_nse_data, _aggregator.run,
build_sector_bundle and UnifiedAnalyst.run are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.shared.pipeline import base_orchestrator as bo_mod
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.pipeline.no_analysis import AnalysisUnavailable
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.schemas.pipeline import AgentOutput, StockQuery


class _AutomobileTestOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "automobile"


@pytest.fixture
def orchestrator() -> _AutomobileTestOrchestrator:
    # get_llm_client() just builds an OpenAI() client object - no network -
    # but stub it out anyway to avoid requiring API keys in the test env.
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
        orch = _AutomobileTestOrchestrator()
    orch._aggregator = MagicMock()
    return orch


def _make_query() -> StockQuery:
    return StockQuery(ticker="MARUTI", company_name="Maruti Suzuki India Ltd")


def _make_unified_outputs() -> dict[str, AgentOutput]:
    return {
        dim: AgentOutput(agent=dim, ticker="MARUTI", overall_score=0.65)
        for dim in DIMENSIONS["automobile"]
    }


def test_the_worker_pool_and_its_switches_are_gone():
    for name in ("_run_via_graph", "_run_via_graph_async", "_unified_enabled",
                 "_worker_pool_graph"):
        assert not hasattr(BaseSectorOrchestrator, name)
    for name in ("UNIFIED_ANALYST_SECTORS", "UNIFIED_ANALYST_FALLBACK_LEGACY"):
        assert not hasattr(bo_mod.settings, name)


def test_a_path_needs_no_analyst_team():
    """A subclass sets only its name; nothing else is required to build it."""
    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client", return_value=MagicMock()):
        orch = _AutomobileTestOrchestrator()
    assert orch.SECTOR_NAME == "automobile"
    assert not hasattr(orch, "_sub_agents")


class TestRunAgents:
    def test_runs_the_one_call_and_fires_progress(self, orchestrator):
        unified_outputs = _make_unified_outputs()
        progress_calls: list[tuple[str, float]] = []

        mock_analyst_instance = MagicMock()
        mock_analyst_instance.run.return_value = unified_outputs

        with patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst",
                   return_value=mock_analyst_instance) as mock_analyst_cls, \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle:
            mock_bundle.return_value = MagicMock(api_calls_made={"serper": 3}, has_real_data=True)
            result = orchestrator._run_agents(
                _make_query(), run_id="r1",
                progress_callback=lambda n, s: progress_calls.append((n, s)))

        mock_analyst_cls.assert_called_once()
        mock_analyst_instance.run.assert_called_once()
        assert result == unified_outputs
        assert len(progress_calls) == 9
        assert {name for name, _ in progress_calls} == set(DIMENSIONS["automobile"])

    def test_an_empty_result_stays_empty_and_keeps_the_analysts_reason(self, orchestrator):
        mock_analyst_instance = MagicMock()
        mock_analyst_instance.run.return_value = {}
        mock_analyst_instance._last_failure = "the model call timed out on all 3 attempts"

        with patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst",
                   return_value=mock_analyst_instance), \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle:
            mock_bundle.return_value = MagicMock(api_calls_made={}, has_real_data=False)
            result = orchestrator._run_agents(_make_query(), run_id="r1", progress_callback=None)

        assert result == {}
        assert orchestrator._last_analyst_failure == "the model call timed out on all 3 attempts"


class TestAnalyseAsync:
    @pytest.mark.asyncio
    async def test_the_async_entry_runs_the_same_one_call(self, orchestrator):
        query = _make_query()
        fake_report = MagicMock(verdict="BUY", final_score=0.6)
        orchestrator._aggregator.run.return_value = fake_report

        with patch.object(orchestrator, "_resolve_ticker", return_value=query), \
             patch.object(orchestrator, "_prefetch_nse_data"), \
             patch.object(orchestrator, "_load_learned_weights", return_value=None), \
             patch.object(orchestrator, "_run_unified",
                          return_value=_make_unified_outputs()) as mock_unified, \
             patch.object(orchestrator, "_apply_decision_gate"), \
             patch.object(orchestrator, "_record_score_history"), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_summary"), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_api_usage"), \
             patch("backend.shared.pipeline.base_orchestrator.log_analysis"), \
             patch("backend.shared.pipeline.base_orchestrator.snapshot_usage", return_value={}):
            report = await orchestrator.analyse_async("maruti")

        mock_unified.assert_called_once()
        assert report is fake_report

    @pytest.mark.asyncio
    async def test_an_empty_result_is_no_analysis_not_a_backup(self, orchestrator):
        with patch.object(orchestrator, "_resolve_ticker", return_value=_make_query()), \
             patch.object(orchestrator, "_prefetch_nse_data"), \
             patch.object(orchestrator, "_load_learned_weights", return_value=None), \
             patch.object(orchestrator, "_run_unified", return_value={}), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_api_usage"), \
             patch("backend.shared.pipeline.base_orchestrator.snapshot_usage", return_value={}):
            with pytest.raises(AnalysisUnavailable):
                await orchestrator.analyse_async("maruti")

        orchestrator._aggregator.run.assert_not_called()
