"""
services/api/routes/delivery_api.py
====================================
Compass Phase C — M4 delivery endpoints: latest brief / weekly review,
manual triggers, alert tail, web-push subscription management.

Auth mirrors scheduler_api (optional X-Scheduler-Key; lockdown deferred —
user decision 2026-07-06).
"""
from __future__ import annotations

import logging
import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from core.config import settings
from core.delivery.alerts import load_recent_alerts
from core.delivery.brief import run_morning_brief
from core.delivery.channels import PushStore
from core.delivery.weekly import run_weekly_review
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery", tags=["Delivery"])


def _check_auth(key: str | None) -> None:
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403,
                            detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[delivery_api] SCHEDULER_KEY not set — endpoint is open.")


@router.get("/brief/latest", summary="Latest morning brief")
async def brief_latest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    brief = PortfolioStore(user_id=user_id).load_latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief yet — run POST /delivery/run-brief.")
    return brief


@router.get("/weekly/latest", summary="Latest weekly review")
async def weekly_latest(
    user_id: str | None = Query(default=None),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    review = PortfolioStore(user_id=user_id).load_latest_weekly()
    if review is None:
        raise HTTPException(status_code=404, detail="No weekly review yet — run POST /delivery/run-weekly.")
    return review


@router.post("/run-brief", status_code=202, summary="Build + deliver the morning brief now")
async def run_brief_now(
    background_tasks: BackgroundTasks,
    on: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    if on:
        try:
            target = date.fromisoformat(on)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid 'on' date; expected YYYY-MM-DD")
    else:
        target = None
    background_tasks.add_task(run_morning_brief, target)
    return {"status": "accepted", "monitor": "/delivery/brief/latest"}


@router.post("/run-weekly", status_code=202, summary="Build + deliver the weekly review now")
async def run_weekly_now(
    background_tasks: BackgroundTasks,
    on: str | None = Query(default=None, description="ISO date; default today"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    if on:
        try:
            target = date.fromisoformat(on)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid 'on' date; expected YYYY-MM-DD")
    else:
        target = None
    background_tasks.add_task(run_weekly_review, target)
    return {"status": "accepted", "monitor": "/delivery/weekly/latest"}


@router.get("/alerts", summary="Recent emitted alerts (sent-log tail)")
async def alerts_tail(
    limit: int = Query(default=50, ge=1, le=500),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    _check_auth(x_scheduler_key)
    return {"alerts": load_recent_alerts(limit=limit)}


@router.get("/push/public-key", summary="VAPID application server key for the browser")
async def push_public_key() -> dict:
    # No auth: the PUBLIC key is safe to expose; the frontend needs it pre-login.
    return {"public_key": settings.VAPID_PUBLIC_KEY}


# Browser push clients don't hold the scheduler key; these endpoints only store/remove the caller's own subscription.
@router.post("/push/subscribe", summary="Store a web-push subscription")
async def push_subscribe(
    subscription: dict,
    user_id: str | None = Query(default=None),
) -> dict:
    if not subscription.get("endpoint"):
        raise HTTPException(status_code=422, detail="subscription.endpoint required")
    count = PushStore().add(subscription, user_id=user_id)
    return {"status": "subscribed", "subscriptions": count}


@router.delete("/push/subscribe", summary="Remove a web-push subscription")
async def push_unsubscribe(
    endpoint: str = Query(...),
    user_id: str | None = Query(default=None),
) -> dict:
    removed = PushStore().remove(endpoint, user_id=user_id)
    return {"removed": removed}
