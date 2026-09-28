"""
Compass Phase C — delivery channels (spec §7).

web-push: pywebpush + VAPID keys (env secrets); subscriptions persisted in
data/delivery/push_subscriptions.json per user. Dead subscriptions
(400/403/404/410) are pruned on send. The PWA service worker displays the payload;
the TWA Android app gets it free.

email: two transports behind one entry point (`send_email` / `send_email_result`).
  - smtp:   stdlib smtplib STARTTLS. Works on Railway Pro (upgraded and
    redeployed 2026-09-21). On Free/Trial/Hobby the platform blocks outbound
    SMTP and every send fails with `[Errno 101] Network is unreachable` (D6).
  - resend: HTTPS POST to the Resend API — the supported path on a host that
    blocks SMTP.
`settings.EMAIL_TRANSPORT` selects; "auto" uses resend when an API key is set.

SA-006 contract. Every transport returns a `SendResult`:
  - `accepted` is the transport's ACCEPTANCE (SMTP 250, HTTP 2xx, push service
    201). No transport here reports that a person received or saw the message,
    so nothing may call an accepted message "received";
  - `permanent` means a retry cannot help (auth, configuration, a disabled
    channel, a rejected recipient) or cannot be made safely (an outcome we do
    not know, where a retry could duplicate the message);
  - `reason` is redacted (`redact`): no address, push endpoint or secret.

EVERY send is non-fatal. deliver() is the only entry point callers need.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import NamedTuple

from backend.shared.config.settings.loader import cfg
from core.config import settings
from core.utils.atomic_io import replace_with_retry

logger = logging.getLogger(__name__)

try:                                     # module-level so tests can monkeypatch
    from pywebpush import WebPushException, webpush
except ImportError:                      # pragma: no cover — dep is in requirements
    webpush = None
    WebPushException = Exception

_SEND_TIMEOUT_S = 20                     # per network operation, every transport


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
        replace_with_retry(tmp, self._path)

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


# ---------------------------------------------------------------------------
# SA-006 — the send contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SendResult:
    """One send attempt's outcome. See the module docstring for the contract.

    `accepted_count` is how many recipients' transports accepted it (1 for
    email; accepting push subscriptions for push). `accepted_by` names the
    transport, the provider's message id when it returns one, or the push
    fan-out ("webpush 2/3 subscriptions"). `retry_after_s` is the provider's
    requested wait (HTTP 429/5xx `Retry-After`), else None."""
    accepted_count: int = 0
    reason: str = ""
    permanent: bool = False
    retry_after_s: float | None = None
    accepted_by: str = ""

    @property
    def accepted(self) -> bool:
        return self.accepted_count > 0


def _refuse(reason: str) -> SendResult:
    """A send that stops here and must not be retried."""
    return SendResult(reason=reason, permanent=True)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_PATH_RE = re.compile(r"(https?://[^/\s'\"]+)/[^\s'\"]*")
_URL_FIELD_RE = re.compile(r"(url: )\S+")


def redact(text: object) -> str:
    """Mask what must not reach a log line or `outbox.last_error`: configured
    secrets, email addresses and URL paths (a push endpoint's path is a bearer
    capability). Hosts and status codes stay — they are what a diagnosis
    needs. Capped at 500 characters."""
    out = str(text)
    for name in ("RESEND_API_KEY", "SMTP_PASSWORD", "VAPID_PRIVATE_KEY"):
        secret = getattr(settings, name, "") or ""
        if len(secret) >= 6:
            out = out.replace(secret, "<secret>")
    out = _EMAIL_RE.sub("<email>", out)
    out = _URL_PATH_RE.sub(r"\1/<redacted>", out)
    out = _URL_FIELD_RE.sub(r"\1<redacted>", out)
    return out.replace("\n", " ")[:500]


def _retry_after_s(resp) -> float | None:
    """Seconds from an HTTP `Retry-After` header (delta-seconds or HTTP-date).
    None when absent or unparseable."""
    headers = getattr(resp, "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(str(raw))
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _with_app_link(body: str) -> str:
    """Append a footer that links back to the app, so every notification email
    is one tap from opening it. No-op when APP_PUBLIC_URL is unset or the link
    is already present (idempotent)."""
    url = (getattr(settings, "APP_PUBLIC_URL", "") or "").rstrip("/")
    if not url or url in body:
        return body
    return f"{body.rstrip()}\n\n----------\nOpen StockAgent → {url}/"


class Recipient(NamedTuple):
    """Where an account's email goes. `address` "" means do not send; then
    `reason` says why and `permanent` whether a later retry could succeed."""
    address: str
    reason: str = ""
    permanent: bool = True


def resolve_recipient(user_id: str | None) -> Recipient:
    """The email address that owns `user_id`. Never raises.

    Multi-user (beta): each account row in `users` carries its own address, so
    a message must reach the account that owns it rather than one global inbox.
    `DELIVERY_EMAIL_TO` is the fallback ONLY for the single-user path — no
    user id, or the default portfolio id, which is not a real account.

    SA-006 recipient isolation: for any other account there is no fallback. A
    failed lookup is transient (retry later); an account without an address is
    permanent. Falling back would send one person's portfolio to the owner."""
    fallback = (getattr(settings, "DELIVERY_EMAIL_TO", "") or "").strip()
    single_user = not user_id or user_id == settings.PORTFOLIO_DEFAULT_USER_ID
    no_fallback = "unconfigured: no recipient (account email and DELIVERY_EMAIL_TO both unset)"
    if not user_id:
        return Recipient(fallback, "" if fallback else no_fallback)
    try:
        from services.data.stores import user_store
        user = user_store.get_user(user_id)
    except Exception as exc:
        if single_user:
            return Recipient(fallback, "" if fallback else no_fallback)
        logger.warning("[delivery] email lookup failed for user '%s'; not falling "
                       "back to DELIVERY_EMAIL_TO, will retry: %s",
                       user_id, redact(exc))
        return Recipient("", f"transient: account email lookup failed "
                             f"({type(exc).__name__}); will retry", permanent=False)
    if user and user.get("email"):
        return Recipient(str(user["email"]))
    if single_user:
        return Recipient(fallback, "" if fallback else no_fallback)
    # No user id in the reason: it reaches the owner's report, which carries
    # none (the row id identifies the account's row).
    return Recipient("", "permanent: no email on file for this account")


