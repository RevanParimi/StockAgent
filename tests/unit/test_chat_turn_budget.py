"""AUD-101: chat fan-out — retry cap per model + wall-clock deadline."""
import asyncio
import time

import pytest

from services.api.routes import ui_data


class _Transient(Exception):
    status_code = 429


class _Msg:
    content = "ok"
    tool_calls = None


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]
    usage = None


class _FakeCompletions:
    def __init__(self, fail_times=10**9, exc=None):
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc or _Transient("429")

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return _Resp()


class _FakeClient:
    def __init__(self, completions):
        self.chat = type("C", (), {"completions": completions})()


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    slept = []

    async def _sleep(s):
        slept.append(s)

    monkeypatch.setattr(ui_data.asyncio, "sleep", _sleep)
    return slept


def test_retries_capped_at_two_per_model():
    fake = _FakeCompletions()  # always 429
    with pytest.raises(Exception):
        asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    # 2 attempts on FAST + 2 on the REASONING fallback = 4 upstream calls max (was 6)
    assert fake.calls == 2 * 2


def test_escalation_to_fallback_still_works():
    fake = _FakeCompletions(fail_times=2)  # primary exhausted, fallback succeeds
    resp = asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    assert resp.choices[0].message.content == "ok"
    assert fake.calls == 3


def test_deadline_skips_backoff_sleep(_fast_sleep):
    fake = _FakeCompletions()  # always 429
    deadline = time.monotonic() + 0.05  # tighter than the first 0.8s backoff
    with pytest.raises(Exception):
        asyncio.run(ui_data._chat_completion(
            _FakeClient(fake), messages=[], deadline=deadline))
    assert fake.calls == 1          # one attempt, then the budget bails out
    assert _fast_sleep == []        # never slept toward a blown deadline


def test_non_transient_raises_immediately():
    class _Fatal(Exception):
        status_code = 400

    fake = _FakeCompletions(exc=_Fatal("bad request"))
    with pytest.raises(_Fatal):
        asyncio.run(ui_data._chat_completion(_FakeClient(fake), messages=[]))
    assert fake.calls == 1
