"""
tools/llm_client.py
====================
Single factory for the OpenAI-compatible LLM client pointed at OpenRouter.

All three callers (BaseAgent, Orchestrator, SignalAggregator) use this
factory so the provider/model can be swapped in one place via config.
Token usage and cost tracking is handled by tools/run_logger.py.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI, OpenAI
from core.config import settings

logger = logging.getLogger(__name__)
_LLM_LOG_DIR = Path("outputs/llm_log")


def get_llm_client() -> OpenAI:
    """Return a configured sync OpenAI client pointed at OpenRouter."""
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )


def get_async_llm_client() -> AsyncOpenAI:
    """Return a configured async OpenAI client pointed at OpenRouter."""
    return AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )


def record_llm_call(
    caller: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
) -> None:
    """Append one JSON line per LLM call to outputs/llm_log/{date}.jsonl. Never raises."""
    try:
        _LLM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _LLM_LOG_DIR / f"{date.today().isoformat()}.jsonl"
        entry = json.dumps({
            "ts":            datetime.now(timezone.utc).isoformat(),
            "caller":        caller,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "latency_ms":    latency_ms,
            "success":       success,
        })
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except Exception as exc:
        logger.warning("[llm_client] telemetry write failed (non-fatal): %s", exc)
