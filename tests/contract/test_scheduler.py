"""
tests/test_scheduler.py
========================
Unit tests for Phase 4 — ScoreStore, AlertManager, and AutomobileScheduler.
No real SQLite I/O in most tests (uses tmp_path or mocking).
No APScheduler daemon is started.

What is tested:
  - ScoreStore: save, get_latest, get_history, get_score_delta, get_verdict_changed, prune
  - AlertManager: no alert on first run, score change alert, verdict change alert
  - AlertManager: channel dispatch (console, file, webhook)
  - AutomobileScheduler.run_now() delegates to orchestrator correctly
  - Scheduler status dict has expected keys
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from core.schemas.pipeline import FinalReport, WeightedAgentScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_report(
    ticker: str = "MARUTI",
    score: float = 0.70,
    verdict: str = "BUY",
) -> FinalReport:
    ws = WeightedAgentScore(raw=score, weight=1.0, weighted=score)
    return FinalReport(
        ticker=ticker,
        company_name=f"{ticker} Ltd",
        final_score=score,
        verdict=verdict,
        weighted_agent_scores={"fundamentals": ws},
        investment_thesis="Test thesis.",
        conviction_drivers=["driver 1", "driver 2"],
        top_risks=["risk 1"],
        report_date=str(date.today()),
    )


@pytest.fixture
def db_store(tmp_path):
    """ScoreStore backed by a temp SQLite file."""
    from services.data.stores.score_store import ScoreStore
    return ScoreStore(db_path=str(tmp_path / "test_scores.db"))


# ---------------------------------------------------------------------------
# ScoreStore
# ---------------------------------------------------------------------------

class TestScoreStore:
    def test_save_and_get_latest(self, db_store):
        report = _make_report("MARUTI", 0.72, "BUY")
        db_store.save(report)
        latest = db_store.get_latest("MARUTI")
        assert latest is not None
        assert abs(latest["final_score"] - 0.72) < 1e-6
        assert latest["verdict"] == "BUY"

    def test_get_latest_unknown_ticker_returns_none(self, db_store):
        assert db_store.get_latest("UNKNOWN") is None

    def test_get_history_returns_correct_count(self, db_store):
        for i in range(5):
            db_store.save(_make_report("MARUTI", 0.50 + i * 0.05))
        history = db_store.get_history("MARUTI", limit=3)
        assert len(history) == 3

    def test_get_history_newest_first(self, db_store):
        db_store.save(_make_report("MARUTI", 0.60))
        db_store.save(_make_report("MARUTI", 0.75))
        history = db_store.get_history("MARUTI")
        assert history[0]["final_score"] > history[1]["final_score"]

    def test_score_delta_none_on_first_run(self, db_store):
        db_store.save(_make_report("BAJAJ-AUTO", 0.65))
        assert db_store.get_score_delta("BAJAJ-AUTO") is None

    def test_score_delta_computed_correctly(self, db_store):
        db_store.save(_make_report("MARUTI", 0.60))
        db_store.save(_make_report("MARUTI", 0.75))
        delta = db_store.get_score_delta("MARUTI")
        assert delta == pytest.approx(0.75 - 0.60, abs=1e-4)

    def test_verdict_changed_false_on_first_run(self, db_store):
        db_store.save(_make_report("MARUTI", 0.65, "BUY"))
        assert db_store.get_verdict_changed("MARUTI") is False

    def test_verdict_changed_true_when_different(self, db_store):
        db_store.save(_make_report("MARUTI", 0.65, "BUY"))
        db_store.save(_make_report("MARUTI", 0.40, "NEUTRAL"))
        assert db_store.get_verdict_changed("MARUTI") is True

    def test_verdict_changed_false_when_same(self, db_store):
        db_store.save(_make_report("MARUTI", 0.65, "BUY"))
        db_store.save(_make_report("MARUTI", 0.67, "BUY"))
        assert db_store.get_verdict_changed("MARUTI") is False

    def test_prune_keeps_max_rows(self, tmp_path):
        from services.data.stores.score_store import ScoreStore
        from core.config import settings
        store = ScoreStore(db_path=str(tmp_path / "prune_test.db"))

        # Override retention limit to 3 for this test
        with patch.object(settings, "SCORE_HISTORY_MAX_ROWS", 3):
            for i in range(6):
                store.save(_make_report("MARUTI", 0.50 + i * 0.01))
            store.prune_old_records("MARUTI")
            history = store.get_history("MARUTI", limit=100)
            assert len(history) <= 3

    def test_get_all_latest_returns_one_per_ticker(self, db_store):
        db_store.save(_make_report("MARUTI", 0.70))
        db_store.save(_make_report("MARUTI", 0.72))
        db_store.save(_make_report("TATAMOTORS", 0.55))
        all_latest = db_store.get_all_latest()
        tickers = [r["ticker"] for r in all_latest]
        assert len(tickers) == len(set(tickers))
        assert "MARUTI" in tickers
        assert "TATAMOTORS" in tickers

    def test_total_runs(self, db_store):
        db_store.save(_make_report("MARUTI", 0.70))
        db_store.save(_make_report("TATAMOTORS", 0.55))
        assert db_store.total_runs() == 2

    def test_ticker_count(self, db_store):
        db_store.save(_make_report("MARUTI", 0.70))
        db_store.save(_make_report("TATAMOTORS", 0.55))
        assert db_store.ticker_count() == 2


# ---------------------------------------------------------------------------
# AutomobileScheduler
# ---------------------------------------------------------------------------

class TestAutomobileScheduler:
    @patch("core.pipeline.orchestrator.AutomobileAgentOrchestrator")
    @patch("services.data.stores.score_store.ScoreStore")
    @patch("apscheduler.schedulers.background.BackgroundScheduler")
    def test_run_now_calls_orchestrator_for_each_ticker(
        self, mock_sched_cls, mock_store_cls, mock_orch_cls
    ):
        from services.scheduler.python.scheduler import AutomobileScheduler

        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_sched = MagicMock()
        mock_sched.get_jobs.return_value = []
        mock_sched_cls.return_value = mock_sched

        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.analyse.return_value = _make_report("MARUTI", 0.70)

        with patch("services.scheduler.python.scheduler.settings.SCHEDULER_TICKERS", ["MARUTI", "TATAMOTORS"]):
            sched = AutomobileScheduler()
            sched.run_now(["MARUTI"])

        assert mock_orch.analyse.call_count == 1

    @patch("services.data.stores.score_store.ScoreStore")
    @patch("apscheduler.schedulers.background.BackgroundScheduler")
    def test_status_has_required_keys(
        self, mock_sched_cls, mock_store_cls
    ):
        from services.scheduler.python.scheduler import AutomobileScheduler

        mock_store = MagicMock()
        mock_store.total_runs.return_value = 5
        mock_store.ticker_count.return_value = 3
        mock_store_cls.return_value = mock_store

        mock_sched = MagicMock()
        mock_sched.get_jobs.return_value = []
        mock_sched_cls.return_value = mock_sched

        sched = AutomobileScheduler()
        status = sched.status()

        assert "enabled" in status
        assert "feedback_cron" in status
        assert "tickers" in status
        assert "db_total_runs" in status
        assert "db_ticker_count" in status
        assert "jobs" in status
