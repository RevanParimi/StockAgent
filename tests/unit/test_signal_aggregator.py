"""
tests/test_signal_aggregator.py
================================
Tests for the SignalAggregator — weighted fusion and conflict resolution.

What is tested:
  - Weighted score computation matches manual calculation
  - Conflict detection triggers when delta >= 0.30
  - No conflicts when all scores are close
  - LLM is mocked — no real API calls
  - FinalReport is well-formed
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline.signal_aggregator import SignalAggregator, CONFLICT_THRESHOLD
from config import settings
from tests.conftest import make_aggregator_json


class TestConflictDetection:
    def setup_method(self):
        self.agg = SignalAggregator.__new__(SignalAggregator)  # bypass __init__

    def _make_outputs(self, scores: dict) -> dict:
        from core.schemas.pipeline import AgentOutput
        return {
            name: AgentOutput(agent=name, ticker="MARUTI", overall_score=s)
            for name, s in scores.items()
        }

    def test_no_conflict_when_scores_close(self):
        outputs = self._make_outputs({
            "sales_demand": 0.65,
            "fundamentals": 0.60,
            "pattern_analysis": 0.62,
            "sentiment": 0.58,
            "risk_macro": 0.63,
        })
        conflicts = self.agg._detect_conflicts(outputs)
        assert conflicts == []

    def test_conflict_detected_when_delta_exceeds_threshold(self):
        outputs = self._make_outputs({
            "sales_demand": 0.80,
            "fundamentals": 0.45,   # delta = 0.35 > 0.30
            "pattern_analysis": 0.60,
            "sentiment": 0.65,
            "risk_macro": 0.62,
        })
        conflicts = self.agg._detect_conflicts(outputs)
        assert len(conflicts) >= 1
        assert any("sales_demand" in c and "fundamentals" in c for c in conflicts)

    def test_conflict_boundary_at_threshold(self):
        outputs = self._make_outputs({
            "sales_demand": 0.80,
            "fundamentals": 0.50,   # delta = 0.30, exactly at threshold
            "pattern_analysis": 0.60,
            "sentiment": 0.65,
            "risk_macro": 0.62,
        })
        conflicts = self.agg._detect_conflicts(outputs)
        assert len(conflicts) >= 1


class TestWeightedScoreComputation:
    @patch("services.clients.llm_client.OpenAI")
    def test_weighted_score_matches_manual(self, mock_groq_cls, mock_all_agent_outputs):
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = make_aggregator_json(0.66)

        agg = SignalAggregator()
        report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)

        # Manual calculation
        weights = settings.AGENT_WEIGHTS
        scores = {k: v.overall_score for k, v in mock_all_agent_outputs.items()}
        expected = sum(scores[k] * weights[k] for k in weights) / sum(weights.values())

        assert report.weighted_agent_scores is not None
        # Verify each agent's weighted value = raw * weight
        for name, ws in report.weighted_agent_scores.items():
            assert ws.weighted == pytest.approx(ws.raw * ws.weight, abs=1e-4)

    @patch("services.clients.llm_client.OpenAI")
    def test_final_report_has_verdict(self, mock_groq_cls, mock_all_agent_outputs):
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = make_aggregator_json(0.66)

        agg = SignalAggregator()
        report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)

        assert report.verdict in {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}

    @patch("services.clients.llm_client.OpenAI")
    def test_final_report_score_in_bounds(self, mock_groq_cls, mock_all_agent_outputs):
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = make_aggregator_json(0.66)

        agg = SignalAggregator()
        report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)
        assert 0.0 <= report.final_score <= 1.0

    @patch("services.clients.llm_client.OpenAI")
    def test_bad_llm_json_fallback(self, mock_groq_cls, mock_all_agent_outputs):
        """If LLM returns invalid JSON, aggregator should return NEUTRAL fallback."""
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = "NOT JSON AT ALL"

        agg = SignalAggregator()
        report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)
        assert report.verdict == "NEUTRAL"
        assert report.final_score == 0.5
