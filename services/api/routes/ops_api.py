"""
services/api/routes/ops_api.py
==============================
SA-011 — the durable-error backlog (core/ops/error_backlog.py), owner only.

    GET  /ops/errors               ranked issues: attention | active | all
    GET  /ops/errors/digest        the same registry as deterministic text
    POST /ops/errors/{fingerprint} triage: status, assignee, task, note

Owner-or-machine (require_owner): the registry is built from every account's
log lines, so a member gets 403, and anonymous gets 401 under AUTH_REQUIRED.
Each read first folds new `app_logs` rows into the registry; that write is the
registry's own, and the raw archive is never changed. Nothing here sends a
message.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core.ops import error_backlog as eb
from services.api.auth import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["Ops"])


def _unavailable(exc: Exception) -> HTTPException:
    logger.warning("[ops] error backlog unavailable: %s", type(exc).__name__)
    return HTTPException(status_code=503,
                         detail=f"Error backlog unavailable ({type(exc).__name__}).")


@router.get("/errors", summary="Ranked durable-error backlog (owner)")
def errors(
    include: Literal["attention", "active", "all"] = Query(default="active"),
    limit: int = Query(default=100, ge=1, le=1000),
    _owner: dict = Depends(require_owner),
) -> dict:
    try:
        return eb.report(include=include, limit=limit)
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/errors/digest", response_class=PlainTextResponse,
            summary="Durable-error backlog as plain text (owner)")
def errors_digest(_owner: dict = Depends(require_owner)) -> str:
    try:
        return eb.digest()
    except Exception as exc:
        raise _unavailable(exc) from exc


class TriageBody(BaseModel):
    status: Literal["open", "acknowledged", "fixed", "wontfix"] | None = None
    assignee: str | None = Field(default=None, max_length=64)
    task: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)
    fixed_at: str | None = Field(
        default=None, max_length=40,
        description="With status 'fixed': when the fix took effect, ISO 8601 with its UTC "
                    "offset, e.g. 2026-10-05T08:00+05:30 (IST) or 2026-10-05T02:30Z. A time "
                    "without an offset, or a date alone, is refused (422). Default now.")


@router.post("/errors/{fingerprint}", summary="Triage one backlog issue (owner)")
def triage_issue(
    body: TriageBody,
    fingerprint: str = Path(pattern=r"^[0-9a-f]{16}$"),
    _owner: dict = Depends(require_owner),
) -> dict:
    try:
        issue = eb.triage(fingerprint, status=body.status, assignee=body.assignee,
                          task=body.task, note=body.note, fixed_at=body.fixed_at)
    except eb.TriageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _unavailable(exc) from exc
    if issue is None:
        raise HTTPException(status_code=404, detail="No backlog issue has that fingerprint.")
    now = datetime.now(timezone.utc)
    return eb.public_issue(issue, eb.classify(issue, now, eb.coverage(), eb.params()))
