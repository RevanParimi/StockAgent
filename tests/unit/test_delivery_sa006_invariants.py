"""SA-006 — delivery invariants, checked at the network boundary.

The expected results here do not come from the outbox or channel code. Fake
servers stand in for the SMTP relay, the Resend API and the push service, and
each one counts what it ACCEPTED — the only thing a person could ever receive.
The invariants are stated in terms of those counts and of the rows a reviewer
would read:

  I1  a message is accepted at most once per row, whatever the transport does
      (timeouts, dropped connections, a process killed mid-send, retries);
  I2  transient failures retry on the configured schedule (or the provider's
      Retry-After) up to the attempt limit, then dead-letter;
  I3  permanent failures stop after one attempt, with an actionable reason;
  I4  an account's email goes only to that account's address — never to the
      owner's DELIVERY_EMAIL_TO by fallback;
  I5  no address, secret, push endpoint or payload reaches a log line,
      `last_error` or the report;
  I6  acceptance is never reported as receipt; dead letters stay history.

Time is a controlled clock; no real transport exists (tests/hermetic.py
refuses the network anyway). The one exception is web push, where the
question is which exceptions the real library raises: `LoopbackPushService`
is reached through the real pywebpush → requests → urllib3 stack on
127.0.0.1, so the error the drainer classifies is the library's own, not one
this module built (review F1).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import smtplib
import socket
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected

import pytest
import requests
from urllib3.exceptions import (ConnectTimeoutError, MaxRetryError, NameResolutionError,
                                NewConnectionError, ProtocolError)
from urllib3.exceptions import SSLError as Urllib3SSLError

import core.delivery.channels as channels
import core.delivery.outbox as outbox
import services.data.stores.atlas_store as atlas_store
from core.config import settings
from services.data.stores import user_store

T0 = datetime(2026, 9, 28, 3, 0, tzinfo=timezone.utc)
OWNER = "owner@example.invalid"
SMTP_SECRET = "smtp-password-5ecret"
RESEND_SECRET = "re_live_key_5ecret"
VAPID_SECRET = "vapid-private-5ecret"


class _ProcessKilled(BaseException):
    """Stands in for the container dying: not an Exception, so nothing in the
    send path can catch it, exactly like SIGKILL."""


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def clock(monkeypatch):
    now = {"t": T0}
    monkeypatch.setattr(outbox, "_now", lambda: now["t"])

    def at(minutes: float) -> datetime:
        now["t"] = T0 + timedelta(minutes=minutes)
        return now["t"]
    return at


@pytest.fixture()
def env(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    # the policy under test, stated here rather than read from config.yaml
    monkeypatch.setattr(outbox, "_max_attempts", lambda: 3)
    monkeypatch.setattr(outbox, "_backoff_minutes", lambda: [1, 5, 30])
    monkeypatch.setattr(outbox, "_retry_after_cap_minutes", lambda: 360)
    monkeypatch.setattr(outbox, "_sending_stale_minutes", lambda: 60)
    for name, value in {
        "DELIVERY_ENABLED": True, "DELIVERY_EMAIL_ENABLED": True,
        "DELIVERY_PUSH_ENABLED": True, "EMAIL_TRANSPORT": "smtp",
        "SMTP_HOST": "smtp.test", "SMTP_PORT": 587, "SMTP_USER": "bot@example.invalid",
        "SMTP_PASSWORD": SMTP_SECRET, "RESEND_API_KEY": "", "DELIVERY_EMAIL_TO": OWNER,
        "APP_PUBLIC_URL": "", "VAPID_PRIVATE_KEY": VAPID_SECRET,
        "DELIVERY_DATA_DIR": str(tmp_path / "delivery"),
    }.items():
        monkeypatch.setattr(settings, name, value, raising=False)
    yield tmp_path
    atlas_store._reset_for_tests()
    if user_store._conn_holder.get("conn") is not None:
        user_store._conn_holder["conn"].close()


def _account(uid: str, email: str) -> None:
    """An account in users.db (the recipient source) and atlas.users (the FK)."""
    user_store.create_user(email, "pw-for-tests", uid, user_id=uid)
    conn = atlas_store._get_conn()
    conn.execute("INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
                 " consent_at) VALUES (?,?,?,?,?)",
                 (uid, email, "h", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    conn.commit()


def _queue(uid: str, channel: str, key: str, body: str = "your portfolio: HOLD") -> int:
    rid = outbox.enqueue(uid, channel, "brief",
                         json.dumps({"title": "Morning brief", "body": body, "url": "/"}), key)
    assert rid is not None
    return rid


def _row(rid: int) -> dict:
    r = atlas_store._get_conn().execute("SELECT * FROM outbox WHERE id=?", (rid,)).fetchone()
    return dict(r)


def _drain_at(clock, minutes: float) -> dict:
    clock(minutes)
    return outbox.drain_once()


# ---------------------------------------------------------------------------
# fake servers — each counts what it ACCEPTED
# ---------------------------------------------------------------------------

class FakeRelay:
    """An SMTP relay driven by a script of per-connection behaviours."""

    def __init__(self, *script: str) -> None:
        self.script = list(script)
        self.connections = 0
        self.accepted: list[list[str]] = []          # RCPT lists of accepted messages
        relay = self

        class _SMTP:
            def __init__(self, host, port, timeout=None):
                relay.connections += 1
                self.action = relay.script.pop(0) if relay.script else "ok"
                if self.action == "unreachable":
                    raise OSError(101, "Network is unreachable")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, *rest):
                if self.action == "quit_fails" and exc_type is None:
                    raise smtplib.SMTPResponseException(451, b"closing badly")
                return False

            def starttls(self):
                pass

            def login(self, user, password):
                if self.action == "auth_535":
                    raise smtplib.SMTPAuthenticationError(
                        535, b"5.7.8 Username and Password not accepted")

            def sendmail(self, frm, to, msg):
                if self.action == "busy_421":
                    raise smtplib.SMTPDataError(421, b"4.7.0 try again later")
                if self.action == "rcpt_550":
                    raise smtplib.SMTPRecipientsRefused(
                        {to[0]: (550, f"5.1.1 <{to[0]}> no such user".encode())})
                relay.accepted.append(list(to))
                if self.action == "accept_then_drop":
                    raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
                if self.action == "accept_then_killed":
                    raise _ProcessKilled()

        self.SMTP = _SMTP


class _Resp:
    def __init__(self, status: int, body: dict | None = None, headers: dict | None = None):
        self.status_code = status
        self.text = json.dumps(body or {})
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


class FakeResend:
    """The Resend API as documented (checked 2026-09-28): a repeat of an
    Idempotency-Key within 24 h returns the first result, no second email."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.first_id: dict[str, str] = {}
        self.accepted: list[list[str]] = []

    def post(self, url, headers=None, json=None, timeout=None):
        action = self.script.pop(0) if self.script else "ok"
        key = (headers or {}).get("Idempotency-Key")
        self.requests.append({"key": key, "to": json["to"]})
        if action in ("ok", "accept_then_timeout"):
            if key is None or key not in self.first_id:
                self.accepted.append(json["to"])
                if key:
                    self.first_id[key] = f"msg-{len(self.accepted)}"
            if action == "accept_then_timeout":
                raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=20)")
            return _Resp(200, {"id": self.first_id.get(key, f"msg-{len(self.accepted)}")})
        status, body, hdrs = action
        return _Resp(status, body, hdrs)


