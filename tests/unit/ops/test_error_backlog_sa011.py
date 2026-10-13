"""SA-011: durable errors become a deterministic, owner-only operations backlog.

Invariants, each stated from the outside rather than read back from the code:

- one cause is one issue: timestamps, ids, numbers, symbols, user ids, frames
  and line numbers vary without splitting it, across the pre-E1 message prefix
  too; different causes (401 vs 429, email vs push, another exception type)
  stay apart;
- no raw message, secret, address or user payload reaches the registry file,
  the API or the digest;
- severity is the record's own level, never Railway's stderr envelope;
- the lifecycle: new, ongoing, quiet, spiking; an open issue regresses after
  a quiet week, an acknowledged one only after more than a month (a weekly or
  monthly job's warning stays owned), a fixed one on any later occurrence;
  a fix is verified only by measured coverage of its window, and never
  against an occurrence already recorded after it, whatever the read order,
  even within one second;
- a fix time without a UTC offset is refused, never guessed as UTC or IST;
  the same instant in any offset notation is the same fix; refusals and the
  digest name times in IST;
- a cause logged inside a run (ticker and run id columns) and outside one is
  one issue;
- ingestion is idempotent, batch-size independent and safe under two writers;
  retention never drops an active issue and never touches app_logs;
- the digest is the same bytes for the same registry and clock;
- only the owner (or the machine key) can read or triage the registry;
- the watchdog check names no template; one registry entry enables it, and
  its notices reach only the owner.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from core.ops import error_backlog as eb
from services.data.stores import log_store

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)          # Mon 09:30 IST
P = eb.Params(new_days=2, quiet_days=7, verify_days=7, spike_baseline_days=14,
              spike_sigma=3.0, spike_min=10, retention_days=90, max_issues=2000,
              daily_days=30, keep_ids=20, batch_rows=50, max_rows_per_refresh=10**6)
REPO = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _archive(path: Path) -> sqlite3.Connection:
    """An app_logs archive with the real log_store schema."""
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.executescript(log_store._SCHEMA)
    log_store._migrate(conn)
    return conn


def _add(conn, ts: datetime, level: str, logger_name: str, message: str,
         run_id: str | None = None, ticker: str | None = None) -> None:
    conn.execute("INSERT INTO app_logs (ts, level, logger, message, run_id, ticker) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (ts.isoformat(), level, logger_name, message, run_id, ticker))


def _fp(message: str, logger_name: str = "core.x", **cols) -> str:
    return eb.fingerprint(eb.SOURCE_APP_LOGS, logger_name, eb.normalize(message, **cols))


def _occ(ts: datetime, message: str = "[x] fetch failed for MARUTI.NS: timeout 30s",
         level: str = "WARNING", logger_name: str = "core.x", run_id=None, ticker=None):
    return eb.Occurrence(ts=ts, level=level, logger=logger_name,
                         template=eb.normalize(message, run_id=run_id, ticker=ticker),
                         run_id=run_id, ticker=ticker)


def _fold(occs, issue=None, p=P):
    for o in occs:
        issue = eb.apply_occurrence(issue, o, p)
    return issue


def _tb(head: str, frames: list[tuple[str, int, str]], exc: str, chained: bool = False) -> str:
    body = "".join(f'  File "{f}", line {n}, in {fn}\n    do_something()\n' for f, n, fn in frames)
    tb = f"Traceback (most recent call last):\n{body}{exc}"
    if chained:
        tb = ("Traceback (most recent call last):\n  File \"/app/a.py\", line 3, in g\n"
              "KeyError: 'close'\n\nDuring handling of the above exception, another "
              "exception occurred:\n\n" + tb)
    return f"{head}\n{tb}"


# ---------------------------------------------------------------------------
# one cause, one issue
# ---------------------------------------------------------------------------

VARIANTS = [
    # (a, b) must group
    ("[daily_review] MARUTI review failed at 2026-10-05T04:00:01+00:00 after 3 tries",
     "[daily_review] TATAMOTORS review failed at 2026-10-06T11:12:13+00:00 after 5 tries"),
    ("[fetch] $MARUTI.NS: possibly delisted; no price data found (period=1d)",
     "[fetch] $INFY.BO: possibly delisted; no price data found (period=5d)"),
    ("[atlas] user u_3f9a12c0 brief for u_3f9a12c0/WELCORP (no-holdings): skipped",
     "[atlas] user u_77be01d4 brief for u_77be01d4/INFY (no-holdings): skipped"),
    ("[run] run 6f1c2a90-1b2c-4d5e-8f90-0a1b2c3d4e5f took 12.5s (cache 0x7ffe12)",
     "[run] run 0b8d7c6e-aaaa-4bbb-8ccc-123456789abc took 0.25s (cache 0x1a2b)"),
    ("[outbox] row 12 dead-lettered after 3 attempt(s) (email/brief): permanent: SMTP auth failed",
     "[outbox] row 9031 dead-lettered after 1 attempt(s) (email/brief): permanent: SMTP auth failed"),
    ("[store] could not write data/portfolio/u_1a2b3c4d/brief.json: disk full",
     "[store] could not write /app/data/portfolio/primary/2026-10-05/brief.json: disk full"),
    ("[review] skipped no_envelope: WELCORP; failed timeout: INFY",
     "[review] skipped no_envelope: WELCORP, ZOMATO, TCS; failed timeout: INFY, HDFCBANK"),
    ("[chat] model said 'I cannot help with that request about my holdings'",
     "[chat] model said 'sure, here is the summary'"),
]


@pytest.mark.parametrize("a,b", VARIANTS)
def test_changing_ids_timestamps_numbers_and_symbols_keep_one_issue(a, b):
    assert _fp(a) == _fp(b)


def test_row_run_id_and_ticker_columns_never_split_a_cause():
    a = _fp("[agent] run r-2026-10-05-aa1 for SUZLON scored nothing", run_id="r-2026-10-05-aa1",
            ticker="SUZLON")
    b = _fp("[agent] run r-2026-10-07-bb9 for NHPC scored nothing", run_id="r-2026-10-07-bb9",
            ticker="NHPC")
    assert a == b


@pytest.mark.parametrize("message", [
    "$MARUTI.NS: possibly delisted; no price data found (period=1d)",
    "[Scheduler] Daily review FAILED for MARUTI: boom",
    "[fetch] no data for MARUTI.NS",
    "[fetch] MARUTI.BO and MARUTI both empty",
    "[agent] quoted 'MARUTI' not resolved",
    "[store] could not write data/predictions/MARUTI/2026-10.json: disk full",
    "[sector] MARUTI-EQ has no sector row",
])
@pytest.mark.parametrize("column", ["MARUTI", "MARUTI.NS"])
def test_a_cause_logged_inside_and_outside_a_run_is_one_issue(message, column):
    # The same line, logged inside an analysis run (the row carries its run id
    # and ticker) and outside one (no columns), and for another ticker.
    outside = _fp(message)
    assert _fp(message, run_id="6f1c2a90", ticker=column) == outside
    other = message.replace("MARUTI", "TATAMOTORS")
    assert _fp(other, run_id="0b8d7c6e", ticker=column.replace("MARUTI", "TATAMOTORS")) == outside


def test_pre_e1_console_prefix_and_e1_message_are_one_issue():
    msg = "[delivery] email send failed: [Errno 101] Network is unreachable"
    legacy = "2026-08-25 23:52:53 IST WARNING  [core.delivery.channels] " + msg
    assert _fp(legacy) == _fp(msg)


@pytest.mark.parametrize("variant", ["moved_lines", "other_caller", "deeper_stack", "chained"])
def test_traceback_variants_of_one_failure_group(variant):
    head = "[Scheduler] Daily review FAILED for MARUTI: boom"
    exc = "ValueError: could not convert string to float: 'n/a'"
    base = _tb(head, [("/app/services/scheduler.py", 801, "run"),
                      ("/app/core/review.py", 40, "review")], exc)
    frames = {
        "moved_lines": [("/app/services/scheduler.py", 812, "run"), ("/app/core/review.py", 44, "review")],
        "other_caller": [("/app/services/api/routes/x.py", 77, "trigger"), ("/app/core/review.py", 40, "review")],
        "deeper_stack": [("/app/services/scheduler.py", 801, "run"), ("/app/core/a.py", 9, "a"),
                         ("/app/core/review.py", 40, "review")],
        "chained": [("/app/services/scheduler.py", 801, "run"), ("/app/core/review.py", 40, "review")],
    }[variant]
    other = _tb("[Scheduler] Daily review FAILED for INFY: boom", frames,
                "ValueError: could not convert string to float: 'x1'", chained=variant == "chained")
    assert _fp(base) == _fp(other)


def test_a_traceback_cut_by_the_archive_cap_is_stable_not_guessed():
    cut = _tb("[x] failed", [("/app/a.py", 1, "f")], "")[:60]
    t = eb.normalize(cut)
    assert t.endswith("exc ?") and t == eb.normalize(cut)


@pytest.mark.parametrize("a,b", [
    ("[llm] OpenRouter HTTP 401: invalid key", "[llm] OpenRouter HTTP 429: rate limited"),
    ("[llm] status_code=401 from provider", "[llm] status_code=402 from provider"),
    ("[smtp] [Errno 101] Network is unreachable", "[smtp] [Errno 111] Network is unreachable"),
    ("[outbox] row 1 dead-lettered after 3 attempt(s) (email/brief): permanent: auth",
     "[outbox] row 1 dead-lettered after 3 attempt(s) (push/brief): permanent: auth"),
    ("[outbox] row 1 dead-lettered after 1 attempt(s) (email/brief): permanent: no address",
     "[outbox] row 1 dead-lettered after 3 attempt(s) (email/brief): retries exhausted (3/3): "
     "transient: timeout"),
    ("[Scheduler] Daily review FAILED for MARUTI: boom",
     "[Scheduler] Daily review SKIPPED for MARUTI: boom"),
    ("[gate] identity NOT resolved for TATAMOTORS", "[gate] identity resolved for TATAMOTORS"),
])
def test_different_causes_stay_apart(a, b):
    assert _fp(a) != _fp(b)


def test_a_url_keeps_its_host_and_loses_its_path():
    a = _fp("[llm] HTTP 503 from https://openrouter.ai/api/v1/chat?key=abc123def")
    b = _fp("[llm] HTTP 503 from https://openrouter.ai/api/v1/models/x9y8z7")
    other = _fp("[llm] HTTP 503 from https://api.resend.com/emails/abc123def")
    assert a == b and a != other
    assert "openrouter.ai" in eb.normalize("[llm] HTTP 503 from https://openrouter.ai/api/v1/chat")


def test_different_exception_types_or_loggers_stay_apart():
    frames = [("/app/x.py", 1, "f")]
    assert _fp(_tb("[x] failed", frames, "KeyError: 'close'")) != \
        _fp(_tb("[x] failed", frames, "TimeoutError: timed out"))
    assert _fp("[x] same text", "core.a") != _fp("[x] same text", "core.b")


def test_fingerprints_are_stable_across_processes_and_releases():
    # A change here re-opens every production issue as NEW on the next deploy:
    # change the normaliser only on purpose, and say so in the release notes.
    t = eb.normalize("[fetch] $MARUTI.NS: possibly delisted; no price data found (period=1d)")
    assert t == "[fetch] <sym>: possibly delisted; no price data found (period=<n>d)"
    assert eb.fingerprint("app_logs", "yfinance", t) == hashlib.sha256(
        "app_logs\x1fyfinance\x1f".encode() + t.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# nothing private reaches the registry, the API or the digest
# ---------------------------------------------------------------------------

SECRETS = {
    "bearer": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1In0.c2lnbmF0dXJl",
    "openrouter": "sk-or-v1-0123456789abcdef0123456789abcdef",
    "apikey": "api_key=ZXCVBNM1234567890qwerty",
    "password": "password=hunter2-correct-horse",
    "email": "investor.person@example.com",
    "url_token": "https://hooks.example.com/push/AbCdEf123456?token=QWERTY987654321",
    "user_text": "'sell all my HDFCBANK before my divorce settles'",
    "user_id": "u_9c8b7a65",
    "resend": "re_AbCdEf123456GhIjKl7890MnOp",
    "bare_base64": "AbcdefGhijklMnop+QrstuvWxyz/AbcdEf1Gh==",     # few digits, no label
    "basic_header": "Authorization: Basic dXNlcjpwYXNzd29yZA==",
    "token_header": "Authorization: Token QwErTyUiOpAsDfGh",          # no digit at all
    "basic_bare": "Basic b3duZXI6aHVudGVy",                            # two digits only
    "pct_email": "someone.else%40example.org",
}
_NEEDLES = ["eyJhbGciOiJIUzI1NiJ9", "sk-or-v1-0123", "ZXCVBNM1234567890", "hunter2",
            "investor.person", "@example.com", "/push/", "AbCdEf123456", "QWERTY987654321", "divorce",
            "9c8b7a65", "GhIjKl7890", "AbcdefGhijklMnop", "QrstuvWxyz", "dXNlcjpw", "QwErTyUiOp",
            "b3duZXI6", "someone.else", "example.org"]


def test_masking_a_credential_keeps_ordinary_words():
    assert "basic validation failed" in eb.normalize("[form] basic validation failed for the form")
    assert "Basic auth not configured" in eb.normalize("[x] Basic auth not configured")
    # two credentials are one cause
    assert _fp("[http] Authorization: Basic dXNlcjpwYXNzd29yZA== refused") == \
        _fp("[http] Authorization: Basic YWRtaW46czNjcjN0 refused")
    assert _fp("[http] retry with Basic dXNlcjpwYXNzd29yZA== failed") == \
        _fp("[http] retry with Basic b3duZXI6aHVudGVy failed")


@pytest.fixture()
def leaky_archive(tmp_path):
    arch = _archive(tmp_path / "telemetry.db")
    for k, (name, secret) in enumerate(sorted(SECRETS.items())):
        _add(arch, T0 + timedelta(minutes=k), "ERROR", "core.leaky",
             f"[{name}] request failed with {secret} after {k} tries")
    return arch


def test_no_secret_or_payload_reaches_the_registry_file(tmp_path, leaky_archive):
    reg_path = tmp_path / "registry.db"
    reg = eb.open_registry(reg_path)
    eb.refresh(reg, source_conn=leaky_archive, p=P, now=T0 + timedelta(hours=1))
    reg.execute("PRAGMA wal_checkpoint(FULL)")
    reg.close()
    blob = b"".join(p.read_bytes() for p in tmp_path.glob("registry.db*"))
    for needle in _NEEDLES:
        assert needle.encode() not in blob, needle
    issues = eb.issues(eb.open_registry(reg_path))
    assert len(issues) == len(SECRETS)            # each still its own, readable issue


def test_no_secret_reaches_the_digest_or_the_public_shape(tmp_path, leaky_archive):
    reg = eb.open_registry(":memory:")
    now = T0 + timedelta(hours=1)
    eb.refresh(reg, source_conn=leaky_archive, p=P, now=now)
    text = eb.build_digest(eb.issues(reg), now, eb.coverage(reg), P)
    shapes = json.dumps([eb.public_issue(i, eb.classify(i, now, eb.coverage(reg), P))
                         for i in eb.issues(reg)])
    for needle in _NEEDLES:
        assert needle not in text and needle not in shapes, needle


# ---------------------------------------------------------------------------
# severity is the app's own level
# ---------------------------------------------------------------------------

def _railway(message: str, envelope: str = "error") -> str:
    return json.dumps({"timestamp": "2026-10-05T04:00:00Z", "message": message, "level": envelope})


def test_info_on_stderr_is_not_an_error_whatever_the_envelope():
    lines = [
        _railway("2026-10-05 09:30:00 IST INFO     [core.delivery.brief] brief sent to 3 users"),
        _railway("INFO:     10.0.0.1:5555 - \"GET /health HTTP/1.1\" 200 OK"),
        _railway("INFO:services.api.server:startup complete"),
        _railway("  File \"/app/x.py\", line 3, in f"),      # a bare traceback line
        _railway("print-style output with no level"),
    ]
    occs, stats = eb.railway_occurrences(lines)
    assert occs == []
    assert stats["below_warning"] == 3 and stats["envelope_error_but_info"] == 3
    assert stats["unparsed"] == 2


def test_app_level_wins_in_both_directions():
    occs, _ = eb.railway_occurrences([
        _railway("2026-10-05 09:30:00 IST WARNING  [core.x] slow fetch", envelope="error"),
        _railway("2026-10-05 09:30:00 IST ERROR    [core.y] write failed", envelope="info"),
        _railway("CRITICAL:core.z:disk full", envelope="info"),
    ])
    assert [(o.level, o.logger) for o in occs] == [
        ("WARNING", "core.x"), ("ERROR", "core.y"), ("CRITICAL", "core.z")]


def test_archive_rows_below_warning_are_skipped_and_level_is_the_column(tmp_path):
    arch = _archive(tmp_path / "t.db")
    _add(arch, T0, "INFO", "core.x", "ERROR: this INFO line only mentions an error")
    _add(arch, T0, "WARNING", "core.x", "ERROR ERROR CRITICAL in the text")
    _add(arch, T0 + timedelta(minutes=1), "ERROR", "core.x", "ERROR ERROR CRITICAL in the text")
    reg = eb.open_registry(":memory:")
    s = eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(hours=1))
    assert s["skipped"] == 1 and s["ingested"] == 2
    (issue,) = eb.issues(reg)
    assert issue["max_level"] == "ERROR" and issue["count"] == 2


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def test_a_warning_flood_is_one_bounded_issue():
    occs = [_occ(T0 + timedelta(seconds=7 * k), run_id=f"run-{k:05d}",
                 ticker=random.Random(k).choice(["MARUTI", "INFY", "TCS"]))
            for k in range(5000)]
    issue = _fold(occs)
    assert issue["count"] == 5000
    assert len(issue["run_ids"]) == P.keep_ids and issue["run_ids"][-1] == "run-04999"
    assert len(issue["tickers"]) <= P.keep_ids
    assert len(issue["daily"]) <= P.daily_days
    text = eb.build_digest([issue], T0 + timedelta(days=1), T0 + timedelta(days=1), P)
    assert len(text) < 2000


def test_new_then_ongoing_then_quiet():
    issue = _fold([_occ(T0)])
    cls = lambda days: eb.classify(issue, T0 + timedelta(days=days), None, P)["state"]  # noqa: E731
    assert cls(0.5) == "new" and cls(3) == "ongoing" and cls(8) == "quiet"


def test_open_issue_regresses_after_a_quiet_spell_and_not_before():
    issue = _fold([_occ(T0)])
    soon = eb.apply_occurrence(issue, _occ(T0 + timedelta(days=6)), P)
    assert soon["regressions"] == 0
    back = eb.apply_occurrence(soon, _occ(T0 + timedelta(days=14)), P)
    assert back["status"] == "open" and back["regressions"] == 1
    cls = eb.classify(back, T0 + timedelta(days=14, hours=1), None, P)
    assert cls["state"] == "regressed" and cls["attention"]


@pytest.mark.parametrize("cadence,returns", [
    ("weekly, a few minutes later each week", [timedelta(days=7 * k, minutes=3 * k) for k in range(1, 9)]),
    ("monthly, on the 1st", [datetime(2026, m, 1, 3, 30, tzinfo=UTC) - datetime(2026, 4, 1, 3, 30, tzinfo=UTC)
                             for m in range(5, 11)]),
])
def test_an_acknowledged_periodic_warning_stays_owned_at_its_cadence(cadence, returns):
    # A weekly or monthly job's known warning is one defect with an owner:
    # each run's return is not a new episode that strips the acknowledgement.
    issue = _fold([_occ(T0)])
    issue.update(status="acknowledged", task="SA-016")
    for gap in returns:
        issue = eb.apply_occurrence(issue, _occ(T0 + gap), P)
        assert issue["status"] == "acknowledged" and issue["regressions"] == 0, (cadence, gap)
    assert issue["task"] == "SA-016"


def test_an_acknowledged_issue_regresses_after_more_than_a_month_of_quiet():
    issue = _fold([_occ(T0)])
    issue.update(status="acknowledged", task="SA-016")
    month = eb.apply_occurrence(issue, _occ(T0 + timedelta(days=31)), P)
    assert month["status"] == "acknowledged"
    back = eb.apply_occurrence(month, _occ(T0 + timedelta(days=31 + P.ack_quiet_days)), P)
    assert back["status"] == "open" and back["regressions"] == 1 and back["task"] == "SA-016"
    cls = eb.classify(back, T0 + timedelta(days=31 + P.ack_quiet_days, hours=1), None, P)
    assert cls["state"] == "regressed" and cls["attention"]


def test_an_acknowledged_issue_that_spikes_still_needs_attention():
    issue = _daily([5] * 14 + [40])
    issue["status"] = "acknowledged"
    cls = eb.classify(issue, T0 + timedelta(days=14, hours=2), None, P)
    assert issue["status"] == "acknowledged" and cls["spiking"] and cls["attention"]


def test_fixed_issue_reopens_on_a_later_occurrence_only():
    issue = _fold([_occ(T0)])
    fixed_at = T0 + timedelta(days=1)
    issue.update(status="fixed", fixed_at=fixed_at.isoformat())
    late_ingested = eb.apply_occurrence(issue, _occ(fixed_at - timedelta(minutes=5)), P)
    assert late_ingested["status"] == "fixed"           # logged before the fix took effect
    recurred = eb.apply_occurrence(late_ingested, _occ(fixed_at + timedelta(hours=2)), P)
    assert recurred["status"] == "open" and recurred["fixed_at"] is None
    assert eb.classify(recurred, fixed_at + timedelta(hours=3), None, P)["state"] == "regressed"


@pytest.mark.parametrize("days_after_fix,coverage_days,expected", [
    (3, 3, "pending"),            # window not over
    (8, 7.5, "verified"),         # window over, archive read past its end
    (8, 6, "unobserved"),         # window over, but the archive stops inside it
    (30, None, "unobserved"),     # no archive coverage at all
])
def test_a_fix_is_verified_only_by_measured_coverage(days_after_fix, coverage_days, expected):
    issue = _fold([_occ(T0)])
    issue.update(status="fixed", fixed_at=T0.isoformat())
    cov = None if coverage_days is None else T0 + timedelta(days=coverage_days)
    assert eb.classify(issue, T0 + timedelta(days=days_after_fix), cov, P)["verification"] == expected


# The F21 case: a fix deployed Monday 08:00 IST; the warning is back Monday
# 20:00; the owner marks it fixed on Wednesday "from Monday 08:00". The same
# rows must give the same outcome whether the registry read them before the
# mark or after it: a fix the archive contradicts is never `fixed, verified`.
_MON = datetime(2026, 10, 5, 2, 30, tzinfo=UTC)                  # 08:00 IST
_FIX_MSG = "[feedback] malformed miss factor for TICK{}X: weight {}.5 out of range"


def _run_order(tmp_path, name, order, prior_status, recurrence, after=None):
    """Insert rows into a real archive in time order, reading (refresh) and
    marking (triage) in `order`; return the final issue, its class and digest.
    `after`: the recurrences' delays after the fix time (default 12 h and 1 day)."""
    arch = _archive(tmp_path / f"{name}.db")
    reg = eb.open_registry(":memory:")
    fix_at = _MON
    before = [_MON - timedelta(days=1), _MON - timedelta(hours=2)]
    if after is None:
        after = [timedelta(hours=12), timedelta(days=1)] if recurrence else []
    after = [_MON + d for d in after]
    mark_at = _MON + timedelta(days=2)
    final = _MON + timedelta(days=12)

    def add(ts, k):
        _add(arch, ts, "WARNING", "core.feedback", _FIX_MSG.format(k, k))

    for k, ts in enumerate(before):
        add(ts, k)
    eb.refresh(reg, source_conn=arch, p=P, now=before[-1] + timedelta(minutes=1))
    fp = eb.issues(reg)[0]["fingerprint"]
    if prior_status != "open":
        eb.triage(fp, status=prior_status, task="SA-016", conn=reg, now=before[-1])
    read_first = {"read_all_then_mark": len(after), "mark_then_read": 0,
                  "read_some_then_mark": min(1, len(after))}[order]
    for k, ts in enumerate(after[:read_first]):
        add(ts, 10 + k)
    eb.refresh(reg, source_conn=arch, p=P, now=mark_at)
    refused = None
    try:
        eb.triage(fp, status="fixed", fixed_at=fix_at.isoformat(), conn=reg, now=mark_at)
    except eb.TriageError as exc:
        refused = str(exc)
    for k, ts in enumerate(after[read_first:]):
        add(ts, 20 + k)
    _add(arch, final - timedelta(days=1), "WARNING", "core.other", "[other] archive keeps going")
    eb.refresh(reg, source_conn=arch, p=P, now=final)
    (issue,) = [i for i in eb.issues(reg) if i["fingerprint"] == fp]
    cls = eb.classify(issue, final, eb.coverage(reg), P)
    digest = eb.build_digest(eb.issues(reg), final, eb.coverage(reg), P)
    return issue, cls, digest, refused


