"""Watchdog runner — wires registry + checks + engine to state and delivery.

Never raises: this is called from a scheduled job that shares a process with
everything else.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.ops.watchdog import checks as checks_mod
from core.ops.watchdog.engine import Notification, evaluate
from core.ops.watchdog.registry import RegistryError, load_registry

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_REGISTRY_PATH = Path("config/milestones.yaml")
_STATE_PATH = Path("data") / "watchdog_state.json"


def _broadcast(events, title: str) -> None:
    from core.delivery.alerts import emit_alerts_broadcast
    emit_alerts_broadcast(events, title=title)


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_STATE_PATH, state, indent=None)
    except Exception as exc:
        logger.warning("[watchdog] state write failed (non-fatal): %s", exc)


def _as_events(notes: list[Notification], today: date):
    from core.delivery.alerts import AlertEvent
    return [AlertEvent(date=today.isoformat(),
                       kind=f"watchdog_{n.milestone_id}_{n.level}",
                       symbol="", message=f"{n.title}\n\n{n.body}",
                       severity=n.severity)
            for n in notes]


def _alert_registry_broken(detail: str, today: date) -> None:
    from core.delivery.alerts import AlertEvent
    try:
        _broadcast([AlertEvent(
            date=today.isoformat(), kind="watchdog_registry_broken", symbol="",
            message=("The watchdog registry could not be loaded, so NOTHING is "
                     f"being watched: {detail}"),
            severity="critical")], "StockAgent ops alert")
    except Exception as exc:
        logger.warning("[watchdog] registry alert failed: %s", exc)


def run_watchdog(now: datetime | None = None) -> dict:
    """Evaluate every entry and notify on transitions. Never raises."""
    now = now or datetime.now(IST)
    today = now.date()
    try:
        entries = load_registry(_REGISTRY_PATH)
    except RegistryError as exc:
        logger.error("[watchdog] registry load failed: %s", exc)
        _alert_registry_broken(str(exc), today)
        return {"evaluated": 0, "notified": 0, "levels": []}

    results = {e.id: checks_mod.run_check(e.check) for e in entries}
    notes, new_state = evaluate(entries, results, now, _load_state())

    if not notes:
        _save_state(new_state)
        return {"evaluated": len(entries), "notified": 0, "levels": []}

    try:
        _broadcast(_as_events(notes, today), "StockAgent ops alert")
    except Exception as exc:
        # Do NOT advance state: an undelivered notification must be retried
        # tomorrow, not silently marked as sent.
        logger.warning("[watchdog] delivery failed, state not advanced: %s", exc)
        return {"evaluated": len(entries), "notified": 0, "levels": []}

    _save_state(new_state)
    return {"evaluated": len(entries), "notified": len(notes),
            "levels": [n.level for n in notes]}
