"""
Compass Phase B — /discovery routes (spec §6.3: shelf visibility +
one-command promote-to-watchlist).

Auth mirrors portfolio_api: optional X-Scheduler-Key (lockdown deferred —
user decision 2026-07-06, virtual money).
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from core.discovery import run_discovery_cycle
from core.discovery.screen import load_latest_screen
from core.discovery.shelf import ShelfStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["Discovery"])


def _check_auth(key: str | None) -> None:
    from services.api.auth import check_scheduler_key
    check_scheduler_key(key, context="discovery_api")


@router.get("/shelf", summary="Discovery shelf — active ideas + paper status")
async def get_shelf(x_scheduler_key: str | None = Header(default=None)) -> dict:
    _check_auth(x_scheduler_key)
    return ShelfStore().load().model_dump()


@router.get("/screen/latest", summary="Most recent weekly screen result")
async def get_latest_screen(x_scheduler_key: str | None = Header(default=None)) -> dict:
    _check_auth(x_scheduler_key)
    result = load_latest_screen()
    if result is None:
        raise HTTPException(status_code=404, detail="No screen has run yet.")
    return result.model_dump()


@router.post("/run", status_code=202, summary="Trigger a discovery cycle now")
async def trigger_run(
    background: BackgroundTasks,
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    background.add_task(run_discovery_cycle)
    return {"status": "accepted", "detail": "Discovery cycle started in background."}


@router.post("/shelf/{symbol}/promote", summary="Promote a shelf idea to the watchlist")
async def promote_idea(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    result = ShelfStore().promote(symbol.strip().upper(), user_id=user_id)
    if result["status"] == "not_on_shelf":
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return result


@router.delete("/shelf/{symbol}", summary="Drop a shelf idea")
async def drop_idea(
    symbol: str,
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    if not ShelfStore().drop(symbol.strip().upper(), reason="manual_api"):
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return {"status": "dropped", "symbol": symbol.upper()}
