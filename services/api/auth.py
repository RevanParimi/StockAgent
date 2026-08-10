"""
services/api/auth.py
====================
Shared optional X-Scheduler-Key gate (Wave B, AUD-099/102).

Semantics (unchanged from the per-router copies this replaces):
enforced only when the SCHEDULER_KEY env var is set; otherwise open,
with a warning so the posture is visible in logs. Lockdown = set the
env var in Railway — no code change needed.
"""
from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException

from core.config import settings

logger = logging.getLogger(__name__)


def check_scheduler_key(key: str | None, context: str = "api") -> None:
    """Raise 403 when SCHEDULER_KEY is set and `key` does not match."""
    required = os.getenv("SCHEDULER_KEY", "")
    if required and key != required:
        raise HTTPException(status_code=403,
                            detail="Invalid or missing X-Scheduler-Key header.")
    if not required:
        logger.warning("[%s] SCHEDULER_KEY not set — endpoint is open.", context)


# ---------------------------------------------------------------------------
# M0 (spec 2026-07-26 §4.3) — bearer-session user identity.
# AUTH_REQUIRED=false (default): anonymous requests act as the owner, so the
# merge deploy is a behavioral no-op. Flip the env var to enforce — no code
# change, same pattern as SCHEDULER_KEY above.
# ---------------------------------------------------------------------------

def _owner_passthrough() -> dict:
    return {"user_id": settings.PORTFOLIO_DEFAULT_USER_ID, "email": "",
            "display_name": "Owner", "role": "owner", "created_at": ""}


def _attribute_telemetry(user_id: str | None) -> None:
    """Atlas C8 (BP4): bind this request's user to LLM-cost telemetry so
    `log_llm_call` attributes chat / on-demand analyse / narrator spend. Only
    when ATLAS is enabled — dormant pre-cutover (unset ⇒ NULL ⇒ shared brain).
    Never raises. (Future hardening: reset per request via middleware so a
    value never leaks to a later non-authenticated request on the same worker.)
    """
    try:
        from services.data.stores import atlas_store, log_store
        if atlas_store.enabled():
            log_store.current_user_id.set(user_id)
    except Exception:
        pass


async def get_current_user_optional(
        authorization: str | None = Header(None)) -> dict | None:
    """Resolve Bearer token → user dict. Invalid *presented* tokens raise 401;
    absent token returns owner-passthrough (AUTH_REQUIRED=false) or None."""
    if authorization and authorization.lower().startswith("bearer "):
        from services.data.stores import user_store
        user = user_store.resolve_session(authorization[7:].strip())
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session.")
        _attribute_telemetry(user["user_id"])
        return user
    if not settings.AUTH_REQUIRED:
        owner = _owner_passthrough()
        _attribute_telemetry(owner["user_id"])
        return owner
    return None


async def get_current_user(
        authorization: str | None = Header(None)) -> dict:
    user = await get_current_user_optional(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


async def get_current_user_or_machine(
        authorization: str | None = Header(None),
        x_scheduler_key: str | None = Header(None)) -> dict:
    """Read-side counterpart to require_owner: any valid session OR the key.

    require_owner is wrong for a per-user READ endpoint — it 403s a member out
    of their own data. get_current_user alone is wrong for server-to-server
    reads, which have no session. This is the union: members keep reading their
    own report, and the machine identity (which already has owner-equivalent
    access to the write side) can read the owner's."""
    required = os.getenv("SCHEDULER_KEY", "")
    if required and x_scheduler_key == required:
        return _owner_passthrough()
    return await get_current_user(authorization)


# ---------------------------------------------------------------------------
# WebSocket identity + on-demand pipeline quota.
#
# Browsers cannot set headers on a WebSocket handshake, so the bearer token
# rides in `Sec-WebSocket-Protocol` as the pair ["sa.bearer", "<token>"]
# (client: `new WebSocket(url, ['sa.bearer', tok])`). That keeps live session
# tokens out of the URL, and therefore out of edge/access logs — a `?token=`
# query param would be logged by Railway on every connection.
# ---------------------------------------------------------------------------

WS_BEARER_SUBPROTOCOL = "sa.bearer"


def ws_token(websocket) -> str | None:
    """Extract the bearer token offered on a WebSocket handshake, or None."""
    subprotocols = list(websocket.scope.get("subprotocols") or [])
    if WS_BEARER_SUBPROTOCOL in subprotocols:
        idx = subprotocols.index(WS_BEARER_SUBPROTOCOL)
        if idx + 1 < len(subprotocols):
            return subprotocols[idx + 1].strip() or None
    # Non-browser clients (scripts, tests) may use a query param instead.
    return (websocket.query_params.get("token") or "").strip() or None


async def get_ws_user(websocket) -> dict | None:
    """WebSocket counterpart to `get_current_user`.

    Returns the user dict, or None when the connection must be rejected.
    Mirrors the HTTP path exactly: a valid token resolves to its user, an
    absent token is owner-passthrough while AUTH_REQUIRED is false, and an
    invalid or missing token under AUTH_REQUIRED=true is a rejection. Never
    raises — a WebSocket has no HTTPException handler, so the caller closes
    the socket instead."""
    token = ws_token(websocket)
    try:
        return await get_current_user_optional(
            f"Bearer {token}" if token else None)
    except HTTPException:
        return None            # presented token was invalid or expired


def check_analyse_quota(user: dict) -> str | None:
    """Meter one on-demand pipeline run against the user's daily quota.

    Returns a human-readable refusal message when exhausted, else None.
    Owner is exempt and 0 means unlimited, matching chat. Availability over
    strict metering: if the counter store fails we allow the run, loudly."""
    quota = int(getattr(settings, "ANALYSE_DAILY_QUOTA", 0) or 0)
    if quota <= 0 or user.get("role") == "owner":
        return None
    try:
        from services.data.stores import user_store
        used = user_store.bump_analyse_usage(user["user_id"])
    except Exception as exc:
        logger.warning("[analyse] quota store failed — allowing run: %s", exc)
        return None
    if used > quota:
        return (f"You've used your {quota} on-demand analyses for today — "
                "resets at midnight IST.")
    return None


async def require_owner(
        authorization: str | None = Header(None),
        x_scheduler_key: str | None = Header(None)) -> dict:
    """M0.1: owner-or-machine gate for config/trigger routes.

    Passes when the request carries EITHER a valid **owner** session (human,
    from the login screen) OR the exact SCHEDULER_KEY header (server-to-server
    machine calls). Browsers therefore never need the key — the key becomes
    purely server-side. Members get 403; anonymous follows AUTH_REQUIRED
    (owner-passthrough when false, 401 when true)."""
    required = os.getenv("SCHEDULER_KEY", "")
    if required and x_scheduler_key == required:
        return _owner_passthrough()        # machine identity acts as owner
    user = await get_current_user(authorization)   # 401 on anonymous/invalid
    if user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    return user
