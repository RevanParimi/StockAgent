"""
tests/unit/test_orchestrator_unified_branch.py
===============================================
Tests for the unified-analyst orchestrator branch (Task 6, 2026-06-12
redesign).

BaseSectorOrchestrator._unified_enabled() / _run_unified() / _run_agents()
dispatch between the new "one bundle + one analyst call" path and the
legacy LangGraph worker-pool path (_run_via_graph / _run_via_graph_async).

No network: _resolve_ticker, _prefetch_nse_data, _aggregator.run,
build_sector_bundle, UnifiedAnalyst.run, _run_via_graph(_async) are all
mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.shared.pipeline import base_orchestrator as bo_mod
from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator
from backend.shared.pipeline.unified_analyst import DIMENSIONS
from core.schemas.pipeline import AgentOutput, StockQuery


class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - never called (graph mocked)
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


class _AutomobileTestOrchestrator(BaseSectorOrchestrator):
    SECTOR_NAME = "automobile"

    def __init__(self) -> None:
        self._sub_agents = {"dummy": _DummyAgent()}
        super().__init__()


@pytest.fixture
def orchestrator(monkeypatch) -> _AutomobileTestOrchestrator:
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


# ---------------------------------------------------------------------------
# _unified_enabled
# ---------------------------------------------------------------------------

class TestUnifiedEnabled:
    def test_flag_off_means_disabled(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "")
        assert orchestrator._unified_enabled() is False

    def test_flag_on_for_sector_means_enabled(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "automobile")
        assert orchestrator._unified_enabled() is True

    def test_flag_on_for_other_sector_means_disabled(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "banking_bfsi")
        assert orchestrator._unified_enabled() is False


# ---------------------------------------------------------------------------
# _run_agents dispatch
# ---------------------------------------------------------------------------

class TestRunAgentsDispatch:
    def test_flag_off_uses_legacy_graph_only(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "")

        legacy_outputs = {"sales_demand": AgentOutput(agent="sales_demand", ticker="MARUTI", overall_score=0.6)}
        with patch.object(orchestrator, "_run_via_graph", return_value=legacy_outputs) as mock_graph, \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst") as mock_analyst_cls:
            result = orchestrator._run_agents(_make_query(), run_id="r1", progress_callback=None)

        mock_graph.assert_called_once()
        mock_analyst_cls.assert_not_called()
        assert result == legacy_outputs

    def test_flag_on_uses_unified_path_and_fires_progress(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "automobile")

        unified_outputs = _make_unified_outputs()
        progress_calls: list[tuple[str, float]] = []

        def progress_callback(name, score):
            progress_calls.append((name, score))

        mock_analyst_instance = MagicMock()
        mock_analyst_instance.run.return_value = unified_outputs

        with patch.object(orchestrator, "_run_via_graph") as mock_graph, \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=mock_analyst_instance) as mock_analyst_cls, \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle:
            mock_bundle.return_value = MagicMock(api_calls_made={"serper": 3}, has_real_data=True)
            result = orchestrator._run_agents(_make_query(), run_id="r1", progress_callback=progress_callback)

        mock_analyst_cls.assert_called_once()
        mock_analyst_instance.run.assert_called_once()
        mock_graph.assert_not_called()
        assert result == unified_outputs
        assert len(progress_calls) == 9
        assert {name for name, _ in progress_calls} == set(DIMENSIONS["automobile"])

    def test_flag_on_empty_outputs_with_fallback_enabled_runs_legacy(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "automobile")
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_FALLBACK_LEGACY", True)

        legacy_outputs = {"sales_demand": AgentOutput(agent="sales_demand", ticker="MARUTI", overall_score=0.6)}
        mock_analyst_instance = MagicMock()
        mock_analyst_instance.run.return_value = {}

        with patch.object(orchestrator, "_run_via_graph", return_value=legacy_outputs) as mock_graph, \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=mock_analyst_instance), \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle:
            mock_bundle.return_value = MagicMock(api_calls_made={}, has_real_data=False)
            result = orchestrator._run_agents(_make_query(), run_id="r1", progress_callback=None)

        mock_graph.assert_called_once()
        assert result == legacy_outputs

    def test_flag_on_empty_outputs_with_fallback_disabled_skips_legacy(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "automobile")
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_FALLBACK_LEGACY", False)

        mock_analyst_instance = MagicMock()
        mock_analyst_instance.run.return_value = {}

        with patch.object(orchestrator, "_run_via_graph") as mock_graph, \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst", return_value=mock_analyst_instance), \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle:
            mock_bundle.return_value = MagicMock(api_calls_made={}, has_real_data=False)
            result = orchestrator._run_agents(_make_query(), run_id="r1", progress_callback=None)

        mock_graph.assert_not_called()
        assert result == {}


# ---------------------------------------------------------------------------
# analyse_async dispatch (flag off -> legacy async path, unified helpers unused)
# ---------------------------------------------------------------------------

class TestAnalyseAsyncDispatch:
    @pytest.mark.asyncio
    async def test_flag_off_uses_run_via_graph_async(self, orchestrator, monkeypatch):
        monkeypatch.setattr(bo_mod.settings, "UNIFIED_ANALYST_SECTORS", "")

        query = _make_query()
        legacy_outputs = {"sales_demand": AgentOutput(agent="sales_demand", ticker="MARUTI", overall_score=0.6)}

        async def fake_run_via_graph_async(*args, **kwargs):
            return legacy_outputs

        fake_report = MagicMock(verdict="BUY", final_score=0.6)
        orchestrator._aggregator.run.return_value = fake_report

        with patch.object(orchestrator, "_resolve_ticker", return_value=query), \
             patch.object(orchestrator, "_prefetch_nse_data"), \
             patch.object(orchestrator, "_load_learned_weights", return_value=None), \
             patch.object(orchestrator, "_run_via_graph_async", side_effect=fake_run_via_graph_async) as mock_async_graph, \
             patch.object(orchestrator, "_run_agents") as mock_run_agents, \
             patch("backend.shared.pipeline.unified_analyst.UnifiedAnalyst") as mock_analyst_cls, \
             patch("services.data.context.bundle_builder.build_sector_bundle") as mock_bundle, \
             patch("backend.shared.pipeline.base_orchestrator.log_run_summary"), \
             patch("backend.shared.pipeline.base_orchestrator.log_run_api_usage"), \
             patch("backend.shared.pipeline.base_orchestrator.log_analysis"), \
             patch("backend.shared.pipeline.base_orchestrator.snapshot_usage", return_value={}):
            report = await orchestrator.analyse_async("maruti")

        mock_async_graph.assert_called_once()
        mock_run_agents.assert_not_called()
        mock_analyst_cls.assert_not_called()
        mock_bundle.assert_not_called()
        assert report is fake_report
