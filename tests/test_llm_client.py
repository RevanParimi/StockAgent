"""
tests/test_llm_client.py
========================
Unit tests for services/clients/llm_client.py

Covers:
  - record_llm_call: telemetry write failure should log at WARNING level
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from services.clients.llm_client import record_llm_call


def test_record_llm_call_warns_on_write_failure(caplog):
    with patch("builtins.open", side_effect=PermissionError("disk full")):
        with caplog.at_level(logging.WARNING, logger="services.clients.llm_client"):
            record_llm_call("test_caller", "test-model", 10, 10, 100, True)
    assert any(
        r.levelno >= logging.WARNING and "telemetry" in r.message.lower()
        for r in caplog.records
    )
