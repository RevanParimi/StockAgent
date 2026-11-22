"""
tools/score_store.py
====================
SQLite-backed persistent store for historical automobile stock scores.

Stores every pipeline run result so the scheduler can:
  - Detect score changes between runs
  - Detect verdict changes
  - Expose trend data for alerts and future dashboards

Public API
----------
ScoreStore().save(report)                          → int (row id)
ScoreStore().get_latest(ticker)                    → dict | None
ScoreStore().get_latest_before(ticker, before)     → dict | None
ScoreStore().get_history(ticker, limit)            → list[dict]
ScoreStore().get_score_delta(ticker)               → float | None
ScoreStore().get_verdict_changed(ticker)           → bool
ScoreStore().prune_old_records(ticker)
ScoreStore().get_all_latest()                      → list[dict]
ScoreStore().theses_between(since, until)          → list[dict] (FIX-033)
theses_between(since, until)                       → the same, from the default store
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from core.schemas.pipeline import FinalReport

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS score_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    company_name    TEXT    NOT NULL,
    run_at          TEXT    NOT NULL,   -- ISO datetime
    final_score     REAL    NOT NULL,
    verdict         TEXT    NOT NULL,
    agent_scores    TEXT    NOT NULL,   -- JSON blob
    investment_thesis TEXT  NOT NULL,
    conviction_drivers TEXT NOT NULL,  -- JSON list
    top_risks       TEXT    NOT NULL,  -- JSON list
    report_json     TEXT    NOT NULL   -- full report JSON
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_score_history_ticker_run
ON score_history (ticker, run_at DESC);
"""


