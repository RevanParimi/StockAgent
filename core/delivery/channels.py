"""
Compass Phase C — delivery channels (spec §7).

web-push: pywebpush + VAPID keys (env secrets); subscriptions persisted in
data/delivery/push_subscriptions.json per user. Expired subscriptions
(404/410) are pruned on send. The PWA service worker displays the payload;
the TWA Android app gets it free.

email: stdlib smtplib STARTTLS fallback — single user, spec §7 "trivial SMTP".

EVERY send is non-fatal. deliver() is the only entry point callers need.
"""
from __future__ import annotations

import json
import logging
import smtplib
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


def send_email(subject: str, body: str) -> bool:
    """SMTP STARTTLS send to DELIVERY_EMAIL_TO. False when disabled/unconfigured
    or on any failure — never raises."""
    if not (settings.DELIVERY_EMAIL_ENABLED and settings.SMTP_HOST
            and settings.DELIVERY_EMAIL_TO):
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER or "stockagent@localhost"
        msg["To"] = settings.DELIVERY_EMAIL_TO
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(msg["From"], [settings.DELIVERY_EMAIL_TO], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("[delivery] email send failed (non-fatal): %s", exc)
        return False


def send_push(
    title: str,
    body: str,
    url: str = "/app/index.html",
    user_id: str | None = None,
    store: PushStore | None = None,
) -> int:
    """Fan one notification out to every stored subscription. Returns the
    number delivered; prunes expired (404/410) subscriptions. Never raises."""
    if not (settings.DELIVERY_PUSH_ENABLED and settings.VAPID_PRIVATE_KEY
            and webpush is not None):
        return 0
    store = store or PushStore()
    payload = json.dumps({"title": title, "body": body[:1500], "url": url})
    sent = 0
    for sub in store.list(user_id):
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
            if code in (404, 410):
                store.remove(sub.get("endpoint", ""), user_id)
                logger.info("[delivery] pruned expired push subscription (%s)", code)
            else:
                logger.warning("[delivery] push send failed (non-fatal): %s", exc)
    return sent


def deliver(
    title: str, body: str, url: str = "/app/index.html", user_id: str | None = None
) -> dict:
    """Fan one message out to all configured channels. Never raises."""
    if not settings.DELIVERY_ENABLED:
        return {"delivered": False, "reason": "delivery_disabled"}
    pushed = emailed = 0
    try:
        pushed = send_push(title, body, url=url, user_id=user_id)
    except Exception as exc:
        logger.warning("[delivery] push channel failed (non-fatal): %s", exc)
    try:
        emailed = int(send_email(title, body))
    except Exception as exc:
        logger.warning("[delivery] email channel failed (non-fatal): %s", exc)
    logger.info("[delivery] %s — push=%d email=%d", title, pushed, emailed)
    return {"delivered": bool(pushed or emailed), "push": pushed, "email": emailed}
