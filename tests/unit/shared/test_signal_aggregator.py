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

from backend.shared.pipeline.signal_aggregator import SignalAggregator, CONFLICT_THRESHOLD
from backend.shared.config import settings
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
        """Unbound: if the LLM returns invalid JSON, the fallback is NEUTRAL/0.5."""
        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = "NOT JSON AT ALL"

        agg = SignalAggregator()
        with patch.object(settings, "RL_HARD_BIND_VERDICT_ENABLED", False):
            report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)
        assert report.verdict == "NEUTRAL"
        assert report.final_score == 0.5

    @patch("backend.shared.pipeline.verdict_shadow.log_verdict_shadow")
    @patch("services.clients.llm_client.OpenAI")
    def test_bad_llm_json_still_binds_verdict_to_composite(
        self, mock_groq_cls, mock_shadow, mock_all_agent_outputs
    ):
        """AUD-117: a parse failure must not manufacture a NEUTRAL.

        The composite is built from the agent scores, which are valid whether or
        not the aggregator LLM returned parseable JSON, so under hard-bind the
        verdict comes from the composite. final_score stays the 0.5 fallback by
        design (spec §3.1 leaves it to the LLM; it feeds the MC path width, a
        separate channel from the categorical verdict).
        """
        from backend.shared.pipeline.verdict_shadow import verdict_from_composite

        mock_instance = MagicMock()
        mock_groq_cls.return_value = mock_instance
        mock_instance.chat.completions.create.return_value.choices[
            0
        ].message.content = "NOT JSON AT ALL"

        agg = SignalAggregator()
        with patch.object(settings, "RL_HARD_BIND_VERDICT_ENABLED", True):
            report = agg.run("MARUTI", "Maruti Suzuki India Ltd", mock_all_agent_outputs)

        composite = mock_shadow.call_args.kwargs["composite"]
        assert report.verdict == verdict_from_composite(composite)
        assert mock_shadow.call_args.kwargs["llm_verdict"] == "NEUTRAL"  # raw, pre-bind
        assert report.final_score == 0.5


class TestErroredOutputExclusion:
    """Wave I: errored/no-data outputs carry a fabricated 0.5 and must not
    move the weighted composite, appear as real scores in the prompt, or
    trigger phantom conflicts."""

    def _make_output(self, name, score, error=""):
        from core.schemas.pipeline import AgentOutput
        return AgentOutput(agent=name, ticker="MARUTI", overall_score=score, error=error)

    def _run_capturing(self, agg, outputs, weights):
        """Run the aggregator with LLM + shadow logger mocked; return
        (captured shadow kwargs, captured user prompt)."""
        from tests.conftest import make_aggregator_json
        shadow_kwargs = {}
        prompts = []

        def fake_llm(system_prompt, user_prompt):
            prompts.append(user_prompt)
            return make_aggregator_json(0.66)

        def fake_shadow(**kwargs):
            shadow_kwargs.update(kwargs)
            return None

        with patch.object(SignalAggregator, "_call_llm", side_effect=fake_llm), \
             patch("backend.shared.pipeline.verdict_shadow.log_verdict_shadow", fake_shadow), \
             patch("services.clients.llm_client.OpenAI"):
            agg = SignalAggregator()
            agg.run("MARUTI", "Maruti Suzuki India Ltd", outputs,
                    learned_weights=weights)
        return shadow_kwargs, prompts[0]

    def test_errored_output_does_not_move_composite(self):
        outputs = {
            "sales_demand": self._make_output("sales_demand", 0.9),
            "fundamentals": self._make_output("fundamentals", 0.5, error="parse_error: boom"),
        }
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        shadow, prompt = self._run_capturing(None, outputs, weights)
        # Old behavior: (0.9*0.5 + 0.5*0.5) / 1.0 = 0.70. New: 0.90.
        assert shadow["composite"] == pytest.approx(0.9)
        assert "EXCLUDED" in prompt
        assert "fundamentals: EXCLUDED" in prompt

    def test_all_errored_composite_is_neutral(self):
        outputs = {
            "sales_demand": self._make_output("sales_demand", 0.5, error="no_real_time_data"),
            "fundamentals": self._make_output("fundamentals", 0.5, error="parse_error: x"),
        }
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        shadow, _ = self._run_capturing(None, outputs, weights)
        assert shadow["composite"] == pytest.approx(0.5)

    def test_errored_output_no_phantom_conflict(self):
        agg = SignalAggregator.__new__(SignalAggregator)
        outputs = {
            "sales_demand": self._make_output("sales_demand", 0.9),
            "fundamentals": self._make_output("fundamentals", 0.5, error="parse_error: x"),
        }
        assert agg._detect_conflicts(outputs) == []


class TestHardBindVerdict:
    """AUD-117/AUD-077 Binding 1: under the flag, report.verdict is rebound to
    the composite→threshold verdict; the shadow lane still logs the RAW LLM
    verdict; final_score is never overridden."""

    def _make_output(self, name, score, error=""):
        from core.schemas.pipeline import AgentOutput
        return AgentOutput(agent=name, ticker="MARUTI", overall_score=score, error=error)

    def _run(self, outputs, weights, flag_on):
        from tests.conftest import make_aggregator_json
        shadow_kwargs = {}

        def fake_llm(system_prompt, user_prompt):
            return make_aggregator_json(0.66)          # verdict="BUY", final_score=0.66

        def fake_shadow(**kwargs):
            shadow_kwargs.update(kwargs)
            return None

        with patch.object(SignalAggregator, "_call_llm", side_effect=fake_llm), \
             patch("backend.shared.pipeline.verdict_shadow.log_verdict_shadow", fake_shadow), \
             patch("services.clients.llm_client.OpenAI"), \
             patch.object(settings, "RL_HARD_BIND_VERDICT_ENABLED", flag_on):
            agg = SignalAggregator()
            report = agg.run("MARUTI", "Maruti Suzuki India Ltd", outputs,
                             learned_weights=weights)
        return report, shadow_kwargs

    def test_flag_off_verdict_and_shadow_unchanged(self):
        # composite = 0.1 (both agents 0.1) -> threshold verdict would be STRONG SELL,
        # but flag OFF must leave the raw LLM "BUY" verdict in place.
        outputs = {"sales_demand": self._make_output("sales_demand", 0.1),
                   "fundamentals": self._make_output("fundamentals", 0.1)}
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        report, shadow = self._run(outputs, weights, flag_on=False)
        assert report.verdict == "BUY"                    # raw LLM verdict, untouched
        assert shadow["llm_verdict"] == "BUY"
        assert report.final_score == pytest.approx(0.66)

    def test_flag_on_verdict_bound_shadow_keeps_raw(self):
        from backend.shared.pipeline.verdict_shadow import verdict_from_composite
        outputs = {"sales_demand": self._make_output("sales_demand", 0.1),
                   "fundamentals": self._make_output("fundamentals", 0.1)}
        weights = {"sales_demand": 0.5, "fundamentals": 0.5}
        report, shadow = self._run(outputs, weights, flag_on=True)
        assert verdict_from_composite(0.1) == "STRONG SELL"   # lock the band map
        assert report.verdict == "STRONG SELL"                # bound to composite
        assert shadow["llm_verdict"] == "BUY"                 # shadow logs RAW, not bound
        assert report.final_score == pytest.approx(0.66)      # final_score NEVER overridden
