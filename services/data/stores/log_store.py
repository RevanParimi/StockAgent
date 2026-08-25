"""
services/data/stores/log_store.py
==================================
Permanent log + telemetry archive in SQLite, on the persistent volume.

Why: Railway console logs rotate per-deployment — every redeploy loses the
runtime history (that's why the 3-week investigation of 2026-07 could only
see one day of logs). The JSONL telemetry under outputs/llm_log/ lives on the
ephemeral container filesystem and dies with each deploy too. This store puts
both on data/ (the Railway volume, mounted at /app/data), so history survives
deploys indefinitely.

Tables
------
llm_calls : one row per LLM call (caller, model, tokens, latency, success)
            → permanent cost/reliability analytics across model swaps.
run_summaries : one row per completed analysis run (ticker, verdict, score,
            tokens, cost, errors) — mirrors data/logs/run_summaries.jsonl so the
            history is queryable and survives a redeploy.
data_health : one row per run describing what that run actually received —
            per-section fetch outcomes, dimensions scored vs expected, and a
            derived ok/degraded/hollow verdict. Mirrors
            data/logs/data_health.jsonl. Write-only until B5's hollow-run gate.
app_logs  : one row per WARNING/ERROR log record from any module (attached
            via configure_logging() — the API server and every standalone
            script entry point). Carries run_id/ticker when the record was
            emitted inside an analysis run, so an error can be traced to the
            verdict it damaged → permanent incident history, queryable long
            after Railway's console has rotated.

Design rules
------------
- Never raises: telemetry failures must not break the pipeline (same
  philosophy as llm_client.record_llm_call).
- WAL mode + busy_timeout: safe under multiple uvicorn workers writing
  concurrently.
- No retention cap: rows are tiny text; the 4.9 GB volume holds years.
  (Add a purge job if the DB ever matters on `du` — it won't soon.)

Querying (examples)
-------------------
    sqlite3 data/telemetry.db "SELECT model, COUNT(*), SUM(success=0)
        FROM llm_calls WHERE ts > datetime('now','-7 days') GROUP BY model"
    sqlite3 data/telemetry.db "SELECT * FROM app_logs
        WHERE level='ERROR' ORDER BY id DESC LIMIT 20"
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

# Atlas C8 / Blueprint 4 — telemetry user attribution. The auth dependency sets
# this per request (only when ATLAS_ENABLED); log_llm_call reads it so the
# user_id need not be threaded through ~20 call sites. Default None = the shared
# brain (scheduled analysis / self-heal have no request context, so they read
# None and stay NULL — the correct "cost belongs to everyone" bucket).
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)

# E1 (Three Loops PI) — run correlation. `app_logs` had no way to say WHICH run
# an error came from, so a degradation could not be tied to the verdict it
# damaged. The orchestrator opens `run_context(run_id)` for the whole of
# analyse()/analyse_async() and names the ticker once resolution succeeds;
# every WARNING+ record emitted underneath is stamped without threading an
# argument through ~200 call sites. ContextVars are copied by
# asyncio.to_thread, which is how the async path fans out, so offloaded work
# stays correlated. Default None = no run in flight (scheduler, startup, API
# request handling) — NULL is the honest answer there, not a guess.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_ticker: ContextVar[str | None] = ContextVar("current_ticker", default=None)


@contextmanager
def run_context(run_id: str, ticker: str | None = None):
    """Stamp every WARNING+ record emitted inside this block with `run_id`.

    The ticker is usually unknown at the top of a run (resolution is the first
    LLM call and can itself fail), so it is optional here and named later via
    `set_run_ticker`. Both are restored on exit — including on a raise, so a
    failed run cannot leak its id into the next one on a reused thread.
    """
    run_token = current_run_id.set(run_id)
    ticker_token = current_ticker.set(ticker)
    try:
        yield
    finally:
        current_ticker.reset(ticker_token)
        current_run_id.reset(run_token)


def set_run_ticker(ticker: str | None) -> None:
    """Name the ticker of the run in flight, once resolution has produced one."""
    current_ticker.set(ticker)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    caller        TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    success       INTEGER NOT NULL DEFAULT 1,
    user_id       TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls (ts);
CREATE INDEX IF NOT EXISTS idx_llm_calls_model ON llm_calls (model);

-- E1 adds run_id/ticker. They are declared here for a FRESH database only;
-- an existing one (prod holds 4,357 rows) is migrated by _add_column below,
-- and the index over run_id is created there too — putting it in this script
-- would abort the whole executescript on a pre-E1 DB and take telemetry down.
CREATE TABLE IF NOT EXISTS app_logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT NOT NULL,
    logger  TEXT NOT NULL,
    message TEXT NOT NULL,
    run_id  TEXT,
    ticker  TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_logs_ts ON app_logs (ts);
CREATE INDEX IF NOT EXISTS idx_app_logs_level ON app_logs (level);

-- B1 (Three Loops PI) — one row per completed analysis run, mirroring
-- data/logs/run_summaries.jsonl. The JSONL is the human/UI copy; this is the
-- queryable one that survives a redeploy.
CREATE TABLE IF NOT EXISTS run_summaries (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                      TEXT NOT NULL,
    run_id                  TEXT NOT NULL,
    ticker                  TEXT NOT NULL,
    company_name            TEXT,
    started_at              TEXT,
    duration_seconds        REAL NOT NULL DEFAULT 0,
    final_score             REAL,
    verdict                 TEXT,
    total_prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd          REAL NOT NULL DEFAULT 0,
    agent_scores            TEXT,
    error_count             INTEGER NOT NULL DEFAULT 0,
    errors                  TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_summaries_ts ON run_summaries (ts);
CREATE INDEX IF NOT EXISTS idx_run_summaries_ticker ON run_summaries (ticker);

-- B2 (Three Loops PI) — one row per run describing what that run actually
-- received: per-section fetch outcomes and which dimensions the analyst
-- produced. Mirrors data/logs/data_health.jsonl. Write-only until B5.
CREATE TABLE IF NOT EXISTS data_health (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    sector              TEXT,
    sections            TEXT,
    live                INTEGER NOT NULL DEFAULT 0,
    degraded            INTEGER NOT NULL DEFAULT 0,
    empty               INTEGER NOT NULL DEFAULT 0,
    not_applicable      INTEGER NOT NULL DEFAULT 0,
    dimensions_expected INTEGER NOT NULL DEFAULT 0,
    dimensions_scored   INTEGER NOT NULL DEFAULT 0,
    dimensions_missing  TEXT,
    api_calls           TEXT,
    health              TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_health_ts ON data_health (ts);
CREATE INDEX IF NOT EXISTS idx_data_health_health ON data_health (health);

-- Atlas C8 (BP4) — nightly cost rollup. user_id NULL = the shared-brain bucket.
CREATE TABLE IF NOT EXISTS cost_by_user_day (
    day           TEXT NOT NULL,
    user_id       TEXT,
    calls         INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cost_by_user_day ON cost_by_user_day (day);
"""


