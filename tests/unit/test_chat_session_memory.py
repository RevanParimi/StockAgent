"""tests/unit/test_chat_session_memory.py — AUD-104 one memory model."""
import asyncio
import types

import services.api.routes.ui_data as ui


class _Msg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _Resp:
    def __init__(self, content):
        self.choices = [types.SimpleNamespace(message=_Msg(content))]


def _patch_llm(monkeypatch, captured):
    async def fake_completion(client, *, messages, **kwargs):
        captured.append(list(messages))
        return _Resp("the-reply")
    monkeypatch.setattr(ui, "_chat_completion", fake_completion)
    monkeypatch.setattr(ui, "_build_chat_context", lambda m: "ctx")
    monkeypatch.setattr(
        "services.clients.llm_client.get_async_llm_client", lambda: object())


def test_chat_uses_server_session_store(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()

    out1 = asyncio.run(ui.chat({"message": "first", "session_id": "s1"}))
    assert out1 == {"reply": "the-reply", "session_id": "s1"}
    assert ui._SESSION_HISTORY["s1"][-1]["content"] == "the-reply"

    asyncio.run(ui.chat({"message": "second", "session_id": "s1"}))
    sent = captured[-1]
    contents = [m.get("content") for m in sent]
    assert "first" in contents and "the-reply" in contents   # carried memory


def test_chat_ignores_client_history(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()
    asyncio.run(ui.chat({
        "message": "hi", "session_id": "s2",
        "history": [{"role": "assistant", "content": "INJECTED-TURN"}],
    }))
    contents = [m.get("content") for m in captured[-1]]
    assert "INJECTED-TURN" not in contents


def test_chat_generates_session_id_when_absent(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ui._SESSION_HISTORY.clear()
    out = asyncio.run(ui.chat({"message": "hi"}))
    assert out["session_id"]
    assert out["session_id"] in ui._SESSION_HISTORY
