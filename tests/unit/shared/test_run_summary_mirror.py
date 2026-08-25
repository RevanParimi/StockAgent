"""
tests/unit/shared/test_run_summary_mirror.py
=============================================
Three Loops PI — task B1: `log_run_summary` gets the SQLite mirror that
`log_llm_call` has had since 2026-07-02.

Moving the JSONL onto the volume (see test_run_history_durable_path.py) stops
the redeploy wipe, but a JSONL file is not queryable and nothing notices when
it stops growing. `telemetry.db` already survives deploys and already carries
`llm_calls` and `app_logs`; run summaries join them there, and a boot line
reports the surviving row count so a broken mirror shows up in the deploy log
instead of waiting 53 days for someone to count rows.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from unittest import mock

import pytest

import services.data.stores.log_store as log_store
import services.data.stores.run_logger as rl


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Point the store at a throwaway DB and reset its cached connection."""
    db_path = tmp_path / "telemetry.db"
    monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(log_store, "_conn", None)
    yield db_path
    if log_store._conn is not None:
        log_store._conn.close()
        log_store._conn = None


@pytest.fixture()
def logs_dir(tmp_path):
    """Re-execute run_logger with LOGS_DIR pinned to a throwaway directory."""
    target = tmp_path / "logs"
    clean = {k: v for k, v in os.environ.items() if k != "LOGS_DIR"}
    clean["LOGS_DIR"] = str(target)
    with mock.patch.dict(os.environ, clean, clear=True):
        importlib.reload(rl)
        yield target
    importlib.reload(rl)


def _log_a_run(mod, *, run_id="r1", ticker="MARUTI", verdict="BUY") -> None:
    mod.log_run_summary(
        run_id=run_id,
        ticker=ticker,
        company_name="Maruti Suzuki",
        started_at=datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc),
        duration_seconds=12.5,
        final_score=0.61,
        verdict=verdict,
        total_prompt_tokens=1200,
        total_completion_tokens=300,
        total_cost_usd=0.0042,
        agent_scores={"technical": 0.5, "fundamentals": 0.7},
        errors=["macro fetch failed"],
    )


# ── the acceptance: a run written is a run queryable ──────────────────────

def test_a_logged_run_is_queryable_from_telemetry_db(fresh_db, logs_dir):
    _log_a_run(rl)

    with sqlite3.connect(str(fresh_db)) as conn:
        rows = conn.execute(
            "SELECT run_id, ticker, verdict, final_score, total_cost_usd, "
            "error_count FROM run_summaries"
        ).fetchall()

    assert rows == [("r1", "MARUTI", "BUY", 0.61, 0.0042, 1)]


def test_agent_scores_and_errors_survive_as_json(fresh_db, logs_dir):
    _log_a_run(rl)

    with sqlite3.connect(str(fresh_db)) as conn:
        scores, errors = conn.execute(
            "SELECT agent_scores, errors FROM run_summaries"
        ).fetchone()

    assert json.loads(scores) == {"technical": 0.5, "fundamentals": 0.7}
    assert json.loads(errors) == ["macro fetch failed"]


def test_the_jsonl_is_still_written(fresh_db, logs_dir):
    """The mirror is additive — the file the UI and scripts read stays."""
    _log_a_run(rl)

    lines = (logs_dir / "run_summaries.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "r1"


def test_a_failing_mirror_never_breaks_the_run(fresh_db, logs_dir, monkeypatch):
    """Telemetry must not be able to take a run down — same rule as
    log_llm_call's mirror."""
    def _boom(**kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(log_store, "log_run_summary", _boom)

    _log_a_run(rl)      # must not raise

    assert (logs_dir / "run_summaries.jsonl").exists()


# ── boot-time durability report ───────────────────────────────────────────

def test_boot_state_reports_the_surviving_row_count(fresh_db, logs_dir):
    _log_a_run(rl, run_id="r1")
    _log_a_run(rl, run_id="r2")

    state = rl.log_boot_state()

    assert state["db_rows"] == 2
    assert state["jsonl_rows"] == 2
    assert state["jsonl_path"].endswith("run_summaries.jsonl")


def test_boot_state_on_a_fresh_volume_reports_zero(fresh_db, logs_dir):
    state = rl.log_boot_state()

    assert state == {
        "jsonl_path": str(logs_dir / "run_summaries.jsonl"),
        "jsonl_rows": 0,
        "db_rows": 0,
        "mirror_broken": False,
    }


def test_boot_state_flags_history_the_mirror_never_captured(fresh_db, logs_dir, caplog):
    """The signal this line exists to catch: the JSONL is growing but the
    durable copy is not, i.e. the mirror is silently failing."""
    (logs_dir).mkdir(parents=True, exist_ok=True)
    (logs_dir / "run_summaries.jsonl").write_text(
        '{"run_id": "r1"}\n{"run_id": "r2"}\n', encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        state = rl.log_boot_state()

    assert state["mirror_broken"] is True
    assert "run_summaries" in caplog.text


def test_boot_state_never_raises_on_a_corrupt_history_file(fresh_db, logs_dir):
    """Startup must not be taken down by a truncated log file."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "run_summaries.jsonl").write_bytes(b"\xff\xfe not utf 8 at all")

    state = rl.log_boot_state()      # must not raise

    assert state["db_rows"] == 0
