"""
tests/integration/test_api_usage.py
====================================
Tests for api_usage store, especially error handling and logging.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch, MagicMock

import pytest


class TestApiUsageLoad:
    """Tests for _load() function error handling."""

    def test_load_logs_warning_on_corrupt_json(self, tmp_path, caplog):
        """Verify that corrupt JSON is logged, not silently swallowed."""
        import services.data.stores.api_usage as au

        usage_file = tmp_path / "api_usage.json"
        usage_file.write_text("not valid json", encoding="utf-8")

        with patch.object(au, "_USAGE_FILE", usage_file):
            with caplog.at_level(logging.WARNING, logger="services.data.stores.api_usage"):
                result = au._load()

        assert result == {}
        assert any("Failed to load" in r.message for r in caplog.records)

    def test_load_returns_empty_dict_when_file_missing(self, tmp_path):
        """Verify that missing file returns empty dict (no error)."""
        import services.data.stores.api_usage as au

        usage_file = tmp_path / "api_usage.json"
        # file does not exist

        with patch.object(au, "_USAGE_FILE", usage_file):
            result = au._load()

        assert result == {}

    def test_load_returns_valid_json_when_present(self, tmp_path):
        """Verify that valid JSON is loaded correctly."""
        import services.data.stores.api_usage as au

        valid_data = {"month": "2026-05", "serper": {"calls": 10}}
        usage_file = tmp_path / "api_usage.json"
        usage_file.write_text(json.dumps(valid_data), encoding="utf-8")

        with patch.object(au, "_USAGE_FILE", usage_file):
            result = au._load()

        assert result == valid_data

    def test_load_logs_warning_on_os_error(self, tmp_path, caplog):
        """Verify that OSError (e.g., permission denied) is logged."""
        import services.data.stores.api_usage as au

        # Create a mock file object that raises OSError on read_text
        usage_file = MagicMock()
        usage_file.exists.return_value = True
        usage_file.read_text.side_effect = OSError("Permission denied")

        with patch.object(au, "_USAGE_FILE", usage_file):
            with caplog.at_level(logging.WARNING, logger="services.data.stores.api_usage"):
                result = au._load()

        assert result == {}
        assert any("Failed to load" in r.message for r in caplog.records)
