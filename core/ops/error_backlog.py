"""Operations error backlog (SA-011) — durable errors grouped into issues.

`app_logs` (telemetry.db) keeps every WARNING+ record forever, but tens of
thousands of rows are unreadable and logging a warning again does not close
the defect behind it. This module groups those rows into issues a person can
work: one issue per cause, with first/last seen, a count, the runs and tickers
it touched, and a lifecycle.

Grouping is deterministic, with no LLM anywhere: the stored message is
normalised (the pre-E1 "<IST ts> LEVEL [logger] " prefix, timestamps, ids,
numbers, paths, URLs, quoted values and secrets removed; a traceback reduced
to its exception type), and the issue's fingerprint is a hash of
(source, logger, template). Only the template is stored, never a raw
message.

Severity is the record's own level from `app_logs.level`. Railway prints
every stderr line, INFO included, under an `error` envelope; that envelope is
never an input. `parse_console_line` reads the app's own level when a Railway
export is analysed offline (scripts/prod_errors.py --railway-json).

Outbox dead letters (SA-006) reach the backlog through the drainer's one
WARNING per dead-lettered row, which names the channel, the kind and the
classified, redacted reason. One issue per (channel, kind, reason class).

Lifecycle
---------
Activity, derived at read time from the occurrences:
    new        first seen within `new_days`
    regressed  came back within `new_days`: after a `fixed` mark, or after a
               quiet gap (`quiet_days` for an open issue, `ack_quiet_days`
               for an acknowledged one); a regression reopens it
    ongoing    seen within `quiet_days`
    quiet      not seen for `quiet_days`
    spiking    (a flag) today's or yesterday's IST count is above its own
               trailing mean + `spike_sigma` sd and at least `spike_min`

An acknowledged issue has an owner, so a return at the cadence of a weekly or
monthly job is the same defect, not a new episode: it regresses only after
`ack_quiet_days` (longer than a month) of quiet, or demands attention earlier
by spiking.

Triage, set by the owner: open | acknowledged | fixed | wontfix, with an
assignee, a linked task and a note. A `fixed` issue is a claim until measured
evidence settles it: `verified` once `verify_days` have passed with no
recurrence AND the archive holds rows from after that window (otherwise
`unobserved`, never verified by silence alone); any recurrence after the fix
reopens it as regressed. The claim must fit the evidence already held: a
`fixed_at` before the issue's `last_seen` (a recurrence after the fix is
already recorded) or in the future is refused, so the outcome never depends
on whether the registry was read before or after the triage. Times are kept
at the precision they were logged. A `fixed_at` must carry its UTC
offset: the owner reads times in IST and a machine caller may mean UTC, so a
guess either way could file a recurrence before the fix.

Retention: the raw `app_logs` rows are never touched. Per issue, the daily
counts keep `daily_days` days and the run/ticker lists `keep_ids` entries.
An issue is pruned only after `retention_days` without an occurrence, and
never while acknowledged or while a fix awaits verification; `max_issues`
caps the table without ever dropping an active issue.

Never raises to a scheduled caller: the watchdog check and the API wrap it.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

LEVELS = ("WARNING", "ERROR", "CRITICAL")
_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
STATUSES = ("open", "acknowledged", "fixed", "wontfix")
SOURCE_APP_LOGS = "app_logs"
SOURCE_RAILWAY = "railway_export"

_TEMPLATE_MAX = 240
_EXC_MAX = 120
_ASSIGNEE_MAX = 64
_TASK_MAX = 64
_NOTE_MAX = 500
# A client clock a little ahead of the server's may still say "now".
_FIXED_AT_FUTURE_TOLERANCE = timedelta(minutes=5)


@dataclass(frozen=True)
class Params:
    new_days: int = 2
    quiet_days: int = 7
    ack_quiet_days: int = 35
    verify_days: int = 7
    spike_baseline_days: int = 14
    spike_sigma: float = 3.0
    spike_min: int = 10
    retention_days: int = 90
    max_issues: int = 2000
    daily_days: int = 30
    keep_ids: int = 20
    batch_rows: int = 2000
    max_rows_per_refresh: int = 20000


def params() -> Params:
    """The configured tunables (config.yaml `error_backlog:`), read per call."""
    from backend.shared.config.settings.loader import cfg
    d = Params()
    return Params(**{f: type(getattr(d, f))(cfg(f"error_backlog.{f}", fallback=getattr(d, f)))
                     for f in d.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Normalisation and fingerprint (pure)
# ---------------------------------------------------------------------------

# The console format, "%(asctime)s %(levelname)-8s [%(name)s] %(message)s".
# Pre-E1 rows carry it inside `message`; a Railway export carries it on every
# line. Python's default "%(levelname)s:%(name)s:%(message)s" and uvicorn's
# "LEVEL:     message" are the other two shapes on Railway's stderr.
_CONSOLE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?: ?(?:IST|UTC|Z|[+-]\d{2}:?\d{2}))? +"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) +\[([^\]]*)\] ?(.*)$", re.S)
_DEFAULT_FMT_RE = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):([\w.]+):(.*)$", re.S)
_UVICORN_RE = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):\s+(.*)$", re.S)

_TRACEBACK = "Traceback (most recent call last):"

_SUBS: tuple[tuple[re.Pattern, str], ...] = (
    # URLs first, whole: keep scheme and host (which provider failed), drop
    # userinfo, path and query, which carry tokens and push capabilities
    (re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]*)://(?:[^\s/@'\"<>]*@)?([^\s/:'\"<>?#]+)[^\s'\"<>]*"),
     r"\1://\2/<path>"),
    # secrets, before anything can split them
    (re.compile(r"(?i)\bbearer\s+[^\s,;'\"]+"), "Bearer <secret>"),
    # an Authorization header's credential, whatever its scheme
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:(?:basic|bearer|digest|token)\s+)?"
                r"[^\s,;'\"]+"), r"\1<secret>"),
    # a Basic credential on its own: base64 with a digit, "+", "/" or padding,
    # so "basic validation failed" keeps its words
    (re.compile(r"(?i)\bbasic\s+(?=[a-z0-9+/]*[0-9+/=])[a-z0-9+/]{8,}={0,2}(?![\w+/=])"),
     "Basic <secret>"),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|token|secret|"
                r"password|passwd|pwd|authorization|signature|session|key)(\s*[:=]\s*)[^\s,;&'\"]+"),
     r"\1\2<secret>"),
    (re.compile(r"\beyJ[\w-]{4,}\.[\w-]{4,}\.[\w-]*"), "<secret>"),
    # an address, also percent-encoded (name%40example.com)
    (re.compile(r"[\w.+-]+(?:@|%40)[\w-]+(?:\.[\w-]+)+"), "<email>"),
    # quoted values: payloads, keys and symbols. An apostrophe inside a word
    # ("can't") is not an opening quote.
    (re.compile(r"(?<![A-Za-z0-9])'[^'\n]{0,300}'(?![A-Za-z0-9])"), "<str>"),
    (re.compile(r'(?<![A-Za-z0-9])"[^"\n]{0,300}"(?![A-Za-z0-9])'), "<str>"),
    # file paths, whole, before a date or id inside one can split it:
    # absolute, Windows, or anything ending in a data/code extension
    (re.compile(r"(?i)\b[A-Z]:\\[^\s'\"<>]+"), "<path>"),
    (re.compile(r"(?<![\w>/:])/(?:[\w.\-]+/)+[\w.\-]*"), "<path>"),   # not inside scheme://host/
    (re.compile(r"\b[\w.\-]+(?:[/\\][\w.\-]+)*\.(?:py|json|jsonl|db|csv|ya?ml|txt|log|parquet|"
                r"html|md|pkl|zip|gz)\b"), "<path>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
     "<uuid>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?"
                r"(?: ?(?:Z|IST|UTC|[+-]\d{2}:?\d{2}))?)?"), "<ts>"),
    (re.compile(r"\b\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?\b"), "<time>"),
    (re.compile(r"(?i)\b0x[0-9a-f]+\b"), "<hex>"),
    (re.compile(r"(?i)\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,}\b"), "<hex>"),
    (re.compile(r"\b(?=[A-Za-z0-9_\-+/=]*[A-Za-z])(?=[A-Za-z0-9_\-+/=]*\d)[A-Za-z0-9_\-+/=]{24,}"),
     "<token>"),
    # identifiers with a prefix: Atlas user ids (u_3f9a12c0), run ids, row
    # keys. "_" is a word character, so the hex rule's \b never sees them.
    (re.compile(r"\b[A-Za-z][A-Za-z0-9]{0,11}[_-](?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,}\b"), "<id>"),
    (re.compile(r"\b(?=\w*[A-Za-z])(?=(?:\w*?\d){3})\w{6,}\b"), "<id>"),
    # market symbols: index (^NSEI), exchange-suffixed (MARUTI.NS, $MARUTI.NS)
    (re.compile(r"\$?\^[A-Z0-9][A-Z0-9.&\-]*"), "<sym>"),
    (re.compile(r"\$?\b[A-Z0-9][A-Z0-9&\-]{0,24}\.(?:NS|BO)\b"), "<sym>"),
)

# A status, error number or HTTP code IS the cause (401 is not 429), so the
# number after these words survives the number rule below.
_KEEP_CODE_RE = re.compile(r"(?i)\b(http|status(?:_code)?|code|errno)(\s*[:=]?\s*\[?)(\d{3}|\d{1,4}(?=\]))")
# A unit suffix stays (period=1d and period=5d are one shape; 1d and 1mo not).
_NUM_RE = re.compile(r"(?<![A-Za-z0-9_<#])[-+]?\d+(?:[.,]\d+)*(?:e[-+]?\d+)?%?"
                     r"(?=(?:[A-Za-z]{1,3})?(?![A-Za-z0-9_]))")

# A bare upper-case word is usually an NSE symbol (WELCORP, TATAMOTORS); left
# in, every ticker would be its own issue. These structural words stay.
_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9&]{2,24}(?:-[A-Z0-9]{1,6})?\b")
_CAPS_KEEP = frozenset("""
ERROR WARNING INFO DEBUG CRITICAL FATAL HTTP HTTPS URL URI API LLM JSON SQL SQLITE NSE BSE
IST UTC GMT NULL NONE TRUE FALSE NAN OK GET POST PUT PATCH DELETE HEAD SMTP DNS SSL TLS TCP
CSV PDF HTML XML YAML UUID RSS FII DII ETF IPO EPS PE PEG ROE ROCE EBITDA GDP CPI RBI SEBI
BUY SELL HOLD WATCH EXIT ADD TRIM AVOID ACCUMULATE REDUCE SKIP OHLC OHLCV VWAP RSI MACD EMA
SMA ATR MAX MIN AVG UNKNOWN DEAD SENT TODO FIXME RL KPI AUM NAV YTD QOQ YOY TTM CAGR USD INR
NOT ALL ANY SKIP SKIPPED SKIPPING FAIL FAILED FAILURE CRASHED BROKEN INVALID INVALIDATED
REFUSING REFUSED DENIED ABSENT MISSING STALE DEGRADED HOLLOW LAPSED BLOCKED TIMEOUT PARTIAL
EMPTY DETECTED SHOCK DRIFT FOREIGN KEY ETL EOD SWITCH AMBIGUOUS VIX NIFTY SIDEWAYS BULL BEAR
RESOLVED UNRESOLVED PENDING DONE COMPLETE SUCCESS RETRY DUPLICATE STARTED STOPPED ABORTED
WARN NEW OLD LIVE DARK OFF
""".split())

# "WELCORP, INFY, TCS" and "INFY" are one list of a varying length: one
# placeholder, so a summary line does not split by how many it names.
_LIST_RE = re.compile(r"(<(?:sym|str|n|id|hex|uuid|path)>)(?:\s*,\s*\1)+")
_WS_RE = re.compile(r"\s+")

# The row's own ticker (E1) is first replaced by this stand-in symbol, which
# the symbol rules then mask exactly as they mask a ticker logged outside a
# run: `$MARUTI.NS` and `MARUTI` read the same inside a run and out of one.
_TICKER_STANDIN = "ROWTICKER"
_EXCHANGE_SUFFIX_RE = re.compile(r"\.(?:NS|BO)$", re.I)


def _strip_console_prefix(message: str) -> str:
    m = _CONSOLE_RE.match(message)
    return m.group(3) if m else message


def _whole(value: str) -> re.Pattern:
    return re.compile(r"(?<![\w])" + re.escape(value) + r"(?![\w])")


def _norm_text(text: str, run_id: str | None = None, ticker: str | None = None) -> str:
    if run_id and len(run_id) >= 2:
        text = _whole(run_id).sub("<id>", text)
    base = _EXCHANGE_SUFFIX_RE.sub("", (ticker or "").strip().lstrip("$"))
    if len(base) >= 2:
        text = _whole(base).sub(_TICKER_STANDIN, text)
    for pattern, repl in _SUBS:
        text = pattern.sub(repl, text)
    kept: list[str] = []

    def _keep(m: re.Match) -> str:
        kept.append(m.group(3))
        return f"{m.group(1)}{m.group(2)}\x00keep\x00"     # no digit, no capital

    text = _KEEP_CODE_RE.sub(_keep, text)
    text = _NUM_RE.sub("<n>", text)
    text = _CAPS_RE.sub(lambda m: m.group(0) if m.group(0) in _CAPS_KEEP else "<sym>", text)
    restore = iter(kept)
    text = re.sub("\x00keep\x00", lambda _m: next(restore), text)
    text = _LIST_RE.sub(r"\1", text)
    return _WS_RE.sub(" ", text).strip()


def _split_traceback(message: str) -> tuple[str, str | None]:
    """(head, "ExcType: message" of the last traceback block, or None).

    Frames and line numbers are dropped on purpose: the same failure reached
    through another caller, or after an edit moved a line, is the same cause.
    A traceback cut by the archive's 4,000-character cap has no exception
    line; it is reported as "?" rather than guessed."""
    idx = message.find(_TRACEBACK)
    if idx < 0:
        return message, None
    head = message[:idx]
    block = message[message.rfind(_TRACEBACK):]
    exc = "?"
    for line in block.splitlines()[1:]:
        if line and not line.startswith((" ", "\t")):
            exc = line.strip()
            break
    return head, exc


def normalize(message: str, *, ticker: str | None = None,
              run_id: str | None = None) -> str:
    """The template of one stored message: deterministic, payload-free text.

    `ticker` and `run_id` are the row's own columns (E1). Both are per-run,
    so a template that kept either would never repeat. The ticker is masked
    as the symbol rules mask any ticker, so a cause logged inside a run and
    outside one is one issue."""
    text = _strip_console_prefix(message or "")
    head, exc = _split_traceback(text)
    template = _norm_text(head, run_id, ticker)
    if exc is not None:
        exc_type, _, exc_msg = exc.partition(":")
        exc_part = _norm_text(exc_type.strip(), run_id, ticker)
        if exc_msg.strip():
            exc_part += ": " + _norm_text(exc_msg.strip(), run_id, ticker)[:_EXC_MAX]
        template = f"{template} | exc {exc_part}" if template else f"exc {exc_part}"
    return template[:_TEMPLATE_MAX] or "<empty>"


def fingerprint(source: str, logger_name: str, template: str) -> str:
    raw = "\x1f".join((source, logger_name, template))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_console_line(line: str) -> tuple[str, str, str] | None:
    """(app level, logger, message) from one console line, or None.

    For a Railway export, `line` is the inner message: Railway's own level is
    `error` for everything on stderr and says nothing about the record."""
    text = (line or "").rstrip("\r\n")
    m = _CONSOLE_RE.match(text)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = _DEFAULT_FMT_RE.match(text)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = _UVICORN_RE.match(text)
    if m:
        return m.group(1), "uvicorn", m.group(2)
    return None


# ---------------------------------------------------------------------------
# Occurrences and the lifecycle (pure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Occurrence:
    ts: datetime              # aware
    level: str
    logger: str
    template: str
    source: str = SOURCE_APP_LOGS
    run_id: str | None = None
    ticker: str | None = None

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.source, self.logger, self.template)


def parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    # Full precision: triage compares a fix time with the stored last_seen,
    # and ingestion compares it with the occurrence's own time; whole seconds
    # in one and not the other would judge a same-second row differently.
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _ist_day(dt: datetime) -> str:
    return dt.astimezone(IST).date().isoformat()


def _ist_minute(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def _ist_iso(dt: datetime) -> str:
    """A time as the owner reads it, exact, in the form `fixed_at` accepts."""
    return dt.astimezone(IST).isoformat()


def occurrence_from_row(row: dict, source: str = SOURCE_APP_LOGS) -> Occurrence | None:
    """An `app_logs` row as an occurrence; None for a row below WARNING or
    with an unreadable timestamp (counted by the caller as skipped)."""
    level = str(row.get("level") or "").upper()
    ts = parse_ts(row.get("ts"))
    if _LEVEL_RANK.get(level, 0) < _LEVEL_RANK["WARNING"] or ts is None:
        return None
    return Occurrence(ts=ts, level=level, logger=str(row.get("logger") or "?"),
                      template=normalize(str(row.get("message") or ""),
                                         ticker=row.get("ticker"), run_id=row.get("run_id")),
                      source=source, run_id=row.get("run_id"), ticker=row.get("ticker"))


def _push_capped(items: list, value, cap: int) -> list:
    if not value:
        return items
    items = [v for v in items if v != value] + [value]
    return items[-cap:]


def new_issue(occ: Occurrence) -> dict:
    return {"fingerprint": occ.fingerprint, "source": occ.source, "logger": occ.logger,
            "template": occ.template, "max_level": occ.level,
            "first_seen": _iso(occ.ts), "last_seen": _iso(occ.ts), "count": 0,
            "daily": {}, "run_ids": [], "tickers": [], "regressions": 0,
            "regressed_at": None, "status": "open", "status_at": None,
            "assignee": None, "task": None, "note": None, "fixed_at": None}


def apply_occurrence(issue: dict | None, occ: Occurrence, p: Params) -> dict:
    """Fold one occurrence into its issue. Pure: returns a new dict."""
    if issue is None:
        out = new_issue(occ)
    else:
        out = {**issue, "daily": dict(issue.get("daily") or {}),
               "run_ids": list(issue.get("run_ids") or []),
               "tickers": list(issue.get("tickers") or [])}
        last = parse_ts(out.get("last_seen"))
        fixed_at = parse_ts(out.get("fixed_at"))
        status = out.get("status") or "open"
        quiet_gap = timedelta(days=p.ack_quiet_days if status == "acknowledged" else p.quiet_days)
        if status == "fixed" and fixed_at is not None and occ.ts > fixed_at:
            out.update(status="open", status_at=_iso(occ.ts), fixed_at=None,
                       regressed_at=_iso(occ.ts), regressions=int(out.get("regressions") or 0) + 1)
        elif (status in ("open", "acknowledged") and last is not None
              and occ.ts - last >= quiet_gap):
            # Back after a quiet spell: a new episode, so an acknowledgement
            # of the old one no longer covers it.
            if status == "acknowledged":
                out.update(status="open", status_at=_iso(occ.ts))
            out.update(regressed_at=_iso(occ.ts),
                       regressions=int(out.get("regressions") or 0) + 1)
        if last is None or occ.ts > last:
            out["last_seen"] = _iso(occ.ts)
        first = parse_ts(out.get("first_seen"))
        if first is None or occ.ts < first:
            out["first_seen"] = _iso(occ.ts)
    out["count"] = int(out.get("count") or 0) + 1
    if _LEVEL_RANK.get(occ.level, 0) > _LEVEL_RANK.get(out.get("max_level") or "", 0):
        out["max_level"] = occ.level
    day = _ist_day(occ.ts)
    out["daily"][day] = int(out["daily"].get(day, 0)) + 1
    last_day = parse_ts(out["last_seen"]).astimezone(IST).date()
    floor = (last_day - timedelta(days=p.daily_days - 1)).isoformat()
    out["daily"] = {d: n for d, n in sorted(out["daily"].items()) if d >= floor}
    out["run_ids"] = _push_capped(out["run_ids"], occ.run_id, p.keep_ids)
    out["tickers"] = _push_capped(out["tickers"], occ.ticker, p.keep_ids)
    return out


def _spiking(issue: dict, now: datetime, p: Params) -> bool:
    daily = issue.get("daily") or {}
    first_day = parse_ts(issue["first_seen"]).astimezone(IST).date()
    today = now.astimezone(IST).date()
    for day in (today, today - timedelta(days=1)):
        n = int(daily.get(day.isoformat(), 0))
        if n < p.spike_min:
            continue
        base_days = [day - timedelta(days=k) for k in range(1, p.spike_baseline_days + 1)]
        base = [int(daily.get(d.isoformat(), 0)) for d in base_days if d >= first_day]
        if len(base) < 3:
            continue          # too little history: it is "new", not a spike
        mean = sum(base) / len(base)
        sd = math.sqrt(sum((x - mean) ** 2 for x in base) / len(base))
        if n > mean + p.spike_sigma * sd:
            return True
    return False


def classify(issue: dict, now: datetime, coverage: datetime | None, p: Params) -> dict:
    """Derived fields at `now`. `coverage` is the newest archived row the
    backlog has read: the measured evidence a fix is verified against."""
    first = parse_ts(issue["first_seen"])
    last = parse_ts(issue["last_seen"])
    regressed_at = parse_ts(issue.get("regressed_at"))
    status = issue.get("status") or "open"
    if regressed_at is not None and now - regressed_at < timedelta(days=p.new_days):
        state = "regressed"
    elif now - first < timedelta(days=p.new_days):
        state = "new"
    elif now - last < timedelta(days=p.quiet_days):
        state = "ongoing"
    else:
        state = "quiet"
    spiking = _spiking(issue, now, p)
    verification = None
    if status == "fixed":
        fixed_at = parse_ts(issue.get("fixed_at"))
        if fixed_at is not None and last > fixed_at:
            # A recorded occurrence after the fix contradicts it. Ingestion
            # and triage never leave this state; a hand-edited row could.
            verification = "recurred"
        elif fixed_at is None or now - fixed_at < timedelta(days=p.verify_days):
            verification = "pending"
        elif coverage is not None and coverage >= fixed_at + timedelta(days=p.verify_days):
            verification = "verified"
        else:
            verification = "unobserved"
    attention = (status == "open" and state in ("new", "regressed")) or \
                (status in ("open", "acknowledged") and spiking) or \
                verification == "recurred"
    week_floor = (now.astimezone(IST).date() - timedelta(days=6)).isoformat()
    last7 = sum(n for d, n in (issue.get("daily") or {}).items() if d >= week_floor)
    return {"state": state, "spiking": spiking, "verification": verification,
            "attention": attention, "last_7_days": last7}


def is_protected(issue: dict, cls: dict) -> bool:
    """Retention never drops this, whatever its age or the cap: someone owns
    it (acknowledged), a fix awaits its evidence, or it needs attention now."""
    status = issue.get("status") or "open"
    return (status == "acknowledged" or cls.get("attention", False)
            or (status == "fixed" and cls.get("verification") != "verified"))


def select_prunable(issues: list[dict], now: datetime, coverage: datetime | None,
                    p: Params) -> list[str]:
    """Fingerprints retention removes.

    1. Unprotected issues not seen for `retention_days`.
    2. While the table is still over `max_issues`: the stalest unprotected
       issues that are quiet (not seen for `quiet_days`).
    An active issue (protected, or seen within `quiet_days`) is never
    selected, so the cap can be exceeded rather than lose one."""
    drop: list[str] = []
    quiet: list[dict] = []
    for issue in issues:
        cls = classify(issue, now, coverage, p)
        if is_protected(issue, cls):
            continue
        if now - parse_ts(issue["last_seen"]) >= timedelta(days=p.retention_days):
            drop.append(issue["fingerprint"])
        elif cls["state"] == "quiet":
            quiet.append(issue)
    excess = len(issues) - len(drop) - p.max_issues
    if excess > 0:
        quiet.sort(key=lambda i: (i["last_seen"], i["fingerprint"]))
        drop += [i["fingerprint"] for i in quiet[:excess]]
    return sorted(drop)


_STATE_RANK = {"regressed": 0, "new": 1, "ongoing": 2, "quiet": 3}


def rank_key(issue: dict, cls: dict):
    return (0 if cls["attention"] else 1, _STATE_RANK.get(cls["state"], 9),
            0 if cls["spiking"] else 1, -_LEVEL_RANK.get(issue.get("max_level") or "", 0),
            -int(cls["last_7_days"]), -int(issue.get("count") or 0), issue["fingerprint"])


def public_issue(issue: dict, cls: dict) -> dict:
    """The API shape: registry fields plus the derived ones. No raw message
    exists to leak; the template is the only text from a log line."""
    return {k: issue.get(k) for k in (
        "fingerprint", "source", "logger", "template", "max_level", "first_seen",
        "last_seen", "count", "daily", "run_ids", "tickers", "regressions",
        "regressed_at", "status", "status_at", "assignee", "task", "note",
        "fixed_at")} | cls


def build_digest(issues: list[dict], now: datetime, coverage: datetime | None,
                 p: Params, top: int = 10) -> str:
    """Deterministic plain-text digest: the same registry and `now` give the
    same bytes, whatever order the issues arrive in."""
    rows = sorted(((i, classify(i, now, coverage, p)) for i in issues),
                  key=lambda ic: rank_key(*ic))
    attention = [(i, c) for i, c in rows if c["attention"]]
    fixed = [(i, c) for i, c in rows if (i.get("status") or "open") == "fixed"]
    ongoing = [(i, c) for i, c in rows if not c["attention"]
               and (i.get("status") or "open") in ("open", "acknowledged")
               and c["state"] != "quiet"]
    quiet = sum(1 for i, c in rows if c["state"] == "quiet"
                and (i.get("status") or "open") in ("open", "acknowledged"))
    wontfix = sum(1 for i, _ in rows if i.get("status") == "wontfix")
    stamp = _ist_minute(now)
    cov = _ist_minute(coverage) if coverage else "none"
    lines = [f"Error backlog — {stamp} (archive read to {cov})",
             f"{len(rows)} issue(s): {len(attention)} need attention, {len(ongoing)} ongoing, "
             f"{len(fixed)} fixed, {quiet} quiet, {wontfix} wontfix.", ""]

    def line(i: dict, c: dict) -> str:
        flags = c["state"] + (", spiking" if c["spiking"] else "")
        if c["verification"]:
            flags = f"fixed, {c['verification']}"
        who = "".join(f" {k}={i[k]}" for k in ("assignee", "task") if i.get(k))
        status = i.get("status") or "open"
        if status == "fixed" and i.get("fixed_at"):
            status += f" since {_ist_minute(parse_ts(i['fixed_at']))}"
        return (f"  [{flags}] {i['max_level']} {i['logger']} — {i['template']}\n"
                f"      {i['count']} total, {c['last_7_days']} in 7d; "
                f"first {_ist_day(parse_ts(i['first_seen']))}, "
                f"last {_ist_minute(parse_ts(i['last_seen']))}; "
                f"runs {len(i.get('run_ids') or [])}; fp {i['fingerprint']}"
                f"; status {status}{who}")

    for title, group in (("Needs attention", attention),
                         ("Fixed — awaiting or holding verification", fixed),
                         (f"Ongoing (top {top})", ongoing[:top])):
        lines.append(f"{title}:")
        lines += [line(i, c) for i, c in group] or ["  (none)"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Store: tables in telemetry.db, on a connection of its own
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS error_issues (
    fingerprint  TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    logger       TEXT NOT NULL,
    template     TEXT NOT NULL,
    max_level    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    count        INTEGER NOT NULL,
    daily        TEXT NOT NULL,
    run_ids      TEXT NOT NULL,
    tickers      TEXT NOT NULL,
    regressions  INTEGER NOT NULL DEFAULT 0,
    regressed_at TEXT,
    status       TEXT NOT NULL DEFAULT 'open',
    status_at    TEXT,
    assignee     TEXT,
    task         TEXT,
    note         TEXT,
    fixed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_error_issues_last_seen ON error_issues (last_seen);
CREATE TABLE IF NOT EXISTS error_backlog_cursor (
    source  TEXT PRIMARY KEY,
    last_id INTEGER NOT NULL,
    last_ts TEXT
);
"""

