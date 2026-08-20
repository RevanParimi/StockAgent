"""
Compass Phase C — event alerts (spec §7): shock reforecast on a holding,
advisor escalations, shelf adds, lock-in expiry, index reconstitution.

Dedupe: one JSONL sent-log (data/delivery/alerts_sent.jsonl), key
"{user_id}|{date}|{kind}|{symbol}" — re-running a pipeline the same day
never re-notifies, and the same event for two different users each still
delivers (emits are per-user; see brief.py / pipeline.py). Records written
before this field existed have no "user_id" key and are treated as the
default user (""). Emission failures are telemetry, never pipeline errors.

Each record carries "delivered" (AUD-085): false means no channel accepted
the batch — such records are ignored by dedupe so the alert retries on the
next emit; records written before this field existed are treated as
delivered.

Presentation (2026-08-20): an event may also carry title/headline/status/
next_step/docs. The Inbox renders those as a card and the email body is
rendered to HTML (`render_alerts_html`, kill-switch delivery.alert_html_
enabled); push stays plain text, and so does every row written before the
fields existed — both fall back to `message`. None of them affect key().
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.delivery.channels import deliver

logger = logging.getLogger(__name__)

_SEVERITY_TAG = {"info": "[INFO]", "warning": "[WARN]", "critical": "[ALERT]"}


class AlertEvent(BaseModel):
    date: str                              # ISO date the event refers to
    kind: str                              # advisor_exit | shelf_add | lockin_expiry | ...
    symbol: str = ""
    message: str
    severity: Literal["info", "warning", "critical"] = "info"
    # Verification layer (2026-08-07): links an alert back to the advice row
    # that produced it, so the auditor grades them as one event. Deliberately
    # NOT part of key() — dedupe behaviour must be unchanged by provenance.
    advice_ref: str = ""

    # Presentation (2026-08-20): the Inbox renders alerts as a card like every
    # other tab, so it needs the parts separately rather than one prose blob.
    # All optional — every existing producer passes `message` alone and keeps
    # working, and rows written before this existed simply lack the keys.
    # Like advice_ref, NOT part of key(): how an alert looks must never change
    # what dedupes.
    title: str = ""          # what this is about, e.g. "Atlas C11 live cutover"
    headline: str = ""       # what happened, WITHOUT restating the title
    status: str = ""         # the check's current reading
    next_step: str = ""      # remediation — omitted when nothing is actionable
    docs: str = ""           # spec/doc path for the full story

    def key(self) -> str:
        return f"{self.date}|{self.kind}|{self.symbol}"


# -- HTML email body (2026-08-20) -------------------------------------------
# Severity -> (chip background, chip ink). Kept in step with the Inbox card's
# SEV_COLOR in src/frontend/prototypes/inbox.jsx.
_SEV_CHIP = {"critical": ("#fdeceb", "#b91c1c"),
             "warning": ("#fff7ed", "#b45309"),
             "info": ("#f1f5f9", "#475569")}


def _html_enabled() -> bool:
    from backend.shared.config.settings.loader import cfg
    return bool(cfg("delivery.alert_html_enabled", fallback=True))


def _alert_card_html(e: "AlertEvent", H: dict, font: str, esc) -> str:
    """One alert as an email-safe card. Rows predating the structured fields
    render their `message` verbatim (pre-wrap), which is all they have."""
    bg, ink = _SEV_CHIP.get(e.severity, _SEV_CHIP["info"])
    head = (
        f'<tr><td style="padding:0 0 10px">'
        f'<span style="display:inline-block;font:800 10px {font};letter-spacing:.09em;'
        f'text-transform:uppercase;padding:3px 9px;border-radius:999px;'
        f'background:{bg};color:{ink}">{esc(e.severity)}</span>'
        + (f'<span style="font:700 12px {font};color:{H["ink"]};margin-left:8px">'
           f'{esc(e.symbol)}</span>' if e.symbol else "")
        + f'<span style="float:right;font:600 11px {font};color:{H["muted"]}">'
          f'{esc(e.date)}</span></td></tr>'
    )
    body: list[str] = []
    if not (e.title or e.headline or e.status):
        body.append(
            f'<tr><td style="font:400 13px/1.55 {font};color:{H["body"]};'
            f'white-space:pre-wrap">{esc(e.message)}</td></tr>')
    else:
        if e.title:
            body.append(f'<tr><td style="font:800 14px {font};color:{H["ink"]};'
                        f'padding:0 0 4px">{esc(e.title)}</td></tr>')
        if e.headline:
            body.append(f'<tr><td style="font:400 13px/1.55 {font};'
                        f'color:{H["body"]}">{esc(e.headline)}</td></tr>')
        if e.status:
            body.append(
                f'<tr><td style="padding:9px 0 0;font:400 12.5px/1.5 {font};'
                f'color:{H["body"]};white-space:pre-wrap">'
                f'<span style="font:700 10px {font};letter-spacing:.09em;'
                f'text-transform:uppercase;color:{H["muted"]}">Status </span>'
                f'{esc(e.status)}</td></tr>')
        if e.next_step:
            body.append(
                f'<tr><td style="padding:11px 0 0">'
                f'<div style="font:700 10px {font};letter-spacing:.09em;'
                f'text-transform:uppercase;color:{H["accent"]};padding:0 0 5px">'
                f'Next step</div>'
                f'<div style="font:400 12.5px/1.55 {font};color:{H["body"]};'
                f'white-space:pre-wrap;border-left:2px solid {H["hair"]};'
                f'padding-left:10px">{esc(e.next_step)}</div></td></tr>')
        if e.docs:
            body.append(f'<tr><td style="padding:10px 0 0;font:400 11.5px {font};'
                        f'color:{H["muted"]};word-break:break-all">'
                        f'<span style="font:700 10px {font};letter-spacing:.09em;'
                        f'text-transform:uppercase">Docs </span>'
                        f'{esc(e.docs)}</td></tr>')
    return (
        f'<tr><td style="padding:0 0 12px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{H["card"]};border:1px solid {H["hair"]};'
        f'border-radius:14px;padding:16px 18px">{head}{"".join(body)}</table>'
        f'</td></tr>')


def render_alerts_html(events: list["AlertEvent"], title: str) -> str:
    """Styled, email-safe HTML for one alert batch. Standalone document, in the
    same visual language as the morning brief — the palette and escaper are
    imported from brief.py rather than copied so the two never drift apart.

    Raises nothing the caller must handle beyond the usual: `emit_alerts`
    wraps this and falls back to the plain-text body.
    """
    from core.delivery.brief import _FONT as font
    from core.delivery.brief import _HTML as H
    from core.delivery.brief import _esc as esc
    cards = "".join(_alert_card_html(e, H, font, esc) for e in events)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)}</title></head>'
        f'<body style="margin:0;padding:22px 12px;background:{H["page"]}">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:640px;margin:0 auto">'
        f'<tr><td style="font:800 12px {font};letter-spacing:.13em;'
        f'text-transform:uppercase;color:{H["accent"]};padding:0 0 14px">'
        f'{esc(title)}</td></tr>'
        f'{cards}</table></body></html>')


def _sent_log_path(sent_log: str | None) -> Path:
    if sent_log:
        p = Path(sent_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(settings.DELIVERY_DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "alerts_sent.jsonl"


_ROTATE_AT_LINES = 4000   # rotate when the sent-log grows past this
_ROTATE_KEEP = 2000       # keep-window; matches the _seen_keys tail


def _rotate_sent_log(path: Path) -> None:
    """AUD-013: cap unbounded sent-log growth (~10 lines/day on the volume).
    Rewrites the newest _ROTATE_KEEP lines atomically; dedupe already only
    looks at that same tail window, so rotation never changes behavior."""
    try:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= _ROTATE_AT_LINES:
            return
        from core.utils.atomic_io import atomic_write_text
        atomic_write_text(path, "\n".join(lines[-_ROTATE_KEEP:]) + "\n")
        logger.info("[alerts] sent-log rotated: %d -> %d lines",
                    len(lines), _ROTATE_KEEP)
    except Exception as exc:
        logger.warning("[alerts] sent-log rotation failed (non-fatal): %s", exc)


def _seen_keys(path: Path, tail: int = 2000) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                rec = json.loads(line)
                if rec.get("delivered") is False:   # AUD-085: undelivered → retryable
                    continue
                keys.add(f"{rec.get('user_id', '')}|{rec.get('date')}|"
                          f"{rec.get('kind')}|{rec.get('symbol')}")
            except Exception:
                continue
    except Exception as exc:
        logger.warning("[alerts] sent-log unreadable (non-fatal): %s", exc)
    return keys


def load_recent_alerts(limit: int = 50, sent_log: str | None = None) -> list[dict]:
    """The newest `limit` alerts, NEWEST FIRST.

    The sent-log is append-only, so the file's own order is oldest-first. The
    Inbox renders this list top-to-bottom and a notification feed reads newest
    at the top, so the reversal belongs here rather than in every caller.
    """
    path = _sent_log_path(sent_log)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.reverse()
    return out


def emit_alerts(
    events: list[AlertEvent],
    user_id: str | None = None,
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """Dedupe, persist, and deliver a batch as ONE bundled message. Never raises.

    Dedupe is user-aware — the sent-log is global but emits are per-user
    (brief.py, pipeline.py), so the key includes user_id to avoid one
    user's alert silently suppressing everyone else's identical event.
    """
    try:
        uid = user_id or ""
        path = _sent_log_path(sent_log)
        _rotate_sent_log(path)   # AUD-013
        seen = _seen_keys(path)
        new = [e for e in events if f"{uid}|{e.key()}" not in seen]
        # in-batch dedupe too
        uniq: list[AlertEvent] = []
        batch_keys: set[str] = set()
        for e in new:
            bk = f"{uid}|{e.key()}"
            if bk not in batch_keys:
                batch_keys.add(bk)
                uniq.append(e)
        if not uniq:
            return {"emitted": 0}
        body = "\n".join(
            f"{_SEVERITY_TAG[e.severity]} {e.symbol + ' — ' if e.symbol else ''}{e.message}"
            for e in uniq
        )
        # The HTML body is a presentation nicety: a render failure must cost
        # the reader styling, never the alert itself.
        html_body = None
        if _html_enabled():
            try:
                html_body = render_alerts_html(uniq, title)
            except Exception as exc:
                logger.warning("[alerts] html render failed, sending text-only "
                               "(non-fatal): %s", exc)
        # AUD-085 rider: deliver FIRST, then record the outcome — a record with
        # delivered=false does not dedupe, so the same-day batch retries once a
        # transport (push sub / SMTP) appears. Legacy records lack the key and
        # are treated as delivered.
        delivered = False
        outcome: dict = {}
        try:
            outcome = deliver(title, body, url="/#/inbox/alerts", user_id=user_id,
                              html_body=html_body) or {}
            delivered = bool(outcome.get("delivered"))
        except Exception as exc:
            logger.warning("[alerts] delivery failed (non-fatal): %s", exc)
        if not delivered:
            logger.warning(
                "[alerts] %d alert(s) NOT delivered (%s) — recorded delivered=false, "
                "will retry on next emit (AUD-085)",
                len(uniq), outcome.get("reason") or "no channel delivered")
        with open(path, "a", encoding="utf-8") as fh:
            for e in uniq:
                rec = e.model_dump()
                rec["user_id"] = uid
                rec["delivered"] = delivered
                fh.write(json.dumps(rec) + "\n")
        return {"emitted": len(uniq), "delivered": delivered,
                "kinds": sorted({e.kind for e in uniq})}
    except Exception as exc:
        logger.warning("[alerts] emit failed (non-fatal): %s", exc)
        return {"emitted": 0, "error": str(exc)}


def _audience_push_store():
    """Seam for tests — the default PushStore."""
    from core.delivery.channels import PushStore
    return PushStore()


def alert_audience() -> list[str]:
    """Every user who should receive SYSTEM-level alerts (AUD-015): all users
    with a push subscription, plus the default portfolio user (the email
    transport is a single global mailbox and rides the default user's emit)."""
    uids: set[str] = set()
    try:
        uids.update(_audience_push_store().user_ids())
    except Exception as exc:
        logger.warning("[alerts] audience lookup failed (non-fatal): %s", exc)
    uids.add(settings.PORTFOLIO_DEFAULT_USER_ID)
    return sorted(uids)


def emit_alerts_broadcast(
    events: list[AlertEvent],
    title: str = "StockAgent alerts",
    sent_log: str | None = None,
) -> dict:
    """emit_alerts to every alert_audience() user (AUD-015). Never raises.

    Note: with >1 audience user the single global mailbox receives one email
    per user (deliver() sends email unconditionally); acceptable at the
    current single-real-user scale, and per-user push still lands correctly.
    """
    results: dict[str, dict] = {}
    for uid in alert_audience():
        results[uid] = emit_alerts(events, user_id=uid, title=title,
                                   sent_log=sent_log)
    return {"users": results,
            "emitted": sum(r.get("emitted", 0) for r in results.values())}
