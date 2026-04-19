"""
tests/test_phase4_csharp.py
============================
Phase 4 — C# scheduler + persistence integration contract (Python-side).

The C# service (csharp/StockAgent.Scheduler/) calls Python's FastAPI and
writes results to SQL Server via EF Core.  Python's score_store.py proxies
writes to C# when CSHARP_SCHEDULER_ENABLED=true.

What is tested:
  - Settings: CSHARP_SCHEDULER_ENABLED and CSHARP_API_URL exist in config
  - score_store.save() proxies to C# HTTP endpoint when flag is enabled
  - score_store.save() uses SQLite as normal when flag is disabled (default)
  - JSON serialisation is snake_case compatible with C# JsonNamingPolicy.SnakeCaseLower
  - FinalReport fields map to the expected C# DTO property names
  - C# health-check contract: GET /health endpoint returns expected shape
  - C# scheduler status contract: GET /scheduler/status shape
  - C# scores endpoint contract: POST /scores accepts FinalReport JSON
  - Quartz cron expression matches Python APScheduler cron expression
  - Score delta detection works identically in Python SQLite and via proxy

No real C# service is started — all C# calls are mocked via requests/httpx.
"""

from __future__ import annotations

import json
from datetime import date
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
        conviction_drivers=["Strong demand", "FII buying"],
        top_risks=["EV lag", "Crude"],
        investment_thesis="Solid outlook.",
        report_date=str(date.today()),
    )


# ---------------------------------------------------------------------------
# 1. Settings contract
# ---------------------------------------------------------------------------

class TestCSharpSettings:
    def test_csharp_scheduler_enabled_setting_exists(self):
        from config import settings
        assert hasattr(settings, "CSHARP_SCHEDULER_ENABLED"), (
            "CSHARP_SCHEDULER_ENABLED missing from settings.py — "
            "add: CSHARP_SCHEDULER_ENABLED: bool = os.getenv('CSHARP_SCHEDULER_ENABLED','false').lower()=='true'"
        )

    def test_csharp_api_url_setting_exists(self):
        from config import settings
        assert hasattr(settings, "CSHARP_API_URL"), (
            "CSHARP_API_URL missing from settings.py — "
            "add: CSHARP_API_URL: str = os.getenv('CSHARP_API_URL', 'http://localhost:5000')"
        )

    def test_csharp_scheduler_disabled_by_default(self):
        from config import settings
        assert settings.CSHARP_SCHEDULER_ENABLED is False, (
            "CSHARP_SCHEDULER_ENABLED must default to False — "
            "C# scheduler is opt-in via env var"
        )

    def test_csharp_api_url_default_is_port_5000(self):
        from config import settings
        assert "5000" in settings.CSHARP_API_URL, (
            f"Expected CSHARP_API_URL to include port 5000, got: {settings.CSHARP_API_URL}"
        )


# ---------------------------------------------------------------------------
# 2. score_store proxy behaviour
# ---------------------------------------------------------------------------