_COLUMNS = ("fingerprint", "source", "logger", "template", "max_level", "first_seen",
            "last_seen", "count", "daily", "run_ids", "tickers", "regressions",
            "regressed_at", "status", "status_at", "assignee", "task", "note", "fixed_at")
_JSON_COLUMNS = ("daily", "run_ids", "tickers")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_op_lock = threading.RLock()


def _serialised(fn):
    """One store operation at a time in this process. The routes run in a
    thread pool and share one connection, and SQLite cannot open a second
    BEGIN on it. Processes (two uvicorn workers) serialise on BEGIN
    IMMEDIATE instead."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _op_lock:
            return fn(*args, **kwargs)
    return wrapper


def _db_path() -> Path:
    from core.config import settings
    return Path(getattr(settings, "TELEMETRY_DB_PATH", "data/telemetry.db"))


def open_registry(path: str | Path) -> sqlite3.Connection:
    """A connection with the registry tables. Its own connection, not
    log_store's: a refresh never holds the lock every WARNING+ write takes.
    isolation_level=None, so BEGIN IMMEDIATE below is the one transaction."""
    on_disk = str(path) != ":memory:"
    if on_disk:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=5.0,
                           isolation_level=None)
    if on_disk:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = open_registry(_db_path())
    return _conn


def _row_to_issue(row: tuple) -> dict:
    issue = dict(zip(_COLUMNS, row))
    for col in _JSON_COLUMNS:
        issue[col] = json.loads(issue[col] or ("{}" if col == "daily" else "[]"))
    return issue


def _load(conn: sqlite3.Connection, fingerprints: Iterable[str] | None = None) -> list[dict]:
    cols = ", ".join(_COLUMNS)
    if fingerprints is None:
        rows = conn.execute(f"SELECT {cols} FROM error_issues ORDER BY fingerprint").fetchall()
    else:
        fps = sorted(set(fingerprints))
        rows = []
        for k in range(0, len(fps), 500):
            chunk = fps[k:k + 500]
            rows += conn.execute(
                f"SELECT {cols} FROM error_issues WHERE fingerprint IN "
                f"({', '.join('?' * len(chunk))})", chunk).fetchall()
    return [_row_to_issue(r) for r in rows]


def _save(conn: sqlite3.Connection, issue: dict) -> None:
    values = [json.dumps(issue[c], sort_keys=True) if c in _JSON_COLUMNS else issue.get(c)
              for c in _COLUMNS]
    conn.execute(f"INSERT OR REPLACE INTO error_issues ({', '.join(_COLUMNS)}) "
                 f"VALUES ({', '.join('?' * len(_COLUMNS))})", values)


def _cursor(conn: sqlite3.Connection, source: str) -> tuple[int, str | None]:
    row = conn.execute("SELECT last_id, last_ts FROM error_backlog_cursor WHERE source = ?",
                       (source,)).fetchone()
    return (int(row[0]), row[1]) if row else (0, None)


def ingest(conn: sqlite3.Connection, occurrences: Iterable[Occurrence], p: Params) -> int:
    """Fold occurrences into the registry inside the caller's transaction."""
    occs = list(occurrences)
    issues = {i["fingerprint"]: i for i in _load(conn, (o.fingerprint for o in occs))}
    for occ in occs:
        fp = occ.fingerprint
        issues[fp] = apply_occurrence(issues.get(fp), occ, p)
    for issue in issues.values():
        _save(conn, issue)
    return len(occs)