def _add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Add a nullable column to an existing table; a no-op once it is there.

    SQLite has no `ADD COLUMN IF NOT EXISTS`, so the duplicate-column error is
    the check. Anything else is left for _migrate to decide about.
    """
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an older database up to the current schema. Never raises.

    Every added column is nullable: old rows keep NULL and stay readable, which
    is why no history is ever rewritten here.

    Non-fatal by design. Two uvicorn workers boot together and both ALTER the
    same table, so one can meet `database is locked`. If that escaped, the
    outer guard in _get_conn would return None and the worker would archive
    NOTHING — llm_calls, run_summaries and data_health included — until the
    next restart. Degrading to the one column we could not add is far cheaper,
    and the next boot retries.
    """
    try:
        _add_column(conn, "llm_calls", "user_id", "TEXT")   # Atlas C8
        _add_column(conn, "app_logs", "run_id", "TEXT")     # E1
        _add_column(conn, "app_logs", "ticker", "TEXT")     # E1
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_logs_run_id ON app_logs (run_id)"
        )
        conn.commit()
    except Exception as exc:
        logger.warning(
            "[log_store] schema migration incomplete (non-fatal, telemetry stays "
            "up; retried on next boot): %s", exc,
        )


def _get_conn() -> sqlite3.Connection | None:
    """Lazily open (and initialize) the shared connection. None on failure.

    Double-checked locking: the fast path stays lock-free once the connection
    exists, but first touch is serialised. Without that, two threads reaching
    an untouched telemetry.db both ran `PRAGMA journal_mode=WAL` and the DDL,
    one lost with `database is locked`, and its record was dropped — silently,
    because every writer here is non-fatal by design. E1's parallel-run test
    reproduces it; the analysis path fans out through asyncio.to_thread, so
    concurrent first touch is normal, not exotic.

    Callers must never hold `_lock` when calling this (they don't: every writer
    takes it only around its INSERT), or this would deadlock on a plain Lock.

    ⚠ Serialises threads, NOT processes. Prod runs two uvicorn workers and they
    still race each other on first touch; `busy_timeout=5000` covers that, and
    the DDL is all `IF NOT EXISTS`, so the loser retries on its next write.
    """
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:      # another thread initialised while we waited
            return _conn
        try:
            db_path = Path(getattr(settings, "TELEMETRY_DB_PATH", "data/telemetry.db"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(_SCHEMA)
            _migrate(conn)
            _conn = conn
            return _conn
        except Exception as exc:
            logger.warning("[log_store] init failed (non-fatal, telemetry off): %s", exc)
            return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_llm_call(
    caller: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    user_id: str | None = None,
) -> None:
    """Persist one LLM call. Never raises.

    Atlas C8 (BP4): `user_id` attributes the cost to a user; when omitted it
    falls back to the `current_user_id` ContextVar (set by the auth dependency
    for chat / on-demand analyse / narrator). It stays NULL for scheduled work
    (no request context) — NULL = the shared brain.
    """
    try:
        uid = user_id if user_id is not None else current_user_id.get()
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO llm_calls "
                "(ts, caller, model, input_tokens, output_tokens, latency_ms, "
                "success, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), caller, model, input_tokens, output_tokens,
                 latency_ms, 1 if success else 0, uid),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[log_store] llm_call write failed (non-fatal): %s", exc)


def log_run_summary(
    *,
    run_id: str,
    ticker: str,
    company_name: str | None,
    started_at: str | None,
    duration_seconds: float,
    final_score: float | None,
    verdict: str | None,
    total_prompt_tokens: int,
    total_completion_tokens: int,
    total_cost_usd: float,
    agent_scores: str | None,
    error_count: int,
    errors: str | None,
) -> None:
    """Persist one completed analysis run. Never raises.

    B1: the JSONL copy lived on ephemeral container storage and held 13 rows
    after 53 days of prod traffic. `agent_scores` and `errors` arrive
    pre-serialised as JSON text — this store does no shaping.
    """
    try:
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO run_summaries "
                "(ts, run_id, ticker, company_name, started_at, duration_seconds, "
                "final_score, verdict, total_prompt_tokens, total_completion_tokens, "
                "total_cost_usd, agent_scores, error_count, errors) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), run_id, ticker, company_name, started_at, duration_seconds,
                 final_score, verdict, total_prompt_tokens, total_completion_tokens,
                 total_cost_usd, agent_scores, error_count, errors),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[log_store] run_summary write failed (non-fatal): %s", exc)


