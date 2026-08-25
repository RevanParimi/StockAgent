"""
tests/unit/shared/test_error_capture_context.py
================================================
Three Loops PI — task E1: close the error-capture gaps.

Prod evidence (spec §2.6): `app_logs` holds 4,357 WARNING+ rows over 53 days
and survives redeploys, so capture itself works. Four gaps stop it being a
diagnosis surface — three named in the spec, one measured while closing them:

1. **No run correlation.** The schema was `(id, ts, level, logger, message)`,
   so an error could not be tied to the run that caused it.
2. **Tracebacks in 18 of 4,254 rows** — NOT because the handler drops them
   (§2.0 records that as a wrong claim; `Formatter.format()` appends
   `exc_text` regardless of the format string) but because 194 call sites pass
   the exception as a `%s` arg instead of `exc_info=`. The fix belongs at
   hot-path call sites.
3. **The handler was attached in exactly one place** (`server.py:75`), so a
   script run under `railway ssh` archived nothing.
4. **MEASURED IN PROD 2026-08-26:** every stored message carried a duplicated
   `"<IST ts> LEVEL [logger] "` prefix. The archive handler's `%(message)s`
   formatter was overwritten two lines later by the loop that re-formats every
   root handler, so the message column embedded a per-record timestamp —
   which would have made E2's fingerprinting impossible.
"""
from __future__ import annotations

import ast
import asyncio
import contextvars
import logging
import sqlite3
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import services.data.stores.log_store as log_store
from core.schemas.pipeline import AgentOutput, StockQuery
from services.data.context import bundle_builder as bb

_REPO = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def archiving_logger():
    """A named logger wired to its own archive handler, isolated from root.

    Isolation matters: tests that import services.api.server leave a
    session-wide SQLiteLogHandler on root, which would double-write every
    record into the redirected DB.
    """
    handler = log_store.SQLiteLogHandler(level=logging.WARNING)
    handler.setFormatter(logging.Formatter("%(message)s"))
    made: list[logging.Logger] = []

    def _attach(name: str) -> logging.Logger:
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        lg.propagate = False
        lg.setLevel(logging.WARNING)
        made.append(lg)
        return lg

    yield _attach
    for lg in made:
        lg.removeHandler(handler)
        lg.propagate = True


def _rows(db_path, sql):
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(sql).fetchall()


# ---------------------------------------------------------------------------
# 1. Run correlation — gap 3 in the spec's list
# ---------------------------------------------------------------------------