@_serialised
def refresh(conn: sqlite3.Connection | None = None, source_conn: sqlite3.Connection | None = None,
            p: Params | None = None, now: datetime | None = None) -> dict:
    """Read new `app_logs` rows (id > cursor) into the registry, in batches.

    Each batch is one BEGIN IMMEDIATE transaction holding the cursor and the
    issues it changed, so two uvicorn workers refreshing at once serialise
    and never count a row twice. At most `max_rows_per_refresh` rows per
    call: `caught_up` says whether the archive was read to its end. Then
    retention runs. `source_conn` is the archive (default: the same DB)."""
    p = p or params()
    conn = conn or _get_conn()
    src = source_conn or conn
    now = now or datetime.now(timezone.utc)
    summary = {"read": 0, "ingested": 0, "skipped": 0, "caught_up": False, "pruned": 0}
    columns = {r[1] for r in src.execute("PRAGMA table_info(app_logs)").fetchall()}
    if not columns:
        summary["caught_up"] = True       # no archive yet: nothing to read
        return summary
    # A pre-E1 archive has no run_id/ticker until log_store's migration runs.
    extra = ", ".join(c if c in columns else f"NULL AS {c}" for c in ("run_id", "ticker"))
    while summary["read"] < p.max_rows_per_refresh:
        limit = min(p.batch_rows, p.max_rows_per_refresh - summary["read"])
        conn.execute("BEGIN IMMEDIATE")
        try:
            last_id, last_ts = _cursor(conn, SOURCE_APP_LOGS)
            rows = src.execute(
                f"SELECT id, ts, level, logger, message, {extra} FROM app_logs "
                "WHERE id > ? ORDER BY id LIMIT ?", (last_id, limit)).fetchall()
            if not rows:
                conn.execute("COMMIT")
                summary["caught_up"] = True
                break
            occs = []
            for rid, ts, level, lg, msg, run_id, ticker in rows:
                occ = occurrence_from_row({"ts": ts, "level": level, "logger": lg,
                                           "message": msg, "run_id": run_id, "ticker": ticker})
                if occ is None:
                    summary["skipped"] += 1
                else:
                    occs.append(occ)
            summary["ingested"] += ingest(conn, occs, p)
            new_ts = max([_iso(o.ts) for o in occs] + ([last_ts] if last_ts else []), default=None)
            conn.execute("INSERT OR REPLACE INTO error_backlog_cursor (source, last_id, last_ts) "
                         "VALUES (?, ?, ?)", (SOURCE_APP_LOGS, rows[-1][0], new_ts))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        summary["read"] += len(rows)
        if len(rows) < limit:
            summary["caught_up"] = True
            break
    summary["pruned"] = prune(conn, p, now)
    return summary


