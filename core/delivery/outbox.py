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

SA-006 delivery policy (the `SendResult` contract is in channels.py):
  - `status='delivered'` means the transport ACCEPTED the row; `accepted_by`
    names the transport (and Resend's message id). Nothing here observes that
    a person received it — `outbox_report()` says so rather than implying it;
  - a permanent failure (auth, configuration, disabled channel, rejected
    recipient, unknown outcome) is dead-lettered at once with its reason;
  - a transient failure retries after max(backoff, provider Retry-After),
    capped, until `outbox_max_attempts`; then it is dead-lettered;
  - a row left in 'sending' by a stopped process is dead-lettered as an
    unknown outcome, never re-sent: at most once, because SMTP and web push
    cannot deduplicate a repeat. Email over Resend carries an Idempotency-Key
    (24 h window at Resend), so its timed-out requests do retry safely;
  - dead rows are history: nothing here re-queues or deletes them.

House rules: hot-path safe (every function logs + degrades, never raises);
tunables via `cfg()`. The payload is stored inline in `payload_ref` as compact
JSON `{title, body, url}` (B4: push bodies are already capped, rows stay tiny;
C9 prunes delivered rows and clears old dead rows' payloads) — a value, not a
large blob.
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


def _retry_after_cap_minutes() -> float:
    """Longest provider-requested wait honoured before the next attempt."""
    return float(cfg("delivery.outbox_retry_after_cap_minutes", fallback=360))


def _sending_stale_minutes() -> float:
    """A 'sending' row older than this was left by a stopped process. It must
    exceed the longest possible send (20 s per network step, up to 50 push
    subscriptions per user)."""
    return float(cfg("delivery.outbox_sending_stale_minutes", fallback=60))


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
                    kind: str = "alert", html_body: str | None = None) -> int:
    """Fan one logical message into the outbox as per-channel rows, mirroring
    `deliver()`'s push+email fan-out — but only for channels currently enabled
    (so a permanently-disabled channel never accrues dead-letters). The full
    payload is stored inline ({title, body, url, html}); the push length cap is
    applied at *send* time (see `_send_row`) so the email row keeps the full text
    + HTML. The dedupe key carries a content hash so re-running an identical brief
    dedupes while two distinct alert bundles each deliver. Returns the number of
    rows enqueued (0 when nothing was queued)."""
    from core.config import settings
    payload = {"title": title, "body": body, "url": url}
    if html_body:
        payload["html"] = html_body
    payload_ref = json.dumps(payload)
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

def idempotency_key(dedupe_key: str) -> str:
    """The provider-side idempotency key for one row: stable across the row's
    retries, unique per row, and a hash — the dedupe key names an internal user
    id, which has no business at the provider."""
    return "stockagent-outbox-" + hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:40]


def _send_row(row):
    """Deliver one claimed row via its channel transport. Returns a
    `SendResult`; its reason is persisted to `outbox.last_error` unless the
    transport accepted the row, so a dead letter explains itself without the
    container log, which on Railway does not outlive the replica."""
    from core.delivery.channels import (SendResult, redact, resolve_recipient,
                                        send_email_result, send_push_result)
    try:
        payload = json.loads(row["payload_ref"])
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as exc:
        logger.warning("[outbox] row %s has unreadable payload_ref: %s",
                       row["id"], exc)
        return SendResult(reason=f"permanent: unreadable payload ({type(exc).__name__})",
                          permanent=True)
    title, body = payload.get("title", ""), payload.get("body", "")
    url, html_body = payload.get("url", "/"), payload.get("html")
    try:
        if row["channel"] == "push":
            return send_push_result(title, body[:1500], url=url,
                                    user_id=row["user_id"])
        if row["channel"] == "email":
            # Multi-user: the row's own account address, never a global inbox.
            recipient = resolve_recipient(row["user_id"])
            if not recipient.address:
                return SendResult(reason=recipient.reason, permanent=recipient.permanent)
            return send_email_result(title, body, html_body=html_body,
                                     to=recipient.address,
                                     idempotency_key=idempotency_key(row["dedupe_key"]))
    except Exception as exc:
        # A transport contract violation (they never raise). Whether anything
        # was sent is unknown, so do not retry into a possible duplicate.
        logger.warning("[outbox] send failed for row %s (non-fatal): %s",
                       row["id"], redact(exc))
        return SendResult(reason=redact(f"unknown outcome: {type(exc).__name__}: {exc}"),
                          permanent=True)
    return SendResult(reason=f"permanent: unknown channel '{row['channel']}'",
                      permanent=True)


