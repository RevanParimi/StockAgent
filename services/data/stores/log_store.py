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
app_logs  : one row per WARNING/ERROR log record from any module (attached
            via SQLiteLogHandler in services/api/server.py)
            → permanent incident history, queryable long after Railway's
            console has rotated.

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
from contextvars import ContextVar
from datetime import datetime, timezone
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

CREATE TABLE IF NOT EXISTS app_logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    level   TEXT NOT NULL,
    logger  TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_logs_ts ON app_logs (ts);
CREATE INDEX IF NOT EXISTS idx_app_logs_level ON app_logs (level);

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


def _get_conn() -> sqlite3.Connection | None:
    """Lazily open (and initialize) the shared connection. None on failure."""
    global _conn
    if _conn is not None:
        return _conn
    try:
        db_path = Path(getattr(settings, "TELEMETRY_DB_PATH", "data/telemetry.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        try:                       # Atlas C8: add user_id to a pre-existing DB
            conn.execute("ALTER TABLE llm_calls ADD COLUMN user_id TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass                   # column already exists
        conn.commit()
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


def log_app_record(level: str, logger_name: str, message: str) -> None:
    """Persist one application log record. Never raises."""
    try:
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO app_logs (ts, level, logger, message) VALUES (?, ?, ?, ?)",
                (_now(), level, logger_name, message[:4000]),
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
