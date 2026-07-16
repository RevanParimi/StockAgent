"""AUD-092/093/094: chat calls disable reasoning + record telemetry."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import services.clients.llm_client as llm_mod
from services.api.routes.ui_data import _chat_completion, _CHAT_FALLBACK_MODEL


def _fake_resp():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def _fake_client(side_effect=None):
    create = AsyncMock(return_value=_fake_resp(), side_effect=side_effect)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_mod, "record_llm_call", lambda *a: calls.append(a))
    return calls


def test_reasoning_disabled_by_default(recorded):
    client = _fake_client()
    asyncio.run(_chat_completion(client, messages=[], temperature=0.4, max_tokens=600))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}


def test_explicit_extra_body_wins(recorded):
    client = _fake_client()
    asyncio.run(_chat_completion(client, messages=[], extra_body={"x": 1}))
    assert client.chat.completions.create.call_args.kwargs["extra_body"] == {"x": 1}


def test_success_recorded(recorded):
    asyncio.run(_chat_completion(_fake_client(), messages=[]))
    assert len(recorded) == 1
    caller, model, pt, ct, latency, success = recorded[0]
    assert caller == "ui_chat" and pt == 11 and ct == 7 and success is True


def test_nontransient_failure_recorded_and_raised(recorded):
    client = _fake_client(side_effect=ValueError("boom"))
    with pytest.raises(ValueError):
        asyncio.run(_chat_completion(client, messages=[]))
    assert len(recorded) == 1 and recorded[0][5] is False


def test_stale_fallback_literal_gone():
    assert _CHAT_FALLBACK_MODEL != "qwen/qwen3.7-max"