def _retry_delay_minutes(attempts: int, retry_after_s: float | None) -> float:
    """The wait before attempt `attempts + 1`: the configured backoff step, or
    the provider's Retry-After when longer, capped."""
    backoff = _backoff_minutes()
    mins = float(backoff[min(attempts - 1, len(backoff) - 1)]) if backoff else 0.0
    if retry_after_s:
        mins = max(mins, min(retry_after_s / 60.0, _retry_after_cap_minutes()))
    return mins


def recover_interrupted() -> int:
    """Dead-letter rows a stopped process left in 'sending' (SA-006).

    The transport may or may not have accepted such a row before the process
    stopped, so re-sending could duplicate the message. The row is not
    re-sent; it becomes a visible dead letter that says so. A row still inside
    the stale window may belong to a live drainer (e.g. the old container
    during a deploy) and is left alone. Rows claimed before `claimed_at`
    existed use their last schedule time. Returns rows recovered."""
    if not atlas_store.enabled():
        return 0
    try:
        conn = atlas_store._get_conn()
        cutoff = (_now() - timedelta(minutes=_sending_stale_minutes())).isoformat(
            timespec="seconds")
        with atlas_store._lock:
            cur = conn.execute(
                "UPDATE outbox SET status='dead', last_error="
                " 'unknown outcome: the process stopped during the send (claimed '"
                " || COALESCE(claimed_at, next_attempt_at, created_at) ||"
                " '); the transport may have accepted it, so it is not re-sent'"
                " WHERE status='sending'"
                " AND COALESCE(claimed_at, next_attempt_at, created_at) < ?", (cutoff,))
            conn.commit()
        n = cur.rowcount or 0
        if n:
            logger.warning("[outbox] %d row(s) left in 'sending' by a stopped process "
                           "dead-lettered as unknown outcome (not re-sent)", n)
        return n
    except Exception as exc:
        logger.warning("[outbox] recover_interrupted failed (non-fatal): %s", exc)
        return 0


def drain_once() -> dict:
    """Claim and deliver every ready row exactly once. Returns a summary;
    never raises. No-op when the flag is off.

    `delivered` counts rows the transport accepted (not receipts); `retrying`
    counts transient failures rescheduled; `dead` counts rows dead-lettered."""
    summary = {"claimed": 0, "delivered": 0, "retrying": 0, "dead": 0}
    if not atlas_store.enabled():
        return summary
    summary["recovered"] = recover_interrupted()
    try:
        conn = atlas_store._get_conn()
        with atlas_store._lock:
            ready = conn.execute(
                "SELECT id, user_id, channel, kind, payload_ref, dedupe_key, attempts"
                " FROM outbox WHERE status='queued' AND (next_attempt_at IS NULL"
                " OR next_attempt_at <= ?) ORDER BY id", (_now_iso(),)).fetchall()
        for row in ready:
            rid = row["id"]
            # atomic claim (reviewer R3) — only the winner proceeds
            with atlas_store._lock:
                cur = conn.execute(
                    "UPDATE outbox SET status='sending', attempts=attempts+1,"
                    " claimed_at=? WHERE id=? AND status='queued'", (_now_iso(), rid))
                conn.commit()
            if cur.rowcount != 1:
                continue
            summary["claimed"] += 1
            attempts = row["attempts"] + 1
            result = _send_row(row)
            reason = result.reason or "no reason recorded"
            with atlas_store._lock:
                if result.accepted:
                    # Clear last_error so a row that recovered on retry does not
                    # keep a stale reason from an earlier attempt.
                    conn.execute("UPDATE outbox SET status='delivered', delivered_at=?,"
                                 " last_error=NULL, accepted_by=? WHERE id=?",
                                 (_now_iso(), result.accepted_by or None, rid))
                    summary["delivered"] += 1
                elif result.permanent or attempts >= _max_attempts():
                    if not result.permanent:
                        reason = f"retries exhausted ({attempts}/{_max_attempts()}): {reason}"
                    conn.execute("UPDATE outbox SET status='dead', last_error=?"
                                 " WHERE id=?", (reason[:500], rid))
                    summary["dead"] += 1
                    logger.warning("[outbox] row %s dead-lettered after %d attempt(s) "
                                   "(%s/%s): %s", rid, attempts, row["channel"],
                                   row["kind"], reason)
                else:
                    mins = _retry_delay_minutes(attempts, result.retry_after_s)
                    nxt = (_now() + timedelta(minutes=mins)).isoformat(timespec="seconds")
                    conn.execute("UPDATE outbox SET status='queued', next_attempt_at=?,"
                                 " last_error=? WHERE id=?", (nxt, reason[:500], rid))
                    summary["retrying"] += 1
                conn.commit()
    except Exception as exc:
        logger.warning("[outbox] drain_once failed (non-fatal): %s", exc)
    return summary


