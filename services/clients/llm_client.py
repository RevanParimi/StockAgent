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


# OpenRouter extra_body for JSON-mode calls: disable upstream "thinking".
# 2026-07: OpenRouter silently rolled qwen3.7-max / qwen3.6-flash to snapshots
# that emit reasoning blocks by default. Reasoning burns the completion budget
# unpredictably, so json_object responses get truncated mid-string (the
# "Expecting value" / "Unterminated string" parse failures seen in prod).
# Structured-output calls gain nothing from emitted reasoning — disable it so
# output size is deterministic. Pass as `extra_body=JSON_MODE_EXTRA_BODY` on
# every chat.completions.create() that sets response_format=json_object.
JSON_MODE_EXTRA_BODY: dict = {"reasoning": {"enabled": False}}


def salvage_truncated_json(raw: str) -> dict:
    """
    Best-effort recovery of a partial top-level JSON object from `raw` when
    `json.loads(raw)` fails (e.g. the response was cut off mid-stream by a
    max_tokens cap).

    Strategy: walk the string tracking string/escape state and brace depth.
    Each time depth returns to 1 immediately after a `}` (i.e. a top-level
    key's object value has just fully closed), record that index as a
    candidate salvage point. Take the LAST such point, truncate the string
    there, close the top-level object. Returns {} if nothing salvageable
    (including on any error, or if `raw` doesn't even open a top-level `{`).

    Safe to call on valid, complete JSON too — callers only invoke this after
    `json.loads(raw)` has already failed.
    """
    if not raw:
        return {}

    depth = 0
    in_string = False
    escape = False
    last_complete_idx: int | None = None
    started = False

    for i, ch in enumerate(raw):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 1:
                # A top-level value's object just closed cleanly.
                last_complete_idx = i

    if last_complete_idx is None:
        return {}

    candidate = raw[: last_complete_idx + 1].rstrip()
    candidate = candidate.rstrip(",")
    candidate += "}"

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


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
