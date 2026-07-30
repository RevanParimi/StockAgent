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


def test_with_app_link_appends_once_and_respects_unset():
    # Appends when set…
    ch.settings.APP_PUBLIC_URL = "https://app.example"
    body = ch._with_app_link("hello")
    assert body.endswith("Open StockAgent → https://app.example/")
    # …idempotent — a body that already has the link is unchanged.
    assert ch._with_app_link(body) == body
    # …and a no-op when APP_PUBLIC_URL is empty.
    ch.settings.APP_PUBLIC_URL = ""
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

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        calls.append(subscription_info["endpoint"])
        if subscription_info["endpoint"] == _SUB["endpoint"]:
            raise _Gone()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    monkeypatch.setattr(ch, "WebPushException", _Gone)
    sent = send_push("t", "b", store=store)
    assert sent == 1 and len(calls) == 2
    assert [s["endpoint"] for s in store.list()] == [_SUB2["endpoint"]]  # 410 pruned


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

    def _fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        raise _Bad()

    monkeypatch.setattr(ch, "webpush", _fake_webpush)
    assert send_push("t", "b", store=store) == 0
    assert store.list() == []                       # 400 pruned


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
    seen = {}

    def _fake_push(title, body, **k):
        seen["push"] = (body, k)
        return 0

    def _fake_email(title, body, html_body=None):
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