# ---------------------------------------------------------------------------
# report — the dead-letter view (GET /delivery/outbox)
# ---------------------------------------------------------------------------

ACCEPTED_MEANS = ("the transport accepted the message: SMTP 250, Resend HTTP 2xx, "
                  "or a push service 201. It is not proof that anyone received it.")
RECEIPT_MEANS = ("not observable: no read receipts, bounce webhooks or push display "
                 "reports are collected. The Resend id in accepted_by can be looked "
                 "up in the Resend dashboard.")


def outbox_report(limit: int = 20) -> dict:
    """Counts per channel and status, the newest dead letters and retrying rows
    with their reasons, and the newest acceptance per channel. Never raises.

    Transport acceptance and user receipt are reported separately: the stored
    status 'delivered' appears as `accepted`, and `user_receipt` states that
    receipt is not observed. Carries no payload, recipient or user id."""
    from core.delivery.channels import redact
    report: dict = {"enabled": atlas_store.enabled(), "accepted_means": ACCEPTED_MEANS,
                    "user_receipt": RECEIPT_MEANS, "counts": {}, "dead_letters": [],
                    "retrying": [], "last_accepted": {}}
    if not report["enabled"]:
        return report
    label = {"delivered": "accepted"}
    limit = max(1, int(limit))
    try:
        conn = atlas_store._get_conn()
        with atlas_store._lock:
            counts = conn.execute("SELECT channel, status, COUNT(*) FROM outbox"
                                  " GROUP BY channel, status").fetchall()
            dead = conn.execute(
                "SELECT id, channel, kind, created_at, attempts, last_error FROM outbox"
                " WHERE status='dead' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            retrying = conn.execute(
                "SELECT id, channel, kind, next_attempt_at, attempts, last_error"
                " FROM outbox WHERE status='queued' AND last_error IS NOT NULL"
                " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            last = conn.execute(
                "SELECT channel, MAX(delivered_at), accepted_by FROM outbox"
                " WHERE status='delivered' GROUP BY channel").fetchall()
        for channel, status, n in counts:
            report["counts"].setdefault(channel, {})[label.get(status, status)] = n
        report["dead_letters"] = [
            {"id": r[0], "channel": r[1], "kind": r[2], "created_at": r[3],
             "attempts": r[4], "reason": redact(r[5] or "no reason recorded")}
            for r in dead]
        report["retrying"] = [
            {"id": r[0], "channel": r[1], "kind": r[2], "next_attempt_at": r[3],
             "attempts": r[4], "reason": redact(r[5])}
            for r in retrying]
        report["last_accepted"] = {r[0]: {"at": r[1], "accepted_by": r[2]} for r in last}
    except Exception as exc:
        logger.warning("[outbox] report failed (non-fatal): %s", exc)
        report["error"] = type(exc).__name__
    return report


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