_ORDERS = ("read_all_then_mark", "mark_then_read", "read_some_then_mark")


@pytest.mark.parametrize("prior_status", ["open", "acknowledged"])
def test_a_recorded_recurrence_after_the_fix_time_never_verifies_whatever_the_read_order(
        tmp_path, prior_status):
    outcomes = {o: _run_order(tmp_path, o, o, prior_status, recurrence=True) for o in _ORDERS}
    for order, (issue, cls, digest, refused) in outcomes.items():
        assert issue["status"] != "fixed" and cls["verification"] is None, order
        assert "[fixed," not in digest, order                # no line claims a fix
        assert issue["count"] == 4 and issue["task"] == ("SA-016" if prior_status != "open" else None)
    # the evidence is the same whatever the order
    assert len({(i["count"], i["last_seen"], i["first_seen"]) for i, *_ in outcomes.values()}) == 1
    # read before the mark: refused, naming when the issue was last seen, in
    # IST (Tue 08:00 IST) and in the form fixed_at accepts
    _, _, _, refused = outcomes["read_all_then_mark"]
    assert refused and "last seen" in refused and "did not hold" in refused
    assert "last seen at 2026-10-06T08:00:00+05:30" in refused
    assert "after fixed_at 2026-10-05T08:00:00+05:30" in refused
    # read after the mark: the recurrence reopens it
    issue, *_ = outcomes["mark_then_read"]
    assert issue["status"] == "open" and issue["regressions"] == 1


