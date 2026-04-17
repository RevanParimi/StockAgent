"""
tools/llm_client.py
====================
Single factory for the OpenAI-compatible LLM client pointed at OpenRouter.

All three callers (BaseAgent, Orchestrator, SignalAggregator) use this
factory so the provider/model can be swapped in one place via config.
Token usage and cost tracking is handled by tools/run_logger.py.
"""

from __future__ import annotations

from openai import OpenAI
from config import settings


def get_llm_client() -> OpenAI:
    """Return a configured OpenAI client pointed at OpenRouter."""
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
