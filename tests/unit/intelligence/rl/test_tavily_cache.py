"""
tests/unit/intelligence/rl/test_tavily_cache.py
================================================
Tests for disk-backed monthly cache in fetch_tavily_context.
"""
import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_fetch_tavily_context_writes_cache_on_first_call(tmp_path):
    """First call hits Tavily API and writes result to disk."""
    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", return_value=[
             {"title": "RBI holds rates", "content": "RBI held rates at 6.5%",
              "url": "https://et.com/1", "published_date": "", "score": 0.9}
         ]):
        from services.clients.tavily_fetcher import fetch_tavily_context
        result = fetch_tavily_context(["RBI rate decision india 2026"])

    assert "RBI holds rates" in result
    cache_files = list(tmp_path.glob("**/*.txt"))
    assert len(cache_files) == 1


def test_fetch_tavily_context_cache_hit_skips_api(tmp_path):
    """Second call with same queries returns cached result without hitting API."""
    queries = ["India Nifty market news today"]
    cached_content = "cached result from month-start"

    month = date.today().strftime("%Y-%m")
    q_hash = hashlib.md5("|".join(sorted(queries[:2])).encode()).hexdigest()[:12]
    cache_file = tmp_path / month / f"{q_hash}.txt"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text(cached_content, encoding="utf-8")

    mock_tavily = MagicMock(return_value=[])

    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", mock_tavily):
        from services.clients.tavily_fetcher import fetch_tavily_context
        result = fetch_tavily_context(queries)

    mock_tavily.assert_not_called()
    assert result == cached_content


def test_fetch_tavily_context_different_month_misses_cache(tmp_path):
    """Queries cached in a previous month do NOT serve current month."""
    queries = ["Sensex outlook India 2026"]
    q_hash = hashlib.md5("|".join(sorted(queries[:2])).encode()).hexdigest()[:12]
    old_cache = tmp_path / "2026-04" / f"{q_hash}.txt"
    old_cache.parent.mkdir(parents=True)
    old_cache.write_text("stale old content", encoding="utf-8")

    mock_tavily = MagicMock(return_value=[])

    with patch("services.clients.tavily_fetcher._TAVILY_CACHE_DIR", tmp_path), \
         patch("services.clients.tavily_fetcher.search_tavily", mock_tavily):
        from services.clients.tavily_fetcher import fetch_tavily_context
        fetch_tavily_context(queries)

    mock_tavily.assert_called()
