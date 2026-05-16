import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


VALID_DISPATCH = {
    "query_decomposition": "User wants 3-day Sensex trend and prediction",
    "user_tier": "active",
    "tasks": [
        {"tool": "get_historical_prices", "args": {"symbol": "^BSESN", "days": 5}, "priority": 1},
        {"tool": "get_live_price", "args": {"symbol": "^BSESN"}, "priority": 1},
        {"tool": "search_market_news", "args": {"query": "Sensex India outlook"}, "priority": 2},
    ],
    "browsing_strategy": {"topics": ["Sensex"], "geo": "in", "always_news": True},
}


@pytest.mark.asyncio
async def test_dispatch_node_parses_valid_llm_output():
    from services.api.chat_graph import _node_dispatch

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps(VALID_DISPATCH)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    state = {
        "messages": [{"role": "user", "content": "compare last 3 days sensex"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph.get_async_llm_client", return_value=mock_client):
        result = await _node_dispatch(state)

    assert result["user_tier"] == "active"
    assert len(result["tasks"]) == 3
    assert result["query_decomposition"] == VALID_DISPATCH["query_decomposition"]


@pytest.mark.asyncio
async def test_dispatch_node_fallback_on_bad_json():
    from services.api.chat_graph import _node_dispatch

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "this is not json at all"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    state = {
        "messages": [{"role": "user", "content": "what is happening in the market"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph.get_async_llm_client", return_value=mock_client):
        result = await _node_dispatch(state)

    tools = {t["tool"] for t in result["tasks"]}
    assert "get_live_price" in tools
    assert "get_macro_news" in tools
    assert "search_market_news" in tools
    assert result["user_tier"] == "active"


@pytest.mark.asyncio
async def test_dispatch_node_falls_back_on_zero_tasks():
    from services.api.chat_graph import _node_dispatch

    bad_dispatch = {**VALID_DISPATCH, "tasks": []}
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps(bad_dispatch)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    state = {
        "messages": [{"role": "user", "content": "market news"}],
        "query_decomposition": None,
        "user_tier": None,
        "browsing_strategy": None,
        "tasks": None,
        "tool_results": None,
    }

    with patch("services.api.chat_graph.get_async_llm_client", return_value=mock_client):
        result = await _node_dispatch(state)

    assert len(result["tasks"]) >= 3