def run_summary_count() -> int:
    """How many runs the durable archive holds. 0 when unavailable; never raises."""
    try:
        conn = _get_conn()
        if conn is None:
            return 0
        with _lock:
            row = conn.execute("SELECT COUNT(*) FROM run_summaries").fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("[log_store] run_summary count failed (non-fatal): %s", exc)
        return 0


def log_data_health(
    *,
    run_id: str,
    ticker: str,
    sector: str | None,
    sections: str | None,
    live: int,
    degraded: int,
    empty: int,
    not_applicable: int,
    dimensions_expected: int,
    dimensions_scored: int,
    dimensions_missing: str | None,
    api_calls: str | None,
    health: str | None,
) -> None:
    """Persist one run's data-health row. Never raises.

    B2: `sections`, `dimensions_missing` and `api_calls` arrive pre-serialised
    as JSON text — this store does no shaping.
    """
    try:
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO data_health "
                "(ts, run_id, ticker, sector, sections, live, degraded, empty, "
                "not_applicable, dimensions_expected, dimensions_scored, "
                "dimensions_missing, api_calls, health) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), run_id, ticker, sector, sections, live, degraded, empty,
                 not_applicable, dimensions_expected, dimensions_scored,
                 dimensions_missing, api_calls, health),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[log_store] data_health write failed (non-fatal): %s", exc)


def data_health_count(health: str | None = None) -> int:
    """How many health rows the durable archive holds, optionally by verdict.

    0 when unavailable; never raises. B3's watchdog check reads the trailing
    degraded+hollow rate off this table.
    """
    try:
        conn = _get_conn()
        if conn is None:
            return 0
        with _lock:
            if health is None:
                row = conn.execute("SELECT COUNT(*) FROM data_health").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM data_health WHERE health = ?", (health,)
                ).fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("[log_store] data_health count failed (non-fatal): %s", exc)
        return 0


def rollup_cost_by_user_day(day: str | None = None) -> dict:
    """Atlas C8 (BP4): rebuild the `cost_by_user_day` rows for one UTC day from
    `llm_calls`, grouped by user_id (NULL = shared brain). Idempotent — a day is
    fully replaced on each run. Returns a summary; never raises."""
    summary = {"day": day, "buckets": 0}
    try:
        conn = _get_conn()
        if conn is None:
            return summary
        day = day or _now()[:10]
        summary["day"] = day
        with _lock:
            conn.execute("DELETE FROM cost_by_user_day WHERE day = ?", (day,))
            cur = conn.execute(
                "INSERT INTO cost_by_user_day (day, user_id, calls, input_tokens,"
                " output_tokens) SELECT ?, user_id, COUNT(*), "
                " COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)"
                " FROM llm_calls WHERE substr(ts,1,10) = ? GROUP BY user_id",
                (day, day))
            conn.commit()
            summary["buckets"] = cur.rowcount
        return summary
    except Exception as exc:
        logger.warning("[log_store] cost rollup failed (non-fatal): %s", exc)
        return summary


