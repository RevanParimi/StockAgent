"""
tests/test_api_routes.py
========================
Unit tests for FastAPI route error handling — ensures internal tracebacks
and file paths are never leaked in HTTP responses.
"""

from __future__ import annotations

import pytest


def test_ws_stream_error_event_does_not_leak_exception_detail():
    """AUD-103: /ws/stream error events must not carry raw str(exc)."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.api.routes.stream import router as stream_router
    import json as _json

    app = FastAPI()
    app.include_router(stream_router)
    client = TestClient(app)

    internal = "/internal/path/secret_module.py line 99 KeyError('OPENROUTER_API_KEY')"
    mock_orch = MagicMock()
    mock_orch.analyse_async = AsyncMock(side_effect=RuntimeError(internal))

    with patch("services.api.routes.stream.detect_sector", return_value="automobile"), \
         patch("services.api.routes.stream.get_orchestrator", return_value=lambda: mock_orch):
        with client.websocket_connect("/ws/stream?ticker=MARUTI") as ws:
            event = _json.loads(ws.receive_text())

    assert event["event"] == "error"
    assert "/internal/path" not in event["detail"]
    assert "OPENROUTER" not in event["detail"]


def test_analyse_route_does_not_leak_exception_detail():
    """HTTP 5xx response must not contain internal exception detail (file paths, line numbers)."""
    from unittest.mock import patch, AsyncMock, MagicMock

    # Build a minimal FastAPI app containing only the analyse router so we
    # don't need to import the full server (which triggers DB/scheduler setup).
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from services.api.routes.analyse import router as analyse_router
    except ImportError as exc:
        pytest.skip(f"FastAPI or analyse router not importable: {exc}")
        return

    mini_app = FastAPI()
    mini_app.include_router(analyse_router, prefix="/api/v1")

    client = TestClient(mini_app, raise_server_exceptions=False)

    # Patch the orchestrator's analyse_async to raise an internal error containing
    # path-like strings that must NOT appear in the HTTP response body.
    internal_error_msg = "/internal/path/module.py line 42 error"

    mock_orch = MagicMock()
    mock_orch.analyse_async = AsyncMock(side_effect=RuntimeError(internal_error_msg))

    with patch("backend.sectors.detect_sector", return_value="automobile"), \
         patch("backend.sectors.get_orchestrator", return_value=lambda: mock_orch):

        resp = client.post(
            "/api/v1/analyse",
            json={"ticker": "MARUTI", "sector": "automobile"},
        )

    # Must be a server error
    assert resp.status_code in (500, 503), (
        f"Expected 500/503, got {resp.status_code}: {resp.text}"
    )

    body = resp.text
    assert "/internal/path" not in body, (
        f"Internal file path must not appear in HTTP response body. Got: {body}"
    )
    assert "line 42" not in body, (
        f"Internal line number must not appear in HTTP response body. Got: {body}"
    )