@_serialised
def coverage(conn: sqlite3.Connection | None = None) -> datetime | None:
    conn = conn or _get_conn()
    return parse_ts(_cursor(conn, SOURCE_APP_LOGS)[1])


@_serialised
def prune(conn: sqlite3.Connection, p: Params, now: datetime) -> int:
    conn.execute("BEGIN IMMEDIATE")
    try:
        drop = select_prunable(_load(conn), now, coverage(conn), p)
        for k in range(0, len(drop), 500):
            chunk = drop[k:k + 500]
            conn.execute(f"DELETE FROM error_issues WHERE fingerprint IN "
                         f"({', '.join('?' * len(chunk))})", chunk)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(drop)


@_serialised
def issues(conn: sqlite3.Connection | None = None) -> list[dict]:
    return _load(conn or _get_conn())


class TriageError(ValueError):
    """A triage request the registry refuses (unknown status, oversized field,
    a fix time the evidence already contradicts)."""


def _parse_fixed_at(value: str, now: datetime) -> datetime:
    """A fix time as given by the owner. Unlike `parse_ts`, a time without a
    UTC offset (a date alone too) is refused rather than read as UTC: the
    owner reads times in IST, and an IST time stored as UTC files the fix
    5.5 hours late, so a recurrence in that gap would count as before it."""
    example = now.astimezone(IST).isoformat(timespec="minutes")
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise TriageError(f"fixed_at {value!r} is not an ISO time: give the time the fix took "
                          f"effect with its UTC offset, e.g. {example} (IST)") from None
    if dt.tzinfo is None:
        bare = dt.isoformat(timespec="minutes" if not (dt.second or dt.microsecond)
                            else "seconds")
        raise TriageError(f"fixed_at {value!r} has no UTC offset, so it could be IST or UTC: "
                          f"give {bare}+05:30 for IST or {bare}Z for UTC")
    return dt


