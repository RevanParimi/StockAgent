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


# --------------------------------------------------------------------------- #
# F2 — read API for the RL daily review (market-wide fallback context).
# The daily review needs HIGH *and* MEDIUM items from today + yesterday: an
# overnight macro event that explains a large unexplained move is frequently
# rated MEDIUM, and get_high_severity() would have hidden it.
# --------------------------------------------------------------------------- #

def _seed_feed(tmp_path, day: date, entries: list[dict]) -> None:
    import json
    (tmp_path / f"{day.isoformat()}_macro_feed.json").write_text(
        json.dumps({
            "date": day.isoformat(), "last_refresh": "", "refresh_count": 1,
            "entries": entries,
        }),
        encoding="utf-8",
    )


def _entry(title: str, severity: str, **kw) -> dict:
    return {
        "id": kw.get("id", "e0001"),
        "title": title,
        "severity": severity,
        "url": kw.get("url", f"https://example.com/{title.replace(' ', '-')}"),
        "published_date": kw.get("published_date", date.today().isoformat()),
        "impact_tags": kw.get("impact_tags", ["rbi"]),
        "summary": kw.get("summary", f"{title} summary."),
    }


def test_daily_review_context_includes_high_and_medium(tmp_path, monkeypatch):
    """Both severities land in the block — MEDIUM is the point of this API."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today(), [
        _entry("RBI holds repo rate", "HIGH"),
        _entry("Crude slips 3% on OPEC signal", "MEDIUM"),
    ])

    block = mod.MacroNewsCache().get_for_daily_review()

    assert "RBI holds repo rate" in block
    assert "Crude slips 3% on OPEC signal" in block


def test_daily_review_context_excludes_low_severity(tmp_path, monkeypatch):
    """LOW noise must not become the explanation for a large move."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today(), [
        _entry("Nifty ends flat in thin trade", "LOW"),
    ])

    assert mod.MacroNewsCache().get_for_daily_review() == ""


def test_daily_review_context_reads_yesterday_too(tmp_path, monkeypatch):
    """A 16:30 IST review must still see last night's macro event."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today() - timedelta(days=1), [
        _entry("Fed signals a pause", "HIGH"),
    ])

    assert "Fed signals a pause" in mod.MacroNewsCache().get_for_daily_review()


def test_daily_review_context_ignores_older_days(tmp_path, monkeypatch):
    """Two-day-old macro is not context for today's move."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today() - timedelta(days=4), [
        _entry("Old budget headline", "HIGH"),
    ])

    assert mod.MacroNewsCache().get_for_daily_review() == ""


def test_daily_review_context_orders_high_first_and_caps(tmp_path, monkeypatch):
    """HIGH outranks MEDIUM, and max_items truncates."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today(), [
        _entry("Medium one", "MEDIUM", url="u1"),
        _entry("Medium two", "MEDIUM", url="u2"),
        _entry("High one", "HIGH", url="u3"),
    ])

    block = mod.MacroNewsCache().get_for_daily_review(max_items=2)

    assert "High one" in block
    assert "Medium one" in block
    assert "Medium two" not in block


def test_daily_review_context_empty_when_no_feed_file(tmp_path, monkeypatch):
    """No macro feed at all is not an error — just no extra context."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)

    assert mod.MacroNewsCache().get_for_daily_review() == ""


def test_daily_review_context_reads_the_reviewed_date_not_today(tmp_path, monkeypatch):
    """
    Backfills (`--date`, the scheduler_api backfill route) review past days.
    Injecting *today's* macro into a June review would be exactly the
    contaminated-attribution bug this fix exists to remove.
    """
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    past = date.today() - timedelta(days=10)
    _seed_feed(tmp_path, past, [_entry("Budget day selloff", "HIGH")])
    _seed_feed(tmp_path, date.today(), [_entry("Todays unrelated macro", "HIGH")])

    block = mod.MacroNewsCache().get_for_daily_review(for_date=past)

    assert "Budget day selloff" in block
    assert "Todays unrelated macro" not in block


def test_daily_review_context_for_past_date_includes_its_previous_day(tmp_path, monkeypatch):
    """Same today+yesterday window, anchored on the reviewed date."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    past = date.today() - timedelta(days=10)
    _seed_feed(tmp_path, past - timedelta(days=1), [_entry("Overnight Fed move", "HIGH")])

    block = mod.MacroNewsCache().get_for_daily_review(for_date=past)

    assert "Overnight Fed move" in block


def test_daily_review_context_for_date_beyond_retention_is_empty(tmp_path, monkeypatch):
    """No feed file for that day ⇒ no context, never a fabricated one."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today(), [_entry("Todays macro", "HIGH")])

    assert mod.MacroNewsCache().get_for_daily_review(
        for_date=date(2020, 1, 6)
    ) == ""


def test_daily_review_context_carries_date_and_severity(tmp_path, monkeypatch):
    """Provenance the FeedbackAgent can reason about: when, and how big."""
    import services.background.macro_news_cache as mod
    monkeypatch.setattr(mod, "_DATA_DIR", tmp_path)
    _seed_feed(tmp_path, date.today(), [
        _entry("RBI holds repo rate", "HIGH", published_date="2026-07-31"),
    ])

    block = mod.MacroNewsCache().get_for_daily_review()

    assert "2026-07-31" in block
    assert "HIGH" in block
