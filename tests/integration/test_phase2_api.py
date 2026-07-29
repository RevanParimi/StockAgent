"""
tests/test_phase2_api.py
=========================
Phase 2 — FastAPI bridge tests.

Uses FastAPI's TestClient (backed by httpx) — no real server is started,
no real LLM calls are made.  The orchestrator and score_store are mocked.

What is tested:
  GET  /health           — returns 200 + {status: "ok", timestamp, service}
  GET  /tickers          — returns configured tickers list
  POST /analyse          — returns FinalReport JSON (orchestrator mocked)
  POST /analyse          — 422 on empty ticker
  POST /analyse          — 503 on orchestrator exception
  GET  /history/{ticker} — returns list from ScoreStore (mocked)
  GET  /history/{ticker}/latest — returns latest or 404
  GET  /history/{ticker} — respects limit query param
  GET  /docs             — OpenAPI docs page is reachable
  WebSocket /ws/stream   — connects, receives progress events + complete

Running:
    pytest tests/test_phase2_api.py -v
"""

from __future__ import annotations

import json
from datetime import date, timezone, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.schemas.pipeline import FinalReport, WeightedAgentScore


# ---------------------------------------------------------------------------
# Fixture: TestClient with mocked orchestrator
# ---------------------------------------------------------------------------

def _make_report(ticker: str = "MARUTI", score: float = 0.66, verdict: str = "BUY") -> FinalReport:
    ws = WeightedAgentScore(raw=score, weight=1.0, weighted=score)
    return FinalReport(
        ticker=ticker,
        company_name=f"{ticker} Ltd",
        final_score=score,
        verdict=verdict,
        weighted_agent_scores={"fundamentals": ws},
        conviction_drivers=["Strong demand"],
        top_risks=["EV lag"],
        investment_thesis="Solid near-term outlook.",
        report_date=str(date.today()),
    )


def _fake_orchestrator(*, report: FinalReport | None = None, error: Exception | None = None):
    """
    Build a (fake_class, instance) pair matching the current route seam.

    Both /analyse and /ws/stream resolve the orchestrator via
    ``get_orchestrator(sector)`` (backend.sectors), then do
    ``OrchestratorClass()`` and ``await instance.analyse_async(ticker, ...)``.
    So the patched ``get_orchestrator`` must *return a class* whose call
    yields the instance. ``__name__`` is set because analyse.py logs it.
    """
    instance = MagicMock()
    if error is not None:
        instance.analyse_async = AsyncMock(side_effect=error)
    else:
        instance.analyse_async = AsyncMock(return_value=report)
    fake_cls = MagicMock(return_value=instance)
    fake_cls.__name__ = "AutomobileAgentOrchestrator"
    return fake_cls, instance


@pytest.fixture
def client():
    """TestClient with no external dependencies."""
    from services.api.server import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mock_orchestrator(mock_final_report):
    """Patch the sector→orchestrator lookup so no real orchestrator/LLM is built.

    analyse.py imports ``get_orchestrator`` locally from ``backend.sectors`` at
    call time, so it must be patched at that source module (not on the route).
    """
    fake_cls, instance = _fake_orchestrator(report=mock_final_report)
    with patch("backend.sectors.get_orchestrator", return_value=fake_cls):
        yield instance


