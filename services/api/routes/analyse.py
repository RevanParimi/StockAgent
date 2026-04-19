"""
api/routes/analyse.py
=====================
POST /analyse  — runs the full 8-agent pipeline and returns a FinalReport.

The orchestrator's analyse_async() uses AsyncOpenAI + asyncio.gather so
all 8 LLM calls are concurrent coroutines — no threads, no GIL contention.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.pipeline.orchestrator import AutomobileAgentOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyseRequest(BaseModel):
    ticker: str
    output_format: str = "json"   # json | markdown (reserved for future use)


@router.post("/analyse", summary="Run full 8-agent stock analysis")
async def analyse(req: AnalyseRequest) -> dict:
    """
    Trigger a complete analysis pipeline for the given ticker.

    Returns the FinalReport as a JSON object.  All 8 LLM agent calls run
    concurrently via asyncio.gather — the event loop is never blocked.
    """
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker must not be empty")

    logger.info("[API /analyse] Received request for %s", ticker)

    orchestrator = AutomobileAgentOrchestrator()
    try:
        report = await orchestrator.analyse_async(ticker)
    except Exception as exc:
        logger.error("[API /analyse] Pipeline failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=503, detail=f"Analysis pipeline failed: {exc}")

    return report.model_dump()
