"""FIX-007: the server's log lines are readable only by the owner or the machine key.

The invariant, through the real application (services.api.server.app, every
router and middleware): for GET /ui/logs and GET /ui/logs/stream, a caller who
is not the owner gets 401 or 403 and no log entry; a line planted with a marker
string never appears in a refused response; and a refused request never reads
the buffer or subscribes to it. The owner and the machine key still get the
buffered history and, on the stream, live lines.

A granted stream never ends, and the TestClient waits for the end of a
response, so every request here is driven as raw ASGI by a client that
disconnects once it has what it came for, or after a few seconds, as a browser
leaving the screen does. A stream that should have been refused then fails the
test instead of hanging it.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging

import pytest
from fastapi.routing import APIRoute

from core.config import settings
from services.api import log_buffer
from services.api.auth import require_owner
from services.api.server import app
from services.data.stores import user_store

KEY = "machine-key-for-fix007-tests"
HISTORY_MARKER = "FIX007-PLANTED-u_7f3a9c21-HISTORY"
LIVE_MARKER = "FIX007-PLANTED-u_7f3a9c21-LIVE"
_planter = logging.getLogger("fix007.planted")


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """An owner and a member with live sessions, the machine key set, a marker
    line in the ring buffer, and spies on every buffer read."""
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    monkeypatch.setenv("SCHEDULER_KEY", KEY)
    owner = user_store.create_user("o@example.invalid", "pw-for-tests-1", "O", role="owner",
                                   user_id=settings.PORTFOLIO_DEFAULT_USER_ID)
    member = user_store.create_user("m@example.invalid", "pw-for-tests-1", "M")
    tokens = {"owner": user_store.create_session(owner["user_id"], True),
              "member": user_store.create_session(member["user_id"], True)}

    _planter.warning("[brief] build failed for user %s", HISTORY_MARKER)
    assert any(HISTORY_MARKER in e["msg"] for e in log_buffer.snapshot()), \
        "precondition: the planted line must be in the ring buffer"

    reads = {"snapshot": 0, "subscribe": 0, "queues": []}
    real_snapshot, real_subscribe = log_buffer.snapshot, log_buffer.subscribe

    def snapshot(*a, **kw):
        reads["snapshot"] += 1
        return real_snapshot(*a, **kw)

    def subscribe():
        reads["subscribe"] += 1
        q = real_subscribe()
        reads["queues"].append(q)
        return q

    monkeypatch.setattr(log_buffer, "snapshot", snapshot)
    monkeypatch.setattr(log_buffer, "subscribe", subscribe)
    yield tokens, reads
    for q in reads["queues"]:
        log_buffer.unsubscribe(q)
    if user_store._conn_holder.get("conn") is not None:
        user_store._conn_holder["conn"].close()


def _headers(tokens: dict, who: str) -> dict:
    return {
        "owner": {"Authorization": f"Bearer {tokens['owner']}"},
        "member": {"Authorization": f"Bearer {tokens['member']}"},
        "machine": {"X-Scheduler-Key": KEY},
        "anonymous": {},
        "bad_token": {"Authorization": "Bearer not-a-session"},
        "wrong_key": {"X-Scheduler-Key": "not-the-key"},
        "member_wrong_key": {"Authorization": f"Bearer {tokens['member']}",
                             "X-Scheduler-Key": "not-the-key"},
    }[who]


def _get(url: str, headers: dict, reads: dict, *, live: str | None = None,
         grace: float = 2.0) -> tuple[int, dict, str]:
    """GET `url` through the real app as raw ASGI; returns (status, headers, body).

    The client disconnects when the response completes, when the history
    marker has arrived (and, with `live`, a line logged after it), or `grace`
    seconds after asking."""
    path, _, query = url.partition("?")

    async def main():
        start: dict = {}
        body = bytearray()
        done = asyncio.Event()
        state = {"requested": False, "logged": False}

        async def receive():
            if not state["requested"]:
                state["requested"] = True
                return {"type": "http.request", "body": b"", "more_body": False}
            try:
                await asyncio.wait_for(done.wait(), grace)
            except asyncio.TimeoutError:
                pass
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                start.update(message)
                return
            body.extend(message.get("body", b""))
            text = body.decode("utf-8", "replace")
            if HISTORY_MARKER in text and live and not state["logged"]:
                state["logged"] = True
                _planter.warning("[delivery] email lookup failed for user '%s'", live)
            if HISTORY_MARKER in text and (live is None or live in text):
                done.set()
            if not message.get("more_body", False):
                done.set()

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "root_path": "",
            "headers": [(b"host", b"testserver")]
                       + [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("testclient", 50000), "server": ("testserver", 80), "state": {},
        }
        try:
            await asyncio.wait_for(app(scope, receive, send), grace + 10)
        finally:
            # A reader thread parked on its queue's 30 s get() would hold up the
            # loop's shutdown; give it something to return.
            for q in reads["queues"]:
                q.put_nowait({"level": "DEBUG", "msg": ""})
        hdrs = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
        return start.get("status"), hdrs, body.decode("utf-8", "replace")

    return asyncio.run(main())


def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


ROUTES = ["/ui/logs", "/ui/logs?level=DEBUG&limit=1000", "/ui/logs/stream",
          "/ui/logs/stream?level=DEBUG"]


def _assert_refused_without_logs(result, code: int, reads: dict) -> None:
    status, headers, text = result
    assert status == code, text[:300]
    assert HISTORY_MARKER not in text and LIVE_MARKER not in text
    assert "text/event-stream" not in headers.get("content-type", "")
    assert _events(text) == [] and set(json.loads(text)) == {"detail"}
    assert reads["snapshot"] == 0 and reads["subscribe"] == 0     # the buffer was never read


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", ROUTES)
@pytest.mark.parametrize("who,code", [
    ("anonymous", 401), ("bad_token", 401), ("wrong_key", 401),
    ("member", 403), ("member_wrong_key", 403),
])
def test_with_auth_required_only_the_owner_or_key_reads_logs(world, monkeypatch, url, who, code):
    tokens, reads = world
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    before = len(log_buffer._SUBSCRIBERS)
    _assert_refused_without_logs(_get(url, _headers(tokens, who), reads), code, reads)
    assert len(log_buffer._SUBSCRIBERS) == before


@pytest.mark.parametrize("url", ROUTES)
@pytest.mark.parametrize("who,code", [("member", 403), ("member_wrong_key", 403), ("bad_token", 401)])
def test_with_auth_off_a_member_is_still_refused(world, monkeypatch, url, who, code):
    tokens, reads = world
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    _assert_refused_without_logs(_get(url, _headers(tokens, who), reads), code, reads)


def test_with_auth_off_anonymous_is_the_owner_as_everywhere(world, monkeypatch):
    """require_owner's single-user mode: with AUTH_REQUIRED off every anonymous
    request is the owner, on these routes as on every other owner route.
    Production's protection rests on AUTH_REQUIRED being on."""
    tokens, reads = world
    monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
    status, _, text = _get("/ui/logs?level=DEBUG", {}, reads)
    assert status == 200 and HISTORY_MARKER in text


