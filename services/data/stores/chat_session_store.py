"""
services/data/stores/chat_session_store.py
==========================================
Volume-backed chat session memory.

The chat loop previously kept session history in a per-process dict
(`_SESSION_HISTORY`). uvicorn runs 2 workers: consecutive turns of one
session can land on different workers, so history silently vanished on
roughly every other turn, and every deploy wiped all sessions. This store
keeps the same semantics (last N messages per session, server-side only)
in SQLite on the mounted volume, shared by both workers and surviving
deploys.

- WAL mode + busy_timeout: safe under multiple uvicorn workers writing
  (same recipe as log_store.py).
- Never raises: on any storage failure chat degrades to stateless for that
  turn instead of failing the request.
- Lives in its own DB file (data/chat_sessions.db), NOT telemetry.db, so
  conversational content stays out of the nightly backup email.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.shared.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_DEFAULT_DB = "data/chat_sessions.db"
SESSION_TTL_DAYS = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id    TEXT NOT NULL DEFAULT 'primary',
    ts         TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_turns_session ON chat_turns (user_id, session_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_turns_ts ON chat_turns (ts);
"""


def _get_conn() -> sqlite3.Connection | None:
    """Lazily open (and initialize) the shared connection. None on failure."""
    global _conn
    if _conn is not None:
        return _conn
    try:
        db_path = Path(getattr(settings, "CHAT_SESSIONS_DB_PATH", _DEFAULT_DB))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        # Atlas A2: migrate a pre-existing DB *before* _SCHEMA runs — the new
        # schema indexes user_id, so the column must exist first. Legacy rows
        # become the owner's ('primary'). On a fresh DB there is no table yet,
        # so the ALTER is a harmless no-op (caught below) and _SCHEMA creates it.
        try:
            conn.execute("ALTER TABLE chat_turns ADD COLUMN"
                         " user_id TEXT NOT NULL DEFAULT 'primary'")
            conn.commit()
        except sqlite3.OperationalError:
            pass                   # no such table (fresh DB) or column exists
        conn.executescript(_SCHEMA)
        conn.commit()
        _conn = conn
        return _conn
    except Exception as exc:
        logger.warning("[chat_session_store] init failed (non-fatal, chat stateless): %s", exc)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_history(session_id: str, max_messages: int, user_id: str = "primary") -> list[dict]:
    """Return the last `max_messages` turns for this user's session, oldest first."""
    try:
        conn = _get_conn()
        if conn is None or not session_id:
            return []
        with _lock:
            rows = conn.execute(
                "SELECT role, content FROM chat_turns"
                " WHERE session_id = ? AND user_id = ?"
                " ORDER BY id DESC LIMIT ?",
                (session_id, user_id, int(max_messages)),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    except Exception as exc:
        logger.warning("[chat_session_store] read failed (non-fatal): %s", exc)
        return []


def append_turns(
    session_id: str, user_text: str, assistant_text: str, max_messages: int,
    user_id: str = "primary",
) -> None:
    """Append one user+assistant exchange for this user and prune to the last
    `max_messages` — pruning is scoped to (user_id, session_id) so one user's
    turns never evict another's on a shared session_id."""
    try:
        conn = _get_conn()
        if conn is None or not session_id:
            return
        ts = _now()
        with _lock:
            conn.execute(
                "INSERT INTO chat_turns (session_id, user_id, ts, role, content)"
                " VALUES (?, ?, ?, 'user', ?)",
                (session_id, user_id, ts, user_text),
            )
            conn.execute(
                "INSERT INTO chat_turns (session_id, user_id, ts, role, content)"
                " VALUES (?, ?, ?, 'assistant', ?)",
                (session_id, user_id, ts, assistant_text),
            )
            conn.execute(
                "DELETE FROM chat_turns WHERE session_id = ? AND user_id = ? AND id NOT IN ("
                "  SELECT id FROM chat_turns WHERE session_id = ? AND user_id = ?"
                "  ORDER BY id DESC LIMIT ?)",
                (session_id, user_id, session_id, user_id, int(max_messages)),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[chat_session_store] write failed (non-fatal): %s", exc)


def has_session(session_id: str, user_id: str = "primary") -> bool:
    """True if any turns exist for this user's session."""
    return bool(get_history(session_id, 1, user_id=user_id))


def sweep_expired(ttl_days: int = SESSION_TTL_DAYS) -> int:
    """Delete turns older than the TTL. Returns rows deleted; never raises."""
    try:
        conn = _get_conn()
        if conn is None:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        with _lock:
            cur = conn.execute("DELETE FROM chat_turns WHERE ts < ?", (cutoff,))
            conn.commit()
        if cur.rowcount:
            logger.info("[chat_session_store] swept %d expired turns (>%dd)", cur.rowcount, ttl_days)
        return cur.rowcount or 0
    except Exception as exc:
        logger.warning("[chat_session_store] sweep failed (non-fatal): %s", exc)
        return 0


def _reset_for_tests() -> None:
    """Close and drop the module connection so tests can repoint the DB path."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None