class TestRunCorrelation:
    def test_row_carries_the_run_id_and_ticker_of_the_run_in_flight(self, fresh_db):
        with log_store.run_context("186c7ad4", "SUZLON"):
            log_store.log_app_record("ERROR", "backend.pipeline", "boom")
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs") == [
            ("186c7ad4", "SUZLON")
        ]

    def test_row_is_null_when_nothing_is_running(self, fresh_db):
        log_store.log_app_record("WARNING", "services.data.backup", "no off-site copy")
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs") == [(None, None)]

    def test_ticker_resolved_mid_run_lands_on_later_rows(self, fresh_db):
        with log_store.run_context("186c7ad4"):
            log_store.log_app_record("WARNING", "orch", "before resolution")
            log_store.set_run_ticker("ADANIGREEN")
            log_store.log_app_record("WARNING", "orch", "after resolution")
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs ORDER BY id") == [
            ("186c7ad4", None),
            ("186c7ad4", "ADANIGREEN"),
        ]

    def test_the_context_is_cleared_when_the_run_ends(self, fresh_db):
        with log_store.run_context("186c7ad4", "SUZLON"):
            pass
        log_store.log_app_record("ERROR", "scheduler", "unrelated later failure")
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs") == [(None, None)]

    def test_a_ticker_set_mid_run_does_not_leak_past_it(self, fresh_db):
        with log_store.run_context("186c7ad4"):
            log_store.set_run_ticker("SUZLON")
        log_store.log_app_record("ERROR", "scheduler", "later")
        assert _rows(fresh_db, "SELECT ticker FROM app_logs") == [(None,)]

    def test_the_context_survives_a_raise(self, fresh_db):
        with pytest.raises(ValueError):
            with log_store.run_context("186c7ad4", "SUZLON"):
                raise ValueError("run blew up")
        log_store.log_app_record("ERROR", "scheduler", "later")
        assert _rows(fresh_db, "SELECT run_id FROM app_logs") == [(None,)]

    def test_the_context_reaches_work_offloaded_to_a_thread(self, fresh_db):
        """analyse_async() fans out through asyncio.to_thread, which copies the
        context — an error raised in that thread must still name its run."""

        async def _run():
            with log_store.run_context("186c7ad4", "SUZLON"):
                await asyncio.to_thread(
                    log_store.log_app_record, "ERROR", "agent.thread", "fetch died"
                )

        asyncio.run(_run())
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs") == [
            ("186c7ad4", "SUZLON")
        ]

    def test_two_runs_in_parallel_do_not_cross_contaminate(self, fresh_db):
        """One ContextVar, two threads, each carrying its own copied context."""

        def _one(run_id: str, ticker: str) -> None:
            with log_store.run_context(run_id, ticker):
                log_store.log_app_record("ERROR", "agent", f"{ticker} failed")

        threads = [
            threading.Thread(target=contextvars.copy_context().run, args=(_one, rid, tkr))
            for rid, tkr in (("aaaa1111", "SUZLON"), ("bbbb2222", "TATAMOTORS"))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        got = dict(_rows(fresh_db, "SELECT run_id, ticker FROM app_logs"))
        assert got == {"aaaa1111": "SUZLON", "bbbb2222": "TATAMOTORS"}

    def test_an_explicit_argument_still_wins_over_the_context(self, fresh_db):
        with log_store.run_context("186c7ad4", "SUZLON"):
            log_store.log_app_record(
                "ERROR", "backfill", "row 12", run_id="deadbeef", ticker="INFY"
            )
        assert _rows(fresh_db, "SELECT run_id, ticker FROM app_logs") == [
            ("deadbeef", "INFY")
        ]


# ---------------------------------------------------------------------------
# 2. The 4,357 existing prod rows must survive the migration
# ---------------------------------------------------------------------------

def _legacy_db(path: Path) -> None:
    """Build the pre-E1 app_logs — the exact schema running in prod today."""
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE app_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT NOT NULL, level TEXT NOT NULL, logger TEXT NOT NULL, "
            "message TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO app_logs (ts, level, logger, message) VALUES (?,?,?,?)",
            ("2026-07-11T09:14:02+00:00", "ERROR",
             "backend.shared.pipeline.graphs.nodes", "agent failed on generic"),
        )
        conn.commit()


class TestLegacyRowsSurvive:
    def test_an_existing_table_gains_the_columns_in_place(self, tmp_path, monkeypatch):
        db_path = tmp_path / "telemetry.db"
        _legacy_db(db_path)
        monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path),
                            raising=False)
        monkeypatch.setattr(log_store, "_conn", None)
        try:
            log_store._get_conn()
            cols = [r[1] for r in _rows(db_path, "PRAGMA table_info(app_logs)")]
        finally:
            if log_store._conn is not None:
                log_store._conn.close()
                log_store._conn = None
        assert "run_id" in cols and "ticker" in cols

    def test_rows_written_before_the_migration_stay_readable(self, tmp_path, monkeypatch):
        db_path = tmp_path / "telemetry.db"
        _legacy_db(db_path)
        monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path),
                            raising=False)
        monkeypatch.setattr(log_store, "_conn", None)
        try:
            log_store.log_app_record("ERROR", "new.module", "after the migration")
            # The pre-E1 projection — what every existing query uses — still works.
            old = _rows(db_path, "SELECT id, ts, level, logger, message FROM app_logs "
                                 "ORDER BY id")
        finally:
            if log_store._conn is not None:
                log_store._conn.close()
                log_store._conn = None
        assert len(old) == 2
        assert old[0][3] == "backend.shared.pipeline.graphs.nodes"
        assert _rows(db_path, "SELECT run_id FROM app_logs ORDER BY id") == [
            (None,), (None,)
        ]

    def test_the_migration_is_idempotent(self, tmp_path, monkeypatch):
        db_path = tmp_path / "telemetry.db"
        _legacy_db(db_path)
        monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path),
                            raising=False)
        for _ in range(2):
            monkeypatch.setattr(log_store, "_conn", None)
            log_store.log_app_record("ERROR", "m", "x")
            if log_store._conn is not None:
                log_store._conn.close()
                log_store._conn = None
        cols = [r[1] for r in _rows(db_path, "PRAGMA table_info(app_logs)")]
        assert cols.count("run_id") == 1 and cols.count("ticker") == 1

    def test_a_migration_that_cannot_run_does_not_take_telemetry_down(
        self, tmp_path, monkeypatch
    ):
        """Two uvicorn workers boot together and both ALTER the same table. If a
        `database is locked` there escaped, _get_conn would return None and that
        worker would silently archive nothing — llm_calls, run_summaries and
        data_health included — until the next restart. Telemetry degrades to the
        column it could not add, never to the whole connection."""
        db_path = tmp_path / "telemetry.db"
        _legacy_db(db_path)
        monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path),
                            raising=False)
        monkeypatch.setattr(log_store, "_conn", None)

        def _locked(conn, table, column, decl):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(log_store, "_add_column", _locked)
        try:
            assert log_store._get_conn() is not None
            log_store.log_llm_call("UnifiedAnalyst", "glm-5.2", 10, 5, 100, True)
            rows = _rows(db_path, "SELECT caller FROM llm_calls")
        finally:
            if log_store._conn is not None:
                log_store._conn.close()
                log_store._conn = None
        assert rows == [("UnifiedAnalyst",)]

    def test_a_legacy_llm_calls_table_still_migrates(self, tmp_path, monkeypatch):
        """The Atlas C8 user_id migration must keep working through the refactor."""
        db_path = tmp_path / "telemetry.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts TEXT NOT NULL, caller TEXT NOT NULL, model TEXT NOT NULL, "
                "input_tokens INTEGER NOT NULL DEFAULT 0, "
                "output_tokens INTEGER NOT NULL DEFAULT 0, "
                "latency_ms INTEGER NOT NULL DEFAULT 0, "
                "success INTEGER NOT NULL DEFAULT 1)"
            )
            conn.commit()
        monkeypatch.setattr(log_store.settings, "TELEMETRY_DB_PATH", str(db_path),
                            raising=False)
        monkeypatch.setattr(log_store, "_conn", None)
        try:
            log_store.log_llm_call("X", "m", 1, 1, 1, True)
            cols = [r[1] for r in _rows(db_path, "PRAGMA table_info(llm_calls)")]
        finally:
            if log_store._conn is not None:
                log_store._conn.close()
                log_store._conn = None
        assert "user_id" in cols


