"""
services/api/routes/delivery_api.py
====================================
Compass Phase C — M4 delivery endpoints: latest brief / weekly review,
manual triggers, alert tail, web-push subscription management.

Auth (M0.1): brief/weekly/alerts reads need a logged-in user (identity from
the bearer session — user_id params removed, IDOR); run-* triggers are
owner-or-machine (require_owner).
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from services.api.auth import get_current_user, require_owner
from core.config import settings
from core.delivery.alerts import load_recent_alerts
from core.delivery.brief import run_morning_brief
from core.delivery.channels import PushStore
from core.delivery.weekly import run_weekly_review
from core.portfolio.store import PortfolioStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery", tags=["Delivery"])


@router.get("/brief/latest", summary="Latest morning brief")
async def brief_latest(
    format: str | None = Query(default=None, description="'text' → rendered text"),
    user: dict = Depends(get_current_user),
) -> dict:
    brief = PortfolioStore(user_id=user["user_id"]).load_latest_brief()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief yet — run POST /delivery/run-brief.")
    if format == "text":
        from core.delivery.brief import render_brief_text
        return {"date": brief.get("date"), "text": render_brief_text(brief)}
    return brief


@router.get("/weekly/latest", summary="Latest weekly review")
async def weekly_latest(
    format: str | None = Query(default=None, description="'text' → rendered text"),
    user: dict = Depends(get_current_user),
) -> dict:
    review = PortfolioStore(user_id=user["user_id"]).load_latest_weekly()
    if review is None:
        raise HTTPException(status_code=404, detail="No weekly review yet — run POST /delivery/run-weekly.")
    if format == "text":
        from core.delivery.weekly import render_weekly_text
        return {"date": review.get("date"), "text": render_weekly_text(review)}
    return review


@router.post("/run-brief", status_code=202, summary="Build + deliver the morning brief now")
async def run_brief_now(
    background_tasks: BackgroundTasks,
    on: str | None = Query(default=None, description="ISO date; default today"),
    _owner: dict = Depends(require_owner),
) -> dict:
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
    _owner: dict = Depends(require_owner),
) -> dict:
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
    user: dict = Depends(get_current_user),
) -> dict:
    return {"alerts": load_recent_alerts(limit=limit)}


@router.get("/push/public-key", summary="VAPID application server key for the browser")
async def push_public_key() -> dict:
    # No auth: the PUBLIC key is safe to expose; the frontend needs it pre-login.
    return {"public_key": settings.VAPID_PUBLIC_KEY}


_MAX_PUSH_SUBS_PER_USER = 50   # AUD-012: bound anonymous store growth


# Session-bound (Atlas A1): the device belongs to whoever is logged in, so we
# ignore any client-supplied user identity and use the session's user_id.
# AUTH_REQUIRED=false keeps the single-user flow (anonymous ⇒ owner). The
# public-key GET above stays open — it's a public key. AUD-012 hardening:
# https-only endpoints + per-user cap.
@router.post("/push/subscribe", summary="Store a web-push subscription")
async def push_subscribe(
    subscription: dict,
    user: dict = Depends(get_current_user),
) -> dict:
    endpoint = subscription.get("endpoint")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://")):
        raise HTTPException(status_code=422,
                            detail="subscription.endpoint must be an https:// URL")
    store = PushStore()
    if len(store.list(user_id=user["user_id"])) >= _MAX_PUSH_SUBS_PER_USER:
        raise HTTPException(status_code=429,
                            detail="Subscription limit reached for this user.")
    count = store.add(subscription, user_id=user["user_id"])
    return {"status": "subscribed", "subscriptions": count}


@router.delete("/push/subscribe", summary="Remove a web-push subscription")
async def push_unsubscribe(
    endpoint: str = Query(...),
    user: dict = Depends(get_current_user),
) -> dict:
    removed = PushStore().remove(endpoint, user_id=user["user_id"])
    return {"removed": removed}
