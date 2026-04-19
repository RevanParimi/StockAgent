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
ScoreStore().get_history(ticker, limit)            → list[dict]
ScoreStore().get_score_delta(ticker)               → float | None
ScoreStore().get_verdict_changed(ticker)           → bool
ScoreStore().prune_old_records(ticker)
ScoreStore().get_all_latest()                      → list[dict]
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests

from config import settings
from models.schemas import FinalReport

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
        Persist a FinalReport.

        When CSHARP_SCHEDULER_ENABLED=True the report is proxied to the C#
        persistence layer (POST {CSHARP_API_URL}/scores).  SQLite is used
        as the default/fallback (CSHARP_SCHEDULER_ENABLED=False).

        Returns the new row id (or -1 when proxied to C#).
        """
        if settings.CSHARP_SCHEDULER_ENABLED:
            try:
                url = f"{settings.CSHARP_API_URL}/scores"
                requests.post(url, json=report.model_dump(), timeout=10)
                logger.info(
                    "[ScoreStore] Proxied %s to C# scheduler at %s", report.ticker, url
                )
            except Exception as exc:
                logger.warning(
                    "[ScoreStore] C# proxy failed for %s (%s) — continuing without persistence",
                    report.ticker, exc,
                )
            return -1

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
