"""
services/data/stores/atlas_store.py
===================================
Atlas M1 user-plane relational core — `data/atlas.db` (design spec
docs/superpowers/specs/2026-07-26-m1-data-architecture-design.md §1/§2).

ONE FK-linked SQLite DB on the existing Railway volume, folding today's
`users.db`, the global `watchlist.json`, and `push_subscriptions.json`, and
adding the missing `user_instruments` join, the plane-boundary
`ticker_verdicts` projection, `user_advice`, and the greenfield
`outbox`/`feedback_events`. Same WAL + process-wide-connection recipe as
`user_store.py`/`chat_session_store.py`; portable SQL only (the eventual
Postgres move is a dump/load).

DORMANT at C1: this task is the schema + connection only. Nothing imports the
store yet, so it is a behavioral no-op — the whole Phase-C build ships behind
`cfg("atlas.enabled", env="ATLAS_ENABLED", fallback=False)` and is wired into
fan-out only at the C11 cutover.

Two properties the M1 design leans on and this module guarantees:
  * `PRAGMA foreign_keys=ON` is issued on **every** connection (it is
    per-connection and NOT persisted — a fresh sqlite connection defaults it
    OFF), so the FKs are actually enforced.
  * `DELETE FROM users WHERE user_id=?` is the single-transaction DPDP cascade:
    the 7 PII tables drop to 0 while the user-free `instruments`/
    `ticker_verdicts` survive and `invites` audit rows are retained with
    `created_by`/`used_by` SET NULL.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.shared.config.settings.loader import cfg

logger = logging.getLogger(__name__)


def db_path() -> Path:
    """Resolve the atlas.db location (env > config.yaml > fallback)."""
    return Path(cfg("atlas.db_path", env="ATLAS_DB_PATH", fallback="data/atlas.db"))


def enabled() -> bool:
    """True when the Atlas relational plane is switched on (env > yaml > False).

    Read LIVE on every call (not resolved once at import) so the C11 cutover —
    flip ATLAS_ENABLED and redeploy — takes effect, and so tests can toggle it.
    While False the whole Phase-C build is a behavioral no-op.
    """
    return bool(cfg("atlas.enabled", env="ATLAS_ENABLED", fallback=False))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_DB_PATH = db_path()               # tests monkeypatch this (same recipe as user_store)
_conn_holder: dict = {"conn": None}
_lock = threading.Lock()

# data/atlas.db — Atlas M1 user-plane relational core (spec §2, owner-first so FK
# targets exist before dependents and the DPDP cascade is complete).
_SCHEMA = """
------------------------------------------------------------------- identity (from users.db)
CREATE TABLE IF NOT EXISTS users (
  user_id      TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  pw_hash      TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  role         TEXT NOT NULL DEFAULT 'member',
  created_at   TEXT NOT NULL,
  consent_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  last_seen  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS invites (
  code       TEXT PRIMARY KEY,
  created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  used_by    TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  used_at    TEXT
);

CREATE TABLE IF NOT EXISTS chat_usage (
  user_id   TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  day       TEXT NOT NULL,
  llm_turns INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);

------------------------------------------------------------------- universe (from managed_tickers.json)
CREATE TABLE IF NOT EXISTS instruments (
  sym           TEXT PRIMARY KEY,
  name          TEXT NOT NULL DEFAULT '',
  sector        TEXT NOT NULL DEFAULT '',
  enabled       INTEGER NOT NULL DEFAULT 0,
  origin        TEXT NOT NULL DEFAULT 'seed',
  cadence       TEXT NOT NULL DEFAULT 'on_demand',
  status        TEXT NOT NULL DEFAULT 'active',
  promoted_at   TEXT,
  holders       INTEGER NOT NULL DEFAULT 0,
  watchers      INTEGER NOT NULL DEFAULT 0,
  chat_hits_7d  INTEGER NOT NULL DEFAULT 0,
  demand_score  REAL NOT NULL DEFAULT 0,
  last_analyzed TEXT,
  created_at    TEXT NOT NULL DEFAULT '',
  updated_at    TEXT NOT NULL DEFAULT '',
  CHECK (cadence IN ('daily','weekly','on_demand')),
  CHECK (status  IN ('active','archived'))
);

------------------------------------------------------------------- the missing join
CREATE TABLE IF NOT EXISTS user_instruments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
  symbol       TEXT NOT NULL REFERENCES instruments(sym) ON DELETE CASCADE,
  relationship TEXT NOT NULL,
  added_at     TEXT NOT NULL DEFAULT '',
  UNIQUE (user_id, symbol, relationship),
  CHECK (relationship IN ('held','watch'))
);
CREATE INDEX IF NOT EXISTS idx_user_instruments_symbol ON user_instruments(symbol, relationship);