@pytest.fixture
def mock_score_store():
    with patch("services.api.routes.history._get_store") as mock_get:
        store = MagicMock()
        mock_get.return_value = store
        yield store


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body_has_status_ok(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_health_body_has_timestamp(self, client):
        body = client.get("/health").json()
        assert "timestamp" in body
        # Verify it's a parseable ISO timestamp
        datetime.fromisoformat(body["timestamp"])

    def test_health_body_has_service(self, client):
        body = client.get("/health").json()
        assert "service" in body
        assert "StockAgent" in body["service"]


# ---------------------------------------------------------------------------
# Tickers meta endpoint
# ---------------------------------------------------------------------------

class TestTickersEndpoint:
    def test_tickers_returns_200(self, client):
        assert client.get("/tickers").status_code == 200

    def test_tickers_body_has_tickers_key(self, client):
        body = client.get("/tickers").json()
        assert "tickers" in body
        assert isinstance(body["tickers"], list)


# ---------------------------------------------------------------------------
# OpenAPI docs
# ---------------------------------------------------------------------------

class TestOpenAPIDocs:
    def test_docs_page_reachable(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_reachable(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/analyse" in schema["paths"]
        assert "/health" in schema["paths"]


# ---------------------------------------------------------------------------
# POST /analyse
# ---------------------------------------------------------------------------

class TestAnalyseEndpoint:
    def test_valid_ticker_returns_200(self, client, mock_orchestrator):
        resp = client.post("/analyse", json={"ticker": "MARUTI"})
        assert resp.status_code == 200

    def test_response_contains_final_score(self, client, mock_orchestrator):
        resp = client.post("/analyse", json={"ticker": "MARUTI"})
        body = resp.json()
        assert "final_score" in body
        assert 0.0 <= body["final_score"] <= 1.0

    def test_response_contains_verdict(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert body["verdict"] in {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}

    def test_response_contains_ticker(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert body["ticker"] == "MARUTI"

    def test_response_contains_investment_thesis(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert "investment_thesis" in body

    def test_response_contains_conviction_drivers(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert isinstance(body.get("conviction_drivers"), list)

    def test_response_contains_top_risks(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert isinstance(body.get("top_risks"), list)

    def test_response_contains_weighted_agent_scores(self, client, mock_orchestrator):
        body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert isinstance(body.get("weighted_agent_scores"), dict)

    def test_orchestrator_called_with_uppercased_ticker(self, client, mock_orchestrator):
        client.post("/analyse", json={"ticker": "maruti"})
        mock_orchestrator.analyse_async.assert_called_once_with("MARUTI")

    def test_empty_ticker_returns_422(self, client):
        resp = client.post("/analyse", json={"ticker": ""})
        assert resp.status_code == 422

    def test_missing_ticker_field_returns_422(self, client):
        resp = client.post("/analyse", json={})
        assert resp.status_code == 422

    def test_orchestrator_failure_returns_503(self, client):
        fake_cls, _ = _fake_orchestrator(error=RuntimeError("LLM unreachable"))
        with patch("backend.sectors.get_orchestrator", return_value=fake_cls):
            resp = client.post("/analyse", json={"ticker": "MARUTI"})
        assert resp.status_code == 503

    def test_503_body_contains_detail(self, client):
        fake_cls, _ = _fake_orchestrator(error=RuntimeError("LLM unreachable"))
        with patch("backend.sectors.get_orchestrator", return_value=fake_cls):
            body = client.post("/analyse", json={"ticker": "MARUTI"}).json()
        assert "detail" in body

    def test_lowercase_ticker_is_normalised(self, client, mock_orchestrator):
        resp = client.post("/analyse", json={"ticker": "tatamotors"})
        assert resp.status_code == 200
        mock_orchestrator.analyse_async.assert_called_with("TATAMOTORS")


# ---------------------------------------------------------------------------
# GET /history/{ticker}
# ---------------------------------------------------------------------------

class TestHistoryEndpoint:
    def test_returns_200_with_list(self, client, mock_score_store):
        mock_score_store.get_history.return_value = [
            {"ticker": "MARUTI", "final_score": 0.70, "verdict": "BUY", "run_at": "2026-04-16"},
        ]
        resp = client.get("/history/MARUTI")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_empty_list_when_no_history(self, client, mock_score_store):
        mock_score_store.get_history.return_value = []
        resp = client.get("/history/UNKNOWN")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_passes_limit_to_store(self, client, mock_score_store):
        mock_score_store.get_history.return_value = []
        client.get("/history/MARUTI?limit=10")
        mock_score_store.get_history.assert_called_once_with("MARUTI", limit=10)

    def test_default_limit_is_30(self, client, mock_score_store):
        mock_score_store.get_history.return_value = []
        client.get("/history/MARUTI")
        mock_score_store.get_history.assert_called_once_with("MARUTI", limit=30)

    def test_ticker_uppercased_in_store_call(self, client, mock_score_store):
        mock_score_store.get_history.return_value = []
        client.get("/history/maruti")
        mock_score_store.get_history.assert_called_with("MARUTI", limit=30)

    def test_limit_too_large_returns_422(self, client, mock_score_store):
        resp = client.get("/history/MARUTI?limit=400")
        assert resp.status_code == 422

    def test_limit_zero_returns_422(self, client, mock_score_store):
        resp = client.get("/history/MARUTI?limit=0")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /history/{ticker}/latest
# ---------------------------------------------------------------------------

class TestHistoryLatestEndpoint:
    def test_returns_200_when_record_exists(self, client, mock_score_store):
        mock_score_store.get_latest.return_value = {
            "ticker": "MARUTI", "final_score": 0.72, "verdict": "BUY"
        }
        resp = client.get("/history/MARUTI/latest")
        assert resp.status_code == 200

    def test_returns_404_when_no_record(self, client, mock_score_store):
        mock_score_store.get_latest.return_value = None
        resp = client.get("/history/UNKNOWN/latest")
        assert resp.status_code == 404

    def test_404_body_has_detail(self, client, mock_score_store):
        mock_score_store.get_latest.return_value = None
        body = client.get("/history/UNKNOWN/latest").json()
        assert "detail" in body


# ---------------------------------------------------------------------------
# WebSocket /ws/stream
# ---------------------------------------------------------------------------

class TestWebSocketStream:
    def test_ws_rejects_missing_ticker(self, client):
        with client.websocket_connect("/ws/stream") as ws:
            msg = json.loads(ws.receive_text())
            assert msg["event"] == "error"
            assert "ticker" in msg["detail"].lower()

    def test_ws_streams_complete_event(self, client, mock_final_report):
        fake_cls, _ = _fake_orchestrator(report=mock_final_report)
        # stream.py imports get_orchestrator at module level → patch it there.
        with patch("services.api.routes.stream.get_orchestrator", return_value=fake_cls):
            with client.websocket_connect("/ws/stream?ticker=MARUTI") as ws:
                events = []
                while True:
                    msg = json.loads(ws.receive_text())
                    events.append(msg)
                    if msg["event"] in ("complete", "error"):
                        break

        event_types = [e["event"] for e in events]
        assert "complete" in event_types

    def test_ws_complete_event_contains_report(self, client, mock_final_report):
        fake_cls, _ = _fake_orchestrator(report=mock_final_report)
        with patch("services.api.routes.stream.get_orchestrator", return_value=fake_cls):
            with client.websocket_connect("/ws/stream?ticker=MARUTI") as ws:
                events = []
                while True:
                    msg = json.loads(ws.receive_text())
                    events.append(msg)
                    if msg["event"] in ("complete", "error"):
                        break

        complete = next(e for e in events if e["event"] == "complete")
        assert "report" in complete
        assert complete["report"]["ticker"] == "MARUTI"
        assert "final_score" in complete["report"]