class FakePushService:
    def __init__(self, **script) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.shown: Counter = Counter()              # accepted per endpoint
        self.calls: Counter = Counter()

    def __call__(self, subscription_info, data, vapid_private_key, vapid_claims,
                 timeout=None, ttl=0, **kw):
        from pywebpush import WebPushException
        ep = subscription_info["endpoint"]
        self.calls[ep] += 1
        queue = self.script.get(ep.rsplit("/", 1)[-1], [])
        action = queue.pop(0) if queue else "ok"
        if action == "ok":
            self.shown[ep] += 1
            return _Resp(201)
        if action == "accept_then_timeout":
            self.shown[ep] += 1
            raise requests.exceptions.ReadTimeout(
                f"HTTPSConnectionPool(host='push.example', port=443): Read timed out. "
                f"url: {ep}")
        if action == "accept_then_drop":
            self.shown[ep] += 1
            raise _dropped_after_send()
        status, hdrs = action
        raise WebPushException(f"Push failed: {status}", response=_Resp(status, {}, hdrs))


def _dropped_after_send() -> Exception:
    """requests' error when the service closes the connection after reading
    the request, before it answers — the shape the review's R1 got from the
    real stack (and LoopbackPushService reproduces)."""
    return requests.exceptions.ConnectionError(ProtocolError(
        "Connection aborted.",
        RemoteDisconnected("Remote end closed connection without response")))


