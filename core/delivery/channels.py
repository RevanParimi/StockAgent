"""
Compass Phase C — delivery channels (spec §7).

web-push: pywebpush + VAPID keys (env secrets); subscriptions persisted in
data/delivery/push_subscriptions.json per user. Dead subscriptions
(400/403/404/410) are pruned on send. The PWA service worker displays the payload;
the TWA Android app gets it free.

email: two transports behind one entry point (`send_email` / `send_email_result`).
  - resend: HTTPS POST to the Resend API. Required on Railway Free/Trial/Hobby,
    where outbound SMTP is disabled at the platform — every send fails with
    `[Errno 101] Network is unreachable` (D6; production since 2026-07-16).
  - smtp:   stdlib smtplib STARTTLS — the original path, kept for local runs
    and for any host that permits outbound 587.
`settings.EMAIL_TRANSPORT` selects; "auto" uses resend when an API key is set.

EVERY send is non-fatal. deliver() is the only entry point callers need.
"""
from __future__ import annotations

import base64
import json
import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

try:                                     # module-level so tests can monkeypatch
    from pywebpush import WebPushException, webpush
except ImportError:                      # pragma: no cover — dep is in requirements
    webpush = None
    WebPushException = Exception


class PushStore:
    """data/delivery/push_subscriptions.json — {user_id: [subscription, ...]}"""

    def __init__(self, path: str | None = None) -> None:
        if path:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            base = Path(settings.DELIVERY_DATA_DIR)
            base.mkdir(parents=True, exist_ok=True)
            self._path = base / "push_subscriptions.json"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[delivery] push store unreadable %s: %s", self._path, exc)
            return {}

    def _save(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def add(self, subscription: dict, user_id: str | None = None) -> int:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        data = self._load()
        subs = data.setdefault(uid, [])
        endpoint = subscription.get("endpoint", "")
        if endpoint and not any(s.get("endpoint") == endpoint for s in subs):
            subs.append(subscription)
            self._save(data)
        return len(subs)

    def remove(self, endpoint: str, user_id: str | None = None) -> bool:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        data = self._load()
        subs = data.get(uid, [])
        kept = [s for s in subs if s.get("endpoint") != endpoint]
        if len(kept) == len(subs):
            return False
        data[uid] = kept
        self._save(data)
        return True

    def list(self, user_id: str | None = None) -> list[dict]:
        uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
        return list(self._load().get(uid, []))

    def user_ids(self) -> list[str]:
        """All user_ids with at least one stored subscription (AUD-015)."""
        return sorted(uid for uid, subs in self._load().items() if subs)


def _with_app_link(body: str) -> str:
    """Append a footer that links back to the app, so every notification email
    is one tap from opening it. No-op when APP_PUBLIC_URL is unset or the link
    is already present (idempotent)."""
    url = (getattr(settings, "APP_PUBLIC_URL", "") or "").rstrip("/")
    if not url or url in body:
        return body
    return f"{body.rstrip()}\n\n----------\nOpen StockAgent → {url}/"


def resolve_recipient(user_id: str | None) -> str:
    """The email address that owns `user_id`, else the single-user fallback.

    Multi-user (beta): every account row in `users` carries its own address, so
    a scheduled message must reach the account that owns the outbox row rather
    than one global inbox. `DELIVERY_EMAIL_TO` stays the fallback for the
    single-user/dev setup and for rows whose user cannot be resolved (e.g. the
    default portfolio id, which is not a real account). Never raises."""
    if user_id:
        try:
            from services.data.stores import user_store
            user = user_store.get_user(user_id)
            if user and user.get("email"):
                return str(user["email"])
        except Exception as exc:
            logger.warning("[delivery] could not resolve an email for user '%s' "
                           "(non-fatal, using fallback): %s", user_id, exc)
    return getattr(settings, "DELIVERY_EMAIL_TO", "") or ""


def _resolve_transport() -> str:
    """Which email transport to use: 'resend' | 'smtp'.

    "auto" prefers resend whenever a key is present, so setting RESEND_API_KEY
    in Railway is the entire cutover — no code or config edit needed."""
    choice = (getattr(settings, "EMAIL_TRANSPORT", "auto") or "auto").strip().lower()
    if choice in ("resend", "smtp"):
        return choice
    return "resend" if getattr(settings, "RESEND_API_KEY", "") else "smtp"


def _send_via_resend(subject: str, body: str, attachments: list[Path] | None,
                     html_body: str | None, recipient: str) -> tuple[bool, str]:
    """POST one message to the Resend API over HTTPS. Never raises.

    Returns `(delivered, reason)`. A 2xx means Resend ACCEPTED the message for
    delivery — it is not proof the recipient's mailbox received it, so callers
    must not report it as confirmed receipt."""
    import requests

    payload: dict = {
        "from": settings.RESEND_FROM,
        "to": [recipient],
        "subject": subject,
        "text": _with_app_link(body),
    }
    if html_body:
        payload["html"] = html_body
    if attachments:
        try:
            payload["attachments"] = [
                {"filename": Path(p).name,
                 "content": base64.b64encode(Path(p).read_bytes()).decode("ascii")}
                for p in attachments
            ]
        except Exception as exc:          # fail closed, same as the SMTP path
            return False, f"attachment unreadable: {type(exc).__name__}: {exc}"[:500]
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload, timeout=20)
    except Exception as exc:
        logger.warning("[delivery] resend request failed (non-fatal): %s", exc)
        return False, f"{type(exc).__name__}: {exc}"[:500]
    if 200 <= resp.status_code < 300:
        return True, ""
    # Body is the provider's error JSON — no recipient data, safe to persist.
    detail = (resp.text or "").strip().replace("\n", " ")[:300]
    logger.warning("[delivery] resend rejected the message: HTTP %s %s",
                   resp.status_code, detail)
    return False, f"resend HTTP {resp.status_code}: {detail}"[:500]


