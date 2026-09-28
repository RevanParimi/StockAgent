"""Compass Phase C — M4 channels: push store, email, push fan-out (spec §7)."""
import core.delivery.channels as ch
from core.delivery.channels import PushStore, deliver, send_email, send_push

_SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
_SUB2 = {"endpoint": "https://push.example/def", "keys": {"p256dh": "k", "auth": "a"}}


def test_push_store_add_dedupe_remove(tmp_path):
    store = PushStore(path=str(tmp_path / "subs.json"))
    assert store.add(_SUB) == 1
    assert store.add(_SUB) == 1                     # same endpoint deduped
    assert store.add(_SUB2) == 2
    assert len(store.list()) == 2
    assert store.remove(_SUB["endpoint"]) is True
    assert store.remove("https://push.example/nope") is False
    assert [s["endpoint"] for s in store.list()] == [_SUB2["endpoint"]]


def test_send_email_disabled_returns_false(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", False)
    assert send_email("s", "b") is False


def test_send_email_smtp_flow(monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent["tls"] = True
        def login(self, user, pwd):
            sent["login"] = user
        def sendmail(self, frm, to, msg):
            sent["to"], sent["msg"] = to, msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "smtp")   # pin: "auto" follows RESEND_API_KEY
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "u@example.com")
    monkeypatch.setattr(ch.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "https://app.example")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)
    assert send_email("Subject", "Body") is True
    assert sent["to"] == ["me@example.com"] and sent["tls"] and sent["login"] == "u@example.com"
    # AUD: every email carries a footer link back to the app (payload is
    # base64-encoded in the MIME message, so decode before asserting).
    import email as _email
    decoded = _email.message_from_string(sent["msg"]).get_payload(decode=True).decode("utf-8")
    assert "https://app.example/" in decoded


def test_with_app_link_appends_once_and_respects_unset(monkeypatch):
    # monkeypatch, not assignment: the assignments below used to outlive the
    # test, and a later email test passed only because of it (SA-005).
    # Appends when set…
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "https://app.example")
    body = ch._with_app_link("hello")
    assert body.endswith("Open StockAgent → https://app.example/")
    # …idempotent — a body that already has the link is unchanged.
    assert ch._with_app_link(body) == body
    # …and a no-op when APP_PUBLIC_URL is empty.
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "")
    assert ch._with_app_link("hello") == "hello"


def test_send_push_fans_out_and_prunes_expired(tmp_path, monkeypatch):
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add(_SUB)
    store.add(_SUB2)
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")

    class _Resp:
        status_code = 410

    class _Gone(Exception):
        def __init__(self):
            self.response = _Resp()

    calls = []

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, **kw):
        calls.append((subscription_info["endpoint"], kw))
        if subscription_info["endpoint"] == _SUB["endpoint"]:
            raise _Gone()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    monkeypatch.setattr(ch, "WebPushException", _Gone)
    sent = send_push("t", "b", store=store)
    assert sent == 1 and len(calls) == 2
    assert [s["endpoint"] for s in store.list()] == [_SUB2["endpoint"]]  # 410 pruned
    # SA-006: a bounded request, and a TTL so an offline phone still gets it
    # (pywebpush's defaults are no timeout and ttl=0, "deliver now or drop").
    assert all(kw["timeout"] == 20 and kw["ttl"] == 43200 for _, kw in calls)


def test_send_push_without_vapid_key_is_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "")
    assert send_push("t", "b", store=PushStore(path=str(tmp_path / "s.json"))) == 0


