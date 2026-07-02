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
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    caller        TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    success       INTEGER NOT NULL DEFAULT 1
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
) -> None:
    """Persist one LLM call. Never raises."""
    try:
        conn = _get_conn()
        if conn is None:
            return
        with _lock:
            conn.execute(
                "INSERT INTO llm_calls "
                "(ts, caller, model, input_tokens, output_tokens, latency_ms, success) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_now(), caller, model, input_tokens, output_tokens,
                 latency_ms, 1 if success else 0),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[log_store] llm_call write failed (non-fatal): %s", exc)


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