def send_email_result(subject: str, body: str, attachments: list[Path] | None = None,
                      html_body: str | None = None,
                      to: str | None = None) -> tuple[bool, str]:
    """`send_email` plus the reason it failed (SA-006). Never raises.

    `to` is the recipient for THIS message — the outbox passes the address of
    the account that owns the row, so multi-user beta mail reaches each account
    rather than one global inbox. It falls back to `DELIVERY_EMAIL_TO`.

    Returns `(delivered, reason)`; `reason` is "" on success. The
    disabled/unconfigured gates report DISTINCT reasons on purpose: previously
    they all returned a bare False with no log line at all, so a dead-lettered
    row was indistinguishable from a blocked one. The reason is persisted to
    `outbox.last_error`, which is what makes a dead letter self-explaining
    without the ephemeral container log. It carries no recipient or payload."""
    if not settings.DELIVERY_EMAIL_ENABLED:
        return False, "disabled: DELIVERY_EMAIL_ENABLED is false"
    recipient = (to or getattr(settings, "DELIVERY_EMAIL_TO", "") or "").strip()
    if not recipient:
        return False, "unconfigured: no recipient (account email and DELIVERY_EMAIL_TO both unset)"
    if _resolve_transport() == "resend":
        if not settings.RESEND_API_KEY:
            return False, "unconfigured: RESEND_API_KEY is unset"
        return _send_via_resend(subject, body, attachments, html_body, recipient)
    if not settings.SMTP_HOST:
        return False, "unconfigured: SMTP_HOST is unset"
    body = _with_app_link(body)
    try:
        alt: MIMEText | MIMEMultipart
        if html_body:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain", "utf-8"))
            alt.attach(MIMEText(html_body, "html", "utf-8"))   # last = preferred
        else:
            alt = MIMEText(body, "plain", "utf-8")
        if attachments:
            msg: MIMEText | MIMEMultipart = MIMEMultipart("mixed")
            msg.attach(alt)
            for path in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(Path(path).read_bytes())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{Path(path).name}"')
                msg.attach(part)
        else:
            msg = alt
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER or "stockagent@localhost"
        msg["To"] = recipient
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(msg["From"], [recipient], msg.as_string())
        return True, ""
    except Exception as exc:
        logger.warning("[delivery] email send failed (non-fatal): %s", exc)
        return False, f"{type(exc).__name__}: {exc}"[:500]


def send_email(subject: str, body: str, attachments: list[Path] | None = None,
               html_body: str | None = None, to: str | None = None) -> bool:
    """Email send to `to`, defaulting to DELIVERY_EMAIL_TO. False when disabled/unconfigured
    or on any failure — never raises. `attachments` (AUD-088): file paths to
    attach; the whole send fails closed if any is unreadable. `html_body`
    (2026-07-30): when set, the message is multipart/alternative — plain `body`
    first, HTML last (clients prefer the last part).

    Thin wrapper over `send_email_result` — use that when you need the reason."""
    return send_email_result(subject, body, attachments, html_body, to=to)[0]


