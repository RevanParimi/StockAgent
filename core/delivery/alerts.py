"""
Compass Phase C — event alerts (spec §7): shock reforecast on a holding,
advisor escalations, shelf adds, lock-in expiry, index reconstitution.

Dedupe: one JSONL sent-log (data/delivery/alerts_sent.jsonl), key
"{user_id}|{date}|{kind}|{symbol}" — re-running a pipeline the same day
never re-notifies, and the same event for two different users each still
delivers (emits are per-user; see brief.py / pipeline.py). Records written
before this field existed have no "user_id" key and are treated as the
default user (""). Emission failures are telemetry, never pipeline errors.

Each record carries "delivered" (AUD-085): false means no channel accepted
the batch — such records are ignored by dedupe so the alert retries on the
next emit; records written before this field existed are treated as
delivered.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.delivery.channels import deliver

logger = logging.getLogger(__name__)

_SEVERITY_TAG = {"info": "[INFO]", "warning": "[WARN]", "critical": "[ALERT]"}


class AlertEvent(BaseModel):
    date: str                              # ISO date the event refers to
    kind: str                              # advisor_exit | shelf_add | lockin_expiry | ...
    symbol: str = ""
    message: str
    severity: Literal["info", "warning", "critical"] = "info"
    # Verification layer (2026-08-07): links an alert back to the advice row
    # that produced it, so the auditor grades them as one event. Deliberately
    # NOT part of key() — dedupe behaviour must be unchanged by provenance.
    advice_ref: str = ""

    def key(self) -> str:
        return f"{self.date}|{self.kind}|{self.symbol}"


def _sent_log_path(sent_log: str | None) -> Path:
    if sent_log:
        p = Path(sent_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(settings.DELIVERY_DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "alerts_sent.jsonl"


_ROTATE_AT_LINES = 4000   # rotate when the sent-log grows past this
_ROTATE_KEEP = 2000       # keep-window; matches the _seen_keys tail


def _rotate_sent_log(path: Path) -> None:
    """AUD-013: cap unbounded sent-log growth (~10 lines/day on the volume).
    Rewrites the newest _ROTATE_KEEP lines atomically; dedupe already only
    looks at that same tail window, so rotation never changes behavior."""
    try:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _ROTATE_AT_LINES:
            return
        from core.utils.atomic_io import atomic_write_text
        atomic_write_text(path, "\n".join(lines[-_ROTATE_KEEP:]) + "\n")
        logger.info("[alerts] sent-log rotated: %d -> %d lines",
                    len(lines), _ROTATE_KEEP)
    except Exception as exc:
        logger.warning("[alerts] sent-log rotation failed (non-fatal): %s", exc)


def _seen_keys(path: Path, tail: int = 2000) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                rec = json.loads(line)
                if rec.get("delivered") is False:   # AUD-085: undelivered → retryable
                    continue
                keys.add(f"{rec.get('user_id', '')}|{rec.get('date')}|"
                          f"{rec.get('kind')}|{rec.get('symbol')}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[alerts] sent-log unreadable (non-fatal): %s", exc)
    return keys


def load_recent_alerts(limit: int = 50, sent_log: str | None = None) -> list[dict]:
    """The newest `limit` alerts, NEWEST FIRST.

    The sent-log is append-only, so the file's own order is oldest-first. The
    Inbox renders this list top-to-bottom and a notification feed reads newest
    at the top, so the reversal belongs here rather than in every caller.
    """
    path = _sent_log_path(sent_log)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.reverse()
    return out


def emit_alerts(
    events: list[AlertEvent],
    user_id: str | None = None,
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """Dedupe, persist, and deliver a batch as ONE bundled message. Never raises.

    Dedupe is user-aware — the sent-log is global but emits are per-user
    (brief.py, pipeline.py), so the key includes user_id to avoid one
    user's alert silently suppressing everyone else's identical event.
    """
    try:
        uid = user_id or ""
        path = _sent_log_path(sent_log)
        _rotate_sent_log(path)   # AUD-013
        seen = _seen_keys(path)
        new = [e for e in events if f"{uid}|{e.key()}" not in seen]
        # in-batch dedupe too
        uniq: list[AlertEvent] = []
        batch_keys: set[str] = set()
        for e in new:
            bk = f"{uid}|{e.key()}"
            if bk not in batch_keys:
                batch_keys.add(bk)
                uniq.append(e)
        if not uniq:
            return {"emitted": 0}
        body = "\n".join(
            f"{_SEVERITY_TAG[e.severity]} {e.symbol + ' — ' if e.symbol else ''}{e.message}"
            for e in uniq
        )
        # AUD-085 rider: deliver FIRST, then record the outcome — a record with
        # delivered=false does not dedupe, so the same-day batch retries once a
        # transport (push sub / SMTP) appears. Legacy records lack the key and
        # are treated as delivered.
        delivered = False
        outcome: dict = {}
        try:
            outcome = deliver(title, body, url="/#/inbox/alerts", user_id=user_id) or {}
            delivered = bool(outcome.get("delivered"))
        except Exception as exc:
            logger.warning("[alerts] delivery failed (non-fatal): %s", exc)
        if not delivered:
            logger.warning(
                "[alerts] %d alert(s) NOT delivered (%s) — recorded delivered=false, "
                "will retry on next emit (AUD-085)",
                len(uniq), outcome.get("reason") or "no channel delivered")
        with open(path, "a", encoding="utf-8") as fh:
            for e in uniq:
                rec = e.model_dump()
                rec["user_id"] = uid
                rec["delivered"] = delivered
                fh.write(json.dumps(rec) + "\n")
        return {"emitted": len(uniq), "delivered": delivered,
                "kinds": sorted({e.kind for e in uniq})}
    except Exception as exc:
        logger.warning("[alerts] emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}


def _audience_push_store():
    """Seam for tests — the default PushStore."""
    from core.delivery.channels import PushStore
    return PushStore()


def alert_audience() -> list[str]:
    """Every user who should receive SYSTEM-level alerts (AUD-015): all users
    with a push subscription, plus the default portfolio user (the email
    transport is a single global mailbox and rides the default user's emit)."""
    uids: set[str] = set()
    try:
        uids.update(_audience_push_store().user_ids())
    except Exception as exc:
        logger.warning("[alerts] audience lookup failed (non-fatal): %s", exc)
    uids.add(settings.PORTFOLIO_DEFAULT_USER_ID)
    return sorted(uids)


def emit_alerts_broadcast(
    events: list[AlertEvent],
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """emit_alerts to every alert_audience() user (AUD-015). Never raises.

    Note: with >1 audience user the single global mailbox receives one email
    per user (deliver() sends email unconditionally); acceptable at the
    current single-real-user scale, and per-user push still lands correctly.
    """
    results: dict[str, dict] = {}
    for uid in alert_audience():
        results[uid] = emit_alerts(events, user_id=uid, title=title,
                                   sent_log=sent_log)
    return {"users": results,
            "emitted": sum(r.get("emitted", 0) for r in results.values())}
