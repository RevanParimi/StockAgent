"""
/events routes: the company-event feed's stored events (KT section 4).

An event is a market fact, not personal data. But the feed covers only the
stocks someone holds or watches, so "this stock has events" would tell a
member what other users hold. A member therefore reads the events of their
own holdings and watchlist and of the active shelf (which every member sees);
the owner reads any stock's. Any other symbol gets the same 404 whether or
not events exist for it.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from core.discovery.shelf import ShelfStore
from core.events.store import EventStore, valid_symbol
from core.portfolio.store import PortfolioStore
from services.api.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])


def _visible_symbols(user_id: str) -> set[str]:
    """The stocks a member may read events for: their own holdings and
    watchlist, and the active shelf."""
    portfolio = PortfolioStore(user_id=user_id).load()
    symbols = {h.symbol.strip().upper() for h in portfolio.holdings}
    symbols |= {w.symbol.strip().upper() for w in portfolio.watchlist}
    try:
        symbols |= {i.symbol.strip().upper() for i in ShelfStore().load().ideas
                    if i.status == "active"}
    except Exception as exc:
        logger.warning("[events_api] shelf unreadable, its ideas not readable: %s", exc)
    return symbols


@router.get("/{symbol}", summary="Stored company events for one stock, newest first")
async def get_events(
    symbol: str,
    since: date | None = Query(None, description="Only events published on or after this IST day"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
) -> dict:
    sym = symbol.strip().upper()
    if not valid_symbol(sym):
        raise HTTPException(status_code=422, detail="Not a stock symbol.")
    if user.get("role") != "owner" and sym not in _visible_symbols(user["user_id"]):
        raise HTTPException(status_code=404, detail=(
            f"{sym} is not in your portfolio, your watchlist or the discovery shelf."))
    events = EventStore().read(sym, since=since, limit=limit)
    return {"symbol": sym, "since": since.isoformat() if since else None,
            "count": len(events), "events": [e.model_dump() for e in events]}
