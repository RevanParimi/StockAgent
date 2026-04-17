"""
tools/run_logger.py
===================
Structured JSONL logger for all LLM calls and run summaries.

Two output files (append-only):
  logs/agent_calls.jsonl   — one line per LLM call (ticker resolution, each agent, aggregator)
  logs/run_summaries.jsonl — one line per full analysis run

JSONL is newline-delimited JSON — each line is valid JSON, easy to parse with Python:

    import json
    calls = [json.loads(l) for l in open("logs/agent_calls.jsonl")]
    # filter by ticker, agent, date — no LLM needed
    maruti_calls = [c for c in calls if c["ticker"] == "MARUTI"]
    total_cost = sum(c["cost_usd"] for c in calls)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.getenv("LOGS_DIR", "logs"))
AGENT_CALLS_LOG = LOGS_DIR / "agent_calls.jsonl"
RUN_SUMMARIES_LOG = LOGS_DIR / "run_summaries.jsonl"


def _append(path: Path, record: dict[str, Any]) -> None:
    """Thread-safe append — each write is a single line (atomic on most OS)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.warning("[run_logger] Failed to write log: %s", exc)


def log_llm_call(
    *,
    run_id: str,
    ticker: str,
    phase: str,                        # "ticker_resolution" | "agent" | "aggregation"
    agent_name: str | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: float,
    cost_usd: float,
    score: float | None = None,
    error: str | None = None,
    data_sources: list[str] | None = None,
    serper_queries: int = 0,
    cache_hit: bool = False,
) -> None:
    """Log a single LLM call to agent_calls.jsonl."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "ticker": ticker,
        "phase": phase,
        "agent": agent_name,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(cost_usd, 7),
        "duration_ms": round(duration_ms, 1),
        "score": score,
        "data_sources": data_sources or [],
        "serper_queries": serper_queries,
        "cache_hit": cache_hit,
        "error": error,
    }
    _append(AGENT_CALLS_LOG, record)
    logger.debug(
        "[run_logger] %s/%s tokens=%d cost=$%.5f",
        phase, agent_name or "–", record["total_tokens"], cost_usd,
    )


def log_run_summary(
    *,
    run_id: str,
    ticker: str,
    company_name: str,
    started_at: datetime,
    duration_seconds: float,
    final_score: float,
    verdict: str,
    total_prompt_tokens: int,
    total_completion_tokens: int,
    total_cost_usd: float,
    agent_scores: dict[str, float],
    errors: list[str],
) -> None:
    """Log a full run summary to run_summaries.jsonl."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "ticker": ticker,
        "company_name": company_name,
        "started_at": started_at.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "final_score": final_score,
        "verdict": verdict,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "total_cost_usd": round(total_cost_usd, 6),
        "agent_scores": agent_scores,
        "error_count": len(errors),
        "errors": errors,
    }
    _append(RUN_SUMMARIES_LOG, record)
    logger.info(
        "[run_logger] Run %s summary: tokens=%d cost=$%.4f verdict=%s",
        run_id, record["total_tokens"], total_cost_usd, verdict,
    )
