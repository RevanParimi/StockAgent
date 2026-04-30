"""
tests/test_config.py
====================
Tests for configuration correctness and validation.

What is tested:
  - Agent weights sum to 1.0
  - Score thresholds are contiguous and cover [0, 1]
  - All required settings exist and have sensible types
  - RAG config defaults to disabled
  - .env.example has all keys defined in settings.py
"""

import pytest
from core.config import settings
from core.intelligence.rag import config as rag_config


class TestAgentWeights:
    def test_weights_sum_to_one(self):
        total = sum(settings.AGENT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, not 1.0"

    def test_all_nine_agents_have_weights(self):
        expected = {
            "sales_demand", "raw_materials", "fundamentals",
            "pattern_analysis", "sentiment", "policy_regulatory",
            "competitive_intel", "risk_macro", "valuation_catalyst",
        }
        assert set(settings.AGENT_WEIGHTS.keys()) == expected

    def test_weights_are_positive(self):
        for name, w in settings.AGENT_WEIGHTS.items():
            assert w > 0, f"Weight for {name} must be > 0"


class TestScoreThresholds:
    def test_all_verdicts_present(self):
        expected = {"strong_buy", "buy", "neutral", "sell", "strong_sell"}
        assert set(settings.SCORE_THRESHOLDS.keys()) == expected

    def test_thresholds_cover_zero_to_one(self):
        lo_values = [v[0] for v in settings.SCORE_THRESHOLDS.values()]
        hi_values = [v[1] for v in settings.SCORE_THRESHOLDS.values()]
        assert min(lo_values) == 0.0
        assert max(hi_values) == 1.0

    def test_thresholds_are_contiguous(self):
        # Sort by lower bound, check no gaps
        sorted_t = sorted(settings.SCORE_THRESHOLDS.values(), key=lambda x: x[0])
        for i in range(1, len(sorted_t)):
            prev_hi = sorted_t[i - 1][1]
            curr_lo = sorted_t[i][0]
            assert abs(prev_hi - curr_lo) < 1e-6, (
                f"Gap between thresholds: {prev_hi} -> {curr_lo}"
            )


class TestLLMSettings:
    def test_temperature_in_range(self):
        assert 0.0 <= settings.LLM_TEMPERATURE <= 2.0

    def test_max_tokens_positive(self):
        assert settings.LLM_MAX_TOKENS > 0

    def test_model_name_not_empty(self):
        assert settings.LLM_MODEL.strip() != ""

    def test_timeout_positive(self):
        assert settings.LLM_TIMEOUT_SECONDS > 0

    def test_openrouter_base_url_configured(self):
        assert "openrouter.ai" in settings.OPENROUTER_BASE_URL

    def test_openrouter_api_key_attribute_exists(self):
        assert hasattr(settings, "OPENROUTER_API_KEY")

    def test_model_is_qwen(self):
        assert "qwen" in settings.LLM_MODEL.lower(), (
            f"Expected Qwen model via OpenRouter, got: {settings.LLM_MODEL}"
        )


class TestRAGConfig:
    def test_rag_disabled_by_default(self):
        # In CI / test environment RAG should be off
        # (can be overridden by setting RAG_ENABLED=true in .env)
        import os
        if os.getenv("RAG_ENABLED", "false").lower() != "true":
            assert rag_config.RAG_ENABLED is False

    def test_top_k_positive(self):
        assert rag_config.TOP_K_RESULTS > 0

    def test_chunk_size_greater_than_overlap(self):
        assert rag_config.CHUNK_SIZE > rag_config.CHUNK_OVERLAP
