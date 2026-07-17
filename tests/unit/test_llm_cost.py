"""AUD-105: per-model cost rates — REASONING calls must not be costed at the BULK rate."""
import pytest

from backend.shared.config import settings


def test_known_model_uses_its_own_rate():
    # glm-5.2 live OpenRouter rate 1.218/3.828 per M (pulled 2026-07-17)
    cost = settings.llm_cost_usd("z-ai/glm-5.2", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.218 + 3.828)


def test_reasoning_call_no_longer_costed_at_bulk_rate():
    reasoning = settings.llm_cost_usd(settings.LLM_MODEL_REASONING, 7440, 2957)
    bulk_flat = (7440 * settings.LLM_INPUT_COST_PER_M
                 + 2957 * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
    assert reasoning > 5 * bulk_flat  # the AUD-105 ~10x undercount is gone


def test_unknown_model_falls_back_to_flat_rate():
    cost = settings.llm_cost_usd("some/unknown-model", 1000, 500)
    expected = (1000 * settings.LLM_INPUT_COST_PER_M
                + 500 * settings.LLM_OUTPUT_COST_PER_M) / 1_000_000
    assert cost == expected


def test_zero_tokens_zero_cost():
    assert settings.llm_cost_usd("z-ai/glm-5.2", 0, 0) == 0.0


def test_all_three_tier_models_have_rates():
    for m in (settings.LLM_MODEL_FAST, settings.LLM_MODEL_REASONING, settings.LLM_MODEL_BULK):
        assert m in settings.LLM_COST_RATES
