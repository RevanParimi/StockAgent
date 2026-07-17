"""
services/data/stores/job_outcomes.py
=====================================
Last-run outcome per scheduled job (AUD-090d).

`run_now` / GET /scheduler/status had no way to answer "did yesterday's run
actually finish, and how much of it?" — logs were the only record. Scheduler
jobs call `record_job_outcome` at their tail; the status route merges
`load_job_outcomes()` into its response. A FILE (not process memory) because
the scheduler thread and the status route live in different uvicorn workers.

Writes are atomic (AUD-057 util) and never raise — outcome telemetry must not
take down the job it describes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_OUTCOMES_PATH = Path("data") / "scheduler_job_outcomes.json"


def load_job_outcomes() -> dict:
    """{job_name: {...fields, finished_at}} — empty dict when absent/corrupt."""
    try:
        return json.loads(_OUTCOMES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_job_outcome(job: str, **fields) -> None:
    """Merge one job's latest outcome into the store. Never raises."""
    try:
        from core.utils.atomic_io import atomic_write_json
        data = load_job_outcomes()
        fields["finished_at"] = datetime.now(timezone.utc).isoformat()
        data[job] = fields
        atomic_write_json(_OUTCOMES_PATH, data, indent=2)
    except Exception as exc:
        logger.warning("[job_outcomes] record failed (non-fatal): %s", exc)