def test_deliver_gated_and_never_raises(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", False)
    assert deliver("t", "b") == {"delivered": False, "reason": "delivery_disabled"}
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    monkeypatch.setattr(ch, "send_push", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(ch, "send_email", lambda *a, **k: False)
    out = deliver("t", "b")
    assert out["delivered"] is False and out["push"] == 0


def test_send_push_prunes_dead_subscription_on_400(tmp_path, monkeypatch):
    """AUD-085 rider: the prod stale sub fails 400 (malformed/VAPID-mismatch)
    on EVERY send and was never pruned — 400/403 are permanent, like 404/410."""
    store = PushStore(path=str(tmp_path / "subs.json"))
    store.add(_SUB)
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")

    class _Resp:
        status_code = 400

    class _Bad(Exception):
        def __init__(self):
            self.response = _Resp()

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, **kw):
        raise _Bad()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    assert send_push("t", "b", store=store) == 0
    assert store.list() == []                       # 400 pruned
    # every subscription gone: nothing a retry could reach (SA-006)
    store.add(_SUB)
    res = ch.send_push_result("t", "b", store=store)
    assert (res.accepted, res.permanent) == (False, True)
    assert "pruned dead subscription (400)" in res.reason


def test_send_push_zero_subscriptions_warns(tmp_path, monkeypatch, caplog):
    """AUD-090c: push enabled + no subscription = notification silently dropped."""
    import logging
    store = PushStore(path=str(tmp_path / "subs.json"))
    monkeypatch.setattr(ch.settings, "DELIVERY_PUSH_ENABLED", True)
    monkeypatch.setattr(ch.settings, "VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setattr(ch, "webpush", lambda **kw: None)
    with caplog.at_level(logging.WARNING, logger="core.delivery.channels"):
        assert send_push("t", "b", store=store) == 0
    assert any("0 subscriptions" in r.message for r in caplog.records)


def test_deliver_warns_when_nothing_delivered(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    # The inline path: Atlas OFF, stated (config.yaml ships it on; SA-005).
    monkeypatch.setenv("ATLAS_ENABLED", "false")
    monkeypatch.setattr(ch, "send_push", lambda *a, **k: 0)
    monkeypatch.setattr(ch, "send_email", lambda *a, **k: False)
    with caplog.at_level(logging.WARNING, logger="core.delivery.channels"):
        out = deliver("Morning brief", "body")
    assert out["delivered"] is False
    assert any("NOWHERE" in r.message for r in caplog.records)


# -- Task 5: send_email multipart/alternative with optional HTML (2026-07-30) --

def test_send_email_multipart_alternative_when_html(monkeypatch):
    import email as _email
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def sendmail(self, frm, to, msg): sent["msg"] = msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "smtp")   # pin: "auto" follows RESEND_API_KEY
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "u@example.com")
    monkeypatch.setattr(ch.settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)

    assert send_email("Subj", "plain body", html_body="<b>hi</b>") is True
    parsed = _email.message_from_string(sent["msg"])
    assert parsed.get_content_type() == "multipart/alternative"
    kinds = [p.get_content_type() for p in parsed.walk()]
    assert "text/plain" in kinds and "text/html" in kinds
    # HTML must be the LAST leaf part (preferred by clients).
    leaves = [p.get_content_type() for p in parsed.walk() if not p.is_multipart()]
    assert leaves[-1] == "text/html"


def test_send_email_html_none_is_single_part(monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def sendmail(self, frm, to, msg): sent["msg"] = msg

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "smtp")   # pin: "auto" follows RESEND_API_KEY
    monkeypatch.setattr(ch.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ch.settings, "SMTP_USER", "")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "")
    monkeypatch.setattr(ch.smtplib, "SMTP", _FakeSMTP)
    assert send_email("Subj", "plain body") is True
    assert "multipart" not in sent["msg"].lower()


# -- Task 6: deliver threads html to email, never to push (2026-07-30) --

def test_deliver_passes_html_to_email_not_push(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    seen = {}

    def _fake_push(title, body, **k):
        seen["push"] = (body, k)
        return 0

    def _fake_email(title, body, html_body=None, to=None):
        seen["email"] = (body, html_body)
        return 1

    monkeypatch.setattr(ch, "send_push", _fake_push)
    monkeypatch.setattr(ch, "send_email", _fake_email)
    # force inline path (Atlas off)
    import services.data.stores.atlas_store as a
    monkeypatch.setattr(a, "enabled", lambda: False)
    out = deliver("t", "plain", html_body="<b>h</b>", kind="brief")
    assert out["email"] == 1
    assert seen["email"] == ("plain", "<b>h</b>")     # html reached email
    assert "html_body" not in seen["push"][1]         # push never got html


# ---------------------------------------------------------------------------
# D6 / SA-006 — HTTPS (Resend) transport + failure reasons
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, text='{"id":"abc"}', headers=None):
        self.status_code, self.text = status_code, text
        self.headers = headers or {}

    def json(self):
        import json as _json
        return _json.loads(self.text)


