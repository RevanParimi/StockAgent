"""Tests for services/background/macro_news_cache.py"""

import logging
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_cleanup_logs_debug_on_bad_filename(tmp_path, caplog, monkeypatch):
    """Files with unparseable names are skipped with a DEBUG log."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    (tmp_path / "not-a-date_macro_feed.json").write_text("{}", encoding="utf-8")

    from services.background.macro_news_cache import MacroNewsCache
    cache = MacroNewsCache()
    with caplog.at_level(logging.DEBUG, logger="services.background.macro_news_cache"):
        cache._cleanup_old_files()

    assert any(
        "Skipping" in r.message or "unparseable" in r.message.lower()
        for r in caplog.records
    ), f"Expected 'Skipping' or 'unparseable' in debug logs, got: {[r.message for r in caplog.records]}"


def test_cleanup_logs_warning_on_delete_failure(tmp_path, caplog, monkeypatch):
    """If unlink() raises OSError, a WARNING is logged."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)

    # Create a file old enough to be deleted (date well in the past)
    old_file = tmp_path / "2020-01-01_macro_feed.json"
    old_file.write_text("{}", encoding="utf-8")

    from services.background.macro_news_cache import MacroNewsCache
    cache = MacroNewsCache()

    # Patch unlink to raise OSError
    with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
        with caplog.at_level(logging.WARNING, logger="services.background.macro_news_cache"):
            cache._cleanup_old_files()

    assert any(
        "Could not delete" in r.message or "delete" in r.message.lower()
        for r in caplog.records
    ), f"Expected 'Could not delete' or 'delete' in warning logs, got: {[r.message for r in caplog.records]}"


def test_cleanup_deletes_old_files_successfully(tmp_path, caplog, monkeypatch):
    """Files older than retention period are deleted successfully."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)

    # Create old file (90+ days old, should be deleted with default retention)
    old_file = tmp_path / "2020-01-01_macro_feed.json"
    old_file.write_text("{}", encoding="utf-8")

    # Create recent file (should not be deleted)
    recent_file = tmp_path / f"{date.today().isoformat()}_macro_feed.json"
    recent_file.write_text("{}", encoding="utf-8")

    from services.background.macro_news_cache import MacroNewsCache
    cache = MacroNewsCache()

    with caplog.at_level(logging.INFO, logger="services.background.macro_news_cache"):
        cache._cleanup_old_files()

    assert not old_file.exists(), "Old file should be deleted"
    assert recent_file.exists(), "Recent file should not be deleted"
    assert any(
        "Deleted old feed" in r.message
        for r in caplog.records
    ), f"Expected 'Deleted old feed' in logs, got: {[r.message for r in caplog.records]}"


def test_cleanup_skips_recent_files(tmp_path, monkeypatch):
    """Files within retention period are not deleted."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)

    # Create file from 30 days ago (within default 90-day retention)
    recent_file = tmp_path / f"{(date.today() - timedelta(days=30)).isoformat()}_macro_feed.json"
    recent_file.write_text("{}", encoding="utf-8")

    from services.background.macro_news_cache import MacroNewsCache
    cache = MacroNewsCache()
    cache._cleanup_old_files()

    assert recent_file.exists(), "File within retention period should not be deleted"
