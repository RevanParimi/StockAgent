"""
tests/test_scheduler.py
=======================
Unit tests for the AutomobileScheduler helper functions.
"""

from __future__ import annotations

import logging
import pytest


def test_active_tickers_warns_on_empty_result(caplog):
    """_active_tickers() must emit a WARNING when it resolves to an empty list."""
    from unittest.mock import patch

    try:
        from services.scheduler.python.scheduler import _active_tickers
    except ImportError as exc:
        pytest.skip(f"scheduler module not importable: {exc}")
        return

    # The function imports get_active_tickers from services.api.log_buffer internally.
    # Patch at the source so the import inside the function uses the mock.
    with patch("services.api.log_buffer.get_active_tickers", return_value=[]):
        # Also patch settings so the fallback list is also empty
        with patch("services.scheduler.python.scheduler.settings") as mock_s:
            mock_s.SCHEDULER_TICKERS = []

            with caplog.at_level(logging.WARNING,
                                 logger="services.scheduler.python.scheduler"):
                result = _active_tickers()

    assert result == [], f"Expected empty list, got {result}"
    assert any(
        "no tickers" in r.message.lower() or "empty" in r.message.lower()
        for r in caplog.records
    ), (
        "Expected a WARNING log containing 'no tickers' or 'empty'. "
        f"Actual records: {[r.message for r in caplog.records]}"
    )


def test_active_tickers_filters_invalid_entries(caplog):
    """_active_tickers() must strip blank strings and non-string entries with a WARNING."""
    from unittest.mock import patch

    try:
        from services.scheduler.python.scheduler import _active_tickers
    except ImportError as exc:
        pytest.skip(f"scheduler module not importable: {exc}")
        return

    dirty_list = ["MARUTI", "", "  ", None, 42, "TATAMOTORS"]

    with patch("services.api.log_buffer.get_active_tickers", return_value=dirty_list):
        with caplog.at_level(logging.WARNING,
                             logger="services.scheduler.python.scheduler"):
            result = _active_tickers()

    # Only valid string tickers should survive
    assert set(result) == {"MARUTI", "TATAMOTORS"}, (
        f"Expected only valid string tickers, got: {result}"
    )
    # Must warn about invalid entries
    assert any(
        "invalid" in r.message.lower() for r in caplog.records
    ), (
        "Expected a WARNING about invalid ticker entries. "
        f"Actual records: {[r.message for r in caplog.records]}"
    )
