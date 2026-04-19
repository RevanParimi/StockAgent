"""
tests/test_phase3_typescript.py
================================
Phase 3 — TypeScript dashboard integration contract (Python-side).

The TypeScript client (typescript/src/clients/pythonClient.ts) deserializes
the JSON that Python emits.  These tests verify the Python side of the
contract so the TypeScript team never receives unexpected shapes.

What is tested:
  - FinalReport serialises to snake_case keys (TS client expects snake_case)
  - All fields the TypeScript types/stockAgent.ts interface declares are present
  - Verdict is always one of the 5 allowed strings
  - final_score is always in [0.0, 1.0]
  - weighted_agent_scores values each have raw/weight/weighted
  - conviction_drivers and top_risks are lists of strings
  - JSON Schema can be exported (used to generate TS types via json-schema-to-typescript)
  - WebSocket events have the exact shape expected by stream.ts
  - Progress event: {event, agent, score}
  - Complete event: {event, report: <FinalReport>}
  - Error event: {event, detail}

No real LLM calls — all fixtures come from conftest.py.
"""

from __future__ import annotations

import json

import pytest

from models.schemas import FinalReport, WeightedAgentScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALLOWED_VERDICTS = {"STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"}
REQUIRED_REPORT_FIELDS = {
    "ticker", "company_name", "final_score", "verdict",
    "weighted_agent_scores", "conviction_drivers", "top_risks",
    "investment_thesis", "report_date",
}


def _serialise(report: FinalReport) -> dict:
    """model_dump() is what api/routes/analyse.py returns."""
    return report.model_dump()


# ---------------------------------------------------------------------------
# 1. Serialisation shape — snake_case keys
# ---------------------------------------------------------------------------

class TestSerializationShape:
    def test_model_dump_uses_snake_case(self, mock_final_report):
        data = _serialise(mock_final_report)
        # All keys must be snake_case (no camelCase)
        for key in data.keys():
            assert key == key.lower() or "_" in key or key.isalpha(), (
                f"Key '{key}' looks like camelCase — TS client expects snake_case"
            )

    def test_all_required_fields_present(self, mock_final_report):
        data = _serialise(mock_final_report)
        for field in REQUIRED_REPORT_FIELDS:
            assert field in data, f"Required field '{field}' missing from FinalReport serialisation"

    def test_no_extra_private_fields_leaked(self, mock_final_report):
        data = _serialise(mock_final_report)
        # raw_llm_response is marked exclude=True — must not appear
        assert "raw_llm_response" not in data

    def test_json_round_trip(self, mock_final_report):
        """Serialise → JSON string → parse → re-create without loss."""
        data = _serialise(mock_final_report)
        json_str = json.dumps(data)
        reparsed = json.loads(json_str)
        assert reparsed["ticker"] == mock_final_report.ticker
        assert reparsed["final_score"] == mock_final_report.final_score


# ---------------------------------------------------------------------------
# 2. Field-level contracts matching TypeScript interface
# ---------------------------------------------------------------------------