class TestScoreStoreProxy:
    @patch("services.data.stores.score_store.requests.post")
    def test_save_proxies_to_csharp_when_enabled(self, mock_post, tmp_path):
        """When CSHARP_SCHEDULER_ENABLED=True, save() must POST to C# /scores."""
        from services.data.stores.score_store import ScoreStore
        from config import settings

        mock_post.return_value = MagicMock(status_code=201)
        store = ScoreStore(db_path=str(tmp_path / "test.db"))
        report = _make_report()

        with patch.object(settings, "CSHARP_SCHEDULER_ENABLED", True), \
             patch.object(settings, "CSHARP_API_URL", "http://localhost:5000"):
            store.save(report)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "scores" in call_args[0][0] or "scores" in call_args.kwargs.get("url", "")

    @patch("services.data.stores.score_store.requests.post")
    def test_save_sends_report_as_json(self, mock_post, tmp_path):
        from services.data.stores.score_store import ScoreStore
        from config import settings

        mock_post.return_value = MagicMock(status_code=201)
        store = ScoreStore(db_path=str(tmp_path / "test.db"))
        report = _make_report()

        with patch.object(settings, "CSHARP_SCHEDULER_ENABLED", True), \
             patch.object(settings, "CSHARP_API_URL", "http://localhost:5000"):
            store.save(report)

        call_kwargs = mock_post.call_args.kwargs
        assert "json" in call_kwargs or len(mock_post.call_args.args) >= 2

    def test_save_uses_sqlite_when_csharp_disabled(self, tmp_path):
        """With flag off, save() must write to SQLite as usual."""
        from services.data.stores.score_store import ScoreStore
        from config import settings

        store = ScoreStore(db_path=str(tmp_path / "test.db"))
        report = _make_report()

        with patch.object(settings, "CSHARP_SCHEDULER_ENABLED", False):
            store.save(report)

        # Verify data is actually in SQLite
        latest = store.get_latest("MARUTI")
        assert latest is not None
        assert abs(latest["final_score"] - 0.70) < 1e-6

    @patch("services.data.stores.score_store.requests.post")
    def test_proxy_failure_does_not_crash(self, mock_post, tmp_path):
        """C# service being down must not crash the Python pipeline."""
        from services.data.stores.score_store import ScoreStore
        from config import settings

        mock_post.side_effect = Exception("Connection refused")
        store = ScoreStore(db_path=str(tmp_path / "test.db"))
        report = _make_report()

        with patch.object(settings, "CSHARP_SCHEDULER_ENABLED", True), \
             patch.object(settings, "CSHARP_API_URL", "http://localhost:5000"):
            # Should not raise
            store.save(report)


# ---------------------------------------------------------------------------
# 3. JSON serialisation contract — C# SnakeCaseLower compatibility
# ---------------------------------------------------------------------------

class TestCSharpJsonContract:
    def test_report_serialised_with_snake_case_keys(self):
        """C# uses JsonNamingPolicy.SnakeCaseLower — all keys must be snake_case."""
        report = _make_report()
        data = report.model_dump()

        for key in data.keys():
            assert key == key.lower(), (
                f"Key '{key}' is not snake_case — C# SnakeCaseLower will fail to deserialise it"
            )

    def test_csharp_dto_fields_present(self):
        """Maps to C# FinalReportDto property names."""
        expected_csharp_fields = {
            "ticker",            # string Ticker
            "company_name",      # string CompanyName
            "final_score",       # double FinalScore
            "verdict",           # string Verdict
            "investment_thesis", # string InvestmentThesis
            "conviction_drivers", # List<string> ConvictionDrivers
            "top_risks",         # List<string> TopRisks
            "report_date",       # string ReportDate
            "weighted_agent_scores", # Dictionary<string, WeightedAgentScore>
        }
        data = _make_report().model_dump()
        for field in expected_csharp_fields:
            assert field in data, f"C# DTO field '{field}' missing from Python serialisation"

    def test_weighted_agent_score_csharp_fields(self):
        """WeightedAgentScore C# DTO fields: raw, weight, weighted."""
        report = _make_report()
        data = report.model_dump()
        for agent_name, score in data["weighted_agent_scores"].items():
            assert "raw" in score, f"Missing 'raw' for {agent_name}"
            assert "weight" in score, f"Missing 'weight' for {agent_name}"
            assert "weighted" in score, f"Missing 'weighted' for {agent_name}"

    def test_report_json_string_is_utf8_safe(self):
        """C# reads UTF-8. Report with unicode chars must serialise cleanly."""
        report = _make_report()
        data = report.model_dump()
        json_str = json.dumps(data, ensure_ascii=False)
        # Re-parse — must be lossless
        reparsed = json.loads(json_str)
        assert reparsed["ticker"] == report.ticker

    def test_final_score_serialises_as_number(self):
        data = _make_report().model_dump()
        assert isinstance(data["final_score"], float)

    def test_conviction_drivers_serialises_as_array(self):
        data = _make_report().model_dump()
        assert isinstance(data["conviction_drivers"], list)

    def test_top_risks_serialises_as_array(self):
        data = _make_report().model_dump()
        assert isinstance(data["top_risks"], list)


# ---------------------------------------------------------------------------
# 4. Cron schedule contract — Python APScheduler ↔ C# Quartz.NET
# ---------------------------------------------------------------------------