@_serialised
def triage(fp: str, *, status: str | None = None, assignee: str | None = None,
           task: str | None = None, note: str | None = None, fixed_at: str | None = None,
           conn: sqlite3.Connection | None = None, now: datetime | None = None) -> dict | None:
    """Set an issue's triage fields. None for an unknown fingerprint.

    `fixed` records when the fix took effect (`fixed_at`, default now): only
    occurrences after it count as a regression. `fixed_at` must carry its
    UTC offset. A `fixed_at` in the future, or before the issue's
    `last_seen`, is refused: the registry already holds a recurrence after
    that time, so the fix did not hold. Folding the same row in after the
    triage would reopen the issue, so either way it is never `fixed` against
    its own evidence. Refusals name times in IST. An empty string clears
    assignee, task or note."""
    conn = conn or _get_conn()
    now = now or datetime.now(timezone.utc)
    if status is not None and status not in STATUSES:
        raise TriageError(f"status must be one of {', '.join(STATUSES)}")
    for name, value, cap in (("assignee", assignee, _ASSIGNEE_MAX), ("task", task, _TASK_MAX),
                             ("note", note, _NOTE_MAX)):
        if value is not None and len(value) > cap:
            raise TriageError(f"{name} is longer than {cap} characters")
    fixed_dt = _parse_fixed_at(fixed_at, now) if fixed_at else None
    if fixed_dt is not None and status != "fixed":
        raise TriageError("fixed_at is only accepted with status 'fixed'")
    if fixed_dt is not None and fixed_dt > now + _FIXED_AT_FUTURE_TOLERANCE:
        raise TriageError(f"fixed_at {_ist_iso(fixed_dt)} is in the future "
                          f"(now {_ist_iso(now)}): give the time the fix took effect")
    conn.execute("BEGIN IMMEDIATE")
    try:
        found = _load(conn, [fp])
        if not found:
            conn.execute("COMMIT")
            return None
        issue = found[0]
        new_fixed_at = None
        if status == "fixed" and (status != issue.get("status") or fixed_dt is not None):
            new_fixed_at = parse_ts(_iso(fixed_dt or now))       # as stored and classified
            last = parse_ts(issue.get("last_seen"))
            if last is not None and last > new_fixed_at:
                raise TriageError(
                    f"this issue was last seen at {_ist_iso(last)}, after fixed_at "
                    f"{_ist_iso(new_fixed_at)}: an occurrence after the fix is already recorded, "
                    "so that fix did not hold. Leave the issue open, or give the time a later "
                    "fix took effect.")
        if status is not None and status != issue.get("status"):
            issue["status"] = status
            issue["status_at"] = _iso(now)
            issue["fixed_at"] = _iso(new_fixed_at) if status == "fixed" else None
        elif new_fixed_at is not None:
            issue["fixed_at"] = _iso(new_fixed_at)
        for name, value in (("assignee", assignee), ("task", task), ("note", note)):
            if value is not None:
                issue[name] = value.strip() or None
        _save(conn, issue)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return issue


