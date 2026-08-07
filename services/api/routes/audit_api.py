"""
services/api/routes/audit_api.py
=================================
Verification layer REST surface (design 2026-08-07 sections 8-9).

GET  /audit/summary    Graded-outcome report: hit-rate by horizon, per-trigger
                       precision, conviction calibration, verdict.
POST /audit/backfill   Grade all matured history. Owner-only, idempotent,
                       single-flight. This is how the backfill runs on prod,
                       where the real ledger lives and `railway ssh` is not
                       available.

Read-only over the learning stack — nothing here mutates weights, lessons or
the portfolio.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from core.audit.outcomes import grade_due
from core.audit.report import build_report
from services.api.auth import get_current_user_or_machine, require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit")

# Single-flight guard: a backfill re-prices thousands of rows and two
# concurrent runs would double the price fetches for no benefit. Idempotency
# means a rejected second call loses nothing.
_BACKFILL_RUNNING = threading.Event()


@router.get("/summary", summary="Graded advice-outcome report")
async def audit_summary(user: dict = Depends(get_current_user_or_machine)) -> dict:
    return await asyncio.to_thread(build_report, user["user_id"])


@router.post("/backfill", summary="Grade all matured history (owner-only)")
async def audit_backfill(user: dict = Depends(require_owner)) -> dict:
    if _BACKFILL_RUNNING.is_set():
        raise HTTPException(status_code=409, detail="a backfill is already running")
    _BACKFILL_RUNNING.set()
    try:
        result = await asyncio.to_thread(grade_due, date.today(), user["user_id"])
    except Exception as exc:
        logger.warning("[audit_api] backfill failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"backfill failed: {exc}")
    finally:
        _BACKFILL_RUNNING.clear()
    logger.info("[audit_api] backfill complete: %s", result)
    return result
