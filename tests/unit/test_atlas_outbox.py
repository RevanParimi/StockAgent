"""Atlas C7 — BP2 durable outbox: in-process drainer, atomic claim, backoff.

The greenfield outbox (spec §7/§8, reviewer R3) replaces inline delivery
fan-out when ATLAS_ENABLED. `deliver()` enqueues per-channel rows; a drainer
running only inside the singleton-lock owner claims each row atomically
(`UPDATE ... status='sending' WHERE id=? AND status='queued'`, act only if
`rowcount==1`) so `--workers 2` can never double-send, then delivers with
backoff → dead-letter. Everything is a no-op when the flag is off.
"""
import json
import threading

import pytest

import core.delivery.outbox as outbox
import core.delivery.channels as channels
from core.delivery.channels import SendResult
import services.data.stores.atlas_store as atlas_store
from core.config import settings


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    yield tmp_path
    outbox.stop_outbox_drainer()
    atlas_store._reset_for_tests()


def _mk_user(uid="u_1"):
    conn = atlas_store._get_conn()
    conn.execute("INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
                 " consent_at) VALUES (?,?,?,?,?)",
                 (uid, f"{uid}@x.com", "h", "2026-01-01T00:00:00+00:00",
                  "2026-01-01T00:00:00+00:00"))
    conn.commit()


def _payload(title="T", body="B", url="/u"):
    return json.dumps({"title": title, "body": body, "url": url})


def _count(status=None):
    sql = "SELECT COUNT(*) FROM outbox" + (f" WHERE status='{status}'" if status else "")
    return atlas_store._get_conn().execute(sql).fetchone()[0]


# --- enqueue ----------------------------------------------------------------

def test_enqueue_idempotent_on_dedupe_key(env):
    _mk_user("u_1")
    first = outbox.enqueue("u_1", "push", "brief", _payload(), "u_1|brief|d1")
    second = outbox.enqueue("u_1", "push", "brief", _payload(), "u_1|brief|d1")
    assert first is not None
    assert second is None                 # duplicate dedupe_key -> no new row
    assert _count() == 1


def test_enqueue_is_flag_gated_noop(env, monkeypatch):
    _mk_user("u_1")
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    assert outbox.enqueue("u_1", "push", "brief", _payload(), "k") is None
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    assert _count() == 0


# --- drain: happy path + claim ---------------------------------------------

def test_drain_delivers_and_marks_delivered(env, monkeypatch):
    _mk_user("u_1")
    calls = []
    monkeypatch.setattr(channels, "send_push_result",
                        lambda *a, **k: (calls.append(a), SendResult(1, accepted_by="webpush 1/1 subscriptions"))[1])
    outbox.enqueue("u_1", "push", "brief", _payload(), "k1")
    result = outbox.drain_once()
    assert result["delivered"] == 1
    assert _count("delivered") == 1
    assert len(calls) == 1
    # a second drain finds no queued rows and never re-sends
    assert outbox.drain_once()["delivered"] == 0
    assert len(calls) == 1


def test_row_already_claimed_is_not_resent(env, monkeypatch):
    _mk_user("u_1")
    calls = []
    monkeypatch.setattr(channels, "send_push_result",
                        lambda *a, **k: (calls.append(a), SendResult(1))[1])
    outbox.enqueue("u_1", "push", "brief", _payload(), "k1")
    # simulate another drainer having claimed the row (status='sending')
    conn = atlas_store._get_conn()
    conn.execute("UPDATE outbox SET status='sending'")
    conn.commit()
    outbox.drain_once()
    assert calls == []                     # a claimed row is skipped, not re-sent


# --- backoff + dead-letter --------------------------------------------------

def test_backoff_then_dead_letter_after_max_attempts(env, monkeypatch):
    _mk_user("u_1")
    monkeypatch.setattr(outbox, "_max_attempts", lambda: 3)
    monkeypatch.setattr(outbox, "_backoff_minutes", lambda: [0, 0, 0])
    calls = []
    monkeypatch.setattr(channels, "send_push_result",
                        lambda *a, **k: (calls.append(a), SendResult(reason="transient: push service HTTP 503"))[1])   # always fails
    outbox.enqueue("u_1", "push", "brief", _payload(), "k1")
    for _ in range(3):
        outbox.drain_once()
    assert len(calls) == 3
    assert _count("dead") == 1
    assert _count("queued") == 0
    reason = atlas_store._get_conn().execute("SELECT last_error FROM outbox").fetchone()[0]
    assert reason == "retries exhausted (3/3): transient: push service HTTP 503"


# --- fan-out helper + deliver() choke point ---------------------------------

