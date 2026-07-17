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


def test_sum_run_usage_splits_rates_by_model():
    """base_orchestrator.sum_run_usage: resolve tokens=BULK rate, aggregator=REASONING rate."""
    from backend.shared.pipeline.base_orchestrator import sum_run_usage

    class _Agg:
        _last_prompt_tokens = 1_000_000
        _last_completion_tokens = 0

    pt, ct, cost = sum_run_usage({}, (1_000_000, 0), _Agg())
    bulk_in = settings.LLM_COST_RATES[settings.LLM_MODEL_BULK][0]
    reason_in = settings.LLM_COST_RATES[settings.LLM_MODEL_REASONING][0]
    assert pt == 2_000_000 and ct == 0
    assert cost == round(bulk_in + reason_in, 6)  # 1M resolve @ bulk + 1M agg @ reasoning
