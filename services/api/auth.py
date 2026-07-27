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
