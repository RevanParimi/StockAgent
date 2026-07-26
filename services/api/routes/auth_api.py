"""
services/api/routes/auth_api.py
===============================
M0 auth routes (spec 2026-07-26 §4.2): signup (invite-gated after the first
user), login, logout, me, owner invite management, DPDP self-service account
deletion. Sessions are bearer tokens resolved by services.api.auth.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from services.api.auth import get_current_user
from services.data.stores import user_store

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
def delete_account(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] == "owner":
        raise HTTPException(status_code=403,
                            detail="The owner account cannot self-delete.")
    user_store.delete_user(user["user_id"])
    pf_dir = Path(settings.PORTFOLIO_DATA_DIR) / user["user_id"]
    try:
        if pf_dir.is_dir():
            shutil.rmtree(pf_dir)
    except Exception as exc:
        logger.warning("[auth] portfolio dir cleanup failed for %s: %s",
                       user["user_id"], exc)
    logger.info("[auth] account deleted (DPDP): %s", user["user_id"])
    return {"ok": True}