def _enable_resend(monkeypatch):
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "resend")
    monkeypatch.setattr(ch.settings, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(ch.settings, "RESEND_FROM", "StockAgent <x@resend.dev>")
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(ch.settings, "APP_PUBLIC_URL", "https://app.example")


def test_resend_transport_posts_and_succeeds(monkeypatch):
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen["url"], seen["headers"], seen["json"] = url, headers, json
        return _FakeResp()

    import requests
    monkeypatch.setattr(requests, "post", _post)
    _enable_resend(monkeypatch)

    res = ch.send_email_result("Subject", "Body", idempotency_key="k-1")
    assert (res.accepted, res.reason) == (True, "")
    assert res.accepted_by == "resend id=abc"          # the provider's id, for lookup
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test_key"
    assert seen["headers"]["Idempotency-Key"] == "k-1"
    assert seen["json"]["to"] == ["me@example.com"]
    # the app-link footer applies on this transport too
    assert "https://app.example/" in seen["json"]["text"]


def test_resend_http_error_returns_reason(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _FakeResp(422, '{"message":"domain not verified"}'))
    _enable_resend(monkeypatch)

    res = ch.send_email_result("s", "b")
    assert res.accepted is False
    assert "422" in res.reason and "domain not verified" in res.reason
    assert res.permanent is True                        # a retry repeats the same request


def test_resend_network_error_returns_reason(monkeypatch):
    def _boom(*a, **k):
        raise OSError("[Errno 101] Network is unreachable")

    import requests
    monkeypatch.setattr(requests, "post", _boom)
    _enable_resend(monkeypatch)

    res = ch.send_email_result("s", "b")
    assert res.accepted is False
    assert "Errno 101" in res.reason
    assert res.permanent is False                       # the network: retry


def test_resend_attachment_is_base64(monkeypatch, tmp_path):
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen["json"] = json
        return _FakeResp()

    import base64 as _b64
    import requests
    monkeypatch.setattr(requests, "post", _post)
    _enable_resend(monkeypatch)

    f = tmp_path / "backup.zip"
    f.write_bytes(b"PK\x03\x04payload")
    assert ch.send_email_result("s", "b", attachments=[f]).accepted is True
    att = seen["json"]["attachments"][0]
    assert att["filename"] == "backup.zip"
    assert _b64.b64decode(att["content"]) == b"PK\x03\x04payload"


def test_resend_unreadable_attachment_fails_closed_without_a_request(monkeypatch, tmp_path):
    posts = []
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: posts.append(a) or _FakeResp())
    _enable_resend(monkeypatch)
    res = ch.send_email_result("s", "b", attachments=[tmp_path / "missing.zip"])
    assert (res.accepted, res.permanent, posts) == (False, True, [])
    assert res.reason.startswith("permanent: attachment unreadable")


def test_resend_missing_key_reports_unconfigured(monkeypatch):
    _enable_resend(monkeypatch)
    monkeypatch.setattr(ch.settings, "RESEND_API_KEY", "")
    res = ch.send_email_result("s", "b")
    assert (res.reason, res.permanent) == ("unconfigured: RESEND_API_KEY is unset", True)


def test_disabled_and_unconfigured_reasons_are_distinct(monkeypatch):
    """The old code returned a bare False for all of these, so a dead letter
    could not say whether email was off or the network was blocked. All are
    permanent: a retry cannot change a setting (SA-006)."""
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", False)
    res = ch.send_email_result("s", "b")
    assert (res.reason, res.permanent) == ("disabled: DELIVERY_EMAIL_ENABLED is false", True)

    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "")
    assert ch.send_email_result("s", "b").reason.startswith("unconfigured: no recipient")
    # …and an explicit per-account address satisfies the same gate.
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "resend")
    monkeypatch.setattr(ch.settings, "RESEND_API_KEY", "")
    assert ch.send_email_result("s", "b", to="beta@example.com").reason == (
        "unconfigured: RESEND_API_KEY is unset")


