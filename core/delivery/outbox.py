"""
core/delivery/outbox.py
=======================
Atlas C7 — BP2 durable delivery outbox (design spec §7/§8, reviewer R3).

When `ATLAS_ENABLED`, `deliver()` hands each message to this durable queue
(one row per channel in `atlas.db outbox`) instead of sending inline; an
in-process drainer — started ONLY inside the singleton-lock owner in
`services/api/server.py` (the same guard that makes the scheduler single-owner
under `--workers 2`) — claims each row atomically and delivers with backoff →
dead-letter. Flag OFF ⇒ nothing enqueues and this module is inert.

Two-worker safety (reviewer R3): the drainer claims each row with a CAS —
`UPDATE outbox SET status='sending', attempts=attempts+1 WHERE id=? AND
status='queued'` — and acts only when `rowcount == 1`. The `dedupe_key` UNIQUE
prevents duplicate *rows* (re-running a fan-out job the same day); the CAS
prevents a duplicate *send* even if a second drainer ever exists.

House rules: hot-path safe (every function logs + degrades, never raises);
tunables via `cfg()`. The payload is stored inline in `payload_ref` as compact
JSON `{title, body, url}` (B4: push bodies are already capped, rows stay tiny;
C9 prunes delivered/dead rows) — a value, not a large blob.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from backend.shared.config.settings.loader import cfg
from services.data.stores import atlas_store

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_drainer_thread: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _max_attempts() -> int:
    return int(cfg("delivery.outbox_max_attempts", fallback=3))


def _backoff_minutes() -> list:
    return list(cfg("delivery.outbox_backoff_minutes", fallback=[1, 5, 30]))


def _poll_seconds() -> float:
    return float(cfg("delivery.outbox_poll_seconds", fallback=30))


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------

def enqueue(user_id: str, channel: str, kind: str, payload_ref: str,
            dedupe_key: str) -> int | None:
    """Durably queue one delivery. Idempotent on the UNIQUE `dedupe_key` (a
    duplicate returns None, no new row). No-op returning None when the flag is
    off or on any failure — never raises."""
    if not atlas_store.enabled():
        return None
    try:
        conn = atlas_store._get_conn()
        now = _now_iso()
        with atlas_store._lock:
            cur = conn.execute(
                "INSERT OR IGNORE INTO outbox (user_id, channel, kind, payload_ref,"
                " dedupe_key, status, created_at, next_attempt_at)"
                " VALUES (?,?,?,?,?, 'queued', ?, ?)",
                (user_id, channel, kind, payload_ref, dedupe_key, now, now))
            conn.commit()
            return cur.lastrowid if cur.rowcount == 1 else None
    except Exception as exc:
        logger.warning("[outbox] enqueue failed for %s/%s (non-fatal): %s",
                       user_id, kind, exc)
        return None


def enqueue_message(user_id: str, title: str, body: str, *, url: str = "/",
                    kind: str = "alert") -> int:
    """Fan one logical message into the outbox as per-channel rows, mirroring
    `deliver()`'s push+email fan-out — but only for channels currently enabled
    (so a permanently-disabled channel never accrues dead-letters). The payload
    is stored inline; the dedupe key carries a content hash so re-running an
    identical brief dedupes while two distinct alert bundles each deliver.
    Returns the number of rows enqueued (0 when nothing was queued)."""
    from core.config import settings
    payload_ref = json.dumps({"title": title, "body": body[:1500], "url": url})
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    base = f"{user_id}|{kind}|{_now().date().isoformat()}|{digest}"
    n = 0
    for channel, enabled in (("push", getattr(settings, "DELIVERY_PUSH_ENABLED", False)),
                             ("email", getattr(settings, "DELIVERY_EMAIL_ENABLED", False))):
        if enabled and enqueue(user_id, channel, kind, payload_ref,
                               f"{base}|{channel}") is not None:
            n += 1
    return n


# ---------------------------------------------------------------------------
# drain
# ---------------------------------------------------------------------------

def _send_row(row) -> bool:
    """Deliver one claimed row via its channel transport. True on delivery."""
    try:
        payload = json.loads(row["payload_ref"])
    except Exception:
        payload = {}
    title, body = payload.get("title", ""), payload.get("body", "")
    url = payload.get("url", "/")
    from core.delivery.channels import send_email, send_push
    try:
        if row["channel"] == "push":
            return send_push(title, body, url=url, user_id=row["user_id"]) > 0
        if row["channel"] == "email":
            return bool(send_email(title, body))
    except Exception as exc:
        logger.warning("[outbox] send failed for row %s (non-fatal): %s",
                       row["id"], exc)
    return False


def drain_once() -> dict:
    """Claim and deliver every ready row exactly once. Returns a summary;
    never raises. No-op when the flag is off."""
    summary = {"claimed": 0, "delivered": 0, "dead": 0}
    if not atlas_store.enabled():
        return summary
    try:
        conn = atlas_store._get_conn()
        with atlas_store._lock:
            ready = conn.execute(
                "SELECT id, user_id, channel, kind, payload_ref, attempts FROM outbox"
                " WHERE status='queued' AND (next_attempt_at IS NULL"
                " OR next_attempt_at <= ?) ORDER BY id", (_now_iso(),)).fetchall()
        for row in ready:
            rid = row["id"]
            # atomic claim (reviewer R3) — only the winner proceeds
            with atlas_store._lock:
                cur = conn.execute(
                    "UPDATE outbox SET status='sending', attempts=attempts+1"
                    " WHERE id=? AND status='queued'", (rid,))
                conn.commit()
            if cur.rowcount != 1:
                continue
            summary["claimed"] += 1
            attempts = row["attempts"] + 1
            ok = _send_row(row)
            with atlas_store._lock:
                if ok:
                    conn.execute("UPDATE outbox SET status='delivered', delivered_at=?"
                                 " WHERE id=?", (_now_iso(), rid))
                    summary["delivered"] += 1
                elif attempts >= _max_attempts():
                    conn.execute("UPDATE outbox SET status='dead' WHERE id=?", (rid,))
                    summary["dead"] += 1
                else:
                    backoff = _backoff_minutes()
                    mins = backoff[min(attempts - 1, len(backoff) - 1)] if backoff else 0
                    nxt = (_now() + timedelta(minutes=mins)).isoformat(timespec="seconds")
                    conn.execute("UPDATE outbox SET status='queued', next_attempt_at=?"
                                 " WHERE id=?", (nxt, rid))
                conn.commit()
    except Exception as exc:
        logger.warning("[outbox] drain_once failed (non-fatal): %s", exc)
    return summary


# ---------------------------------------------------------------------------
# drainer lifecycle — started only in the singleton-lock owner (server.py)
# ---------------------------------------------------------------------------

def _drain_loop() -> None:
    while not _stop_event.is_set():
        try:
            drain_once()
        except Exception as exc:      # defence in depth — drain_once already guards
            logger.warning("[outbox] drain loop iteration failed (non-fatal): %s", exc)
        _stop_event.wait(_poll_seconds())


def start_outbox_drainer() -> threading.Thread | None:
    """Start the in-process drainer daemon. Call this ONLY inside the
    singleton-lock owner branch of the server lifespan. Returns None (no-op)
    when the flag is off, else the started daemon thread."""
    global _drainer_thread
    if not atlas_store.enabled():
        return None
    _stop_event.clear()
    _drainer_thread = threading.Thread(target=_drain_loop,
                                       name="atlas-outbox-drainer", daemon=True)
    _drainer_thread.start()
    logger.info("[outbox] drainer thread started (poll=%.0fs)", _poll_seconds())
    return _drainer_thread


def stop_outbox_drainer() -> None:
    """Signal the drainer loop to exit (used on shutdown and in tests)."""
    _stop_event.set()