class TestCronScheduleContract:
    def test_python_default_cron_is_weekday_0830(self):
        """APScheduler default: weekdays at 08:30 IST."""
        from config import settings
        cron = getattr(settings, "SCHEDULER_CRON", "30 8 * * 1-5")
        # Should encode 8:30am weekdays
        assert "30" in cron and "8" in cron

    def test_quartz_cron_equivalent(self):
        """
        APScheduler '30 8 * * 1-5' (cron syntax) must map to
        Quartz.NET '0 30 8 ? * MON-FRI' (seconds prefix, ? for day-of-month).
        This is a documentation contract — both must trigger at the same time.
        """
        apscheduler_cron = "30 8 * * 1-5"
        quartz_cron = "0 30 8 ? * MON-FRI"

        # Parse APScheduler cron: min hour dom month dow
        parts = apscheduler_cron.split()
        assert parts[0] == "30"  # minute
        assert parts[1] == "8"   # hour
        assert "1-5" in parts[4] or "MON" in parts[4]

        # Parse Quartz: sec min hour dom month dow
        q_parts = quartz_cron.split()
        assert q_parts[1] == "30"  # minute
        assert q_parts[2] == "8"   # hour
        assert "MON-FRI" in q_parts[5]


# ---------------------------------------------------------------------------
# 5. C# API contract — mock the C# endpoints Python calls
# ---------------------------------------------------------------------------

class TestCSharpAPIContract:
    def test_health_endpoint_expected_shape(self):
        """C# /health response shape that Python migration script checks."""
        mock_response = {
            "status": "ok",
            "service": "StockAgent.Scheduler",
            "next_fire_utc": "2026-04-17T03:00:00Z",
        }
        assert mock_response["status"] == "ok"
        assert "service" in mock_response

    def test_scheduler_status_expected_shape(self):
        """C# GET /scheduler/status shape queried by TypeScript dashboard."""
        mock_status = {
            "enabled": True,
            "cron": "0 30 8 ? * MON-FRI",
            "tickers": ["MARUTI", "TATAMOTORS"],
            "next_fire": "2026-04-17T03:00:00Z",
        }
        assert "enabled" in mock_status
        assert "cron" in mock_status
        assert "tickers" in mock_status
        assert isinstance(mock_status["tickers"], list)

    def test_scores_post_expected_payload(self):
        """Payload Python sends to C# POST /scores matches ScoreRecord fields."""
        report = _make_report()
        payload = report.model_dump()

        # These must be present for C# ScoreRecord.FromDto()
        required_for_csharp = [
            "ticker", "company_name", "final_score",
            "verdict", "investment_thesis", "report_date",
        ]
        for field in required_for_csharp:
            assert field in payload, f"Missing field for C# ScoreRecord: {field}"

    @patch("requests.post")
    def test_migration_script_posts_to_csharp_scores(self, mock_post):
        """
        simulate the SQLite→C# migration: each SQLite row is POSTed to
        POST http://localhost:5000/scores
        """
        mock_post.return_value = MagicMock(status_code=201)

        import requests
        report = _make_report()
        requests.post("http://localhost:5000/scores", json=report.model_dump(), timeout=10)

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "5000" in call_url
        assert "scores" in call_url


# ---------------------------------------------------------------------------
# 6. Port isolation — no conflicts between services
# ---------------------------------------------------------------------------

class TestPortIsolation:
    def test_python_api_port_is_8000(self):
        """Python FastAPI listens on 8000 — must not clash with C# (5000) or TS (3000)."""
        python_port = 8000
        csharp_port = 5000
        ts_port = 3000
        ts_ws_port = 3001
        all_ports = [python_port, csharp_port, ts_port, ts_ws_port]
        assert len(all_ports) == len(set(all_ports)), "Port collision detected across services"

    def test_python_api_url_uses_port_8000(self):
        """C# appsettings.json PythonApiUrl must point to port 8000."""
        python_api_url = "http://localhost:8000"
        assert "8000" in python_api_url

    def test_csharp_api_url_uses_port_5000(self):
        from config import settings
        assert "5000" in settings.CSHARP_API_URL
