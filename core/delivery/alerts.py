"""
Compass Phase C — event alerts (spec §7): shock reforecast on a holding,
advisor escalations, shelf adds, lock-in expiry, index reconstitution.

Dedupe: one JSONL sent-log (data/delivery/alerts_sent.jsonl), key
"{user_id}|{date}|{kind}|{symbol}" — re-running a pipeline the same day
never re-notifies, and the same event for two different users each still
delivers (emits are per-user; see brief.py / pipeline.py). Records written
before this field existed have no "user_id" key and are treated as the
default user (""). Emission failures are telemetry, never pipeline errors.
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


def _seen_keys(path: Path, tail: int = 2000) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                rec = json.loads(line)
                keys.add(f"{rec.get('user_id', '')}|{rec.get('date')}|"
                          f"{rec.get('kind')}|{rec.get('symbol')}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[alerts] sent-log unreadable (non-fatal): %s", exc)
    return keys


def load_recent_alerts(limit: int = 50, sent_log: str | None = None) -> list[dict]:
    path = _sent_log_path(sent_log)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
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
        with open(path, "a", encoding="utf-8") as fh:
            for e in uniq:
                rec = e.model_dump()
                rec["user_id"] = uid
                fh.write(json.dumps(rec) + "\n")
        body = "\n".join(
            f"{_SEVERITY_TAG[e.severity]} {e.symbol + ' — ' if e.symbol else ''}{e.message}"
            for e in uniq
        )
        try:
            deliver(title, body, user_id=user_id)
        except Exception as exc:
            logger.warning("[alerts] delivery failed (non-fatal): %s", exc)
        return {"emitted": len(uniq), "kinds": sorted({e.kind for e in uniq})}
    except Exception as exc:
        logger.warning("[alerts] emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}
