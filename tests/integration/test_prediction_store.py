"""
tests/integration/test_prediction_store.py
==========================================
Tests for core/intelligence/rl/stores/prediction_store.py

Covers:
  - _write_json: .tmp file is cleaned up when Path.replace raises OSError
  - _read_json: narrowed exception scope (json.JSONDecodeError | OSError),
                logs at ERROR level with "Failed to read" message
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest


def test_write_json_cleans_tmp_on_oserror(tmp_path):
    """
    When Path.replace raises OSError (e.g. Windows file lock), the .tmp
    file must be removed — not orphaned forever.
    """
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    store = PredictionStore("TEST", base_dir=str(tmp_path))
    target = store._dir / "test.json"

    with patch.object(Path, "replace", side_effect=OSError("locked")):
        with pytest.raises((RuntimeError, OSError)):
            store._write_json(target, {"key": "value"})

    # .tmp file must be cleaned up after failure
    assert not target.with_suffix(".tmp").exists()


def test_read_json_logs_error_on_corrupt_file(tmp_path, caplog):
    """
    When the JSON file is corrupt, _read_json must:
    - Return None (not raise)
    - Log at ERROR level with "Failed to read" in the message
    """
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    store = PredictionStore("TEST", base_dir=str(tmp_path))
    bad = store._dir / "bad.json"
    bad.write_text("not json", encoding="utf-8")

    with caplog.at_level(
        logging.ERROR, logger="core.intelligence.rl.stores.prediction_store"
    ):
        result = store._read_json(bad)

    assert result is None
    assert any("Failed to read" in r.message for r in caplog.records)


def test_read_json_returns_none_on_oserror(tmp_path, caplog):
    """
    When the file exists but read_text raises OSError (e.g. permissions),
    _read_json must return None and log at ERROR level.
    """
    from core.intelligence.rl.stores.prediction_store import PredictionStore
    store = PredictionStore("TEST", base_dir=str(tmp_path))
    target = store._dir / "locked.json"
    target.write_text('{"ok": true}', encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        with caplog.at_level(
            logging.ERROR, logger="core.intelligence.rl.stores.prediction_store"
        ):
            result = store._read_json(target)

    assert result is None
    assert any("Failed to read" in r.message for r in caplog.records)