@pytest.mark.parametrize("prior_status", ["open", "acknowledged"])
def test_with_no_recurrence_every_read_order_verifies_the_fix(tmp_path, prior_status):
    for order in _ORDERS:
        issue, cls, digest, refused = _run_order(tmp_path, order, order, prior_status,
                                                 recurrence=False)
        assert refused is None, (order, refused)
        assert issue["status"] == "fixed" and cls["verification"] == "verified", order
        assert "fixed, verified" in digest


@pytest.mark.parametrize("delay", [timedelta(milliseconds=400), timedelta(microseconds=1),
                                   timedelta(seconds=1)])
def test_a_recurrence_within_a_second_of_the_fix_time_never_verifies_whatever_the_read_order(
        tmp_path, delay):
    # A fix at 08:00:00 and the warning back 0.4 s (or 1 us) later, in the
    # same second: still after the fix, read before the mark or after it.
    outcomes = {o: _run_order(tmp_path, f"{o}_{delay.microseconds}_{delay.seconds}", o, "open",
                              True, after=[delay]) for o in _ORDERS}
    for order, (issue, cls, digest, refused) in outcomes.items():
        assert issue["status"] != "fixed" and cls["verification"] is None, order
        assert "[fixed," not in digest and issue["count"] == 3, order
    assert outcomes["read_all_then_mark"][3] is not None              # refused
    assert outcomes["mark_then_read"][0]["regressions"] == 1          # reopened