def _push_sub(uid: str, token: str) -> str:
    endpoint = f"https://push.example/send/{token}"
    channels.PushStore().add({"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}},
                             user_id=uid)
    return endpoint


class LoopbackPushService:
    """A push service on 127.0.0.1 that counts what it STORED. Each
    connection takes the next scripted action: "ok" stores the push and
    answers 201; "store_then_drop" stores it and closes the connection without
    answering. Until `listen()` the port is reserved but not listening, so a
    connect is refused."""

    def __init__(self, *script: str) -> None:
        self.script = list(script)
        self.stored = 0
        self.connections = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self.endpoint = f"http://127.0.0.1:{self._sock.getsockname()[1]}/send/tokLOOP"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def listen(self) -> None:
        self._sock.listen(8)
        self._sock.settimeout(0.2)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._sock.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:                              # the 0.2 s poll
                continue
            with conn:
                conn.settimeout(5)
                self.connections += 1
                action = self.script.pop(0) if self.script else "ok"
                if not self._read_request(conn):
                    continue
                self.stored += 1
                if action == "ok":
                    conn.sendall(b"HTTP/1.1 201 Created\r\nContent-Length: 0\r\n"
                                 b"Connection: close\r\n\r\n")
                # "store_then_drop": leaving the block closes without a response

    @staticmethod
    def _read_request(conn: socket.socket) -> bool:
        """Read one whole HTTP request (headers and Content-Length body)."""
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                return False
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        length = 0
        for line in head.split(b"\r\n")[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower() == b"content-length":
                length = int(value.strip())
        while len(body) < length:
            chunk = conn.recv(65536)
            if not chunk:
                return False
            body += chunk
        return True


@pytest.fixture()
def loopback(env, monkeypatch):
    """A LoopbackPushService, with real VAPID and subscription keys so the
    real pywebpush can sign and encrypt for it."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    vapid = ec.generate_private_key(ec.SECP256R1())
    device = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY",
                        b64(vapid.private_numbers().private_value.to_bytes(32, "big")))
    monkeypatch.setattr(settings, "VAPID_CLAIM_EMAIL", "ops@example.invalid", raising=False)
    keys = {"p256dh": b64(device.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
            "auth": b64(os.urandom(16))}
    made: list[LoopbackPushService] = []

    def make(uid: str, *script: str) -> LoopbackPushService:
        svc = LoopbackPushService(*script)
        made.append(svc)
        channels.PushStore().add({"endpoint": svc.endpoint, "keys": keys}, user_id=uid)
        return svc
    yield make
    for svc in made:
        svc.close()


# ---------------------------------------------------------------------------
# I2 / I1 — transient failures retry on schedule and deliver once
# ---------------------------------------------------------------------------

def test_transient_smtp_failures_retry_on_schedule_and_deliver_once(env, clock, monkeypatch):
    relay = FakeRelay("unreachable", "busy_421", "ok")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")

    _drain_at(clock, 0)                    # attempt 1: network unreachable
    assert (relay.connections, _row(rid)["status"]) == (1, "queued")
    _drain_at(clock, 0.5)                  # inside the 1-minute backoff: untouched
    assert relay.connections == 1
    _drain_at(clock, 1)                    # attempt 2: 421
    assert relay.connections == 2
    _drain_at(clock, 5.5)                  # inside the 5-minute backoff: untouched
    assert relay.connections == 2
    _drain_at(clock, 6)                    # attempt 3: accepted
    row = _row(rid)
    assert (relay.connections, relay.accepted) == (3, [["a@example.invalid"]])
    assert (row["status"], row["attempts"], row["accepted_by"], row["last_error"]) == (
        "delivered", 3, "smtp", None)
    for minutes in (60, 600):              # nothing is ever sent again
        _drain_at(clock, minutes)
    assert relay.connections == 3


def test_transient_failures_exhaust_to_a_dead_letter(env, clock, monkeypatch):
    relay = FakeRelay(*["unreachable"] * 10)
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    for minutes in (0, 1, 6, 36, 600, 6000):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert (relay.connections, row["status"], row["attempts"]) == (3, "dead", 3)
    assert row["last_error"].startswith("retries exhausted (3/3): transient: ")
    assert "RESEND_API_KEY" in row["last_error"]          # the Errno 101 hint


# ---------------------------------------------------------------------------
# I3 — permanent failures stop at once, with a diagnosis
# ---------------------------------------------------------------------------

def test_auth_rejection_stops_after_one_attempt(env, clock, monkeypatch):
    relay = FakeRelay("auth_535", "ok", "ok")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert (relay.connections, relay.accepted, row["status"], row["attempts"]) == (1, [], "dead", 1)
    assert row["last_error"].startswith("permanent: SMTP login rejected")
    assert "SMTP_PASSWORD" in row["last_error"]


def test_resend_rejection_is_permanent_and_names_the_setting(env, clock, monkeypatch):
    # Resend's testing-sender refusal names the account owner's address.
    api = FakeResend((403, {"name": "validation_error", "message":
                            f"You can only send testing emails to your own email address ({OWNER})."},
                      {}))
    monkeypatch.setattr(requests, "post", api.post)
    monkeypatch.setattr(settings, "EMAIL_TRANSPORT", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", RESEND_SECRET)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    for minutes in (0, 1, 6):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert (len(api.requests), row["status"]) == (1, "dead")
    assert "resend HTTP 403" in row["last_error"] and "RESEND_FROM" in row["last_error"]
    assert OWNER not in row["last_error"]


def test_a_disabled_channel_is_dead_lettered_without_a_send(env, clock, monkeypatch):
    relay = FakeRelay()
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    monkeypatch.setattr(settings, "DELIVERY_EMAIL_ENABLED", False)   # switched off after queueing
    _drain_at(clock, 0)
    _drain_at(clock, 10)
    row = _row(rid)
    assert (relay.connections, row["status"], row["attempts"]) == (0, "dead", 1)
    assert row["last_error"] == "disabled: DELIVERY_EMAIL_ENABLED is false"
    # and while disabled, nothing new is queued for that channel at all
    assert outbox.enqueue_message("u_a", "t", "fresh body", kind="alert") == 1   # push only


# ---------------------------------------------------------------------------
# I1 — ambiguous outcomes and a killed process never produce a second copy
# ---------------------------------------------------------------------------

def test_connection_dropped_after_acceptance_is_not_resent(env, clock, monkeypatch):
    relay = FakeRelay("accept_then_drop", "ok", "ok")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert relay.accepted == [["a@example.invalid"]]       # exactly one copy
    assert (relay.connections, row["status"]) == (1, "dead")
    assert row["last_error"].startswith("unknown outcome:")


def test_quit_failing_after_acceptance_still_counts_as_accepted(env, clock, monkeypatch):
    relay = FakeRelay("quit_fails")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    _drain_at(clock, 0)
    _drain_at(clock, 10)
    assert (relay.connections, len(relay.accepted), _row(rid)["status"]) == (1, 1, "delivered")


def test_process_killed_after_acceptance_is_never_resent(env, clock, monkeypatch):
    relay = FakeRelay("accept_then_killed", "ok", "ok")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    clock(0)
    with pytest.raises(_ProcessKilled):
        outbox.drain_once()                # the container dies mid-send
    assert _row(rid)["status"] == "sending"
    # a restarted drainer inside the stale window leaves it alone (it may be a
    # live drainer in the old container during a deploy)...
    _drain_at(clock, 30)
    assert (_row(rid)["status"], relay.connections) == ("sending", 1)
    # ...and after it, dead-letters it as an unknown outcome instead of re-sending
    _drain_at(clock, 61)
    _drain_at(clock, 120)
    row = _row(rid)
    assert relay.accepted == [["a@example.invalid"]]
    assert (relay.connections, row["status"]) == (1, "dead")
    assert row["last_error"].startswith("unknown outcome: the process stopped during the send")


def test_a_row_stuck_before_claimed_at_existed_is_recovered(env, clock):
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    conn = atlas_store._get_conn()
    conn.execute("UPDATE outbox SET status='sending', claimed_at=NULL WHERE id=?", (rid,))
    conn.commit()
    _drain_at(clock, 90)
    assert _row(rid)["status"] == "dead"


def test_resend_timeout_retry_is_deduplicated_by_the_idempotency_key(env, clock, monkeypatch):
    api = FakeResend("accept_then_timeout", "ok")
    monkeypatch.setattr(requests, "post", api.post)
    monkeypatch.setattr(settings, "EMAIL_TRANSPORT", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", RESEND_SECRET)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "u_a|brief|2026-09-28|abc|email")
    _drain_at(clock, 0)                    # accepted at Resend, response lost
    assert _row(rid)["status"] == "queued"
    _drain_at(clock, 1)                    # the retry repeats the same key
    row = _row(rid)
    keys = {r["key"] for r in api.requests}
    assert len(api.requests) == 2 and len(keys) == 1
    assert api.accepted == [["a@example.invalid"]]          # one email, not two
    assert (row["status"], row["accepted_by"]) == ("delivered", "resend id=msg-1")
    # the key identifies the row without naming the internal user id
    assert "u_a" not in keys.pop()


def test_resend_retry_after_is_honoured_and_capped(env, clock, monkeypatch):
    api = FakeResend((429, {"name": "rate_limit_exceeded"}, {"retry-after": "600"}), "ok",
                     (503, {}, {"Retry-After": "999999"}), "ok")
    monkeypatch.setattr(requests, "post", api.post)
    monkeypatch.setattr(settings, "EMAIL_TRANSPORT", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", RESEND_SECRET)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "email", "k-a")
    _drain_at(clock, 0)                    # 429, Retry-After 10 minutes (> 1-minute backoff)
    _drain_at(clock, 5)
    assert len(api.requests) == 1          # not before the provider's time
    _drain_at(clock, 10)
    assert (len(api.requests), _row(rid)["status"]) == (2, "delivered")

    rid2 = _queue("u_a", "email", "k-b")
    _drain_at(clock, 20)                   # 503 asking for ~11.6 days: capped at 6 h
    nxt = datetime.fromisoformat(_row(rid2)["next_attempt_at"])
    assert nxt == T0 + timedelta(minutes=20 + 360)


# ---------------------------------------------------------------------------
# push — partial fan-out, retries and ambiguous timeouts
# ---------------------------------------------------------------------------

def test_push_retries_only_when_nothing_was_accepted(env, clock, monkeypatch):
    svc = FakePushService(tokA=[(503, {})], tokB=[(429, {"Retry-After": "120"})])
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    ep_a, ep_b = _push_sub("u_a", "tokA"), _push_sub("u_a", "tokB")
    rid = _queue("u_a", "push", "k-p")
    _drain_at(clock, 0)                    # both transient; Retry-After 2 min wins
    _drain_at(clock, 1.5)
    assert sum(svc.calls.values()) == 2
    _drain_at(clock, 2)
    row = _row(rid)
    assert svc.shown == Counter({ep_a: 1, ep_b: 1})        # each device once
    assert (row["status"], row["accepted_by"]) == ("delivered", "webpush 2/2 subscriptions")


def test_push_partial_acceptance_is_not_retried(env, clock, monkeypatch):
    svc = FakePushService(tokB=[(503, {})])
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    ep_a, _ = _push_sub("u_a", "tokA"), _push_sub("u_a", "tokB")
    rid = _queue("u_a", "push", "k-p")
    for minutes in (0, 1, 6):
        _drain_at(clock, minutes)
    assert svc.shown == Counter({ep_a: 1})
    assert _row(rid)["accepted_by"] == "webpush 1/2 subscriptions"


def test_push_read_timeout_is_an_unknown_outcome_and_not_resent(env, clock, monkeypatch):
    svc = FakePushService(tokA=["accept_then_timeout"])
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    ep_a = _push_sub("u_a", "tokA")
    rid = _queue("u_a", "push", "k-p")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert svc.shown == Counter({ep_a: 1}) and svc.calls[ep_a] == 1
    assert row["status"] == "dead" and row["last_error"].startswith("unknown outcome:")


def test_real_push_dropped_after_the_service_stored_it_is_not_resent(env, clock, loopback):
    """Review F1, through the real pywebpush/requests/urllib3 stack: the
    service stores the push, then closes the connection before its 201. Before
    the fix the drainer called this transient and the phone got it twice."""
    _account("u_a", "a@example.invalid")
    svc = loopback("u_a", "store_then_drop", "ok", "ok")
    svc.listen()
    rid = _queue("u_a", "push", "k-p")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert (svc.stored, svc.connections) == (1, 1)          # one copy, never re-sent
    assert (row["status"], row["attempts"]) == ("dead", 1)
    assert row["last_error"].startswith("unknown outcome:")
    assert "Connection aborted" in row["last_error"]         # the library's own error
    assert "tokLOOP" not in row["last_error"]                # endpoint path redacted


def test_real_push_refused_connection_is_retried_and_shown_once(env, clock, loopback):
    """The other side of F1: a connection that was never made cannot have
    delivered anything, so it is retried — and the retry shows it once."""
    _account("u_a", "a@example.invalid")
    svc = loopback("u_a", "ok")                             # not listening yet: refused
    rid = _queue("u_a", "push", "k-p")
    _drain_at(clock, 0)
    row = _row(rid)
    assert (svc.stored, row["status"]) == (0, "queued")
    assert row["last_error"].startswith("transient: ConnectionError")
    svc.listen()
    for minutes in (1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert (svc.stored, row["status"], row["attempts"]) == (1, "delivered", 2)
    assert row["accepted_by"] == "webpush 1/1 subscriptions"


def test_a_push_drop_on_one_device_stops_the_row_for_all(env, clock, monkeypatch):
    """One service stored the push and dropped; another answered 503. Retrying
    the row would re-send to the first device, so the row stops (at most once:
    the 503 device loses this notification, visibly, as a dead letter)."""
    svc = FakePushService(tokA=["accept_then_drop"], tokB=[(503, {})])
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    ep_a, ep_b = _push_sub("u_a", "tokA"), _push_sub("u_a", "tokB")
    rid = _queue("u_a", "push", "k-p")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    row = _row(rid)
    assert svc.shown == Counter({ep_a: 1})
    assert svc.calls == Counter({ep_a: 1, ep_b: 1})
    assert row["status"] == "dead" and row["last_error"].startswith("unknown outcome:")


def _max_retry(reason: Exception) -> MaxRetryError:
    return MaxRetryError(None, "/send/tok", reason=reason)


@pytest.mark.parametrize("exc, retried", [
    # never connected: nothing can have reached the service -> retry
    (requests.exceptions.ConnectTimeout(_max_retry(ConnectTimeoutError(None, "timed out"))), True),
    (requests.exceptions.ConnectionError(_max_retry(
        NewConnectionError(None, "Failed to establish a new connection: refused"))), True),
    (requests.exceptions.ConnectionError(_max_retry(NameResolutionError(
        "push.example", None, socket.gaierror(11001, "getaddrinfo failed")))), True),
    # the request may have been stored -> unknown outcome, never retried
    (_dropped_after_send(), False),
    (requests.exceptions.ReadTimeout("Read timed out. (read timeout=20)"), False),
    (requests.exceptions.SSLError(_max_retry(Urllib3SSLError("EOF in violation of protocol"))),
     False),
    (requests.exceptions.ChunkedEncodingError(ProtocolError("Connection broken")), False),
    (RuntimeError("anything else"), False),
    # the message says "refused" but no type proves it: not retried (no text matching)
    (requests.exceptions.ConnectionError("Failed to connect: Connection refused"), False),
], ids=["connect-timeout", "refused", "dns", "dropped-after-send", "read-timeout", "tls",
        "chunked", "other", "text-only-refused"])
def test_push_is_retried_only_when_the_connection_was_never_made(env, monkeypatch,
                                                                 exc, retried):
    def _raise(**kw):
        raise exc
    monkeypatch.setattr(channels, "webpush", _raise)
    _push_sub("u_a", "tokA")
    res = channels.send_push_result("t", "b", user_id="u_a")
    assert res.accepted is False
    assert (res.permanent, res.reason.split(":")[0]) == (
        (False, "transient") if retried else (True, "unknown outcome"))


def test_no_push_subscription_is_permanent(env, clock, monkeypatch):
    svc = FakePushService()
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    rid = _queue("u_a", "push", "k-p")
    _drain_at(clock, 0)
    _drain_at(clock, 10)
    row = _row(rid)
    assert (row["status"], row["attempts"]) == ("dead", 1)
    assert "no push subscriptions registered" in row["last_error"]


def test_same_day_fan_out_rerun_reaches_each_device_once(env, clock, monkeypatch):
    svc = FakePushService()
    relay = FakeRelay()
    monkeypatch.setattr(channels, "webpush", svc)
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    ep = _push_sub("u_a", "tokA")
    clock(0)
    assert outbox.enqueue_message("u_a", "Morning brief", "same text", kind="brief") == 2
    assert outbox.enqueue_message("u_a", "Morning brief", "same text", kind="brief") == 0
    _drain_at(clock, 0)
    assert svc.shown == Counter({ep: 1}) and relay.accepted == [["a@example.invalid"]]


# ---------------------------------------------------------------------------
# I4 — recipient isolation, end to end
# ---------------------------------------------------------------------------

def test_each_account_gets_only_its_own_mail_even_when_lookup_fails(env, clock, monkeypatch):
    relay = FakeRelay()
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    _account("u_b", "b@example.invalid")
    rid_a = _queue("u_a", "email", "k-a", body="A's holdings")
    rid_b = _queue("u_b", "email", "k-b", body="B's holdings")
    real_get_user = user_store.get_user

    def _locked(uid):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(user_store, "get_user", _locked)
    _drain_at(clock, 0)                    # users.db unavailable: nothing sent
    assert relay.accepted == []
    assert (_row(rid_a)["status"], _row(rid_b)["status"]) == ("queued", "queued")
    assert "will retry" in _row(rid_a)["last_error"]

    monkeypatch.setattr(user_store, "get_user", real_get_user)
    _drain_at(clock, 1)
    assert sorted(relay.accepted) == [["a@example.invalid"], ["b@example.invalid"]]
    assert all(OWNER not in rcpt for rcpt in relay.accepted)


def test_an_account_without_an_address_is_not_mailed_to_the_owner(env, clock, monkeypatch):
    relay = FakeRelay()
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    conn = atlas_store._get_conn()       # atlas row only: no users.db account
    conn.execute("INSERT INTO users (user_id, email, pw_hash, created_at, consent_at)"
                 " VALUES ('u_gone','x','h','2026-01-01','2026-01-01')")
    conn.commit()
    rid = _queue("u_gone", "email", "k-g")
    _drain_at(clock, 0)
    assert (relay.connections, _row(rid)["status"]) == (0, "dead")


# ---------------------------------------------------------------------------
# I5 — redaction
# ---------------------------------------------------------------------------

def test_nothing_private_reaches_logs_rows_or_the_report(env, clock, monkeypatch, caplog):
    relay = FakeRelay("rcpt_550")
    svc = FakePushService(tokSECRET=["accept_then_timeout"])
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    monkeypatch.setattr(channels, "webpush", svc)
    _account("u_a", "a@example.invalid")
    _push_sub("u_a", "tokSECRET")
    _queue("u_a", "email", "k-e", body="PRIVATE-BODY-TEXT")
    _queue("u_a", "push", "k-p", body="PRIVATE-BODY-TEXT")
    conn = atlas_store._get_conn()         # review F2: an account with no address
    conn.execute("INSERT INTO users (user_id, email, pw_hash, created_at, consent_at)"
                 " VALUES ('u_9f3a1c2e','x','h','2026-01-01','2026-01-01')")
    conn.commit()
    _queue("u_9f3a1c2e", "email", "k-n")

    def _leaky(*a, **k):
        raise RuntimeError(f"auth failed for {RESEND_SECRET} sending to {OWNER}")
    with caplog.at_level(logging.DEBUG):
        _drain_at(clock, 0)
        monkeypatch.setattr(settings, "EMAIL_TRANSPORT", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", RESEND_SECRET)
        monkeypatch.setattr(requests, "post", _leaky)
        _queue("u_a", "email", "k-r")
        _drain_at(clock, 1)
        report = outbox.outbox_report()
    stored = " ".join(str(r[0]) for r in atlas_store._get_conn().execute(
        "SELECT last_error FROM outbox").fetchall())
    for text in (caplog.text, stored, json.dumps(report)):
        for secret in ("a@example.invalid", OWNER, "tokSECRET", RESEND_SECRET,
                       SMTP_SECRET, VAPID_SECRET):
            assert secret not in text, (secret, text[:300])
    report_text = json.dumps(report)
    assert "PRIVATE-BODY-TEXT" not in report_text
    for uid in ("u_a", "u_9f3a1c2e"):      # the report carries no user id (F2)
        assert uid not in report_text and uid not in stored
    assert "permanent: no email on file for this account" in [
        d["reason"] for d in report["dead_letters"]]
    assert "<email>" in stored             # masked, not dropped: the reason still reads


# ---------------------------------------------------------------------------
# I6 — the report: acceptance is not receipt; dead letters are history
# ---------------------------------------------------------------------------

def test_report_separates_acceptance_from_receipt_and_keeps_history(env, clock, monkeypatch):
    relay = FakeRelay("ok", "auth_535")
    monkeypatch.setattr(channels.smtplib, "SMTP", relay.SMTP)
    _account("u_a", "a@example.invalid")
    conn = atlas_store._get_conn()
    conn.execute("INSERT INTO outbox (user_id, channel, kind, payload_ref, dedupe_key,"
                 " status, attempts, created_at, last_error) VALUES ('u_a','email',"
                 "'brief','{}','historic','dead',3,'2026-09-01T00:00:00+00:00',"
                 "'OSError: [Errno 101] Network is unreachable')")
    conn.commit()
    before = dict(conn.execute("SELECT * FROM outbox WHERE dedupe_key='historic'").fetchone())
    _queue("u_a", "email", "k-1")
    _queue("u_a", "email", "k-2")
    for minutes in (0, 1, 6, 36):
        _drain_at(clock, minutes)
    after = dict(conn.execute("SELECT * FROM outbox WHERE dedupe_key='historic'").fetchone())
    assert after == before                 # history is not re-queued or rewritten

    report = outbox.outbox_report()
    assert report["counts"] == {"email": {"accepted": 1, "dead": 2}}
    assert "delivered" not in json.dumps(report["counts"])
    assert report["user_receipt"].startswith("not observable")
    assert "not proof" in report["accepted_means"]
    reasons = [d["reason"] for d in report["dead_letters"]]
    assert reasons[0].startswith("permanent: SMTP login rejected")    # newest first
    assert reasons[1] == "OSError: [Errno 101] Network is unreachable"
    assert report["last_accepted"]["email"]["accepted_by"] == "smtp"


def test_outbox_route_is_owner_only(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import services.api.routes.delivery_api as dapi
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    monkeypatch.setenv("SCHEDULER_KEY", "sekret")
    app = FastAPI()
    app.include_router(dapi.router)
    c = TestClient(app)
    assert c.get("/delivery/outbox").status_code == 401
    ok = c.get("/delivery/outbox?limit=5", headers={"X-Scheduler-Key": "sekret"})
    assert ok.status_code == 200
    assert ok.json()["user_receipt"].startswith("not observable")


def test_existing_outbox_gains_the_new_columns_without_touching_rows(tmp_path, monkeypatch):
    """Production's table predates SA-006: the additive migration must add
    accepted_by/claimed_at and leave every existing row as it was."""
    db = tmp_path / "atlas.db"
    old = sqlite3.connect(db)
    old.execute("CREATE TABLE outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT"
                " NOT NULL, channel TEXT NOT NULL, kind TEXT NOT NULL, payload_ref TEXT"
                " NOT NULL, dedupe_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT"
                " 'queued', attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,"
                " next_attempt_at TEXT, delivered_at TEXT)")
    old.execute("INSERT INTO outbox (user_id, channel, kind, payload_ref, dedupe_key,"
                " status, attempts, created_at) VALUES ('u','email','brief','{}','old',"
                "'dead',3,'2026-09-01')")
    old.commit()
    old.close()
    monkeypatch.setattr(atlas_store, "_DB_PATH", db)
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    try:
        conn = atlas_store._get_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(outbox)")}
        assert {"last_error", "accepted_by", "claimed_at"} <= cols
        row = dict(conn.execute("SELECT * FROM outbox").fetchone())
        assert (row["dedupe_key"], row["status"], row["attempts"]) == ("old", "dead", 3)
    finally:
        atlas_store._reset_for_tests()