def _resolve_transport() -> str:
    """Which email transport to use: 'resend' | 'smtp'.

    "auto" prefers resend whenever a key is present, so setting RESEND_API_KEY
    in Railway is the entire cutover — no code or config edit needed."""
    choice = (getattr(settings, "EMAIL_TRANSPORT", "auto") or "auto").strip().lower()
    if choice in ("resend", "smtp"):
        return choice
    return "resend" if getattr(settings, "RESEND_API_KEY", "") else "smtp"


# ---------------------------------------------------------------------------
# email — resend (HTTPS)
# ---------------------------------------------------------------------------

def _json_field(resp, name: str) -> str:
    """One field of a JSON response body as text; "" when the body has none."""
    try:
        body = resp.json()
    except ValueError:                    # not JSON (requests raises a ValueError subclass)
        return ""
    return str(body.get(name, "") or "") if isinstance(body, dict) else ""


def _resend_failure(resp) -> SendResult:
    """Classify a non-2xx Resend response (error names from Resend's API docs,
    checked 2026-09-28). 429, 5xx and a concurrent same-key request retry;
    everything else is a request or account problem that a retry repeats."""
    code = resp.status_code
    detail = redact((resp.text or "").strip())[:300]
    name = _json_field(resp, "name")
    if code == 429 or code >= 500 or (code == 409 and name != "invalid_idempotent_request"):
        return SendResult(reason=f"transient: resend HTTP {code}: {detail}",
                          retry_after_s=_retry_after_s(resp))
    if code in (401, 403):
        hint = ("check RESEND_API_KEY, and RESEND_FROM: the shared onboarding "
                "sender reaches only the Resend account owner, so other "
                "recipients need a verified-domain sender")
    else:
        hint = "the provider rejected this request; retrying repeats it"
    return _refuse(f"permanent: resend HTTP {code}: {detail} — {hint}")


def _send_via_resend(subject: str, body: str, attachments: list[Path] | None,
                     html_body: str | None, recipient: str,
                     idempotency_key: str | None) -> SendResult:
    """POST one message to the Resend API over HTTPS. Never raises.

    A 2xx means Resend ACCEPTED the message — not that the mailbox received it.
    `idempotency_key` (the outbox passes one per row) makes Resend drop a
    repeat of the same request within 24 hours, which is what lets the drainer
    retry a timed-out request without sending the message twice. A caller that
    passes no key must not retry."""
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
            return _refuse(redact(f"permanent: attachment unreadable: "
                                  f"{type(exc).__name__}: {exc}"))
    headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}",
               "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        resp = requests.post("https://api.resend.com/emails", headers=headers,
                             json=payload, timeout=_SEND_TIMEOUT_S)
    except Exception as exc:
        reason = redact(f"transient: {type(exc).__name__}: {exc}")
        logger.warning("[delivery] resend request failed (non-fatal): %s", reason)
        return SendResult(reason=reason)
    if 200 <= resp.status_code < 300:
        msg_id = _json_field(resp, "id")
        return SendResult(1, accepted_by=f"resend id={msg_id}" if msg_id else "resend")
    result = _resend_failure(resp)
    logger.warning("[delivery] resend did not accept the message: %s", result.reason)
    return result


