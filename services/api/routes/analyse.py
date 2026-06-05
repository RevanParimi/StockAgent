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

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyseRequest(BaseModel):
    ticker: str
    sector: str = ""              # optional override; auto-detected from ticker if empty
    output_format: str = "json"   # json | markdown (reserved for future use)


@router.post("/analyse", summary="Run full multi-sector stock analysis")
async def analyse(req: AnalyseRequest) -> dict:
    """
    Trigger a complete analysis pipeline for the given ticker.

    Sector is auto-detected from the ticker symbol (HDFCBANK → banking_bfsi,
    TCS → it_sector, ADANIGREEN → renewable_energy, else automobile).
    Pass `sector` explicitly to override auto-detection.

    Returns the FinalReport as a JSON object.
    """
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker must not be empty")

    # Sector routing: explicit override > auto-detect from ticker symbol
    from backend.sectors import detect_sector, get_orchestrator
    sector = req.sector.strip().lower() if req.sector.strip() else detect_sector(ticker)
    OrchestratorClass = get_orchestrator(sector)

    logger.info("[API /analyse] ticker=%s sector=%s orchestrator=%s",
                ticker, sector, OrchestratorClass.__name__)

    orchestrator = OrchestratorClass()
    try:
        report = await orchestrator.analyse_async(ticker)
    except Exception as exc:
        logger.error(
            "[API /analyse] Pipeline failed for ticker=%s sector=%s: %s",
            ticker, sector, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Analysis pipeline failed. Please try again or contact support.",
        )

    return report.model_dump()