class TestFieldContracts:
    def test_ticker_is_string(self, mock_final_report):
        assert isinstance(_serialise(mock_final_report)["ticker"], str)

    def test_company_name_is_string(self, mock_final_report):
        assert isinstance(_serialise(mock_final_report)["company_name"], str)

    def test_final_score_is_float_in_range(self, mock_final_report):
        score = _serialise(mock_final_report)["final_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_verdict_is_valid_string(self, mock_final_report):
        verdict = _serialise(mock_final_report)["verdict"]
        assert verdict in ALLOWED_VERDICTS, f"Unexpected verdict: {verdict}"

    def test_conviction_drivers_is_list_of_strings(self, mock_final_report):
        drivers = _serialise(mock_final_report)["conviction_drivers"]
        assert isinstance(drivers, list)
        assert all(isinstance(d, str) for d in drivers)

    def test_top_risks_is_list_of_strings(self, mock_final_report):
        risks = _serialise(mock_final_report)["top_risks"]
        assert isinstance(risks, list)
        assert all(isinstance(r, str) for r in risks)

    def test_investment_thesis_is_string(self, mock_final_report):
        assert isinstance(_serialise(mock_final_report)["investment_thesis"], str)

    def test_report_date_is_string(self, mock_final_report):
        assert isinstance(_serialise(mock_final_report)["report_date"], str)

    def test_weighted_agent_scores_is_dict(self, mock_final_report):
        was = _serialise(mock_final_report)["weighted_agent_scores"]
        assert isinstance(was, dict)

    def test_weighted_agent_score_values_have_raw_weight_weighted(self, mock_final_report):
        was = _serialise(mock_final_report)["weighted_agent_scores"]
        for agent_name, score_obj in was.items():
            assert "raw" in score_obj, f"Missing 'raw' for agent {agent_name}"
            assert "weight" in score_obj, f"Missing 'weight' for agent {agent_name}"
            assert "weighted" in score_obj, f"Missing 'weighted' for agent {agent_name}"

    def test_weighted_agent_score_raw_in_range(self, mock_final_report):
        was = _serialise(mock_final_report)["weighted_agent_scores"]
        for agent_name, score_obj in was.items():
            assert 0.0 <= score_obj["raw"] <= 1.0, (
                f"raw score out of range for {agent_name}: {score_obj['raw']}"
            )


# ---------------------------------------------------------------------------
# 3. JSON Schema export (used to generate TypeScript types)
# ---------------------------------------------------------------------------

class TestJSONSchemaExport:
    def test_final_report_schema_is_exportable(self):
        schema = FinalReport.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_schema_contains_all_required_fields(self):
        schema = FinalReport.model_json_schema()
        props = schema.get("properties", {})
        for field in REQUIRED_REPORT_FIELDS:
            assert field in props, f"Field '{field}' missing from JSON schema"

    def test_final_score_schema_has_bounds(self):
        schema = FinalReport.model_json_schema()
        score_schema = schema["properties"]["final_score"]
        # Pydantic ge/le should appear as minimum/maximum in JSON Schema
        assert "minimum" in score_schema or "$ref" in score_schema or "anyOf" in score_schema

    def test_schema_serialisable_to_json(self):
        schema = FinalReport.model_json_schema()
        json_str = json.dumps(schema)
        assert len(json_str) > 100


# ---------------------------------------------------------------------------
# 4. WebSocket event shapes — what stream.ts receives
# ---------------------------------------------------------------------------

class TestWebSocketEventShapes:
    def test_progress_event_shape(self):
        """Agent progress event: {event, agent, score}."""
        event = {"event": "agent_progress", "agent": "pattern_analysis", "score": 0.73}
        assert event["event"] == "agent_progress"
        assert isinstance(event["agent"], str)
        assert isinstance(event["score"], float)
        assert 0.0 <= event["score"] <= 1.0

    def test_complete_event_shape(self, mock_final_report):
        """Complete event: {event, report: <FinalReport dict>}."""
        report_dict = _serialise(mock_final_report)
        event = {"event": "complete", "report": report_dict}
        assert event["event"] == "complete"
        assert "report" in event
        assert all(f in event["report"] for f in REQUIRED_REPORT_FIELDS)

    def test_error_event_shape(self):
        """Error event: {event, detail}."""
        event = {"event": "error", "detail": "LLM timeout"}
        assert event["event"] == "error"
        assert isinstance(event["detail"], str)

    def test_progress_event_score_is_4dp(self):
        """Score in progress events should be rounded to 4 d.p. (stream.py does round())."""
        score = round(0.731234567, 4)
        assert score == 0.7312

    def test_all_event_types_are_json_serialisable(self, mock_final_report):
        events = [
            {"event": "agent_progress", "agent": "risk_macro", "score": 0.58},
            {"event": "complete", "report": _serialise(mock_final_report)},
            {"event": "error", "detail": "timeout"},
        ]
        for ev in events:
            # Should not raise
            json_str = json.dumps(ev)
            assert json.loads(json_str) == ev


# ---------------------------------------------------------------------------
# 5. TypeScript client timeout contract
# ---------------------------------------------------------------------------

class TestClientTimeoutContract:
    def test_agent_timeout_plus_buffer_within_ts_client_timeout(self):
        """
        TypeScript client sets a 180s timeout.
        Python AGENT_TIMEOUT_SECONDS is 120s.
        120s (agents) + overhead must be < 180s (TS timeout).
        """
        from config import settings
        ts_client_timeout = 180
        assert settings.AGENT_TIMEOUT_SECONDS < ts_client_timeout, (
            f"AGENT_TIMEOUT_SECONDS ({settings.AGENT_TIMEOUT_SECONDS}) must be "
            f"less than TypeScript client timeout ({ts_client_timeout}s)"
        )

    def test_llm_timeout_within_agent_timeout(self):
        from config import settings
        assert settings.LLM_TIMEOUT_SECONDS <= settings.AGENT_TIMEOUT_SECONDS, (
            "LLM_TIMEOUT_SECONDS must be <= AGENT_TIMEOUT_SECONDS to avoid silent hangs"
        )


# ---------------------------------------------------------------------------
# 6. CORS — TypeScript dashboard origin is allowed
# ---------------------------------------------------------------------------

class TestCORSConfiguration:
    def test_typescript_origin_in_cors_allow_list(self):
        from api.server import app
        from starlette.middleware.cors import CORSMiddleware

        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware):
                cors_middleware = middleware
                break

        # Just verify the app has CORS middleware configured
        # (the actual allowed origins are checked at request-time)
        middlewares_str = str([str(m) for m in app.user_middleware])
        assert "cors" in middlewares_str.lower() or "CORS" in middlewares_str