# ---------------------------------------------------------------------------
# email — smtp
# ---------------------------------------------------------------------------

def _smtp_failure(exc: Exception, phase: str) -> SendResult:
    """Classify an SMTP failure. `phase` is where it happened: "connect"
    (connect, STARTTLS, login — nothing sent yet) or "send" (inside sendmail).

    A reply code decides first: 4xx is the server saying "later" (retry), 5xx a
    refusal (stop). With no code — a network, TLS or dropped-connection error —
    a connect-phase failure retries; a send-phase one may have been accepted
    before the connection died, so it is not retried (at most once)."""
    base = redact(f"{type(exc).__name__}: {exc}")
    code = getattr(exc, "smtp_code", None)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [v[0] for v in exc.recipients.values() if isinstance(v, tuple) and v]
        code = codes[0] if codes else None
    code = code if isinstance(code, int) and 400 <= code < 600 else None
    if isinstance(exc, smtplib.SMTPAuthenticationError) and not (code and code < 500):
        return _refuse(f"permanent: SMTP login rejected ({base}) — check SMTP_USER "
                       "and SMTP_PASSWORD (Gmail needs an app password)")
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return _refuse(f"permanent: {base} — SMTP_HOST:SMTP_PORT does not offer "
                       "STARTTLS/AUTH; check the host and port (587 = STARTTLS)")
    if code and code < 500:
        return SendResult(reason=f"transient: SMTP {code}: {base}")
    if code:
        return _refuse(f"permanent: SMTP {code}: {base}")
    if phase == "send":
        return _refuse(f"unknown outcome: the connection failed during the send "
                       f"({base}); the server may have accepted the message, so it "
                       "is not retried — a retry could duplicate it")
    hint = ""
    if getattr(exc, "errno", None) == 101 or "Network is unreachable" in str(exc):
        hint = (" — if every send fails like this, the host blocks outbound SMTP "
                "(Railway Free/Trial/Hobby): set RESEND_API_KEY for the HTTPS transport")
    return SendResult(reason=f"transient: {base}{hint}")


def _send_via_smtp(subject: str, body: str, attachments: list[Path] | None,
                   html_body: str | None, recipient: str) -> SendResult:
    """stdlib smtplib STARTTLS. Never raises. A 250 to DATA is the relay's
    acceptance, not the mailbox's receipt."""
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
    except Exception as exc:              # e.g. an unreadable attachment: fail closed
        return _refuse(redact(f"permanent: could not build the message: "
                              f"{type(exc).__name__}: {exc}"))
    phase = "connect"
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT,
                          timeout=_SEND_TIMEOUT_S) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            phase = "send"
            s.sendmail(msg["From"], [recipient], msg.as_string())
            phase = "sent"                # only QUIT remains
        return SendResult(1, accepted_by="smtp")
    except Exception as exc:
        if phase == "sent":               # the relay already said 250
            logger.info("[delivery] SMTP QUIT failed after acceptance: %s", redact(exc))
            return SendResult(1, accepted_by="smtp")
        result = _smtp_failure(exc, phase)
        logger.warning("[delivery] email send failed (non-fatal): %s", result.reason)
        return result


