"""
Compass Phase B — /discovery routes (spec §6.3: shelf visibility +
one-command promote-to-watchlist).

Auth (M0.1): reads need a logged-in user; run/drop are owner-or-machine
(require_owner). Promote is user-scoped — identity from the bearer session.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from services.api.auth import get_current_user, require_owner
from core.discovery import run_discovery_cycle
from core.discovery.screen import load_latest_screen
from core.discovery.shelf import ShelfStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["Discovery"])


@router.get("/shelf", summary="Discovery shelf — active ideas + paper status")
async def get_shelf(user: dict = Depends(get_current_user)) -> dict:
    return ShelfStore().load().model_dump()


@router.get("/screen/latest", summary="Most recent weekly screen result")
async def get_latest_screen(user: dict = Depends(get_current_user)) -> dict:
    result = load_latest_screen()
    if result is None:
        raise HTTPException(status_code=404, detail="No screen has run yet.")
    return result.model_dump()


@router.post("/run", status_code=202, summary="Trigger a discovery cycle now")
async def trigger_run(
    background: BackgroundTasks,
    _owner: dict = Depends(require_owner),
) -> dict:
    background.add_task(run_discovery_cycle)
    return {"status": "accepted", "detail": "Discovery cycle started in background."}


@router.post("/shelf/{symbol}/promote", summary="Promote a shelf idea to the watchlist")
async def promote_idea(
    symbol: str,
    user: dict = Depends(get_current_user),
) -> dict:
    result = ShelfStore().promote(symbol.strip().upper(), user_id=user["user_id"])
    if result["status"] == "not_on_shelf":
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return result


@router.delete("/shelf/{symbol}", summary="Drop a shelf idea")
async def drop_idea(
    symbol: str,
    _owner: dict = Depends(require_owner),
) -> dict:
    if not ShelfStore().drop(symbol.strip().upper(), reason="manual_api"):
        raise HTTPException(status_code=404, detail=f"{symbol.upper()} is not an active shelf idea.")
    return {"status": "dropped", "symbol": symbol.upper()}
