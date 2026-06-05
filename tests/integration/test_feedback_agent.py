"""
tests/integration/test_feedback_agent.py
=========================================
Integration tests for FeedbackAgent error-handling.
Tests that LLM failures degrade gracefully rather than bubbling up.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from core.intelligence.rl.agents.feedback_agent import FeedbackAgent
from core.schemas.feedback import FeedbackAgentInput, LearningLedger


def _make_fb_input():
    return FeedbackAgentInput(
        ticker="MARUTI",
        sector="automobile",
        date="2026-05-20",
        predicted_close=12000.0,
        actual_close=11800.0,
        price_error_pct=-1.67,
        direction_correct=False,
        predicted_agent_scores={"fundamentals": 0.6},
        todays_agent_scores={"fundamentals": 0.55},
        market_context_today="Market context unavailable.",
        key_assumptions_made=["Stable crude"],
        active_lessons_summary="No active lessons.",
    )


def test_feedback_agent_run_survives_llm_failure():
    """run() must not raise when LLM is down — must return a valid FeedbackAgentOutput."""
    agent = FeedbackAgent.__new__(FeedbackAgent)
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = RuntimeError("LLM down")

    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-05-20")
    result = agent.run(_make_fb_input(), ledger)

    assert result is not None
    assert hasattr(result, "miss_type")
    # Must not raise — degraded output is acceptable


def test_feedback_agent_run_logs_error_on_llm_failure(caplog):
    """An ERROR log must be emitted when the LLM call fails."""
    agent = FeedbackAgent.__new__(FeedbackAgent)
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = RuntimeError("LLM down")

    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-05-20")
    with caplog.at_level(logging.ERROR, logger="core.intelligence.rl.agents.feedback_agent"):
        agent.run(_make_fb_input(), ledger)

    assert any("LLM" in r.message or "llm" in r.message.lower() for r in caplog.records)


def test_feedback_agent_run_degraded_output_has_miss_type():
    """Degraded output from LLM failure must have a valid miss_type field."""
    agent = FeedbackAgent.__new__(FeedbackAgent)
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = Exception("Connection refused")

    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-05-20")
    result = agent.run(_make_fb_input(), ledger)

    assert result.miss_type is not None
    assert isinstance(result.miss_type, str)


def test_feedback_agent_run_degraded_output_has_revised_context():
    """Degraded output must contain a RevisedContext object (not None)."""
    agent = FeedbackAgent.__new__(FeedbackAgent)
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = RuntimeError("timeout")

    ledger = LearningLedger(ticker="MARUTI", last_updated="2026-05-20")
    result = agent.run(_make_fb_input(), ledger)

    assert result.revised_context is not None
    assert hasattr(result.revised_context, "headline")