def send_email_result(subject: str, body: str, attachments: list[Path] | None = None,
                      html_body: str | None = None, to: str | None = None,
                      idempotency_key: str | None = None) -> SendResult:
    """`send_email` with the full `SendResult` (SA-006). Never raises.

    `to` is the recipient for THIS message — the outbox passes the address of
    the account that owns the row. It falls back to `DELIVERY_EMAIL_TO`, which
    is right only for the owner's own reports (the direct callers).
    `idempotency_key` is sent to Resend; SMTP has no equivalent.

    The disabled/unconfigured gates report DISTINCT reasons and are permanent:
    a retry cannot change a setting. The reason is persisted to
    `outbox.last_error`, so a dead letter explains itself without the container
    log. It carries no recipient, payload or secret."""
    if not settings.DELIVERY_EMAIL_ENABLED:
        return _refuse("disabled: DELIVERY_EMAIL_ENABLED is false")
    recipient = (to or getattr(settings, "DELIVERY_EMAIL_TO", "") or "").strip()
    if not recipient:
        return _unconfigured("no recipient (account email and DELIVERY_EMAIL_TO both unset)")
    if _resolve_transport() == "resend":
        if not settings.RESEND_API_KEY:
            return _unconfigured("RESEND_API_KEY is unset")
        return _send_via_resend(subject, body, attachments, html_body, recipient,
                                idempotency_key)
    if not settings.SMTP_HOST:
        return _unconfigured("SMTP_HOST is unset")
    return _send_via_smtp(subject, body, attachments, html_body, recipient)


def _unconfigured(what: str) -> SendResult:
    """Email is enabled but cannot be sent. Logged, because the direct callers
    (monthly report, watchdog heartbeat, backup) have no outbox row to hold
    the reason."""
    logger.warning("[delivery] email enabled but unconfigured: %s", what)
    return _refuse(f"unconfigured: {what}")


def send_email(subject: str, body: str, attachments: list[Path] | None = None,
               html_body: str | None = None, to: str | None = None) -> bool:
    """Email send to `to`, defaulting to DELIVERY_EMAIL_TO. True means the
    transport accepted it; False when disabled/unconfigured or on any failure —
    never raises. `attachments` (AUD-088): file paths to attach; the whole send
    fails closed if any is unreadable. `html_body` (2026-07-30): when set, the
    message is multipart/alternative — plain `body` first, HTML last (clients
    prefer the last part).

    Thin wrapper over `send_email_result` — use that when you need the reason."""
    return send_email_result(subject, body, attachments, html_body, to=to).accepted


# ---------------------------------------------------------------------------
# web push
# ---------------------------------------------------------------------------

def _push_ttl_s() -> int:
    """How long the push service keeps an undelivered notification. pywebpush's
    default is 0 — "deliver now or drop" — so a phone that is offline or dozing
    when the service accepts the push never shows it (SA-006)."""
    return int(cfg("delivery.push_ttl_seconds", fallback=43200))


def _push_never_connected(exc: BaseException) -> bool:
    """True only when a push failed while CONNECTING, so the request never
    reached the push service: a connect timeout, a refused connection or a
    failed DNS lookup. Only then is a retry safe (SA-006 review F1).

    Decided by exception type, never message text. requests reports these as
    `ConnectTimeout`, or as a `ConnectionError` wrapping urllib3's
    `MaxRetryError` whose `reason` is a `NewConnectionError` (refused) or
    `NameResolutionError` (DNS); all three are urllib3 `ConnectTimeoutError`s.
    Anything else can follow the service storing the push: a connection
    dropped after the request was written ("Connection aborted.", a
    `ProtocolError`), a read timeout, a TLS error."""
    try:
        from requests.exceptions import ConnectTimeout
        from urllib3.exceptions import ConnectTimeoutError
    except ImportError:                  # pragma: no cover — pywebpush needs both
        return False
    seen: set[int] = set()
    todo: list[object] = [exc]
    while todo and len(seen) < 16:
        node = todo.pop()
        if not isinstance(node, BaseException) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, (ConnectTimeout, ConnectTimeoutError)):
            return True
        # requests puts the urllib3 error in args[0]; MaxRetryError holds the
        # connect error in `reason`; urllib3 raises it `from` the OSError.
        todo.extend((getattr(node, "reason", None), node.__cause__, *node.args))
    return False