def _listed_active(issue: dict, cls: dict) -> bool:
    status = issue.get("status") or "open"
    if cls["attention"]:
        return True
    if status == "fixed":
        return cls["verification"] != "verified"
    return status in ("open", "acknowledged") and cls["state"] != "quiet"


@_serialised
def report(*, include: str = "active", limit: int = 100, p: Params | None = None,
           conn: sqlite3.Connection | None = None, now: datetime | None = None) -> dict:
    """Refresh, then the ranked registry. `include`: attention | active | all
    (active leaves out quiet, verified-fixed and wontfix issues)."""
    p = p or params()
    conn = conn or _get_conn()
    now = now or datetime.now(timezone.utc)
    summary = refresh(conn, p=p, now=now)
    cov = coverage(conn)
    rows = sorted(((i, classify(i, now, cov, p)) for i in issues(conn)),
                  key=lambda ic: rank_key(*ic))
    counts = {"total": len(rows), "attention": sum(1 for _, c in rows if c["attention"])}
    if include == "attention":
        rows = [(i, c) for i, c in rows if c["attention"]]
    elif include == "active":
        rows = [(i, c) for i, c in rows if _listed_active(i, c)]
    return {"generated_at": _iso(now), "coverage": _iso(cov), "refresh": summary,
            "counts": counts,
            "issues": [public_issue(i, c) for i, c in rows[:max(1, int(limit))]]}