def test_enqueue_message_fans_to_enabled_channels(env, monkeypatch):
    _mk_user("u_1")
    monkeypatch.setattr(settings, "DELIVERY_PUSH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "DELIVERY_EMAIL_ENABLED", True, raising=False)
    n = outbox.enqueue_message("u_1", "Morning brief", "body text",
                               url="/#/inbox/brief", kind="brief")
    assert n == 2
    channels_seen = {r[0] for r in atlas_store._get_conn().execute(
        "SELECT channel FROM outbox").fetchall()}
    assert channels_seen == {"push", "email"}


def test_deliver_enqueues_when_enabled_else_inline(env, monkeypatch):
    _mk_user("u_1")
    monkeypatch.setattr(settings, "DELIVERY_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "DELIVERY_PUSH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "DELIVERY_EMAIL_ENABLED", False, raising=False)
    sent = []
    monkeypatch.setattr(channels, "send_push",
                        lambda *a, **k: (sent.append("push"), 1)[1])
    monkeypatch.setattr(channels, "send_email",
                        lambda *a, **k: (sent.append("email"), 0)[1])
    # flag ON -> enqueues, does NOT send inline
    channels.deliver("Morning brief", "b", url="/x", user_id="u_1", kind="brief")
    assert sent == []
    assert _count("queued") == 1
    # flag OFF -> inline send (both transports self-gate internally), no new rows
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    channels.deliver("Morning brief", "b", url="/x", user_id="u_1", kind="brief")
    assert "push" in sent                  # inline path was taken, not the outbox
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    assert _count() == 1


# --- drainer lifecycle (singleton-owner only) -------------------------------

def test_drainer_start_is_flag_gated(env, monkeypatch):
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    assert outbox.start_outbox_drainer() is None
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(outbox, "_poll_seconds", lambda: 0.05)
    t = outbox.start_outbox_drainer()
    try:
        assert isinstance(t, threading.Thread)
        assert t.is_alive()
    finally:
        outbox.stop_outbox_drainer()
        t.join(timeout=2)
    assert not t.is_alive()


# --- HTML carry-through (redesign 2026-07-30) -------------------------------

def test_enqueue_message_stores_full_body_and_html(monkeypatch):
    captured = {}

    def _fake_enqueue(user_id, channel, kind, payload_ref, dedupe_key):
        captured[channel] = payload_ref
        return 1

    monkeypatch.setattr(outbox, "enqueue", _fake_enqueue)
    monkeypatch.setattr(settings, "DELIVERY_PUSH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "DELIVERY_EMAIL_ENABLED", True, raising=False)

    long_body = "x" * 4000
    n = outbox.enqueue_message("u1", "Subj", long_body, kind="brief", html_body="<b>hi</b>")
    assert n == 2
    email_payload = json.loads(captured["email"])
    assert email_payload["html"] == "<b>hi</b>"
    assert len(email_payload["body"]) == 4000          # full body stored (no 1500 clip)


@pytest.fixture()
def account_u1(tmp_path, monkeypatch):
    """A real account row for u1 in a throwaway users.db (SA-005). The email
    rows resolve their recipient from it, as in production; the global
    DELIVERY_EMAIL_TO fallback is empty, so nothing depends on a developer's
    .env address."""
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(settings, "DELIVERY_EMAIL_TO", "")
    user_store.create_user("u1@example.invalid", "pw-for-tests", "U One", user_id="u1")
    yield "u1@example.invalid"
    user_store._conn_holder["conn"].close()


def test_send_row_without_an_account_or_fallback_is_refused(monkeypatch, account_u1):
    """The premise the next tests rely on: no account and no fallback address
    means no email is attempted."""
    sent = []
    monkeypatch.setattr(channels, "send_email_result",
                        lambda *a, **k: (sent.append(k), SendResult(1))[1])
    payload = json.dumps({"title": "t", "body": "b", "url": "/"})
    res = outbox._send_row({"id": 9, "user_id": "u_nobody", "channel": "email",
                            "payload_ref": payload, "dedupe_key": "k9"})
    assert (res.accepted, res.permanent, sent) == (False, True, [])
    assert res.reason == "permanent: no email on file for this account"
    assert "u_nobody" not in res.reason        # the owner report carries no user id


def test_send_row_caps_push_and_passes_html_to_email(monkeypatch, account_u1):
    calls = {}
    # SA-006: _send_row calls the *_result variants and returns a SendResult.
    monkeypatch.setattr(channels, "send_push_result",
                        lambda title, body, url="/", user_id=None, store=None:
                        (calls.__setitem__("push", body), SendResult(1))[1])
    monkeypatch.setattr(channels, "send_email_result",
                        lambda title, body, html_body=None, to=None, idempotency_key=None:
                        (calls.__setitem__("email", (len(body), html_body, to, idempotency_key)),
                         SendResult(1))[1])

    payload = json.dumps({"title": "t", "body": "y" * 4000, "url": "/", "html": "<i>h</i>"})
    assert outbox._send_row({"id": 1, "user_id": "u1", "channel": "push",
                             "payload_ref": payload, "dedupe_key": "k1"}).accepted
    assert len(calls["push"]) == 1500                   # push capped at send time
    assert outbox._send_row({"id": 2, "user_id": "u1", "channel": "email",
                             "payload_ref": payload, "dedupe_key": "k2"}).accepted
    # full body + html, to the account, with the row's provider idempotency key
    assert calls["email"] == (4000, "<i>h</i>", account_u1, outbox.idempotency_key("k2"))


def test_send_row_returns_transport_reason(monkeypatch, account_u1):
    """The reason travels back so drain_once can persist it (SA-006)."""
    monkeypatch.setattr(channels, "send_email_result",
                        lambda title, body, html_body=None, to=None, idempotency_key=None:
                        SendResult(reason="transient: OSError: [Errno 101] Network is unreachable"))
    payload = json.dumps({"title": "t", "body": "b", "url": "/"})
    res = outbox._send_row({"id": 3, "user_id": "u1", "channel": "email",
                            "payload_ref": payload, "dedupe_key": "k3"})
    assert (res.accepted, res.permanent) == (False, False)
    assert "Errno 101" in res.reason