def test_auto_transport_follows_api_key(monkeypatch):
    monkeypatch.setattr(ch.settings, "EMAIL_TRANSPORT", "auto")
    monkeypatch.setattr(ch.settings, "RESEND_API_KEY", "re_key")
    assert ch._resolve_transport() == "resend"
    monkeypatch.setattr(ch.settings, "RESEND_API_KEY", "")
    assert ch._resolve_transport() == "smtp"


# ---------------------------------------------------------------------------
# Multi-user beta — per-account recipients (SA-006 recipient isolation)
# ---------------------------------------------------------------------------

def test_resolve_recipient_prefers_the_account_email(monkeypatch):
    import services.data.stores.user_store as us
    monkeypatch.setattr(us, "get_user",
                        lambda uid: {"user_id": uid, "email": "beta@example.com"})
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "owner@example.com")
    assert ch.resolve_recipient("u_42").address == "beta@example.com"


def test_resolve_recipient_never_falls_back_for_a_real_account(monkeypatch):
    """The 590bc9f defect: a failed users.db lookup fell back to
    DELIVERY_EMAIL_TO, so a beta tester's brief could reach the owner."""
    import services.data.stores.user_store as us
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "owner@example.com")

    def _boom(uid):
        raise RuntimeError("users.db locked")
    monkeypatch.setattr(us, "get_user", _boom)
    r = ch.resolve_recipient("u_42")
    assert r.address == ""                              # not the owner
    assert r.permanent is False and "will retry" in r.reason
    # an account with no row / no address: permanent, still no fallback
    monkeypatch.setattr(us, "get_user", lambda uid: None)
    r = ch.resolve_recipient("u_42")
    assert (r.address, r.permanent) == ("", True)
    assert r.reason == "permanent: no email on file for this account"   # no user id


def test_resolve_recipient_single_user_path_keeps_the_fallback(monkeypatch):
    import services.data.stores.user_store as us
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "owner@example.com")
    monkeypatch.setattr(us, "get_user", lambda uid: None)
    # no user id, or the default portfolio id (not a real account): the owner
    assert ch.resolve_recipient(None).address == "owner@example.com"
    assert ch.resolve_recipient(ch.settings.PORTFOLIO_DEFAULT_USER_ID).address == (
        "owner@example.com")

    def _boom(uid):
        raise RuntimeError("users.db locked")
    monkeypatch.setattr(us, "get_user", _boom)
    assert ch.resolve_recipient(ch.settings.PORTFOLIO_DEFAULT_USER_ID).address == (
        "owner@example.com")


def test_resend_sends_to_the_account_address(monkeypatch):
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen["json"] = json
        return _FakeResp()

    import requests
    monkeypatch.setattr(requests, "post", _post)
    _enable_resend(monkeypatch)
    assert ch.send_email_result("s", "b", to="beta@example.com").accepted is True
    # the per-message recipient wins over the global DELIVERY_EMAIL_TO
    assert seen["json"]["to"] == ["beta@example.com"]


def test_inline_deliver_mails_the_account_not_the_owner(monkeypatch):
    """The inline path (Atlas off, or the outbox unreachable) used to call
    send_email with no recipient, i.e. DELIVERY_EMAIL_TO, for every user."""
    import services.data.stores.atlas_store as a
    import services.data.stores.user_store as us
    monkeypatch.setattr(a, "enabled", lambda: False)
    monkeypatch.setattr(ch.settings, "DELIVERY_ENABLED", True)
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_ENABLED", True)
    monkeypatch.setattr(ch.settings, "DELIVERY_EMAIL_TO", "owner@example.com")
    monkeypatch.setattr(ch, "send_push", lambda *a, **k: 0)
    to_seen = []
    monkeypatch.setattr(ch, "send_email",
                        lambda title, body, html_body=None, to=None: to_seen.append(to) or True)
    monkeypatch.setattr(us, "get_user",
                        lambda uid: {"email": "beta@example.com"} if uid == "u_b" else None)
    deliver("t", "b", user_id="u_b")
    deliver("t", "b", user_id="u_gone")                  # no account: skipped
    assert to_seen == ["beta@example.com"]