class ScoreStore:
    """
    Thread-safe SQLite wrapper for persisting FinalReport outputs.

    The database file is created automatically if it doesn't exist.
    """

    def __init__(self, db_path: str = settings.SCORE_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
        logger.debug("[ScoreStore] DB ready at %s", self._db_path)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, report: FinalReport) -> int:
        """
        Persist a FinalReport to SQLite.

        Returns the new row id.
        """
        agent_scores = {
            name: {"raw": ws.raw, "weight": ws.weight, "weighted": ws.weighted}
            for name, ws in report.weighted_agent_scores.items()
        }

        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO score_history
                  (ticker, company_name, run_at, final_score, verdict,
                   agent_scores, investment_thesis, conviction_drivers,
                   top_risks, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.ticker,
                    report.company_name,
                    datetime.utcnow().isoformat(),
                    report.final_score,
                    report.verdict,
                    json.dumps(agent_scores),
                    report.investment_thesis,
                    json.dumps(report.conviction_drivers),
                    json.dumps(report.top_risks),
                    report.model_dump_json(),
                ),
            )
            row_id = cursor.lastrowid

        logger.info(
            "[ScoreStore] Saved run for %s — score=%.3f verdict=%s (id=%d)",
            report.ticker, report.final_score, report.verdict, row_id,
        )

        # Prune old records to stay within the retention limit
        self.prune_old_records(report.ticker)
        return row_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_latest(self, ticker: str) -> dict | None:
        """Return the most recent score record for a ticker."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM score_history
                WHERE ticker = ?
                ORDER BY run_at DESC
                LIMIT 1
                """,
                (ticker.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_before(self, ticker: str, before: datetime) -> dict | None:
        """The most recent score record for a ticker run strictly before
        `before` (FIX-029). `run_at` is naive UTC, so an aware `before` is
        compared in UTC and a naive one is taken as UTC. Example: the newest
        analysis made before Monday's 15:30 IST close is
        `get_latest_before(t, datetime(2026, 11, 2, 15, 30, tzinfo=IST))`,
        i.e. run before 10:00 UTC."""
        if before.tzinfo is not None:
            before = before.astimezone(timezone.utc).replace(tzinfo=None)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM score_history
                WHERE ticker = ? AND run_at < ?
                ORDER BY run_at DESC
                LIMIT 1
                """,
                (ticker.upper(), before.isoformat()),
            ).fetchone()
        return dict(row) if row else None

    def get_previous(self, ticker: str) -> dict | None:
        """Return the second-most-recent score record for a ticker."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM score_history
                WHERE ticker = ?
                ORDER BY run_at DESC
                LIMIT 2
                """,
                (ticker.upper(),),
            ).fetchall()
        return dict(rows[1]) if len(rows) >= 2 else None

    def get_history(self, ticker: str, limit: int = 30) -> list[dict]:
        """Return the last N score records for a ticker, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, company_name, run_at, final_score, verdict,
                       investment_thesis
                FROM score_history
                WHERE ticker = ?
                ORDER BY run_at DESC
                LIMIT ?
                """,
                (ticker.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_records(self, ticker: str, limit: int = 90) -> list[dict]:
        """The last N full records for a ticker (report_json included, so the
        decision gate can be read), newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM score_history
                WHERE ticker = ?
                ORDER BY run_at DESC
                LIMIT ?
                """,
                (ticker.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_date_range(self, since_iso: str, until_iso: str | None = None) -> list[dict]:
        """
        Return all score records with run_at between since_iso and until_iso (inclusive).
        If until_iso is None, returns everything from since_iso to now.
        Results are ordered newest first.
        """
        until = until_iso or datetime.utcnow().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM score_history
                WHERE run_at >= ? AND run_at <= ?
                ORDER BY run_at DESC
                """,
                (since_iso, until),
            ).fetchall()
        return [dict(r) for r in rows]

    def theses_between(self, since_iso: str, until_iso: str) -> list[dict]:
        """{"ticker", "thesis"} for each analysis run between the naive-UTC
        bounds (inclusive), the thesis cut to its first 800 characters, as a
        deep dive keeps it on its shelf idea (FIX-033). A server-side identity
        check reads it (`core/discovery/shelf.py`); no viewer is shown it, so
        FIX-010's visibility filter does not apply (its guard names the one
        caller). No report JSON is read."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT ticker, substr(investment_thesis, 1, 800) AS thesis
                FROM score_history
                WHERE run_at >= ? AND run_at <= ?
                """,
                (since_iso, until_iso),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_latest(self) -> list[dict]:
        """Return the most recent run for every ticker in the database."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT s.*
                FROM score_history s
                INNER JOIN (
                    SELECT ticker, MAX(run_at) AS max_run
                    FROM score_history
                    GROUP BY ticker
                ) latest ON s.ticker = latest.ticker AND s.run_at = latest.max_run
                ORDER BY s.ticker
                """
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Delta / change detection
    # ------------------------------------------------------------------

    def get_score_delta(self, ticker: str) -> float | None:
        """
        Return the difference between the latest and previous score.
        Returns None if fewer than 2 runs exist.
        """
        latest = self.get_latest(ticker)
        previous = self.get_previous(ticker)
        if latest is None or previous is None:
            return None
        return round(latest["final_score"] - previous["final_score"], 4)

    def get_verdict_changed(self, ticker: str) -> bool:
        """Return True if the verdict changed between the last two runs."""
        latest = self.get_latest(ticker)
        previous = self.get_previous(ticker)
        if latest is None or previous is None:
            return False
        return latest["verdict"] != previous["verdict"]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune_old_records(self, ticker: str) -> None:
        """Keep only the most recent SCORE_HISTORY_MAX_ROWS rows per ticker."""
        max_rows = settings.SCORE_HISTORY_MAX_ROWS
        with self._conn() as conn:
            conn.execute(
                """
                DELETE FROM score_history
                WHERE ticker = ?
                  AND id NOT IN (
                      SELECT id FROM score_history
                      WHERE ticker = ?
                      ORDER BY run_at DESC
                      LIMIT ?
                  )
                """,
                (ticker.upper(), ticker.upper(), max_rows),
            )

    def ticker_count(self) -> int:
        """Return number of distinct tickers in the database."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(DISTINCT ticker) FROM score_history"
            ).fetchone()[0]

    def total_runs(self) -> int:
        """Return total number of pipeline run records."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM score_history"
            ).fetchone()[0]


def theses_between(since_iso: str, until_iso: str) -> list[dict]:
    """`ScoreStore().theses_between` on the default store (FIX-033)."""
    return ScoreStore().theses_between(since_iso, until_iso)