def test_owner_marks_a_fix_now_and_the_warning_returns_within_the_same_second(tmp_path):
    # The default fix time is now; a row logged a moment later reopens it.
    arch = _archive(tmp_path / "t.db")
    _add(arch, T0, "WARNING", "core.x", "[x] boom")
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(milliseconds=100))
    fp = eb.issues(reg)[0]["fingerprint"]
    eb.triage(fp, status="fixed", conn=reg, now=T0 + timedelta(milliseconds=200))
    _add(arch, T0 + timedelta(milliseconds=300), "WARNING", "core.x", "[x] boom")
    eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(milliseconds=400))
    (issue,) = eb.issues(reg)
    assert issue["status"] == "open" and issue["regressions"] == 1


# A fix time is an instant: the owner reads the app in IST, a machine caller
# may think in UTC. 08:00 IST on Mon 5 Oct is 02:30 UTC.
_SAME_INSTANT = ("2026-10-05T08:00+05:30", "2026-10-05T08:00:00.000+05:30",
                 "2026-10-05T02:30Z", "2026-10-05T02:30:00+00:00")


def _one_issue_registry(tmp_path, name):
    arch = _archive(tmp_path / f"{name}.db")
    _add(arch, _MON - timedelta(days=1), "WARNING", "core.x", "[x] boom")
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=arch, p=P, now=_MON + timedelta(days=2))
    return reg, eb.issues(reg)[0]


@pytest.mark.parametrize("given", _SAME_INSTANT)
def test_the_same_instant_in_any_offset_notation_is_the_same_fix(tmp_path, given):
    reg, before = _one_issue_registry(tmp_path, "n")
    fixed = eb.triage(before["fingerprint"], status="fixed", fixed_at=given, conn=reg,
                      now=_MON + timedelta(days=2))
    assert fixed["fixed_at"] == "2026-10-05T02:30:00+00:00"


@pytest.mark.parametrize("given,shown", [
    ("2026-10-05T08:00", "2026-10-05T08:00+05:30"),          # the app's IST clock, typed bare
    ("2026-10-05T08:00:15", "2026-10-05T08:00:15+05:30"),
    ("2026-10-05", "2026-10-05T00:00+05:30"),                # a date alone
])
def test_a_fix_time_without_an_offset_is_refused_and_changes_nothing(tmp_path, given, shown):
    reg, before = _one_issue_registry(tmp_path, "bare")
    with pytest.raises(eb.TriageError, match="no UTC offset") as refused:
        eb.triage(before["fingerprint"], status="fixed", task="SA-016", fixed_at=given,
                  conn=reg, now=_MON + timedelta(days=2))
    assert shown in str(refused.value)                       # it shows the form to give
    assert eb.issues(reg) == [before]                        # not even the task was written


