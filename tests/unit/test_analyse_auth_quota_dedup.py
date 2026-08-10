"""
On-demand pipeline entry points: authentication, per-user quota, and
per-ticker fan-out dedup.

Covers the two endpoints that run a full 8-agent LLM pipeline —
``POST /analyse`` and ``WS /ws/stream`` — which were previously reachable
anonymously, unmetered, and with one pipeline run per viewer.

The dedup tests drive the hub primitives directly rather than opening two
TestClient websockets. Production serves every connection from one uvicorn
event loop, but TestClient gives each ``websocket_connect`` its own loop, so
the nested-client version would exercise cross-loop queue wakeups that never
happen in the real server.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from services.api.routes import stream as stream_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    from services.data.stores import user_store
    monkeypatch.setattr(user_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(user_store, "_conn_holder", {"conn": None})
    return user_store


@pytest.fixture()
def enforced(monkeypatch):
    """AUTH_REQUIRED=true, as prod runs it."""
    from core.config import settings
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True, raising=False)
    return settings


@pytest.fixture()
def client():
    from services.api.server import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_hub():
    """The hub is module-level state; never leak a run between tests."""
    stream_mod._hub.clear()
    yield
    stream_mod._hub.clear()


def _member(store, email="m@x.com"):
    user = store.create_user(email, "hunter2longer", "Member")
    return user, store.create_session(user["user_id"], remember_me=False)


def _fake_orchestrator_cls(analyse_async):
    instance = MagicMock()
    instance.analyse_async = analyse_async
    cls = MagicMock(return_value=instance)
    cls.__name__ = "FakeOrchestrator"
    return cls


def _report(ticker="MARUTI"):
    report = MagicMock()
    report.model_dump.return_value = {"ticker": ticker, "final_score": 0.6}
    return report


# ---------------------------------------------------------------------------
# POST /analyse — authentication
# ---------------------------------------------------------------------------

class TestAnalyseAuth:
    def test_anonymous_rejected_when_auth_required(self, client, enforced):
        resp = client.post("/analyse", json={"ticker": "MARUTI"})
        assert resp.status_code == 401

    def test_invalid_token_rejected(self, client, enforced, store):
        resp = client.post("/analyse", json={"ticker": "MARUTI"},
                           headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == 401

    def test_anonymous_still_allowed_when_auth_not_required(self, client,
                                                            monkeypatch):
        """The single-user escape hatch must keep working unchanged."""
        from core.config import settings
        monkeypatch.setattr(settings, "AUTH_REQUIRED", False, raising=False)
        monkeypatch.setattr("backend.sectors.get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(
                                _async_returning(_report())))
        resp = client.post("/analyse", json={"ticker": "MARUTI"})
        assert resp.status_code == 200


def _async_returning(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------

class TestAnalyseQuota:
    def test_member_blocked_over_quota(self, store, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "ANALYSE_DAILY_QUOTA", 2, raising=False)
        from services.api.auth import check_analyse_quota
        member = {"user_id": "u_ab", "role": "member"}
        assert check_analyse_quota(member) is None      # run 1
        assert check_analyse_quota(member) is None      # run 2
        blocked = check_analyse_quota(member)           # run 3
        assert blocked is not None and "on-demand analyses" in blocked

    def test_owner_exempt(self, store, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "ANALYSE_DAILY_QUOTA", 1, raising=False)
        from services.api.auth import check_analyse_quota
        owner = {"user_id": "primary", "role": "owner"}
        for _ in range(5):
            assert check_analyse_quota(owner) is None

    def test_zero_means_unlimited(self, store, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "ANALYSE_DAILY_QUOTA", 0, raising=False)
        from services.api.auth import check_analyse_quota
        member = {"user_id": "u_ab", "role": "member"}
        for _ in range(5):
            assert check_analyse_quota(member) is None

    def test_store_failure_allows_run(self, store, monkeypatch):
        """Availability over strict metering."""
        from core.config import settings
        monkeypatch.setattr(settings, "ANALYSE_DAILY_QUOTA", 1, raising=False)
        from services.data.stores import user_store
        monkeypatch.setattr(user_store, "bump_analyse_usage",
                            lambda uid: (_ for _ in ()).throw(RuntimeError("db gone")))
        from services.api.auth import check_analyse_quota
        assert check_analyse_quota({"user_id": "u_ab", "role": "member"}) is None

    def test_analyse_returns_429_over_quota(self, client, enforced, store,
                                            monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "ANALYSE_DAILY_QUOTA", 1, raising=False)
        monkeypatch.setattr("backend.sectors.get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(
                                _async_returning(_report())))
        _, token = _member(store)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/analyse", json={"ticker": "MARUTI"},
                           headers=headers).status_code == 200
        resp = client.post("/analyse", json={"ticker": "MARUTI"},
                           headers=headers)
        assert resp.status_code == 429

    def test_counter_is_per_user_and_separate_from_chat(self, store):
        assert store.get_analyse_usage("u_a") == 0
        assert store.bump_analyse_usage("u_a") == 1
        assert store.bump_analyse_usage("u_a") == 2
        assert store.get_analyse_usage("u_b") == 0        # per user
        assert store.get_chat_usage("u_a") == 0           # separate counter


# ---------------------------------------------------------------------------
# WS /ws/stream — authentication
# ---------------------------------------------------------------------------

class TestStreamAuth:
    def test_anonymous_ws_rejected_when_auth_required(self, client, enforced):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/stream?ticker=MARUTI") as ws:
                ws.receive_text()

    def test_ws_accepts_token_via_subprotocol(self, client, enforced, store,
                                              monkeypatch):
        monkeypatch.setattr(stream_mod, "get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(
                                _async_returning(_report())))
        _, token = _member(store)
        with client.websocket_connect(
                "/ws/stream?ticker=MARUTI",
                subprotocols=["sa.bearer", token]) as ws:
            while True:
                msg = json.loads(ws.receive_text())
                if msg["event"] in ("complete", "error"):
                    break
        assert msg["event"] == "complete"

    def test_ws_rejects_invalid_token(self, client, enforced, store):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                    "/ws/stream?ticker=MARUTI",
                    subprotocols=["sa.bearer", "bogus-token"]) as ws:
                ws.receive_text()


# ---------------------------------------------------------------------------
# Per-ticker fan-out dedup (the behaviour lost with wsHub.ts)
# ---------------------------------------------------------------------------

class TestFanOutDedup:
    @pytest.mark.asyncio
    async def test_two_viewers_one_pipeline(self, monkeypatch):
        runs: list[str] = []
        release = asyncio.Event()

        async def analyse_async(ticker, progress_callback=None):
            runs.append(ticker)
            progress_callback("fundamentals", 0.5)
            await release.wait()
            return _report(ticker)

        monkeypatch.setattr(stream_mod, "detect_sector", lambda t: "automobile")
        monkeypatch.setattr(stream_mod, "get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(analyse_async))

        run_a, queue_a, is_new = stream_mod._subscribe("MARUTI")
        assert is_new is True
        run_a.task = asyncio.create_task(stream_mod._run_pipeline(run_a))
        await asyncio.sleep(0)                 # let the first event be emitted

        run_b, queue_b, is_new_b = stream_mod._subscribe("MARUTI")
        assert is_new_b is False and run_b is run_a

        # The late joiner is replayed the progress it missed.
        replayed = json.loads(queue_b.get_nowait())
        assert replayed["event"] == "agent_progress"

        release.set()
        await run_a.task

        assert runs == ["MARUTI"], "two viewers must share one pipeline run"
        for queue in (queue_a, queue_b):
            events = []
            while not queue.empty():
                events.append(json.loads(queue.get_nowait())["event"])
            assert "complete" in events

    @pytest.mark.asyncio
    async def test_distinct_tickers_run_separately(self, monkeypatch):
        runs: list[str] = []

        async def analyse_async(ticker, progress_callback=None):
            runs.append(ticker)
            return _report(ticker)

        monkeypatch.setattr(stream_mod, "detect_sector", lambda t: "automobile")
        monkeypatch.setattr(stream_mod, "get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(analyse_async))

        for ticker in ("MARUTI", "TCS"):
            run, _q, _new = stream_mod._subscribe(ticker)
            run.task = asyncio.create_task(stream_mod._run_pipeline(run))
            await run.task

        assert sorted(runs) == ["MARUTI", "TCS"]

    @pytest.mark.asyncio
    async def test_last_viewer_leaving_cancels_the_run(self, monkeypatch):
        started = asyncio.Event()

        async def analyse_async(ticker, progress_callback=None):
            started.set()
            await asyncio.sleep(30)            # never completes during the test
            return _report(ticker)

        monkeypatch.setattr(stream_mod, "detect_sector", lambda t: "automobile")
        monkeypatch.setattr(stream_mod, "get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(analyse_async))

        run, queue, _new = stream_mod._subscribe("MARUTI")
        run.task = asyncio.create_task(stream_mod._run_pipeline(run))
        await started.wait()

        stream_mod._unsubscribe(run, queue)
        await asyncio.sleep(0)

        assert run.task.cancelled() or run.task.done()
        assert "MARUTI" not in stream_mod._hub

    @pytest.mark.asyncio
    async def test_run_is_retired_after_completion(self, monkeypatch):
        async def analyse_async(ticker, progress_callback=None):
            return _report(ticker)

        monkeypatch.setattr(stream_mod, "detect_sector", lambda t: "automobile")
        monkeypatch.setattr(stream_mod, "get_orchestrator",
                            lambda sector: _fake_orchestrator_cls(analyse_async))

        run, _queue, _new = stream_mod._subscribe("MARUTI")
        run.task = asyncio.create_task(stream_mod._run_pipeline(run))
        await run.task

        # A finished run must not be replayed to the next viewer forever.
        assert "MARUTI" not in stream_mod._hub
        _run2, _q2, is_new = stream_mod._subscribe("MARUTI")
        assert is_new is True
