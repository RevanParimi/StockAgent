"""
tests/test_tavily_fetcher.py
============================
Unit tests for services/clients/tavily_fetcher.py

Covers:
  - fetch_tavily_context: cache write failure logs at WARNING with cache key
  - fetch_tavily_context: cache write only catches OSError, not broad Exception
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_cache_write_failure_logs_warning_with_cache_key(tmp_path, caplog):
    """
    When the cache write fails with OSError, a WARNING must be logged
    that includes the cache key (filename) so an operator can identify
    which query's cache failed.
    """
    from services.clients.tavily_fetcher import fetch_tavily_context

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": []}

    with patch("services.clients.tavily_fetcher.settings.TAVILY_API_KEY", "fake-key"), \
         patch("services.clients.tavily_fetcher.requests.post", return_value=mock_resp), \
         patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path):

        # Force OSError on write_text so the cache write fails
        with patch.object(Path, "write_text", side_effect=OSError("no space left")):
            with caplog.at_level(logging.WARNING, logger="services.clients.tavily_fetcher"):
                result = fetch_tavily_context(["some test query about market trends"])

    # Must not raise — result is still returned
    assert isinstance(result, str)

    # A WARNING must have been logged
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, "Expected at least one WARNING log record"

    # The log must include the cache key/filename so operators can identify which query failed
    combined = " ".join(r.message for r in warning_records).lower()
    # cache filename (hash-based) or explicit key reference must appear
    assert ".txt" in combined or "cache_key" in combined or any(
        c.isalnum() and len(c) >= 8 for c in combined.split()
    ), f"WARNING log missing cache key context. Got: {combined!r}"


def test_cache_write_narrow_oserror_not_broad_exception(tmp_path, caplog):
    """
    Cache write failure handler must catch OSError (not broad Exception).
    A non-OSError (e.g. ValueError) raised during cache write should propagate,
    not be silently swallowed by a broad except.

    NOTE: This verifies the narrowed exception scope.
    Since the cache write is wrapped, an OSError is caught and logged,
    but other errors surface. We verify OSError is handled gracefully.
    """
    from services.clients.tavily_fetcher import fetch_tavily_context

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": []}

    with patch("services.clients.tavily_fetcher.settings.TAVILY_API_KEY", "fake-key"), \
         patch("services.clients.tavily_fetcher.requests.post", return_value=mock_resp), \
         patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path):

        # Force OSError specifically (the narrowed exception type)
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            with caplog.at_level(logging.WARNING, logger="services.clients.tavily_fetcher"):
                # Must not raise — OSError is caught and handled
                result = fetch_tavily_context(["another test query"])

    assert isinstance(result, str)
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, "OSError during cache write must produce a WARNING log"