------------------------------------------------------------------- PLANE BOUNDARY (user-free projection)
CREATE TABLE IF NOT EXISTS ticker_verdicts (
  symbol                TEXT NOT NULL REFERENCES instruments(sym) ON DELETE CASCADE,
  as_of_date            TEXT NOT NULL,
  verdict               TEXT NOT NULL DEFAULT 'HOLD',
  confidence            REAL NOT NULL DEFAULT 0.5,
  regime                TEXT NOT NULL DEFAULT 'NORMAL',
  triggers              TEXT NOT NULL DEFAULT '[]',
  envelope_direction    TEXT NOT NULL DEFAULT 'FLAT',
  predicted_close       REAL,
  confidence_trend      REAL NOT NULL DEFAULT 0,
  reversion_prior       REAL NOT NULL DEFAULT 0,
  reforecast_reason     TEXT NOT NULL DEFAULT '',
  direction_accuracy_7d REAL,
  thesis_intact         INTEGER,
  cycle_id              TEXT NOT NULL DEFAULT '',
  source                TEXT NOT NULL DEFAULT 'projection',
  created_at            TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (symbol, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_ticker_verdicts_date ON ticker_verdicts(as_of_date);

------------------------------------------------------------------- per-user application (from advice_ledger.jsonl)
CREATE TABLE IF NOT EXISTS user_advice (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id            TEXT NOT NULL REFERENCES users(user_id)   ON DELETE CASCADE,
  symbol             TEXT NOT NULL REFERENCES instruments(sym) ON DELETE CASCADE,
  as_of_date         TEXT NOT NULL,
  verdict            TEXT NOT NULL,
  verdict_ref        TEXT NOT NULL DEFAULT '',
  close              REAL NOT NULL DEFAULT 0,
  unrealised_pnl_pct REAL NOT NULL DEFAULT 0,
  stop_pct           REAL NOT NULL DEFAULT 0,
  confidence         REAL NOT NULL DEFAULT 0.5,
  triggers           TEXT NOT NULL DEFAULT '[]',
  rationale_hash     TEXT NOT NULL DEFAULT '',
  outcome_10td       REAL,
  outcome_30td       REAL,
  outcome_60td       REAL,
  created_at         TEXT NOT NULL DEFAULT '',
  UNIQUE (user_id, symbol, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_user_advice_user_date ON user_advice(user_id, as_of_date);

------------------------------------------------------------------- PII channels (from push_subscriptions.json, A1)
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  endpoint   TEXT NOT NULL,
  p256dh     TEXT NOT NULL DEFAULT '',
  auth       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT '',
  UNIQUE (user_id, endpoint)
);

------------------------------------------------------------------- BP2 outbox (greenfield)
CREATE TABLE IF NOT EXISTS outbox (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  channel         TEXT NOT NULL,
  kind            TEXT NOT NULL,
  payload_ref     TEXT NOT NULL,
  dedupe_key      TEXT NOT NULL UNIQUE,
  status          TEXT NOT NULL DEFAULT 'queued',
  attempts        INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  next_attempt_at TEXT,
  delivered_at    TEXT,
  CHECK (channel IN ('push','email')),
  CHECK (kind    IN ('brief','digest','weekly','alert')),
  CHECK (status  IN ('queued','sending','delivered','failed','dead'))
);
CREATE INDEX IF NOT EXISTS idx_outbox_ready ON outbox(status, next_attempt_at);

------------------------------------------------------------------- BP5 feedback (greenfield, user plane, OUTSIDE intelligence)
CREATE TABLE IF NOT EXISTS feedback_events (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                 TEXT NOT NULL,
  user_id            TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  symbol             TEXT NOT NULL,
  advice_ref         TEXT NOT NULL DEFAULT '',
  verdict_shown      TEXT NOT NULL DEFAULT '',
  action             TEXT NOT NULL,
  override_direction TEXT NOT NULL DEFAULT '',
  position_state     TEXT NOT NULL DEFAULT '',
  CHECK (action IN ('accepted','overridden','ignored')),
  CHECK (position_state IN ('winning','losing',''))
);
CREATE INDEX IF NOT EXISTS idx_feedback_events_symbol ON feedback_events(symbol);
"""


def _get_conn() -> sqlite3.Connection:
    """Return the process-wide connection, opening + initializing on first use.

    All three PRAGMAs are issued here because they are per-connection: a fresh
    sqlite connection defaults `foreign_keys` OFF and does not remember WAL from
    a prior process, so they must be (re)issued whenever a connection is opened.
    """
    conn = _conn_holder.get("conn")
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.row_factory = sqlite3.Row
        _conn_holder["conn"] = conn
    return conn


def _reset_for_tests() -> None:
    """Close and drop the module connection so tests can repoint `_DB_PATH`."""
    conn = _conn_holder.get("conn")
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _conn_holder["conn"] = None


# ---------------------------------------------------------------------------
# Business functions (C3) — the user_instruments reverse index (spec §4).
# All hot-path safe: they log + return on any failure so a portfolio write
# never fails because of the atlas index. Callers gate on `enabled()`.
# ---------------------------------------------------------------------------

def user_ids() -> list[str]:
    """All registered user_ids (SELECT user_id FROM users). [] on any failure."""
    try:
        conn = _get_conn()
        with _lock:
            rows = conn.execute("SELECT user_id FROM users ORDER BY created_at").fetchall()
        return [r[0] for r in rows]
    except Exception as exc:
        logger.warning("[atlas_store] user_ids read failed (non-fatal): %s", exc)
        return []


def upsert_user_instrument(user_id: str, symbol: str, relationship: str, *,
                           origin: str = "seed", cadence: str = "on_demand") -> bool:
    """Ensure the `instruments` FK target exists, then record the (user, symbol,
    relationship) membership. Idempotent (INSERT OR IGNORE on the UNIQUE key).
    `origin`/`cadence` are set only when the instrument row is first created —
    the nightly Universe recompute (C4) is the authority on cadence thereafter.
    Atomic (both rows or neither); returns False on any failure, never raises."""
    sym = symbol.strip().upper()
    now = _now_iso()
    try:
        conn = _get_conn()
        with _lock:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO instruments (sym, origin, cadence,"
                    " created_at, updated_at) VALUES (?,?,?,?,?)",
                    (sym, origin, cadence, now, now))
                conn.execute(
                    "INSERT OR IGNORE INTO user_instruments (user_id, symbol,"
                    " relationship, added_at) VALUES (?,?,?,?)",
                    (user_id, sym, relationship, now))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return True
    except Exception as exc:
        logger.warning("[atlas_store] upsert_user_instrument failed for %s/%s"
                       " (non-fatal): %s", user_id, sym, exc)
        return False


def remove_user_instrument(user_id: str, symbol: str, relationship: str) -> bool:
    """Delete one (user, symbol, relationship) membership row. Returns False on
    any failure, never raises."""
    sym = symbol.strip().upper()
    try:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "DELETE FROM user_instruments WHERE user_id=? AND symbol=?"
                " AND relationship=?", (user_id, sym, relationship))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("[atlas_store] remove_user_instrument failed for %s/%s"
                       " (non-fatal): %s", user_id, sym, exc)
        return False


# ---------------------------------------------------------------------------
# DPDP right-to-erasure (C6, spec §DPDP / B4 Q3/Q5).
# ---------------------------------------------------------------------------

def delete_user_completely(user_id: str) -> dict:
    """Erase every trace of `user_id` across all planes — the single DPDP entry
    point. Order is DB-commit-first so the authoritative record is destroyed
    before best-effort filesystem/cross-DB cleanup: a stray artifact can never
    block the erasure.

      1. atlas.db — `DELETE FROM users` one-transaction cascade drops the 7 PII
         tables to 0 (feedback_events HARD-DELETE, B4 Q5); the user-free
         instruments/ticker_verdicts survive; invites created_by/used_by SET NULL.
      2. filesystem — `data/portfolio/<user_id>/` removed.
      3. chat_sessions.db — this user's chat_turns deleted.
      4. telemetry.db — this user's llm_calls ANONYMIZED (user_id→NULL, B4 Q3),
         row count preserved.

    Every step is idempotent and hot-path safe (log + continue): a second call
    no-ops and one failing step never blocks the others. NOT flag-gated — DPDP
    erasure must run whether or not ATLAS_ENABLED (pre-cutover the user lives in
    users.db, so atlas.db simply holds no rows and step 1 is a harmless 0-row
    delete). Returns a summary of what was erased.
    """
    summary = {"atlas_cascade": False, "portfolio_removed": False,
               "chat_turns_deleted": 0, "telemetry_anonymized": 0}

    # (1) authoritative DB erasure FIRST — commit before any fs/cross-DB work.
    try:
        conn = _get_conn()
        with _lock:
            conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            conn.commit()
        summary["atlas_cascade"] = True
    except Exception as exc:
        logger.warning("[atlas_store] DPDP atlas cascade failed for %s"
                       " (non-fatal): %s", user_id, exc)

    # (2) portfolio directory.
    try:
        import shutil
        from core.config import settings
        pf_dir = Path(settings.PORTFOLIO_DATA_DIR) / user_id
        if pf_dir.is_dir():
            shutil.rmtree(pf_dir)
        summary["portfolio_removed"] = True
    except Exception as exc:
        logger.warning("[atlas_store] DPDP portfolio cleanup failed for %s"
                       " (non-fatal): %s", user_id, exc)

    # (3) chat history (its own DB, owns its connection).
    try:
        from services.data.stores import chat_session_store
        summary["chat_turns_deleted"] = chat_session_store.delete_user_turns(user_id)
    except Exception as exc:
        logger.warning("[atlas_store] DPDP chat cleanup failed for %s"
                       " (non-fatal): %s", user_id, exc)

    # (4) telemetry anonymize (row count preserved — shared-brain cost signal).
    try:
        from services.data.stores import log_store
        summary["telemetry_anonymized"] = log_store.anonymize_user(user_id)
    except Exception as exc:
        logger.warning("[atlas_store] DPDP telemetry anonymize failed for %s"
                       " (non-fatal): %s", user_id, exc)

    logger.info("[atlas_store] DPDP delete complete for %s: %s", user_id, summary)
    return summary


# ---------------------------------------------------------------------------
# BP5 feedback events (C8) — user reactions to advice cards. Append-only,
# user-plane, OUTSIDE core/intelligence (Learning Constitution R1). The
# aggregate refuses to return below a distinct-user floor (reviewer R3).
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"accepted", "overridden", "ignored"}
_VALID_POSITION_STATES = {"winning", "losing", ""}


def _feedback_floor() -> int:
    return int(cfg("atlas.feedback.aggregation_floor_users", fallback=20))


def record_feedback_event(user_id: str, symbol: str, action: str, *,
                          ts: str | None = None, advice_ref: str = "",
                          verdict_shown: str = "", override_direction: str = "",
                          position_state: str = "") -> int | None:
    """Append one feedback event (a user accepting/overriding/ignoring an advice
    card). Flag-gated no-op when ATLAS disabled; rejects an invalid action or
    position_state (returns None); never raises. Returns the new row id."""
    if not enabled():
        return None
    if action not in _VALID_ACTIONS or position_state not in _VALID_POSITION_STATES:
        logger.warning("[atlas_store] feedback rejected — bad action/state (%s/%s)",
                       action, position_state)
        return None
    try:
        conn = _get_conn()
        with _lock:
            cur = conn.execute(
                "INSERT INTO feedback_events (ts, user_id, symbol, advice_ref,"
                " verdict_shown, action, override_direction, position_state)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (ts or _now_iso(), user_id, symbol.strip().upper(), advice_ref,
                 verdict_shown, action, override_direction, position_state))
            conn.commit()
            return cur.lastrowid
    except Exception as exc:
        logger.warning("[atlas_store] record_feedback_event failed for %s/%s"
                       " (non-fatal): %s", user_id, symbol, exc)
        return None


def feedback_aggregate() -> dict | None:
    """Privacy-safe aggregate of all feedback events. Returns None below the
    distinct-user floor (reviewer R3) so small-N cohorts can't be de-anonymised;
    otherwise the counts by action. [] / None on any failure, never raises."""
    try:
        conn = _get_conn()
        with _lock:
            n_users = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM feedback_events").fetchone()[0]
            if n_users < _feedback_floor():
                return None
            rows = conn.execute(
                "SELECT action, COUNT(*) FROM feedback_events GROUP BY action"
            ).fetchall()
        by_action = {a: 0 for a in _VALID_ACTIONS}
        for action, count in rows:
            by_action[action] = count
        return {"users": n_users, "by_action": by_action}
    except Exception as exc:
        logger.warning("[atlas_store] feedback_aggregate failed (non-fatal): %s", exc)
        return None