# ---------------------------------------------------------------------------
# 3. Tracebacks — gap 1. The handler was always fine; the call sites were not.
# ---------------------------------------------------------------------------

class TestTracebacksReachTheArchive:
    def test_exc_info_puts_a_traceback_in_the_archived_message(
        self, fresh_db, archiving_logger
    ):
        lg = archiving_logger("test.hotpath")
        try:
            raise RuntimeError("connection reset by peer")
        except RuntimeError as exc:
            lg.error("[X] fetch failed: %s", exc, exc_info=True)
        message = _rows(fresh_db, "SELECT message FROM app_logs")[0][0]
        assert "Traceback (most recent call last)" in message
        assert "RuntimeError: connection reset by peer" in message

    def test_a_percent_s_call_site_archives_no_traceback(self, fresh_db, archiving_logger):
        """Pins the mechanism §2.0 corrects: the gap is the call site, not the
        handler. Without exc_info the message is the formatted string alone."""
        lg = archiving_logger("test.percent_s")
        try:
            raise RuntimeError("connection reset by peer")
        except RuntimeError as exc:
            lg.error("[X] fetch failed: %s", exc)
        message = _rows(fresh_db, "SELECT message FROM app_logs")[0][0]
        assert "Traceback" not in message

    def test_a_failing_bundle_section_archives_its_traceback(
        self, fresh_db, archiving_logger
    ):
        """The single highest-value site: _safe wraps all 10 bundle sections."""
        archiving_logger(bb.__name__)

        def _boom():
            raise ConnectionError("serper timed out")

        sections, status = {}, {}
        bb._safe(sections, status, "company_news", _boom)

        message = _rows(fresh_db, "SELECT message FROM app_logs")[0][0]
        assert "Traceback (most recent call last)" in message
        assert "ConnectionError: serper timed out" in message
        # The B2 contract is untouched: the section still degrades, not raises.
        assert status["company_news"] == "failed:ConnectionError"