def test_a_fix_time_before_last_seen_is_refused_and_changes_nothing(tmp_path):
    arch = _archive(tmp_path / "t.db")
    for k in range(3):
        _add(arch, T0 + timedelta(days=k), "WARNING", "core.x", f"[x] boom {k}")
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(days=3))
    (before,) = eb.issues(reg)
    with pytest.raises(eb.TriageError, match="last seen"):
        eb.triage(before["fingerprint"], status="fixed", task="SA-016",
                  fixed_at=(T0 + timedelta(days=1, hours=1)).isoformat(),
                  conn=reg, now=T0 + timedelta(days=3))
    assert eb.issues(reg) == [before]                     # not even the task was written
    # the fix time of a later fix, after the last occurrence, is accepted
    ok = eb.triage(before["fingerprint"], status="fixed",
                   fixed_at=(T0 + timedelta(days=2, hours=1)).isoformat(),
                   conn=reg, now=T0 + timedelta(days=3))
    assert ok["status"] == "fixed"
    # and an already-fixed issue cannot be backdated past its own evidence
    with pytest.raises(eb.TriageError, match="last seen"):
        eb.triage(before["fingerprint"], status="fixed", fixed_at=T0.isoformat(), conn=reg,
                  now=T0 + timedelta(days=3))


def test_a_future_fix_time_is_refused_beyond_a_small_clock_tolerance(tmp_path):
    arch = _archive(tmp_path / "t.db")
    _add(arch, T0, "WARNING", "core.x", "[x] boom")
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(hours=1))
    fp = eb.issues(reg)[0]["fingerprint"]
    now = T0 + timedelta(hours=1)
    for ahead in (timedelta(hours=1), timedelta(days=30)):
        with pytest.raises(eb.TriageError, match="future") as refused:
            eb.triage(fp, status="fixed", fixed_at=(now + ahead).isoformat(), conn=reg, now=now)
        assert "(now 2026-10-05T10:30:00+05:30)" in str(refused.value)     # IST
    assert eb.issues(reg)[0]["status"] == "open"
    ok = eb.triage(fp, status="fixed", fixed_at=(now + timedelta(minutes=2)).isoformat(),
                   conn=reg, now=now)                     # a client clock slightly ahead
    assert ok["status"] == "fixed"


def test_a_fix_contradicted_by_its_own_last_seen_is_never_verified():
    # Defence in depth: ingestion and triage never store this, a hand edit could.
    now = T0 + timedelta(days=20)
    issue = _fold([_occ(T0), _occ(T0 + timedelta(days=2))])
    issue.update(status="fixed", fixed_at=(T0 + timedelta(days=1)).isoformat())
    cls = eb.classify(issue, now, now, P)
    assert cls["verification"] == "recurred" and cls["attention"]
    assert eb.is_protected(issue, cls) and eb._listed_active(issue, cls)
    digest = eb.build_digest([issue], now, now, P)
    assert "fixed, verified" not in digest and "Needs attention:\n  [fixed, recurred]" in digest


def test_the_digest_reads_first_last_and_fix_times_in_ist():
    # Around IST midnight the UTC date is the day before: 20:00 UTC on 4 Oct
    # is 01:30 IST on 5 Oct.
    issue = _fold([_occ(datetime(2026, 10, 4, 20, 0, tzinfo=UTC)),
                   _occ(datetime(2026, 10, 5, 21, 0, tzinfo=UTC))])      # 6 Oct 02:30 IST
    issue.update(status="fixed", fixed_at="2026-10-05T21:30:00+00:00")  # 6 Oct 03:00 IST
    now = datetime(2026, 10, 7, 4, 30, tzinfo=UTC)
    digest = eb.build_digest([issue], now, now, P)
    assert digest.startswith("Error backlog — 2026-10-07 10:00 IST")
    assert "first 2026-10-05, last 2026-10-06 02:30 IST;" in digest
    assert "; status fixed since 2026-10-06 03:00 IST" in digest


def _daily(counts: list[int], start: datetime = T0):
    occs = []
    for d, n in enumerate(counts):
        occs += [_occ(start + timedelta(days=d, minutes=m)) for m in range(n)]
    return _fold(occs)


def test_spike_against_its_own_baseline():
    steady_then_burst = _daily([5] * 14 + [40])
    now = T0 + timedelta(days=14, hours=2)
    assert eb.classify(steady_then_burst, now, None, P)["spiking"]
    assert not eb.classify(_daily([40] * 15), now, None, P)["spiking"]       # its normal
    assert not eb.classify(_daily([0] * 14 + [8]), now, None, P)["spiking"]   # below spike_min
    first_day = _daily([50], start=now - timedelta(hours=1))
    cls = eb.classify(first_day, now, None, P)
    assert not cls["spiking"] and cls["state"] == "new"                      # too little history


def test_wontfix_counts_but_never_asks_or_reopens():
    issue = _fold([_occ(T0)])
    issue["status"] = "wontfix"
    later = _fold([_occ(T0 + timedelta(days=20 + k)) for k in range(3)], issue)
    assert later["status"] == "wontfix" and later["count"] == 4
    assert not eb.classify(later, T0 + timedelta(days=22, hours=1), None, P)["attention"]


# ---------------------------------------------------------------------------
# ingestion
# ---------------------------------------------------------------------------

@pytest.fixture()
def busy_archive(tmp_path):
    arch = _archive(tmp_path / "telemetry.db")
    rng = random.Random(11)
    for k in range(400):
        cause = rng.choice(["[a] timeout after 30s for MARUTI.NS", "[b] HTTP 429 from provider",
                            "[c] no envelope for WELCORP on 2026-10-05"])
        _add(arch, T0 + timedelta(minutes=k), rng.choice(["WARNING", "ERROR"]), "core.x",
             cause, run_id=f"r{k}")
    return arch


def _snapshot(reg):
    return sorted((i["fingerprint"], i["count"], i["first_seen"], i["last_seen"], i["max_level"])
                  for i in eb.issues(reg))


def test_refresh_is_idempotent_and_never_changes_app_logs(busy_archive):
    before = busy_archive.execute("SELECT * FROM app_logs ORDER BY id").fetchall()
    reg = eb.open_registry(":memory:")
    first = eb.refresh(reg, source_conn=busy_archive, p=P, now=T0 + timedelta(days=1))
    again = eb.refresh(reg, source_conn=busy_archive, p=P, now=T0 + timedelta(days=1))
    assert first["ingested"] == 400 and again["ingested"] == 0 and again["caught_up"]
    assert sum(i["count"] for i in eb.issues(reg)) == 400 and len(eb.issues(reg)) == 3
    assert busy_archive.execute("SELECT * FROM app_logs ORDER BY id").fetchall() == before


def test_result_does_not_depend_on_batch_size_or_read_cap(busy_archive):
    whole = eb.open_registry(":memory:")
    eb.refresh(whole, source_conn=busy_archive, p=P, now=T0 + timedelta(days=1))
    pieces = eb.open_registry(":memory:")
    small = replace(P, batch_rows=7, max_rows_per_refresh=60)
    calls = 0
    while True:
        calls += 1
        s = eb.refresh(pieces, source_conn=busy_archive, p=small, now=T0 + timedelta(days=1))
        if s["caught_up"]:
            break
        assert s["read"] == 60
    assert calls == 7 and _snapshot(pieces) == _snapshot(whole)