@_serialised
def digest(*, p: Params | None = None, conn: sqlite3.Connection | None = None,
           now: datetime | None = None) -> str:
    p = p or params()
    conn = conn or _get_conn()
    now = now or datetime.now(timezone.utc)
    refresh(conn, p=p, now=now)
    return build_digest(issues(conn), now, coverage(conn), p)


# ---------------------------------------------------------------------------
# Offline: a Railway log export (scripts/prod_errors.py --railway-json)
# ---------------------------------------------------------------------------

def railway_occurrences(lines: Iterable[str]) -> tuple[list[Occurrence], dict]:
    """Occurrences from `railway logs --json` lines, by the app's own level.

    Railway's `level`/`severity` is the stream (stderr = error), so it is
    recorded in the stats and never decides anything. A line with no app
    level (a bare traceback line, a print) is `unparsed`, not an error."""
    stats = {"lines": 0, "below_warning": 0, "unparsed": 0, "envelope_error_but_info": 0,
             "occurrences": 0}
    occs: list[Occurrence] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        stats["lines"] += 1
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = {"message": raw}
        if not isinstance(obj, dict):
            stats["unparsed"] += 1
            continue
        envelope = str(obj.get("level") or obj.get("severity")
                       or (obj.get("attributes") or {}).get("level") or "").lower()
        parsed = parse_console_line(str(obj.get("message") or obj.get("msg") or ""))
        if parsed is None:
            stats["unparsed"] += 1
            continue
        level, lg, message = parsed
        if _LEVEL_RANK[level] < _LEVEL_RANK["WARNING"]:
            stats["below_warning"] += 1
            if envelope == "error":
                stats["envelope_error_but_info"] += 1
            continue
        ts = parse_ts(obj.get("timestamp") or obj.get("ts")) or datetime.now(timezone.utc)
        occs.append(Occurrence(ts=ts, level=level, logger=lg, template=normalize(message),
                               source=SOURCE_RAILWAY))
    stats["occurrences"] = len(occs)
    return occs, stats