def log_app_record(
    level: str,
    logger_name: str,
    message: str,
    run_id: str | None = None,
    ticker: str | None = None,
) -> None:
    """Persist one application log record. Never raises.

    E1: `run_id`/`ticker` default to the `run_context` in flight, so the
    handler passes nothing and an error logged anywhere under a run is tied to
    it. Both stay NULL outside a run — that is the honest answer, not a gap.
    """
    try:
        rid = run_id if run_id is not None else current_run_id.get()
        tkr = ticker if ticker is not None else current_ticker.get()
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO app_logs (ts, level, logger, message, run_id, ticker) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), level, logger_name, message[:4000], rid, tkr),
            )
            conn.commit()
    except Exception:
        pass  # never let telemetry recurse into logging


def anonymize_user(user_id: str) -> int:
    """DPDP erasure (Atlas C6): detach a deleted user's LLM-cost rows from their
    identity (user_id → NULL) while *preserving the rows* — cost/telemetry is a
    shared-brain signal, so B4 Q3 chose ANONYMIZE over delete. Returns the number
    of rows anonymized; never raises.

    The `user_id` column on llm_calls is added by Atlas C8; until then the table
    has no such column, so a missing-column error is a benign no-op (there is
    nothing yet to anonymize). Idempotent — a second call anonymizes 0.
    """
    try:
        conn = _get_conn()
        if conn is None:
            return 0
        with _lock:
            try:
                cur = conn.execute(
                    "UPDATE llm_calls SET user_id=NULL WHERE user_id=?", (user_id,))
                conn.commit()
                return cur.rowcount or 0
            except sqlite3.OperationalError as exc:
                if "no such column" in str(exc).lower():
                    return 0            # pre-C8: llm_calls has no user_id yet
                raise
    except Exception as exc:
        logger.warning("[log_store] anonymize_user failed (non-fatal): %s", exc)
        return 0


class SQLiteLogHandler(logging.Handler):
    """logging.Handler that mirrors WARNING+ records into app_logs.

    Attach once to the root logger (services/api/server.py). Guarded against
    recursion: records emitted by this module itself are dropped.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == __name__:
            return  # never log our own warnings back into ourselves
        try:
            log_app_record(record.levelname, record.name, self.format(record))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# One logging setup for every entry point (E1)
# ---------------------------------------------------------------------------
# Before E1 the archive handler was attached in exactly one place —
# services/api/server.py — so the APScheduler jobs (in-process with the API)
# were covered but anything run as `railway ssh python -m ...` archived
# nothing. This lives beside the handler rather than in a new module so that
# `core` never has to import from `services` to configure its own logging.

_IST = timezone(timedelta(hours=5, minutes=30))

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"


class _ISTFormatter(logging.Formatter):
    """Console timestamps in IST (UTC+5:30) with the full date.

    The market, the schedule and the person reading the console are all on IST;
    UTC console lines cost a mental conversion on every incident.
    """

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, tz=_IST).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )


def configure_logging(
    level: int | str = logging.INFO,
    *,
    stream=None,
    ist_time: bool = True,
) -> None:
    """Configure console logging and attach the permanent WARNING+ archive.

    Idempotent: safe to call from a module imported by an already-configured
    process. That matters because the RL workflow modules configure at import
    time and the API server imports them — a second archive handler would
    double every row.

    E1 also fixes a duplication measured in prod on 2026-08-26: the archive
    handler was given a `%(message)s` formatter and then had it overwritten two
    lines later by the loop that re-formats every root handler, so all 4,357
    stored messages carried a redundant `"<IST ts> LEVEL [logger] "` prefix.
    `ts`, `level` and `logger` are already columns, and a per-record timestamp
    inside the message body would make E2's fingerprints unique-by-construction.
    The console keeps the prefix; the archive stores the message alone.
    """
    if stream is not None:
        logging.basicConfig(level=level, stream=stream)
    else:
        logging.basicConfig(level=level)
    root = logging.getLogger()
    root.setLevel(level)   # basicConfig is a no-op once root has any handler

    try:
        if not any(isinstance(h, SQLiteLogHandler) for h in root.handlers):
            archive = SQLiteLogHandler(level=logging.WARNING)
            archive.setFormatter(logging.Formatter("%(message)s"))
            root.addHandler(archive)
    except Exception as exc:   # telemetry must never block a process from booting
        logging.getLogger(__name__).warning(
            "[log_store] SQLite log handler unavailable (non-fatal): %s", exc
        )

    console_fmt = (
        _ISTFormatter(_CONSOLE_FORMAT) if ist_time else logging.Formatter(_CONSOLE_FORMAT)
    )
    for handler in root.handlers:
        if not isinstance(handler, SQLiteLogHandler):
            handler.setFormatter(console_fmt)
