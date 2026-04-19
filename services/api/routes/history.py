"""
api/routes/history.py
=====================
GET /history/{ticker}  — returns persisted score history from SQLite.
GET /history/{ticker}/latest  — returns the single most-recent record.

These endpoints are consumed by the TypeScript dashboard and C# scheduler.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_store():
    from services.data.stores.score_store import ScoreStore
    return ScoreStore()


@router.get("/history/{ticker}", summary="Get score history for a ticker")
async def get_history(
    ticker: str,
    limit: int = Query(default=30, ge=1, le=365),
) -> list[dict[str, Any]]:
    """Returns up to `limit` historical score records, newest first."""
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker must not be empty")

    store = _get_store()
    rows = store.get_history(ticker, limit=limit)
    return rows


@router.get("/history/{ticker}/latest", summary="Get most-recent score for a ticker")
async def get_latest(ticker: str) -> dict[str, Any]:
    """Returns the single most-recent score record, or 404 if none exists."""
    ticker = ticker.strip().upper()
    store = _get_store()
    row = store.get_latest(ticker)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No history found for {ticker}")
    return row
