"""
services/data/stores/user_store.py
==================================
M0 identity store (spec 2026-07-26 §4.1): users, sessions, invites, chat quota
counters. SQLite on the Railway volume (data/users.db) — same WAL +
process-wide-connection pattern as chat_session_store. Portable SQL only
(the M1 Postgres move is a dump/load).

Security notes: passwords are scrypt-hashed (stdlib, per-user salt); session
tokens are stored SHA-256-hashed so a DB leak does not leak live sessions;
verification uses constant-time comparison.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/users.db")
_conn_holder: dict = {"conn": None}
_lock = threading.Lock()
_IST = ZoneInfo("Asia/Kolkata")

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 16384, 8, 1

_SCHEMA = """
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
  token_hash  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  created_at  REAL NOT NULL,
  expires_at  REAL NOT NULL,
  last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE TABLE IF NOT EXISTS invites (
  code        TEXT PRIMARY KEY,
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  used_by     TEXT,
  used_at     TEXT
);
CREATE TABLE IF NOT EXISTS chat_usage (
  user_id   TEXT NOT NULL,
  day       TEXT NOT NULL,
  llm_turns INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS analyse_usage (
  user_id   TEXT NOT NULL,
  day       TEXT NOT NULL,
  runs      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);
"""


def _now_epoch() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ist_today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _get_conn() -> sqlite3.Connection:
    conn = _conn_holder.get("conn")
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        _conn_holder["conn"] = conn
    return conn


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt$n={},r={},p={}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def _check_password(password: str, stored: str) -> bool:
    try:
        _, params, salt_b64, hash_b64 = stored.split("$")
        kv = dict(p.split("=") for p in params.split(","))
        dk = hashlib.scrypt(password.encode(),
                            salt=base64.b64decode(salt_b64),
                            n=int(kv["n"]), r=int(kv["r"]), p=int(kv["p"]),
                            dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _row_to_user(row: sqlite3.Row) -> dict:
    return {"user_id": row["user_id"], "email": row["email"],
            "display_name": row["display_name"], "role": row["role"],
            "created_at": row["created_at"]}


# -- users -------------------------------------------------------------------

def create_user(email: str, password: str, display_name: str, *,
                role: str = "member", user_id: str | None = None,
                consent: bool = True) -> dict:
    email = email.strip().lower()
    uid = user_id or ("u_" + secrets.token_hex(4))
    conn = _get_conn()
    with _lock:
        try:
            conn.execute(
                "INSERT INTO users (user_id, email, pw_hash, display_name,"
                " role, created_at, consent_at) VALUES (?,?,?,?,?,?,?)",
                (uid, email, _hash_password(password), display_name, role,
                 _now_iso(), _now_iso() if consent else ""))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"email or user_id already registered") from exc
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    return _row_to_user(row)


def verify_password(email: str, password: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=?",
                       (email.strip().lower(),)).fetchone()
    # Constant-time-ish: always run one scrypt even for unknown emails.
    stored = row["pw_hash"] if row else _hash_password("x" * 12)
    if _check_password(password, stored) and row:
        return _row_to_user(row)
    return None


def count_users() -> int:
    return _get_conn().execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user(user_id: str) -> dict | None:
    row = _get_conn().execute("SELECT * FROM users WHERE user_id=?",
                              (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def delete_user(user_id: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM chat_usage WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()


# -- sessions ----------------------------------------------------------------

def create_session(user_id: str, remember_me: bool) -> str:
    raw = secrets.token_urlsafe(32)
    ttl = timedelta(days=30) if remember_me else timedelta(hours=24)
    now = _now_epoch()
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at,"
            " expires_at, last_seen) VALUES (?,?,?,?,?)",
            (_token_hash(raw), user_id, now, now + ttl.total_seconds(), now))
        conn.commit()
    return raw


def resolve_session(raw_token: str) -> dict | None:
    if not raw_token:
        return None
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE token_hash=?",
                       (_token_hash(raw_token),)).fetchone()
    if row is None or row["expires_at"] < _now_epoch():
        return None
    with _lock:
        conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?",
                     (_now_epoch(), row["token_hash"]))
        conn.commit()
    return get_user(row["user_id"])


def revoke_session(raw_token: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",
                     (_token_hash(raw_token),))
        conn.commit()


def sweep_expired_sessions() -> int:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?",
                           (_now_epoch(),))
        conn.commit()
    return cur.rowcount


# -- invites -----------------------------------------------------------------

def create_invite(created_by: str) -> str:
    code = "inv_" + secrets.token_urlsafe(8)
    conn = _get_conn()
    with _lock:
        conn.execute("INSERT INTO invites (code, created_by, created_at)"
                     " VALUES (?,?,?)", (code, created_by, _now_iso()))
        conn.commit()
    return code


def list_invites() -> list[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM invites ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def consume_invite(code: str, used_by: str) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "UPDATE invites SET used_by=?, used_at=?"
            " WHERE code=? AND used_by IS NULL", (used_by, _now_iso(), code))
        conn.commit()
    return cur.rowcount == 1


# -- chat quota --------------------------------------------------------------

def bump_chat_usage(user_id: str) -> int:
    day = _ist_today()
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO chat_usage (user_id, day, llm_turns) VALUES (?,?,1)"
            " ON CONFLICT(user_id, day) DO UPDATE SET llm_turns=llm_turns+1",
            (user_id, day))
        conn.commit()
    return get_chat_usage(user_id)


def get_chat_usage(user_id: str) -> int:
    row = _get_conn().execute(
        "SELECT llm_turns FROM chat_usage WHERE user_id=? AND day=?",
        (user_id, _ist_today())).fetchone()
    return int(row["llm_turns"]) if row else 0


# -- on-demand analysis quota -------------------------------------------------
# Separate counter from chat: one /analyse run is a full 8-agent pipeline
# (~8 LLM calls), so it is metered far more tightly than a single chat turn.

def bump_analyse_usage(user_id: str) -> int:
    day = _ist_today()
    conn = _get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO analyse_usage (user_id, day, runs) VALUES (?,?,1)"
            " ON CONFLICT(user_id, day) DO UPDATE SET runs=runs+1",
            (user_id, day))
        conn.commit()
    return get_analyse_usage(user_id)


def get_analyse_usage(user_id: str) -> int:
    row = _get_conn().execute(
        "SELECT runs FROM analyse_usage WHERE user_id=? AND day=?",
        (user_id, _ist_today())).fetchone()
    return int(row["runs"]) if row else 0
