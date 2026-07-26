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
from pathlib import Path

from backend.shared.config.settings.loader import cfg

logger = logging.getLogger(__name__)


def db_path() -> Path:
    """Resolve the atlas.db location (env > config.yaml > fallback)."""
    return Path(cfg("atlas.db_path", env="ATLAS_DB_PATH", fallback="data/atlas.db"))


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
  CHECK (status  IN ('queued','delivered','failed','dead'))
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
