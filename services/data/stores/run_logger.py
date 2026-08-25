"""
tools/run_logger.py
===================
Structured JSONL logger for all LLM calls and run summaries.

Two output files (append-only), on the Railway volume:
  data/logs/agent_calls.jsonl   — one line per LLM call (ticker resolution, each agent, aggregator)
  data/logs/run_summaries.jsonl — one line per full analysis run

Run summaries are also mirrored into `telemetry.db.run_summaries`, which is
queryable and survives a redeploy the way the JSONL alone did not.

JSONL is newline-delimited JSON — each line is valid JSON, easy to parse with Python:

    import json
    calls = [json.loads(l) for l in open("data/logs/agent_calls.jsonl")]
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

# B1: data/logs is the Railway volume mount; the bare `logs/` this used to
# default to is ephemeral container storage, wiped by every redeploy.
LOGS_DIR = Path(os.getenv("LOGS_DIR", "data/logs"))
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
    # Mirror into the permanent SQLite archive (data/telemetry.db on the
    # Railway volume) — the JSONL above lives on the ephemeral container FS
    # and dies with each deploy. Never fatal.
    try:
        from services.data.stores.log_store import log_llm_call as _log_llm_call_sqlite
        _log_llm_call_sqlite(
            caller=f"{phase}:{agent_name or ticker}",
            model=model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=int(duration_ms),
            success=error is None,
        )
    except Exception as exc:
        logger.warning("[run_logger] telemetry DB mirror failed (non-fatal): %s", exc)
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
    # Mirror into telemetry.db the way log_llm_call does — the JSONL is the
    # human/UI copy, this is the queryable one. Never fatal.
    try:
        from services.data.stores import log_store
        log_store.log_run_summary(
            run_id=run_id,
            ticker=ticker,
            company_name=company_name,
            started_at=record["started_at"],
            duration_seconds=record["duration_seconds"],
            final_score=final_score,
            verdict=verdict,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_cost_usd=record["total_cost_usd"],
            agent_scores=json.dumps(agent_scores, default=str),
            error_count=len(errors),
            errors=json.dumps(errors, default=str),
        )
    except Exception as exc:
        logger.warning("[run_logger] telemetry DB mirror failed (non-fatal): %s", exc)
    logger.info(
        "[run_logger] Run %s summary: tokens=%d cost=$%.4f verdict=%s",
        run_id, record["total_tokens"], total_cost_usd, verdict,
    )


def log_boot_state() -> dict:
    """
    Report the surviving run history at process start — B1's self-check.

    `run_summaries.jsonl` held 13 rows after 53 days of prod traffic because it
    sat on ephemeral storage and nothing ever counted it. Logging both copies at
    boot puts the evidence in the deploy log: an INFO with the row counts, and a
    WARNING when the JSONL has history the durable mirror does not — which is
    what a silently failing mirror looks like. Read-only; never raises.

    Returns {jsonl_path, jsonl_rows, db_rows, mirror_broken} for callers/tests.
    """
    state: dict[str, Any] = {
        "jsonl_path": str(RUN_SUMMARIES_LOG),
        "jsonl_rows": 0,
        "db_rows": 0,
        "mirror_broken": False,
    }
    try:
        if RUN_SUMMARIES_LOG.exists():
            with open(RUN_SUMMARIES_LOG, "r", encoding="utf-8", errors="replace") as f:
                state["jsonl_rows"] = sum(1 for line in f if line.strip())

        from services.data.stores.log_store import run_summary_count
        state["db_rows"] = run_summary_count()

        state["mirror_broken"] = state["jsonl_rows"] > state["db_rows"]
        if state["mirror_broken"]:
            logger.warning(
                "[run_logger] run_summaries: %d rows in %s but only %d in "
                "telemetry.db — the durable mirror is behind or failing.",
                state["jsonl_rows"], RUN_SUMMARIES_LOG, state["db_rows"],
            )
        else:
            logger.info(
                "[run_logger] run history at boot: %d rows in telemetry.db, "
                "%d in %s", state["db_rows"], state["jsonl_rows"], RUN_SUMMARIES_LOG,
            )
    except Exception as exc:
        logger.warning("[run_logger] boot state check failed (non-fatal): %s", exc)
    return state