def test_two_writers_never_count_a_row_twice(tmp_path, busy_archive):
    path = tmp_path / "telemetry.db"
    regs = [eb.open_registry(path), eb.open_registry(path)]
    srcs = [sqlite3.connect(str(path), check_same_thread=False) for _ in regs]
    small = replace(P, batch_rows=5)
    errors: list[BaseException] = []

    # Two uvicorn workers are two processes: each has its own in-process lock,
    # so only the database transaction keeps them apart. The unwrapped refresh
    # models that (the hermetic guard forbids real test subprocesses).
    refresh_in_another_process = eb.refresh.__wrapped__

    def run(k):
        try:
            refresh_in_another_process(regs[k], source_conn=srcs[k], p=small,
                                       now=T0 + timedelta(days=1))
        except BaseException as exc:      # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(k,)) for k in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sum(i["count"] for i in eb.issues(regs[0])) == 400


def test_concurrent_reads_in_one_worker_share_its_connection_safely(tmp_path, monkeypatch,
                                                                     busy_archive):
    # The routes run in a thread pool over one shared connection, as in a
    # uvicorn worker; SQLite cannot open a second BEGIN on it.
    shared = eb.open_registry(tmp_path / "telemetry.db")
    monkeypatch.setattr(eb, "_conn", shared)
    small = replace(P, batch_rows=3)
    errors: list[BaseException] = []
    results: list[dict] = []
    gate = threading.Barrier(4)

    def read():
        try:
            gate.wait()
            results.append(eb.report(include="all", limit=10, p=small,
                                     now=T0 + timedelta(days=1)))
        except BaseException as exc:      # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert sum(r["refresh"]["ingested"] for r in results) == 400
    assert sum(i["count"] for i in eb.issues(shared)) == 400


def test_pre_e1_archive_and_missing_archive_are_readable(tmp_path):
    old = sqlite3.connect(str(tmp_path / "old.db"), isolation_level=None)
    old.execute("CREATE TABLE app_logs (id INTEGER PRIMARY KEY, ts TEXT, level TEXT, "
                "logger TEXT, message TEXT)")
    old.execute("INSERT INTO app_logs (ts, level, logger, message) VALUES (?, ?, ?, ?)",
                (T0.isoformat(), "ERROR", "core.x",
                 "2026-07-02 13:04:45 IST ERROR    [core.x] boom 1"))
    reg = eb.open_registry(":memory:")
    assert eb.refresh(reg, source_conn=old, p=P, now=T0)["ingested"] == 1
    empty = sqlite3.connect(":memory:")
    assert eb.refresh(eb.open_registry(":memory:"), source_conn=empty, p=P, now=T0) == {
        "read": 0, "ingested": 0, "skipped": 0, "caught_up": True, "pruned": 0}


# ---------------------------------------------------------------------------
# retention
# ---------------------------------------------------------------------------

def _issue(fp: str, last: datetime, status: str = "open", **kw) -> dict:
    base = _fold([_occ(last)])
    base.update(fingerprint=fp, status=status, first_seen=(last - timedelta(days=1)).isoformat(),
                last_seen=last.isoformat(), **kw)
    return base


def test_retention_prunes_only_inactive_issues():
    now = T0 + timedelta(days=200)
    old = now - timedelta(days=120)
    issues = [
        _issue("a" * 16, old),                                         # inactive: pruned
        _issue("b" * 16, old, "wontfix"),                              # inactive: pruned
        _issue("c" * 16, old, "acknowledged"),                         # someone owns it
        _issue("d" * 16, old, "fixed", fixed_at=(now - timedelta(days=2)).isoformat()),
        _issue("e" * 16, old, "fixed", fixed_at=(old + timedelta(days=1)).isoformat()),
        _issue("f" * 16, now - timedelta(days=30)),                    # recent enough
    ]
    cov = now - timedelta(hours=1)
    assert eb.select_prunable(issues, now, cov, P) == ["a" * 16, "b" * 16, "e" * 16]


def test_the_cap_drops_the_stalest_quiet_issues_and_never_an_active_one():
    now = T0 + timedelta(days=200)
    attention = [_issue(f"{k:016x}", now - timedelta(hours=k + 1)) for k in range(5)]
    ongoing = _issue(f"{50:016x}", now - timedelta(days=3))
    ongoing["first_seen"] = (now - timedelta(days=40)).isoformat()
    quiet = [_issue(f"{100 + k:016x}", now - timedelta(days=20 + k)) for k in range(4)]
    issues = attention + [ongoing] + quiet
    assert eb.classify(ongoing, now, now, P)["state"] == "ongoing"
    drop = eb.select_prunable(issues, now, now, replace(P, max_issues=8))
    assert drop == sorted([quiet[3]["fingerprint"], quiet[2]["fingerprint"]])  # stalest two
    tiny = eb.select_prunable(issues, now, now, replace(P, max_issues=1))
    assert set(tiny) == {i["fingerprint"] for i in quiet}         # over the cap, not over an active one


def test_prune_runs_inside_refresh_and_keeps_raw_rows(tmp_path):
    arch = _archive(tmp_path / "t.db")
    _add(arch, T0, "WARNING", "core.x", "[x] ancient cause")
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(hours=1))
    s = eb.refresh(reg, source_conn=arch, p=P, now=T0 + timedelta(days=200))
    assert s["pruned"] == 1 and eb.issues(reg) == []
    assert arch.execute("SELECT COUNT(*) FROM app_logs").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# deterministic digest
# ---------------------------------------------------------------------------

def test_digest_is_the_same_bytes_for_the_same_registry_and_clock(busy_archive):
    reg = eb.open_registry(":memory:")
    now = T0 + timedelta(days=1)
    eb.refresh(reg, source_conn=busy_archive, p=P, now=now)
    issues = eb.issues(reg)
    texts = set()
    for seed in range(5):
        shuffled = issues[:]
        random.Random(seed).shuffle(shuffled)
        texts.add(eb.build_digest(shuffled, now, eb.coverage(reg), P))
    assert len(texts) == 1
    other = eb.open_registry(":memory:")
    eb.refresh(other, source_conn=busy_archive, p=replace(P, batch_rows=3), now=now)
    assert eb.build_digest(eb.issues(other), now, eb.coverage(other), P) in texts


# ---------------------------------------------------------------------------
# real capture: the log handler, real tracebacks, real outbox dead letters
# ---------------------------------------------------------------------------

@pytest.fixture()
def captured(tmp_path, monkeypatch):
    """A real SQLiteLogHandler writing to a temporary telemetry.db."""
    db = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db), raising=False)
    if log_store._conn is not None:
        log_store._conn.close()
    log_store._conn = None
    handler = log_store.SQLiteLogHandler(level=logging.WARNING)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    # Exactly one archive handler, as configure_logging guarantees: an earlier
    # test in the same process may have left one on the root logger.
    monkeypatch.setattr(root, "handlers", [h for h in root.handlers
                                           if not isinstance(h, log_store.SQLiteLogHandler)]
                        + [handler])
    yield db
    if log_store._conn is not None:
        log_store._conn.close()
    log_store._conn = None


def _site_a(x):
    return float(x)


def _site_b(x):
    return _site_a(x)


def test_real_tracebacks_from_two_call_sites_group(captured):
    log = logging.getLogger("tests.sa011.sites")
    for fn, value in ((_site_a, "MARUTI"), (_site_b, "INFY"), (_site_b, "TATAMOTORS")):
        try:
            fn(value)
        except ValueError:
            log.error("[job] price for %s is not a number", value, exc_info=True)
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=sqlite3.connect(str(captured)), p=P,
               now=datetime.now(UTC))
    (issue,) = [i for i in eb.issues(reg) if i["logger"] == "tests.sa011.sites"]
    assert issue["count"] == 3 and "ValueError" in issue["template"]


