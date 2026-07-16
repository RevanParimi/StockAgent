"""
services/api/auth.py
====================
Shared optional X-Scheduler-Key gate (Wave B, AUD-099/102).

Semantics (unchanged from the per-router copies this replaces):
enforced only when the SCHEDULER_KEY env var is set; otherwise open,
with a warning so the posture is visible in logs. Lockdown = set the
env var in Railway — no code change needed.
"""
from __future__ import annotations

import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def check_scheduler_key(key: str | None, context: str = "api") -> None:
    """Raise 403 when SCHEDULER_KEY is set and `key` does not match."""
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403,
                            detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[%s] SCHEDULER_KEY not set — endpoint is open.", context)
