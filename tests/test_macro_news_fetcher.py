"""
tests/test_macro_news_fetcher.py
================================
Tests for macro_news_fetcher.py LLM error handling and review coverage.
"""

import pytest
from unittest.mock import patch, MagicMock


def _make_raw(n=2):
    """Helper: create n mock raw results from fetcher."""
    return [
        {
            "title": f"Title {i}",
            "snippet": "snippet",
            "url": f"http://x.com/{i}",
            "published_date": "2026-05-21",
            "query_used": "q",
        }
        for i in range(n)
    ]


def test_review_coverage_llm_failure_returns_unsatisfied():
    """When LLM call raises, satisfied must be False so the retry loop can fire."""
    from services.background.macro_news_fetcher import MacroNewsFetcher

    fetcher = MacroNewsFetcher.__new__(MacroNewsFetcher)
    # Inject a fake cache so __init__ doesn't run
    fetcher._cache = MagicMock()

    raw = _make_raw(2)

    with patch("services.clients.llm_client.get_llm_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = RuntimeError("LLM down")
        result = fetcher._review_coverage(raw)

    assert result["satisfied"] is False, "satisfied must be False on LLM failure"
    assert len(result["tagged_entries"]) == len(raw), "articles must not be discarded"
    assert result["missing_topics"], "missing_topics must be non-empty to trigger retry"


def test_review_coverage_llm_failure_entries_tagged_low():
    """Fallback entries must have severity=LOW and impact_tags=[]."""
    from services.background.macro_news_fetcher import MacroNewsFetcher

    fetcher = MacroNewsFetcher.__new__(MacroNewsFetcher)
    fetcher._cache = MagicMock()

    raw = _make_raw(1)

    with patch("services.clients.llm_client.get_llm_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = RuntimeError("LLM down")
        result = fetcher._review_coverage(raw)

    entry = result["tagged_entries"][0]
    assert entry["severity"] == "LOW"
    assert entry["impact_tags"] == []
    assert entry["title"] == raw[0]["title"]