def test_real_capture_inside_and_outside_a_run_is_one_issue(captured):
    # The real handler stamps run id and ticker from the real run_context.
    log = logging.getLogger("tests.sa011.runs")
    with log_store.run_context("6f1c2a90"):
        log_store.set_run_ticker("MARUTI")
        log.warning("$%s.NS: possibly delisted; no price data found (period=1d)", "MARUTI")
    log.warning("$%s.NS: possibly delisted; no price data found (period=5d)", "INFY")
    rows = sqlite3.connect(str(captured)).execute(
        "SELECT run_id, ticker FROM app_logs WHERE logger = 'tests.sa011.runs' ORDER BY id").fetchall()
    assert rows == [("6f1c2a90", "MARUTI"), (None, None)]
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=sqlite3.connect(str(captured)), p=P, now=datetime.now(UTC))
    (issue,) = [i for i in eb.issues(reg) if i["logger"] == "tests.sa011.runs"]
    assert issue["count"] == 2 and issue["tickers"] == ["MARUTI"]


def test_outbox_dead_letters_become_one_issue_per_channel_and_reason(captured, tmp_path,
                                                                      monkeypatch):
    from core.config import settings
    from core.delivery import outbox
    from core.delivery.channels import SendResult
    from services.data.stores import atlas_store
    monkeypatch.setattr(atlas_store, "_DB_PATH", tmp_path / "atlas.db")
    monkeypatch.setattr(atlas_store, "_conn_holder", {"conn": None})
    atlas_store._reset_for_tests()
    monkeypatch.setenv("ATLAS_ENABLED", "true")
    monkeypatch.setattr(settings, "DELIVERY_DATA_DIR", str(tmp_path / "delivery"), raising=False)
    conn = atlas_store._get_conn()
    for uid in ("primary", "u_a1b2c3d4"):
        conn.execute("INSERT OR IGNORE INTO users (user_id, email, pw_hash, created_at,"
                     " consent_at) VALUES (?,?,?,?,?)",
                     (uid, f"{uid}@example.com", "h", "2026-01-01T00:00:00+00:00",
                      "2026-01-01T00:00:00+00:00"))
    conn.commit()
    reasons = {"email": "permanent: SMTP authentication failed (535): check SMTP_PASSWORD",
               "push": "permanent: push subscription gone (410)"}
    monkeypatch.setattr(outbox, "_send_row",
                        lambda row: SendResult(reason=reasons[row["channel"]], permanent=True))
    n = 0
    for uid in ("primary", "u_a1b2c3d4"):
        for channel in ("email", "push", "email"):
            n += 1
            outbox.enqueue(uid, channel, "brief", json.dumps(
                {"title": "Brief", "body": f"secret holdings of {uid}", "url": "/"}), f"k{n}")
    assert outbox.drain_once()["dead"] == 6
    reg = eb.open_registry(":memory:")
    eb.refresh(reg, source_conn=sqlite3.connect(str(captured)), p=P, now=datetime.now(UTC))
    dead = sorted((i["template"], i["count"]) for i in eb.issues(reg)
                  if i["logger"] == "core.delivery.outbox")
    assert [c for _, c in dead] == [4, 2]
    assert "(email/brief)" in dead[0][0] and "check SMTP_PASSWORD" in dead[0][0]
    assert "(push/brief)" in dead[1][0]
    blob = json.dumps(eb.issues(reg))
    assert "secret holdings" not in blob and "a1b2c3d4" not in blob
    atlas_store._reset_for_tests()


# ---------------------------------------------------------------------------
# the API: owner only, and usable to assign and close a real defect
# ---------------------------------------------------------------------------

@pytest.fixture()
def api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.config import settings
    from services.api.routes import ops_api
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    monkeypatch.setenv("SCHEDULER_KEY", "machine-key-for-tests")
    db = tmp_path / "telemetry.db"
    arch = _archive(db)
    reg = eb.open_registry(db)
    monkeypatch.setattr(eb, "_conn", reg)
    owner = user_store.create_user("o@example.invalid", "pw-for-tests-1", "O", role="owner",
                                   user_id="primary")
    member = user_store.create_user("m@example.invalid", "pw-for-tests-1", "M")
    app = FastAPI()
    app.include_router(ops_api.router)
    client = TestClient(app)
    tokens = {"owner": user_store.create_session(owner["user_id"], True),
              "member": user_store.create_session(member["user_id"], True)}
    yield client, tokens, arch
    reg.close()
    if user_store._conn_holder.get("conn") is not None:
        user_store._conn_holder["conn"].close()


def _auth(tokens, who):
    return {"Authorization": f"Bearer {tokens[who]}"} if who in tokens else {}


@pytest.mark.parametrize("method,path", [
    ("get", "/ops/errors"), ("get", "/ops/errors/digest"),
    ("post", "/ops/errors/0123456789abcdef"),
])
@pytest.mark.parametrize("who,code", [("member", 403), ("anonymous", 401)])
def test_only_the_owner_or_machine_can_read_or_triage(api, method, path, who, code):
    client, tokens, arch = api
    _add(arch, datetime.now(UTC), "ERROR", "core.x", "[x] something private-ish 42")
    kwargs = {"json": {"status": "acknowledged"}} if method == "post" else {}
    resp = getattr(client, method)(path, headers=_auth(tokens, who), **kwargs)
    assert resp.status_code == code
    assert "private-ish" not in resp.text


def test_owner_assigns_fixes_and_sees_a_regression_through_http(api):
    client, tokens, arch = api
    now = datetime.now(UTC)
    for k in range(3):
        _add(arch, now - timedelta(minutes=30 - k), "ERROR", "core.feedback",
             f"[feedback] malformed miss factor for TICK{k}X: weight {k}.5 out of range")
    owner = _auth(tokens, "owner")
    listed = client.get("/ops/errors", headers=owner).json()
    (issue,) = listed["issues"]
    assert issue["count"] == 3 and issue["state"] == "new" and issue["attention"]
    fp = issue["fingerprint"]

    r = client.post(f"/ops/errors/{fp}", headers=owner,
                    json={"status": "acknowledged", "assignee": "owner", "task": "SA-016"})
    assert r.status_code == 200 and r.json()["assignee"] == "owner" and not r.json()["attention"]
    fixed_at = (now - timedelta(minutes=5)).isoformat()
    r = client.post(f"/ops/errors/{fp}", headers=owner, json={"status": "fixed", "fixed_at": fixed_at})
    assert r.json()["status"] == "fixed" and r.json()["verification"] == "pending"
    by_key = client.get("/ops/errors?include=all",
                        headers={"X-Scheduler-Key": "machine-key-for-tests"}).json()
    assert by_key["issues"][0]["status"] == "fixed"

    _add(arch, now, "ERROR", "core.feedback",
         "[feedback] malformed miss factor for TICK9X: weight 9.5 out of range")
    after = client.get("/ops/errors", headers=owner).json()["issues"][0]
    assert after["fingerprint"] == fp and after["status"] == "open"
    assert after["state"] == "regressed" and after["regressions"] == 1 and after["count"] == 4
    assert after["task"] == "SA-016"                                 # the assignment survives
    digest = client.get("/ops/errors/digest", headers=owner)
    assert digest.status_code == 200 and "[regressed]" in digest.text and fp in digest.text


