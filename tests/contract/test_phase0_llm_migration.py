"""
tests/test_phase0_llm_migration.py
====================================
Phase 0 — LLM migration: Groq → OpenRouter + Qwen.

Verifies that:
  - No `groq` SDK imports remain in any agent file
  - All agents use the OpenAI-compatible client pointed at OpenRouter
  - settings.py exposes OPENROUTER_API_KEY and OPENROUTER_BASE_URL
  - The model is a Qwen variant (accuracy-first selection)
  - BaseAgent, orchestrator, signal_aggregator, feedback_agent all
    instantiate OpenAI (not Groq) clients
  - No GROQ_API_KEY references remain in settings

These tests run without making any real LLM calls.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(__file__).parent.parent.parent / "core" / "pipeline"
AGENT_FILES = [p for p in AGENTS_DIR.glob("*.py") if not p.name.startswith("__")]


# ---------------------------------------------------------------------------
# 1. No groq imports anywhere in the agents package
# ---------------------------------------------------------------------------

class TestNoGroqImports:
    @pytest.mark.parametrize("agent_file", AGENT_FILES, ids=lambda p: p.name)
    def test_no_groq_import_in_agent_files(self, agent_file: Path):
        source = agent_file.read_text(encoding="utf-8")
        assert "from groq" not in source, (
            f"{agent_file.name} still has 'from groq' import — must use openai SDK"
        )
        assert "import groq" not in source, (
            f"{agent_file.name} still has 'import groq' — must use openai SDK"
        )

    def test_no_groq_in_settings(self):
        settings_path = Path(__file__).parent.parent.parent / "config" / "settings" / "base.py"
        source = settings_path.read_text(encoding="utf-8")
        assert "GROQ_API_KEY" not in source, "settings.py still references GROQ_API_KEY"
        assert "groq.com" not in source, "settings.py still references Groq base URL"


# ---------------------------------------------------------------------------
# 2. settings.py exposes correct OpenRouter config
# ---------------------------------------------------------------------------

class TestOpenRouterSettings:
    def test_openrouter_api_key_exists(self):
        from config import settings
        assert hasattr(settings, "OPENROUTER_API_KEY"), "OPENROUTER_API_KEY missing from settings"

    def test_openrouter_base_url_exists(self):
        from config import settings
        assert hasattr(settings, "OPENROUTER_BASE_URL"), "OPENROUTER_BASE_URL missing from settings"

    def test_openrouter_base_url_value(self):
        from config import settings
        assert "openrouter.ai" in settings.OPENROUTER_BASE_URL, (
            f"Expected openrouter.ai in base URL, got: {settings.OPENROUTER_BASE_URL}"
        )

    def test_model_is_qwen(self):
        from config import settings
        assert "qwen" in settings.LLM_MODEL.lower(), (
            f"Expected Qwen model, got: {settings.LLM_MODEL}. "
            "Set LLM_MODEL=qwen/qwen3-235b-a22b in .env"
        )

    def test_no_groq_api_key_attribute(self):
        from config import settings
        assert not hasattr(settings, "GROQ_API_KEY"), (
            "settings still has GROQ_API_KEY — remove it to avoid confusion"
        )


# ---------------------------------------------------------------------------
# 3. BaseAgent uses OpenAI client with OpenRouter base_url
# ---------------------------------------------------------------------------

class TestBaseAgentUsesOpenAI:
    @patch("services.clients.llm_client.OpenAI")
    def test_base_agent_instantiates_openai(self, mock_openai_cls):
        mock_openai_cls.return_value = MagicMock()
        from core.sectors.automobile.sales_demand import SalesDemandAgent
        # Re-import to trigger __init__
        agent = SalesDemandAgent.__new__(SalesDemandAgent)
        agent.__init__()
        mock_openai_cls.assert_called_once()

    @patch("services.clients.llm_client.OpenAI")
    def test_base_agent_passes_openrouter_base_url(self, mock_openai_cls):
        from config import settings
        mock_openai_cls.return_value = MagicMock()
        from core.sectors.automobile.sales_demand import SalesDemandAgent
        SalesDemandAgent()
        _, kwargs = mock_openai_cls.call_args
        assert kwargs.get("base_url") == settings.OPENROUTER_BASE_URL, (
            f"Expected OpenRouter base_url, got: {kwargs.get('base_url')}"
        )

    @patch("services.clients.llm_client.OpenAI")
    def test_base_agent_passes_openrouter_api_key(self, mock_openai_cls):
        from config import settings
        mock_openai_cls.return_value = MagicMock()
        from core.sectors.automobile.sales_demand import SalesDemandAgent
        SalesDemandAgent()
        _, kwargs = mock_openai_cls.call_args
        assert kwargs.get("api_key") == settings.OPENROUTER_API_KEY


# ---------------------------------------------------------------------------
# 4. Orchestrator uses OpenAI client
# ---------------------------------------------------------------------------

class TestOrchestratorUsesOpenAI:
    @patch("services.clients.llm_client.OpenAI")
    @patch("core.pipeline.orchestrator._SUB_AGENTS", {})
    @patch("core.pipeline.orchestrator.SignalAggregator")
    def test_orchestrator_instantiates_openai(self, mock_agg, mock_openai_cls):
        mock_openai_cls.return_value = MagicMock()
        mock_agg.return_value = MagicMock()
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        AutomobileAgentOrchestrator()
        mock_openai_cls.assert_called_once()

    @patch("services.clients.llm_client.OpenAI")
    @patch("core.pipeline.orchestrator._SUB_AGENTS", {})
    @patch("core.pipeline.orchestrator.SignalAggregator")
    def test_orchestrator_uses_openrouter_url(self, mock_agg, mock_openai_cls):
        from config import settings
        mock_openai_cls.return_value = MagicMock()
        mock_agg.return_value = MagicMock()
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        AutomobileAgentOrchestrator()
        _, kwargs = mock_openai_cls.call_args
        assert kwargs.get("base_url") == settings.OPENROUTER_BASE_URL


# ---------------------------------------------------------------------------
# 5. SignalAggregator uses OpenAI client
# ---------------------------------------------------------------------------

class TestSignalAggregatorUsesOpenAI:
    @patch("services.clients.llm_client.OpenAI")
    def test_signal_aggregator_instantiates_openai(self, mock_openai_cls):
        mock_openai_cls.return_value = MagicMock()
        from core.pipeline.signal_aggregator import SignalAggregator
        SignalAggregator()
        mock_openai_cls.assert_called_once()

    @patch("services.clients.llm_client.OpenAI")
    def test_signal_aggregator_uses_openrouter_url(self, mock_openai_cls):
        from config import settings
        mock_openai_cls.return_value = MagicMock()
        from core.pipeline.signal_aggregator import SignalAggregator
        SignalAggregator()
        _, kwargs = mock_openai_cls.call_args
        assert kwargs.get("base_url") == settings.OPENROUTER_BASE_URL


# ---------------------------------------------------------------------------
# 6. FeedbackAgent uses OpenAI client
# ---------------------------------------------------------------------------

class TestFeedbackAgentUsesOpenAI:
    @patch("intelligence.rl.agents.feedback_agent.OpenAI")
    def test_feedback_agent_instantiates_openai(self, mock_openai_cls):
        mock_openai_cls.return_value = MagicMock()
        from intelligence.rl.agents.feedback_agent import FeedbackAgent
        FeedbackAgent()
        mock_openai_cls.assert_called_once()


# ---------------------------------------------------------------------------
# 7. progress_callback wiring in orchestrator
# ---------------------------------------------------------------------------

class TestProgressCallback:
    def test_analyse_accepts_progress_callback_param(self):
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        sig = inspect.signature(AutomobileAgentOrchestrator.analyse)
        assert "progress_callback" in sig.parameters, (
            "analyse() must accept progress_callback for WebSocket streaming"
        )

    def test_progress_callback_default_is_none(self):
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        sig = inspect.signature(AutomobileAgentOrchestrator.analyse)
        default = sig.parameters["progress_callback"].default
        assert default is None

    @patch("services.clients.llm_client.OpenAI")
    @patch("core.pipeline.orchestrator.SignalAggregator")
    @patch("core.pipeline.orchestrator._SUB_AGENTS")
    def test_progress_callback_called_per_agent(self, mock_agents, mock_agg_cls, mock_openai_cls):
        """Callback must fire once per agent that completes."""
        from core.pipeline.orchestrator import AutomobileAgentOrchestrator
        from core.schemas.pipeline import AgentOutput, FinalReport, WeightedAgentScore

        # Setup mock LLM for ticker resolution
        mock_llm = MagicMock()
        mock_llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"ticker":"MARUTI","company_name":"Maruti Suzuki","exchange":"NSE","confidence":0.99}'))]
        )
        mock_openai_cls.return_value = mock_llm

        # Two mock agents
        agent_a = MagicMock()
        agent_a.run.return_value = AgentOutput(agent="a", ticker="MARUTI", overall_score=0.7)
        agent_b = MagicMock()
        agent_b.run.return_value = AgentOutput(agent="b", ticker="MARUTI", overall_score=0.6)
        mock_agents.__iter__ = MagicMock(return_value=iter({"a": agent_a, "b": agent_b}.items()))
        mock_agents.items.return_value = {"a": agent_a, "b": agent_b}.items()
        mock_agents.__len__ = MagicMock(return_value=2)

        ws = WeightedAgentScore(raw=0.65, weight=1.0, weighted=0.65)
        mock_agg = MagicMock()
        mock_agg.run.return_value = FinalReport(
            ticker="MARUTI", company_name="Maruti Suzuki",
            final_score=0.65, verdict="BUY",
            weighted_agent_scores={"a": ws},
        )
        mock_agg_cls.return_value = mock_agg

        fired: list[tuple[str, float]] = []
        orch = AutomobileAgentOrchestrator()
        orch.analyse("MARUTI", progress_callback=lambda name, score: fired.append((name, score)))

        assert len(fired) == 2
        assert all(isinstance(score, float) for _, score in fired)