class TestHotPathCallSitesPassExcInfo:
    """A CI gate for gap 1, so it cannot silently re-open.

    §2.6 measured 24 `exc_info=` uses against 194 `%s`-arg sites repo-wide. E1
    does NOT touch all 194 — it fixes the analysis hot path and pins it here.
    An `except` clause that binds its exception and then logs it must pass
    `exc_info`, unless the failure is expected and self-describing.
    """

    HOT_PATH = [
        "src/backend/shared/pipeline/base_orchestrator.py",
        "src/backend/shared/pipeline/unified_analyst.py",
        "services/data/context/bundle_builder.py",
        "core/intelligence/rl/stores/prediction_store.py",
    ]

    # Expected, self-describing, retried failures. A traceback here is noise at
    # WARNING volume — the message already carries the cause and the attempt.
    ALLOWED_WITHOUT = (
        "Rate limit hit",
        "Timeout (attempt",
        "response truncated",
    )

    @staticmethod
    def _sites(path: Path):
        """Yield (lineno, first-format-arg, has_exc_info) for every logger
        error/warning call lexically inside an exception-binding except block."""
        # utf-8-sig: prediction_store.py still carries a UTF-8 BOM on main.
        # Stripping it belongs to the repo-hygiene branch, not to this gate.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler) or handler.name is None:
                continue
            for node in ast.walk(handler):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr not in ("error", "warning", "exception"):
                    continue
                if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
                    continue
                fmt = node.args[0] if node.args else None
                text = fmt.value if isinstance(fmt, ast.Constant) else ""
                has = (
                    func.attr == "exception"
                    or any(kw.arg == "exc_info" for kw in node.keywords)
                )
                yield node.lineno, text, has

    @pytest.mark.parametrize("rel", HOT_PATH)
    def test_every_exception_binding_site_carries_a_traceback(self, rel):
        path = _REPO / rel
        missing = [
            f"{rel}:{lineno} {text[:60]!r}"
            for lineno, text, has in self._sites(path)
            if not has and not any(a in text for a in self.ALLOWED_WITHOUT)
        ]
        assert missing == [], (
            "hot-path except handlers logging without exc_info=True:\n  "
            + "\n  ".join(missing)
        )

    def test_the_gate_actually_inspects_something(self):
        """Guards against a silently-empty parametrised assertion."""
        total = sum(len(list(self._sites(_REPO / rel))) for rel in self.HOT_PATH)
        assert total >= 10, f"expected the hot path to hold sites to check, found {total}"


# ---------------------------------------------------------------------------
# 4. One configure_logging() — gap 2, plus the measured prefix duplication
# ---------------------------------------------------------------------------

@pytest.fixture()
def clean_root():
    """Run with a bare root logger, restoring the session's handlers after."""
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    root.handlers = []
    yield root
    root.handlers = saved
    root.setLevel(saved_level)


class TestConfigureLogging:
    def test_it_attaches_the_archive_handler(self, clean_root, fresh_db):
        log_store.configure_logging()
        assert any(isinstance(h, log_store.SQLiteLogHandler)
                   for h in clean_root.handlers)

    def test_calling_it_twice_attaches_one_handler(self, clean_root, fresh_db):
        log_store.configure_logging()
        log_store.configure_logging()
        archives = [h for h in clean_root.handlers
                    if isinstance(h, log_store.SQLiteLogHandler)]
        assert len(archives) == 1

    def test_a_script_entry_point_archives_its_warnings(self, clean_root, fresh_db):
        """Gap 2: before E1 the handler lived only in server.py, so anything
        run as `railway ssh python -m ...` archived nothing."""
        log_store.configure_logging()
        logging.getLogger("scripts.atlas_etl").warning("etl skipped 3 rows")
        assert _rows(fresh_db, "SELECT logger, message FROM app_logs") == [
            ("scripts.atlas_etl", "etl skipped 3 rows")
        ]

    def test_the_archived_message_carries_no_timestamp_prefix(self, clean_root, fresh_db):
        """Gap 4, measured in prod: ts/level/logger already have columns, and a
        per-record timestamp inside the message would break E2's fingerprints."""
        log_store.configure_logging()
        logging.getLogger("core.delivery.channels").warning(
            "[delivery] email send failed (non-fatal): %s", "Errno 101"
        )
        message = _rows(fresh_db, "SELECT message FROM app_logs")[0][0]
        assert message == "[delivery] email send failed (non-fatal): Errno 101"

    def test_the_console_handler_still_shows_ist_and_the_logger_name(
        self, clean_root, fresh_db
    ):
        """Fixing the archive prefix must not strip the console format."""
        log_store.configure_logging()
        stream = [h for h in clean_root.handlers
                  if not isinstance(h, log_store.SQLiteLogHandler)]
        assert stream, "expected a console handler"
        record = logging.LogRecord("core.delivery.channels", logging.WARNING,
                                   "f.py", 1, "email send failed", None, None)
        rendered = stream[0].format(record)
        assert "IST" in rendered and "[core.delivery.channels]" in rendered

    def test_info_still_stays_out_of_the_archive(self, clean_root, fresh_db):
        log_store.configure_logging()
        log_store._get_conn()  # force schema creation so the count query is valid
        logging.getLogger("chatty.module").info("routine line")
        assert _rows(fresh_db, "SELECT COUNT(*) FROM app_logs") == [(0,)]

    def test_a_broken_archive_never_blocks_startup(self, clean_root, monkeypatch):
        """Telemetry must never be the reason a process fails to boot."""

        class _BrokenHandler(log_store.SQLiteLogHandler):
            def __init__(self, *a, **kw):
                raise RuntimeError("no disk")

        monkeypatch.setattr(log_store, "SQLiteLogHandler", _BrokenHandler)
        log_store.configure_logging()  # no exception = pass
        assert clean_root.handlers, "console logging must still be configured"