@pytest.mark.parametrize("path,body,code", [
    ("/ops/errors/ffffffffffffffff", {"status": "fixed"}, 404),
    ("/ops/errors/not-a-fingerprint", {"status": "fixed"}, 422),
    ("/ops/errors/{fp}", {"status": "closed"}, 422),
    ("/ops/errors/{fp}", {"note": "x" * 501}, 422),
    ("/ops/errors/{fp}", {"status": "acknowledged", "fixed_at": "2026-10-05T00:00:00+00:00"}, 422),
    ("/ops/errors/{fp}", {"status": "fixed", "fixed_at": "yesterday"}, 422),
    ("/ops/errors/{fp}", {"status": "fixed", "fixed_at": "2099-01-01T00:00:00+00:00"}, 422),
    ("/ops/errors/{fp}", {"status": "fixed", "fixed_at": "2026-10-05T08:00"}, 422),
    ("/ops/errors/{fp}", {"status": "fixed", "fixed_at": "2026-10-05"}, 422),
])
def test_triage_refuses_what_it_cannot_record(api, path, body, code):
    client, tokens, arch = api
    _add(arch, datetime.now(UTC), "ERROR", "core.x", "[x] boom")
    owner = _auth(tokens, "owner")
    fp = client.get("/ops/errors", headers=owner).json()["issues"][0]["fingerprint"]
    assert client.post(path.format(fp=fp), headers=owner, json=body).status_code == code


def _ist_wall(ts: datetime) -> datetime:
    """The IST wall clock the app shows for `ts`, with no offset attached."""
    return (ts.astimezone(UTC) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)


def test_a_backdated_fix_over_a_recorded_recurrence_is_refused_through_http(api):
    client, tokens, arch = api
    now = datetime.now(UTC)
    deployed = now - timedelta(days=2)
    recurred = deployed + timedelta(hours=12)                         # back after the fix
    for ts in (now - timedelta(days=3), recurred):
        _add(arch, ts, "WARNING", "core.feedback", "[feedback] malformed miss factor for TICK1X")
    owner = _auth(tokens, "owner")
    (issue,) = client.get("/ops/errors", headers=owner).json()["issues"]
    r = client.post(f"/ops/errors/{issue['fingerprint']}", headers=owner,
                    json={"status": "fixed", "fixed_at": deployed.isoformat()})
    assert r.status_code == 422
    last_seen_ist = _ist_wall(recurred).isoformat() + "+05:30"
    assert f"last seen at {last_seen_ist}" in r.json()["detail"]
    assert "did not hold" in r.json()["detail"]
    (after,) = client.get("/ops/errors?include=all", headers=owner).json()["issues"]
    assert after["status"] == "open" and after["fixed_at"] is None and after["verification"] is None


def test_a_fix_time_typed_from_the_ist_clock_without_an_offset_is_refused_through_http(api):
    """The RR-M1 case: a fix deployed 9 days ago at 08:00-ish IST; the warning
    came back 2 hours later and the registry read it. The owner types the
    deploy time as the app shows it, with no offset. Read as UTC it would
    file the fix 5.5 hours late, after the recurrence, and verify a fix that
    did not hold."""
    client, tokens, arch = api
    now = datetime.now(UTC)
    deployed = (now - timedelta(days=9)).replace(second=0, microsecond=0)
    for ts in (deployed - timedelta(days=1), deployed + timedelta(hours=2)):
        _add(arch, ts, "WARNING", "core.feedback", "[feedback] malformed miss factor for TICK1X")
    _add(arch, now - timedelta(hours=1), "WARNING", "core.other", "[other] archive alive")
    owner = _auth(tokens, "owner")
    (issue,) = [i for i in client.get("/ops/errors?include=all", headers=owner).json()["issues"]
                if i["logger"] == "core.feedback"]
    fp = issue["fingerprint"]
    typed = _ist_wall(deployed).isoformat(timespec="minutes")         # e.g. 2026-10-03T08:00

    for bare in (typed, typed[:10]):                                  # the time; the date alone
        r = client.post(f"/ops/errors/{fp}", headers=owner,
                        json={"status": "fixed", "fixed_at": bare})
        assert r.status_code == 422, (bare, r.text)
        assert "no UTC offset" in r.json()["detail"] and "+05:30" in r.json()["detail"]
    assert f"{typed}+05:30" in client.post(f"/ops/errors/{fp}", headers=owner, json={
        "status": "fixed", "fixed_at": typed}).json()["detail"]       # the form to give

    # The same time with its offset is the real fix time: refused, it did not hold.
    r = client.post(f"/ops/errors/{fp}", headers=owner,
                    json={"status": "fixed", "fixed_at": f"{typed}+05:30"})
    assert r.status_code == 422 and "last seen" in r.json()["detail"]
    listed = client.get("/ops/errors?include=all", headers=owner).json()["issues"]
    (after,) = [i for i in listed if i["fingerprint"] == fp]          # nothing was recorded
    assert after["status"] == "open" and after["fixed_at"] is None
    assert "fixed, verified" not in client.get("/ops/errors/digest", headers=owner).text

    # A later fix (an hour after the recurrence), given in UTC with Z, is
    # accepted; with no row of the cause since, and the archive read past
    # its 7-day window, it is verified.
    later = (deployed + timedelta(hours=3)).astimezone(UTC).replace(tzinfo=None)
    r = client.post(f"/ops/errors/{fp}", headers=owner,
                    json={"status": "fixed", "fixed_at": later.isoformat() + "Z"})
    assert r.status_code == 200 and r.json()["status"] == "fixed"
    assert r.json()["fixed_at"] == later.isoformat() + "+00:00"
    assert r.json()["verification"] == "verified"


def test_unknown_ops_paths_are_api_404s_not_the_app_page():
    from fastapi.testclient import TestClient
    from services.api.server import app
    client = TestClient(app, raise_server_exceptions=False)
    assert "text/html" in client.get("/").headers["content-type"]     # the catch-all is live
    for path in ("/ops/nope", "/ops/errors/0123456789abcdef"):     # the second is POST-only
        r = client.get(path)
        assert r.status_code == 404 and "text/html" not in r.headers.get("content-type", ""), path


# ---------------------------------------------------------------------------
# the watchdog check
# ---------------------------------------------------------------------------

def test_watchdog_check_names_no_template(monkeypatch):
    from core.ops.watchdog import checks
    issue = _fold([_occ(T0, "[x] user secret text 'abc' failed")])
    cls = eb.classify(issue, T0 + timedelta(hours=1), None, P)
    monkeypatch.setattr(checks, "_error_backlog_report", lambda: {
        "counts": {"attention": 1, "total": 1}, "coverage": None, "refresh": {"caught_up": True},
        "issues": [eb.public_issue(issue, cls)]})
    r = checks.run_check("error_backlog")
    assert r.state == "pending" and issue["fingerprint"] in r.detail
    assert issue["template"] not in r.detail and "secret" not in r.detail
    monkeypatch.setattr(checks, "_error_backlog_report", lambda: {
        "counts": {"attention": 0, "total": 4}, "issues": [], "refresh": {}})
    assert checks.run_check("error_backlog").state == "satisfied"


def test_one_registry_entry_enables_the_check_and_notifies_only_the_owner(monkeypatch):
    # FIX-008 registered the check once operator notices reached the owner
    # alone; test_operator_notices_owner_only_fix008.py drives it end to end.
    from core.config import settings
    from core.delivery import alerts
    from core.ops.watchdog import runner
    doc = yaml.safe_load((REPO / "config" / "milestones.yaml").read_text(encoding="utf-8"))
    using = [e["id"] for key in ("milestones", "invariants") for e in (doc.get(key) or [])
             if e.get("check") == "error_backlog"]
    assert len(using) == 1
    emitted: list[str] = []
    monkeypatch.setattr(alerts, "_owner_account_ids", lambda: [settings.PORTFOLIO_DEFAULT_USER_ID])
    monkeypatch.setattr(alerts, "_audience_push_store", lambda: type(
        "Subs", (), {"user_ids": lambda self: ["u_member01", settings.PORTFOLIO_DEFAULT_USER_ID]})())
    monkeypatch.setattr(alerts, "emit_alerts",
                        lambda events, user_id=None, **kw: emitted.append(user_id) or {})
    runner._broadcast([], "StockAgent ops alert")
    assert emitted == [settings.PORTFOLIO_DEFAULT_USER_ID]