# ---------------------------------------------------------------------------
# The owner and the machine key still read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("auth_required", [True, False])
@pytest.mark.parametrize("who", ["owner", "machine"])
def test_owner_and_machine_key_read_recent_lines(world, monkeypatch, auth_required, who):
    tokens, reads = world
    monkeypatch.setattr(settings, "AUTH_REQUIRED", auth_required, raising=False)
    status, _, text = _get("/ui/logs?level=DEBUG&limit=1000", _headers(tokens, who), reads)
    assert status == 200
    body = json.loads(text)
    assert body["count"] == len(body["entries"]) >= 1
    assert any(HISTORY_MARKER in e["msg"] for e in body["entries"])
    assert reads["snapshot"] == 1


@pytest.mark.parametrize("auth_required", [True, False])
@pytest.mark.parametrize("who", ["owner", "machine"])
def test_owner_and_machine_key_get_history_then_live_lines(world, monkeypatch, auth_required, who):
    tokens, reads = world
    monkeypatch.setattr(settings, "AUTH_REQUIRED", auth_required, raising=False)
    status, headers, text = _get("/ui/logs/stream?level=DEBUG", _headers(tokens, who), reads,
                                 live=LIVE_MARKER)
    assert status == 200 and headers["content-type"].startswith("text/event-stream")
    msgs = [e["msg"] for e in _events(text)]
    history = next(i for i, m in enumerate(msgs) if HISTORY_MARKER in m)
    live = next(i for i, m in enumerate(msgs) if LIVE_MARKER in m)
    assert history < live
    assert reads["subscribe"] == 1
    assert reads["queues"][0] not in log_buffer._SUBSCRIBERS      # leaving the screen unsubscribes


# ---------------------------------------------------------------------------
# Every route that reads the ring buffer carries the gate
# ---------------------------------------------------------------------------

def test_every_route_reading_the_log_buffer_requires_the_owner():
    readers = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        source = inspect.getsource(route.endpoint)
        if "log_buffer" in source and ("snapshot(" in source or "subscribe(" in source):
            readers.append(route.path)
            calls = [d.call for d in route.dependant.dependencies]
            assert require_owner in calls, f"{route.path} reads server logs without require_owner"
    assert sorted(readers) == ["/ui/logs", "/ui/logs/stream"]
