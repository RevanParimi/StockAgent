"""
services/api/routes/auth_api.py
===============================
M0 auth routes (spec 2026-07-26 §4.2): signup (invite-gated after the first
user), login, logout, me, owner invite management, DPDP self-service account
deletion. Sessions are bearer tokens resolved by services.api.auth.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from services.api.auth import get_current_user
from services.data.stores import atlas_store, user_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

_MIN_PW = 10


class SignupBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=_MIN_PW)
    display_name: str = ""
    invite_code: str | None = None
    remember_me: bool = True
    consent: bool


class LoginBody(BaseModel):
    email: str
    password: str
    remember_me: bool = False


def _session_response(user: dict, remember_me: bool) -> dict:
    return {"token": user_store.create_session(user["user_id"], remember_me),
            "user": user}


def _mirror_to_atlas(user_id: str) -> None:
    """Mirror a brand-new account into atlas.db's derived `users` table — the
    fan-out set the brief and autopilot iterate. Without this, a post-cutover
    signup authenticates fine (auth reads users.db) and receives nothing.

    A no-op while ATLAS is off, and it must stay one: any atlas_store write
    creates atlas.db, which the cutover pre-flight reads as dirty.

    Never fails signup — the Atlas plane is a derived index, not the account,
    and the ETL rebuilds it. Drift is caught by the `users_mirrored` invariant
    rather than left to hope.
    """
    try:
        atlas_store.mirror_user(user_id, users_db=user_store.db_path())
    except Exception as exc:            # defense in depth — the callee guards too
        logger.warning("[auth] atlas user mirror failed for %s (non-fatal): %s",
                       user_id, exc)


@router.post("/signup")
def signup(body: SignupBody) -> dict:
    if not body.consent:
        raise HTTPException(status_code=422,
                            detail="Consent to the data-use notice is required.")
    first_user = user_store.count_users() == 0
    if first_user:
        try:
            user = user_store.create_user(
                body.email, body.password, body.display_name,
                role="owner", user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
        except ValueError:
            raise HTTPException(status_code=409, detail="Email already registered.")
        logger.info("[auth] owner account created")
        _mirror_to_atlas(user["user_id"])
        return _session_response(user, body.remember_me)
    if not body.invite_code:
        raise HTTPException(status_code=403, detail="An invite code is required.")
    try:
        user = user_store.create_user(body.email, body.password, body.display_name)
    except ValueError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    if not user_store.consume_invite(body.invite_code, user["user_id"]):
        user_store.delete_user(user["user_id"])
        raise HTTPException(status_code=403, detail="Invalid or used invite code.")
    # AFTER consume_invite: a rejected code deletes the users.db row above, and
    # mirroring before that point would strand an atlas row pointing at a user
    # that no longer exists.
    _mirror_to_atlas(user["user_id"])
    return _session_response(user, body.remember_me)


@router.post("/login")
def login(body: LoginBody) -> dict:
    user = user_store.verify_password(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _session_response(user, body.remember_me)


@router.post("/logout")
def logout(user: dict = Depends(get_current_user),
           authorization: str | None = Header(None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        user_store.revoke_session(authorization[7:].strip())
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": user}


@router.post("/invites")
def create_invite(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    return {"code": user_store.create_invite(user["user_id"])}


@router.get("/invites")
def list_invites(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only.")
    return {"invites": user_store.list_invites()}


@router.delete("/account")
def delete_account(user: dict = Depends(get_current_user),
                   authorization: str | None = Header(None)) -> dict:
    if user["role"] == "owner":
        raise HTTPException(status_code=403,
                            detail="The owner account cannot self-delete.")
    uid = user["user_id"]
    # Erase across both identity stores so deletion is correct whether or not
    # ATLAS_ENABLED: users.db is the pre-cutover identity SoT; atlas_store owns
    # the cross-plane cascade (atlas.db PII + portfolio dir + chat_turns +
    # telemetry anonymize). Then revoke the caller's session token.
    user_store.delete_user(uid)
    atlas_store.delete_user_completely(uid)
    if authorization and authorization.lower().startswith("bearer "):
        user_store.revoke_session(authorization[7:].strip())
    logger.info("[auth] account deleted (DPDP): %s", uid)
    return {"ok": True}
