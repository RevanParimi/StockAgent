"""
tests/test_base_agent.py
========================
Unit tests for BaseAgent._safe_parse — error logging quality.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


def _make_concrete_agent():
    """Return a concrete BaseAgent subclass instance without calling __init__."""
    # Late import so conftest fixtures can patch settings first
    from src.backend.shared.pipeline.base_agent import BaseAgent
    from backend.shared.schemas.pipeline import AgentOutput

    class ConcreteAgent(BaseAgent):
        @property
        def agent_name(self) -> str:
            return "test_agent"

        def _build_prompt(self, query, context):
            return ("sys", "usr")

        def _parse_output(self, data, ticker):
            mock = MagicMock(spec=AgentOutput)
            mock.overall_score = 0.5
            mock.error = None
            mock.raw_llm_response = ""
            return mock

    # Bypass __init__ to avoid LLM client construction
    agent = object.__new__(ConcreteAgent)
    # Minimal attribute state needed by _safe_parse → _error_output
    return agent


def test_safe_parse_logs_ticker_on_json_failure(caplog):
    """JSON parse failure must include the ticker symbol in the log message."""
    agent = _make_concrete_agent()

    with caplog.at_level(logging.ERROR, logger="src.backend.shared.pipeline.base_agent"):
        result = agent._safe_parse("not valid json {{{{", "TATAMOTORS")

    # The result should be an error output (overall_score == 0.5)
    assert result is not None

    # Ticker must appear in at least one log record
    assert any(
        "TATAMOTORS" in r.message for r in caplog.records
    ), (
        "Ticker 'TATAMOTORS' must appear in the JSON parse failure log. "
        f"Actual log records: {[r.message for r in caplog.records]}"
    )
