"""
services/api/routes/portfolio_api.py
=====================================
Compass Phase A — virtual portfolio + advisor REST surface.

Endpoints (user_id query param defaults to portfolio.default_user_id)
---------------------------------------------------------------------
GET    /portfolio                      Holdings + watchlist, marked to market
POST   /portfolio/holdings             Add virtual buy (priced at real NSE close)
DELETE /portfolio/holdings/{symbol}
POST   /portfolio/watchlist
DELETE /portfolio/watchlist/{symbol}
POST   /portfolio/import-csv           Raw CSV body: symbol,sector,qty,avg_buy_price,buy_date
GET    /portfolio/advice               Advice-ledger tail
GET    /portfolio/digest/latest
POST   /portfolio/run-advisor          Manual pipeline trigger (202, background)

Authentication: same optional X-Scheduler-Key pattern as scheduler_api.
USER DECISION 2026-07-06: hard lockdown deferred while portfolio is virtual.
All output is research/analysis, never "advice". No auto-trading, ever.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from pydantic import BaseModel

from core.config import settings
from backend.shared.schemas.portfolio import Holding, WatchlistItem
from core.portfolio.pipeline import run_post_review_pipeline
from core.portfolio.pricing import PriceUnavailableError, close_on
from core.portfolio.promotion import SUPPORTED_SECTORS, demote_symbol, promote_symbol
from core.portfolio.store import PortfolioStore, import_csv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[portfolio_api] SCHEDULER_KEY not set — endpoint is open "
                       "(accepted for virtual-money phase; revisit before real holdings).")


def _store(user_id: str | None) -> PortfolioStore:
    try:
        return PortfolioStore(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class HoldingIn(BaseModel):
    symbol: str
    sector: str
    qty: float
    buy_date: str                      # ISO date
    price: float | None = None         # omitted -> real NSE close on buy_date


class WatchlistIn(BaseModel):
    symbol: str
    sector: str
    reason: str = ""


@router.get("", summary="Portfolio with mark-to-market P&L")
async def get_portfolio(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = _store(user_id)
    p = store.load()
    holdings = []
    for h in p.holdings:
        last_close, pnl = None, None
        try:
            last_close = await asyncio.to_thread(close_on, h.symbol, date.today())
            pnl = round(h.unrealised_pnl_pct(last_close), 2)
        except Exception as exc:
            logger.warning("[portfolio_api] mark failed for %s: %s", h.symbol, exc)
        holdings.append({**h.model_dump(), "last_close": last_close, "pnl_pct": pnl})
    return {
        "user_id": p.user_id,
        "risk_profile": p.risk_profile,
        "holdings": holdings,
        "watchlist": [w.model_dump() for w in p.watchlist],
        "disclaimer": "Research/analysis output for the portfolio owner — not investment advice.",
    }


@router.post("/holdings", summary="Add a virtual holding (mock money, real prices)")
async def add_holding(
    body: HoldingIn,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    symbol = body.symbol.strip().upper()
    if body.sector.strip().lower() not in SUPPORTED_SECTORS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Sector '{body.sector}' not yet supported — Phase A covers "
                f"{sorted(SUPPORTED_SECTORS)} only."
            ),
        )
    try:
        buy_date = date.fromisoformat(body.buy_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid buy_date '{body.buy_date}'. Use ISO format: YYYY-MM-DD.",
        )
    if body.price is not None:
        price = body.price
    else:
        try:
            price = await asyncio.to_thread(close_on, symbol, buy_date)
        except PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    holding = Holding(
        symbol=symbol, sector=body.sector, qty=body.qty, avg_buy_price=price,
        adj_avg_price=price, adj_qty=body.qty, buy_date=body.buy_date,
    )
    try:
        _store(user_id).add_holding(holding)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    promotion = promote_symbol(symbol, body.sector, origin="held")
    return {"holding": holding.model_dump(), "promotion": promotion}


@router.delete("/holdings/{symbol}", summary="Remove a holding")
async def delete_holding(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = _store(user_id)
    if not store.remove_holding(symbol):
        raise HTTPException(status_code=404, detail=f"No holding {symbol.upper()}")
    demoted = False
    p = store.load()
    if not any(w.symbol == symbol.upper() for w in p.watchlist):
        demoted = demote_symbol(symbol)
    return {"removed": symbol.upper(), "demoted": demoted}


@router.post("/watchlist", summary="Add a watchlist symbol")
async def add_watchlist(
    body: WatchlistIn,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    symbol = body.symbol.strip().upper()
    if body.sector.strip().lower() not in SUPPORTED_SECTORS:
        raise HTTPException(
            status_code=422,
            detail=f"Sector '{body.sector}' not yet supported — Phase A covers {sorted(SUPPORTED_SECTORS)} only.",
        )
    promotion = promote_symbol(symbol, body.sector, origin="watchlist")
    item = WatchlistItem(
        symbol=symbol, sector=body.sector, added=date.today().isoformat(),
        reason=body.reason, source="user",
    )
    _store(user_id).add_watchlist(item)
    return {"watchlist_item": item.model_dump(), "promotion": promotion}


@router.delete("/watchlist/{symbol}", summary="Remove a watchlist symbol")
async def delete_watchlist(
    symbol: str,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    store = _store(user_id)
    if not store.remove_watchlist(symbol):
        raise HTTPException(status_code=404, detail=f"No watchlist entry {symbol.upper()}")
    demoted = False
    p = store.load()
    if not any(h.symbol == symbol.upper() for h in p.holdings):
        demoted = demote_symbol(symbol)
    return {"removed": symbol.upper(), "demoted": demoted}


@router.post("/import-csv", summary="Bulk import holdings from CSV text")
async def import_csv_endpoint(
    request: Request,
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    _store(user_id)  # validate user_id before running the import
    text = (await request.body()).decode("utf-8", errors="replace")
    result = await asyncio.to_thread(
        import_csv, text, user_id=user_id,
        price_lookup=lambda sym, d: close_on(sym, date.fromisoformat(d)),
    )
    # Promote successfully imported symbols (held origin).
    p = _store(user_id).load()
    for h in p.holdings:
        try:
            promote_symbol(h.symbol, h.sector, origin="held")
        except Exception as exc:
            logger.warning("[portfolio_api] promotion failed for %s: %s", h.symbol, exc)
    return result


@router.get("/advice", summary="Advice-ledger tail")
async def get_advice(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    records = _store(user_id).load_advice(limit=limit)
    return {"records": [r.model_dump() for r in records]}


@router.get("/digest/latest", summary="Latest EOD digest")
async def get_latest_digest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    digest = _store(user_id).load_latest_digest()
    if digest is None:
        raise HTTPException(status_code=404, detail="No digest yet — run the advisor first.")
    return digest


@router.post("/run-advisor", status_code=202, summary="Manually trigger the post-review pipeline")
async def run_advisor(
    background_tasks: BackgroundTasks,
    review_date: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    if review_date:
        try:
            target = date.fromisoformat(review_date)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date '{review_date}'. Use ISO format: YYYY-MM-DD.",
            )
    else:
        target = date.today()

    async def _task() -> None:
        result = await asyncio.to_thread(run_post_review_pipeline, target)
        logger.info("[portfolio_api] manual advisor run: %s", result)

    background_tasks.add_task(_task)
    return {"status": "accepted", "review_date": target.isoformat()}