def send_push_result(
    title: str,
    body: str,
    url: str = "/",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> tuple[int, str]:
    """`send_push` plus the reason nothing was delivered (SA-006). Never raises.

    Returns `(sent, reason)`; `reason` is "" whenever `sent > 0`. Endpoints are
    never included — only the failure class — so `outbox.last_error` stays free
    of recipient data."""
    if not settings.DELIVERY_PUSH_ENABLED:
        return 0, "disabled: DELIVERY_PUSH_ENABLED is false"
    if not settings.VAPID_PRIVATE_KEY:
        return 0, "unconfigured: VAPID_PRIVATE_KEY is unset"
    if webpush is None:
        return 0, "unavailable: pywebpush is not installed"
    store = store or PushStore()
    subs = store.list(user_id)
    if not subs:
        # AUD-090c: enabled-but-no-recipients is the silent-drop signature.
        logger.warning(
            "[delivery] push enabled but 0 subscriptions registered for user "
            "'%s' — notification dropped (enable alerts in the PWA)",
            user_id or settings.PORTFOLIO_DEFAULT_USER_ID)
        return 0, "no push subscriptions registered (enable alerts in the PWA)"
    payload = json.dumps({"title": title, "body": body[:1500], "url": url})
    sent = 0
    failures: list[str] = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"},
            )
            sent += 1
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (400, 403, 404, 410):
                # 404/410 = expired; 400/403 = malformed sub or VAPID-key
                # mismatch (AUD-085 prod stale sub) — all permanent, prune.
                store.remove(sub.get("endpoint", ""), user_id)
                logger.info("[delivery] pruned dead push subscription (%s)", code)
                failures.append(f"pruned dead subscription ({code})")
            else:
                logger.warning("[delivery] push send failed (non-fatal): %s", exc)
                failures.append(f"{type(exc).__name__}: {exc}")
    if sent:
        return sent, ""
    return 0, ("; ".join(failures) or "no subscription accepted the push")[:500]


def send_push(
    title: str,
    body: str,
    url: str = "/",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> int:
    """Fan one notification out to every stored subscription. Returns the
    number delivered; prunes expired (404/410) subscriptions. Never raises.

    Thin wrapper over `send_push_result` — use that when you need the reason."""
    return send_push_result(title, body, url=url, user_id=user_id, store=store)[0]


def deliver(
    title: str, body: str, url: str = "/", user_id: str | None = None,
    kind: str = "alert", html_body: str | None = None,
) -> dict:
    """Fan one message out to all configured channels. Never raises.

    Atlas C7 (BP2): when the relational plane is on, hand the message to the
    durable outbox (per-channel rows, atomic-claim drainer) instead of sending
    inline — `delivered=True` then means *accepted for delivery*; the outbox
    owns retry/dead-letter. `kind` (brief|digest|weekly|alert) tags the queued
    rows. The dormant path (flag off) below is byte-for-byte today's behaviour.
    """
    if not settings.DELIVERY_ENABLED:
        return {"delivered": False, "reason": "delivery_disabled"}
    try:
        from services.data.stores import atlas_store
        if atlas_store.enabled():
            from core.delivery.outbox import enqueue_message
            uid = user_id or settings.PORTFOLIO_DEFAULT_USER_ID
            queued = enqueue_message(uid, title, body, url=url, kind=kind, html_body=html_body)
            if queued:
                logger.info("[delivery] %s — queued to outbox (%d row(s))", title, queued)
            return {"delivered": bool(queued), "queued": queued, "push": 0, "email": 0}
    except Exception as exc:
        logger.warning("[delivery] outbox enqueue failed, falling back to inline "
                       "(non-fatal): %s", exc)
    pushed = emailed = 0
    try:
        pushed = send_push(title, body, url=url, user_id=user_id)
    except Exception as exc:
        logger.warning("[delivery] push channel failed (non-fatal): %s", exc)
    try:
        emailed = int(send_email(title, body, html_body=html_body))
    except Exception as exc:
        logger.warning("[delivery] email channel failed (non-fatal): %s", exc)
    if pushed or emailed:
        logger.info("[delivery] %s — push=%d email=%d", title, pushed, emailed)
    else:
        logger.warning(
            "[delivery] %s — landed NOWHERE (push=0 email=0): no push "
            "subscriptions and email disabled/unconfigured (AUD-085)", title)
    return {"delivered": bool(pushed or emailed), "push": pushed, "email": emailed}
