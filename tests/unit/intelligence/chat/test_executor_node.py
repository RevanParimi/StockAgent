import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_executor_runs_all_tasks_concurrently():
    call_log = []

    async def mock_execute(name: str, args: dict) -> str:
        call_log.append(name)
        return f"result_{name}"

    tasks = [
        {"tool": "get_live_price", "args": {"symbol": "^NSEI"}, "priority": 1},
        {"tool": "get_macro_news", "args": {}, "priority": 2},
    ]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert len(results) == 2
    assert "get_live_price" in call_log
    assert "get_macro_news" in call_log


@pytest.mark.asyncio
async def test_executor_one_failure_does_not_block_others():
    async def mock_execute(name: str, args: dict) -> str:
        if name == "bad_tool":
            raise ValueError("simulated failure")
        return "ok result"

    tasks = [
        {"tool": "bad_tool",  "args": {}, "priority": 1},
        {"tool": "good_tool", "args": {}, "priority": 1},
    ]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert len(results) == 2
    ok = next(r for r in results if r["tool"] == "good_tool")
    assert ok["result"] == "ok result"
    bad = next(r for r in results if r["tool"] == "bad_tool")
    assert bad["result"] == ""
    assert "error" in bad


@pytest.mark.asyncio
async def test_executor_unknown_tool_returns_empty():
    async def mock_execute(name: str, args: dict) -> str:
        return f"Unknown tool: {name}"

    tasks = [{"tool": "nonexistent_tool", "args": {}, "priority": 1}]

    with patch("services.api.routes.ui_data._execute_chat_tool", side_effect=mock_execute):
        from services.api.chat_graph import _run_tasks_parallel
        results = await _run_tasks_parallel(tasks)

    assert len(results) == 1
    assert "nonexistent_tool" in results[0]["result"] or results[0]["result"] == ""