def send_push_result(
    title: str,
    body: str,
    url: str = "/",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> SendResult:
    """`send_push` with the full `SendResult` (SA-006). Never raises.

    Accepted when at least one subscription's push service accepted it (201);
    that is not proof the device showed it. Failures per subscription:
    400/403/404/410 prune the subscription; 429 and 5xx are transient; so is a
    failure to connect at all (`_push_never_connected`). Any other exception
    — a read timeout, a connection dropped after the request was sent, a TLS
    error — may follow the service storing the push, so it is an unknown
    outcome and stops the row: a retry could show the notification twice.
    Endpoints never appear in the reason."""
    if not settings.DELIVERY_PUSH_ENABLED:
        return _refuse("disabled: DELIVERY_PUSH_ENABLED is false")
    if not settings.VAPID_PRIVATE_KEY:
        return _refuse("unconfigured: VAPID_PRIVATE_KEY is unset")
    if webpush is None:
        return _refuse("unavailable: pywebpush is not installed")
    store = store or PushStore()
    subs = store.list(user_id)
    if not subs:
        # AUD-090c: enabled-but-no-recipients is the silent-drop signature.
        logger.warning(
            "[delivery] push enabled but 0 subscriptions registered for user "
            "'%s' — notification dropped (enable alerts in the PWA)",
            user_id or settings.PORTFOLIO_DEFAULT_USER_ID)
        return _refuse("no push subscriptions registered (enable alerts in the PWA)")
    payload = json.dumps({"title": title, "body": body[:1500], "url": url})
    ttl = _push_ttl_s()
    sent = 0
    retry: list[str] = []
    stop: list[str] = []
    unknown: list[str] = []
    retry_after: float | None = None
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"},
                timeout=_SEND_TIMEOUT_S,
                ttl=ttl,
            )
            sent += 1
        except Exception as exc:
            resp = getattr(exc, "response", None)
            code = getattr(resp, "status_code", None)
            if code in (400, 403, 404, 410):
                # 404/410 = expired; 400/403 = malformed sub or VAPID-key
                # mismatch (AUD-085 prod stale sub) — all permanent, prune.
                store.remove(sub.get("endpoint", ""), user_id)
                logger.info("[delivery] pruned dead push subscription (%s)", code)
                stop.append(f"pruned dead subscription ({code})")
            elif code == 429 or (isinstance(code, int) and code >= 500):
                retry.append(f"push service HTTP {code}")
                wait = _retry_after_s(resp)
                if wait is not None:
                    retry_after = max(retry_after or 0.0, wait)
            elif isinstance(code, int):
                stop.append(f"push service HTTP {code}")
            elif _push_never_connected(exc):
                retry.append(f"{type(exc).__name__}: {exc}")
            else:
                unknown.append(f"{type(exc).__name__}: {exc}")
            logger.warning("[delivery] push send failed (non-fatal): %s", redact(exc))
    if sent:
        return SendResult(sent, accepted_by=f"webpush {sent}/{len(subs)} subscriptions")
    if unknown:
        return _refuse(redact(
            "unknown outcome: " + "; ".join(unknown + retry + stop)
            + " — the push service may have accepted it, so it is not retried"))
    if retry:
        return SendResult(reason=redact("transient: " + "; ".join(retry + stop)),
                          retry_after_s=retry_after)
    return _refuse(redact("permanent: " + "; ".join(stop)))


def send_push(
    title: str,
    body: str,
    url: str = "/",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> int:
    """Fan one notification out to every stored subscription. Returns the
    number of subscriptions whose push service accepted it; prunes dead
    subscriptions. Never raises.

    Thin wrapper over `send_push_result` — use that when you need the reason."""
    return send_push_result(title, body, url=url, user_id=user_id,
                            store=store).accepted_count


def deliver(
    title: str, body: str, url: str = "/", user_id: str | None = None,
    kind: str = "alert", html_body: str | None = None,
) -> dict:
    """Fan one message out to all configured channels. Never raises.

    Atlas C7 (BP2): when the relational plane is on, hand the message to the
    durable outbox (per-channel rows, atomic-claim drainer) instead of sending
    inline — `delivered=True` then means *queued for delivery*; the outbox
    owns retry/dead-letter. `kind` (brief|digest|weekly|alert) tags the queued
    rows. On the inline path (flag off, or the outbox unreachable)
    `delivered=True` means a transport accepted it. Neither is proof that a
    person received it (SA-006).
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
        # SA-006: the account's own address, never the owner's by fallback.
        recipient = resolve_recipient(user_id)
        if recipient.address:
            emailed = int(send_email(title, body, html_body=html_body,
                                     to=recipient.address))
        elif settings.DELIVERY_EMAIL_ENABLED:
            logger.warning("[delivery] %s — email skipped: %s", title, recipient.reason)
    except Exception as exc:
        logger.warning("[delivery] email channel failed (non-fatal): %s", exc)
    if pushed or emailed:
        logger.info("[delivery] %s — push=%d email=%d", title, pushed, emailed)
    else:
        logger.warning(
            "[delivery] %s — landed NOWHERE (push=0 email=0): no push "
            "subscriptions and email disabled/unconfigured (AUD-085)", title)
    return {"delivered": bool(pushed or emailed), "push": pushed, "email": emailed}