# ---------------------------------------------------------------------------
# 5. The orchestrator opens the run context
# ---------------------------------------------------------------------------

class _DummyAgent:
    def run(self, query, run_id):  # pragma: no cover - graph is never invoked
        return AgentOutput(agent="dummy", ticker=query.ticker, overall_score=0.5)


def _orchestrator():
    from backend.shared.pipeline.base_orchestrator import BaseSectorOrchestrator

    class _TestOrchestrator(BaseSectorOrchestrator):
        SECTOR_NAME = "renewable_energy"

        def __init__(self) -> None:
            self._sub_agents = {"dummy": _DummyAgent()}
            super().__init__()

    with patch("backend.shared.pipeline.base_orchestrator.get_llm_client",
               return_value=MagicMock()):
        orch = _TestOrchestrator()
    orch._aggregator = MagicMock()
    orch._aggregator.run.return_value = MagicMock(
        final_score=0.5, verdict="HOLD", data_health=None
    )
    return orch


@pytest.fixture()
def quiet_orchestrator(monkeypatch):
    """An orchestrator with every side-effecting leg of analyse() stubbed."""
    import backend.shared.pipeline.base_orchestrator as bo

    orch = _orchestrator()
    monkeypatch.setattr(
        orch, "_resolve_ticker",
        lambda user_input, run_id="": StockQuery(ticker="SUZLON",
                                                company_name="Suzlon Energy Ltd"),
    )
    monkeypatch.setattr(orch, "_resolve_weights_for", lambda ticker: None)
    monkeypatch.setattr(orch, "_load_learned_weights", lambda ticker: None)
    monkeypatch.setattr(orch, "_prefetch_nse_data", lambda query: None)
    monkeypatch.setattr(bo, "log_run_summary", lambda **kw: None)
    monkeypatch.setattr(bo, "log_run_api_usage", lambda *a, **kw: None)
    monkeypatch.setattr(bo, "log_analysis", lambda **kw: None)
    return orch


class TestOrchestratorOpensTheRunContext:
    def test_agents_run_inside_the_context(self, quiet_orchestrator, monkeypatch):
        seen = {}

        def _agents(query, run_id="", progress_callback=None):
            seen["run_id"] = log_store.current_run_id.get()
            seen["ticker"] = log_store.current_ticker.get()
            seen["passed"] = run_id
            return {}

        monkeypatch.setattr(quiet_orchestrator, "_run_agents", _agents)
        quiet_orchestrator.analyse("suzlon")

        assert seen["run_id"] == seen["passed"] != ""
        assert seen["ticker"] == "SUZLON"

    def test_the_context_is_closed_when_analyse_returns(
        self, quiet_orchestrator, monkeypatch
    ):
        monkeypatch.setattr(quiet_orchestrator, "_run_agents",
                            lambda *a, **kw: {})
        quiet_orchestrator.analyse("suzlon")
        assert log_store.current_run_id.get() is None
        assert log_store.current_ticker.get() is None

    def test_the_async_path_opens_it_too(self, quiet_orchestrator, monkeypatch):
        seen = {}

        def _agents(query, run_id="", progress_callback=None):
            seen["run_id"] = log_store.current_run_id.get()
            seen["ticker"] = log_store.current_ticker.get()
            return {}

        monkeypatch.setattr(quiet_orchestrator, "_run_agents", _agents)
        monkeypatch.setattr(quiet_orchestrator, "_unified_enabled", lambda: True)
        asyncio.run(quiet_orchestrator.analyse_async("suzlon"))

        assert seen["run_id"] and seen["ticker"] == "SUZLON"

    def test_a_failing_run_still_closes_the_context(
        self, quiet_orchestrator, monkeypatch
    ):
        def _explode(*a, **kw):
            raise RuntimeError("aggregator died")

        monkeypatch.setattr(quiet_orchestrator, "_run_agents", _explode)
        with pytest.raises(RuntimeError):
            quiet_orchestrator.analyse("suzlon")
        assert log_store.current_run_id.get() is None
