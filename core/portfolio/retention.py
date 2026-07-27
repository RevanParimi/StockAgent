"""
core/portfolio/retention.py
===========================
Atlas C9 — nightly retention / prune (design spec §7).

Keeps the user-plane stores bounded. Every cap is a `cfg()` tunable; a None cap
means keep-all (skip that prune). `user_advice` and `feedback_events` are kept
indefinitely by default (they are the learning ledger). Each prune is
independently hot-path safe — one failure logs and is skipped, never aborting
the nightly lane. Dormant no-op unless ATLAS_ENABLED (wired as scheduler Job 18).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.shared.config.settings.loader import cfg
from services.data.stores import atlas_store

logger = logging.getLogger(__name__)


# -- cap resolvers (monkeypatchable seams) -----------------------------------

def _verdicts_cap_days():
    return cfg("atlas.retention.ticker_verdicts_days", fallback=400)


def _outbox_cap_days():
    return cfg("delivery.outbox_retention_days", fallback=30)


def _value_history_cap():
    return cfg("atlas.retention.value_history_cap", fallback=400)


# -- individual prunes -------------------------------------------------------

def _prune_ticker_verdicts() -> int:
    """Drop ticker_verdicts older than the cap (by as_of_date). Returns rows removed."""
    days = _verdicts_cap_days()
    if not days or int(days) <= 0:
        return 0                                       # keep-all
    cutoff = (date.today() - timedelta(days=int(days))).isoformat()
    conn = atlas_store._get_conn()
    with atlas_store._lock:
        cur = conn.execute("DELETE FROM ticker_verdicts WHERE as_of_date < ?", (cutoff,))
        conn.commit()
    return cur.rowcount or 0


def _prune_outbox() -> int:
    """Drop delivered/dead outbox rows older than the cap. Queued/sending rows are
    never pruned regardless of age. Returns rows removed."""
    days = _outbox_cap_days()
    if not days or int(days) <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat(timespec="seconds")
    conn = atlas_store._get_conn()
    with atlas_store._lock:
        cur = conn.execute(
            "DELETE FROM outbox WHERE status IN ('delivered','dead') AND created_at < ?",
            (cutoff,))
        conn.commit()
    return cur.rowcount or 0


def _prune_value_history() -> int:
    """Truncate every user's value_history.jsonl to the last `cap` points (atomic).
    Returns the number of files trimmed."""
    cap = _value_history_cap()
    if not cap or int(cap) <= 0:
        return 0
    cap = int(cap)
    from core.config import settings
    from core.utils.atomic_io import atomic_write_text
    root = Path(settings.PORTFOLIO_DATA_DIR)
    if not root.is_dir():
        return 0
    trimmed = 0
    for vh in root.glob("*/value_history.jsonl"):
        try:
            lines = vh.read_text(encoding="utf-8").splitlines()
            if len(lines) > cap:
                atomic_write_text(vh, "\n".join(lines[-cap:]) + "\n")
                trimmed += 1
        except Exception as exc:
            logger.warning("[retention] value_history trim failed for %s (non-fatal): %s",
                           vh, exc)
    return trimmed


def _prune_sessions() -> int:
    """Sweep expired auth sessions (idempotent with the startup sweep). Returns rows removed."""
    from services.data.stores.user_store import sweep_expired_sessions
    return sweep_expired_sessions()


# -- lane orchestration ------------------------------------------------------

def run_retention() -> dict:
    """Nightly retention sweep. Dormant no-op unless ATLAS_ENABLED. Each prune is
    guarded independently so one failure never aborts the lane. Never raises."""
    if not atlas_store.enabled():
        return {"skipped": "atlas_disabled"}
    summary: dict = {}
    for name, fn in (("ticker_verdicts", _prune_ticker_verdicts),
                     ("outbox", _prune_outbox),
                     ("value_history", _prune_value_history),
                     ("sessions", _prune_sessions)):
        try:
            summary[name] = fn()
        except Exception as exc:
            logger.warning("[retention] %s prune failed (non-fatal): %s", name, exc)
            summary[name] = "error"
    logger.info("[retention] nightly prune: %s", summary)
    return summary
