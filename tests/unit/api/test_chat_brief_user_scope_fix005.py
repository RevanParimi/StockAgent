"""FIX-005: chat's get_portfolio_brief reads only the caller's own portfolio.

The invariant, tested at every layer a request passes through: for accounts
with different briefs, no caller ever receives another account's brief or
digest, and a request without a valid user id never falls back to the default
user. The routes are driven for real, with only the model stubbed: the stub
asks for the tool and then echoes what the tool returned.
"""
import asyncio
import json
import types
from pathlib import Path

import pytest

import services.api.routes.ui_data as ui
import services.data.stores.chat_session_store as css
from core.config import settings
from core.portfolio.store import PortfolioStore

OWNER = "primary"                      # settings.PORTFOLIO_DEFAULT_USER_ID
MARKERS = {
    OWNER: "OWNER-ONLY-HEADLINE-7731",
    "member_a": "MEMBER-A-HEADLINE-4410",
}
DIGEST_MARKERS = {OWNER: "OWNERCO", "member_b": "MEMBCO"}
ALL_MARKERS = list(MARKERS.values()) + list(DIGEST_MARKERS.values())


def _brief(headline: str) -> dict:
    return {
        "date": "2026-10-09", "kind": "morning_brief", "headline": headline,
        "portfolio": {"portfolio_value": 110000.0, "total_pnl_pct": 10.0},
        "advisor_flags": [], "overnight": [], "earnings_soon": [],
        "discovery_adds": [], "ipo_watch": [], "lockin_flags": [], "regime": None,
    }


def _digest(user_id: str, symbol: str) -> dict:
    return {
        "date": "2026-10-08", "user_id": user_id, "portfolio_value": 90000.0,
        "total_pnl_pct": -2.0,
        "holdings": [{"symbol": symbol, "verdict": "EXIT", "pnl_pct": -15.0,
                      "close": 80.0, "reason": "stop", "notes": []}],
        "escalations": [symbol],
    }


@pytest.fixture()
def portfolios(tmp_path, monkeypatch):
    """Owner: brief + digest. member_a: brief. member_b: digest only.
    member_c: no portfolio at all."""
    root = tmp_path / "portfolio"
    root.mkdir()
    monkeypatch.setattr(settings, "PORTFOLIO_DATA_DIR", str(root))
    owner = PortfolioStore(user_id=OWNER, base_dir=str(root))
    owner.save_brief(_brief(MARKERS[OWNER]))
    owner.save_digest(_digest(OWNER, DIGEST_MARKERS[OWNER]))
    PortfolioStore(user_id="member_a", base_dir=str(root)).save_brief(_brief(MARKERS["member_a"]))
    PortfolioStore(user_id="member_b", base_dir=str(root)).save_digest(
        _digest("member_b", DIGEST_MARKERS["member_b"]))
    return root


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _others(own: str | None) -> list[str]:
    return [m for m in ALL_MARKERS if m != own]


# ---------------------------------------------------------------------------
# The tool, the dispatcher and the executor
# ---------------------------------------------------------------------------

_CALLERS = {
    "tool": lambda uid: ui._chat_tool_portfolio_brief(uid),
    "dispatch": lambda uid: asyncio.run(
        ui._dispatch_chat_tool("get_portfolio_brief", {}, user_id=uid)),
    "execute": lambda uid: asyncio.run(
        ui._execute_chat_tool("get_portfolio_brief", {}, user_id=uid)),
    "execute_cached": lambda uid: asyncio.run(
        ui._execute_chat_tool("get_portfolio_brief", {}, {}, user_id=uid)),
}


@pytest.mark.parametrize("layer", sorted(_CALLERS))
@pytest.mark.parametrize("user_id,own", [
    (OWNER, MARKERS[OWNER]),
    ("member_a", MARKERS["member_a"]),
    ("member_b", DIGEST_MARKERS["member_b"]),
])
def test_each_caller_sees_only_their_own_portfolio(portfolios, layer, user_id, own):
    out = _CALLERS[layer](user_id)
    assert own in out
    for other in _others(own):
        assert other not in out, f"{user_id} received {other} via {layer}"


@pytest.mark.parametrize("layer", sorted(_CALLERS))
def test_member_without_portfolio_gets_no_brief_and_no_directory(portfolios, layer):
    before = _tree(portfolios)
    out = _CALLERS[layer]("member_c")
    assert out == ui._BRIEF_NOT_YET
    assert _tree(portfolios) == before          # a read never mints a portfolio


@pytest.mark.parametrize("layer", sorted(_CALLERS))
@pytest.mark.parametrize("bad", [None, "", " primary", "../primary", "a/b", "x" * 65,
                                 "primary/../member_a"])
def test_missing_or_invalid_user_never_falls_back(portfolios, layer, bad):
    before = _tree(portfolios)
    out = _CALLERS[layer](bad)
    assert out == ui._BRIEF_NO_USER
    for marker in ALL_MARKERS:
        assert marker not in out
    assert _tree(portfolios) == before


def test_default_argument_fails_closed(portfolios):
    """A caller that forgets the user gets a refusal, not the default user."""
    assert asyncio.run(ui._dispatch_chat_tool("get_portfolio_brief", {})) == ui._BRIEF_NO_USER
    assert asyncio.run(ui._execute_chat_tool("get_portfolio_brief", {})) == ui._BRIEF_NO_USER


# ---------------------------------------------------------------------------
# Both real chat routes, model stubbed
# ---------------------------------------------------------------------------

@pytest.fixture()
def chat_env(portfolios, tmp_path, monkeypatch):
    monkeypatch.setattr(css.settings, "CHAT_SESSIONS_DB_PATH",
                        str(tmp_path / "chat_sessions.db"), raising=False)
    css._reset_for_tests()
    calls = []

    async def fake_completion(client, *, messages, **kwargs):
        calls.append(kwargs.get("tools") is not None)
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if kwargs.get("tools") is not None and not tool_msgs:
            call = types.SimpleNamespace(
                id="call-1",
                function=types.SimpleNamespace(name="get_portfolio_brief", arguments="{}"))
            msg = types.SimpleNamespace(content="", tool_calls=[call])
        else:
            echoed = tool_msgs[-1]["content"] if tool_msgs else "no tool ran"
            msg = types.SimpleNamespace(content=f"Your brief:\n{echoed}", tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)

    monkeypatch.setattr(ui, "_chat_completion", fake_completion)
    monkeypatch.setattr(ui, "_build_chat_context", lambda m: "ctx")
    monkeypatch.setattr(ui, "check_chat_quota", lambda user: None)
    monkeypatch.setattr("services.clients.llm_client.get_async_llm_client", lambda: object())
    yield calls
    css._reset_for_tests()


def _stream_events(user: dict) -> list[dict]:
    async def run():
        resp = await ui.chat_stream({"message": "show my brief", "session_id": "s-1"}, user=user)
        chunks = [c async for c in resp.body_iterator]
        return chunks
    events = []
    for chunk in asyncio.run(run()):
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


@pytest.mark.parametrize("user,own", [
    ({"user_id": OWNER, "role": "owner"}, MARKERS[OWNER]),
    ({"user_id": "member_a", "role": "member"}, MARKERS["member_a"]),
    ({"user_id": "member_b", "role": "member"}, DIGEST_MARKERS["member_b"]),
])
def test_streaming_route_serves_each_caller_their_own_brief(chat_env, user, own):
    events = _stream_events(user)
    tool_results = [e for e in events if e.get("event") == "tool_result"
                    and e.get("tool") == "get_portfolio_brief"]
    assert len(tool_results) == 1 and own in tool_results[0]["summary"]
    whole = json.dumps(events)
    reply = "".join(e["text"] for e in events if e.get("event") == "token")
    assert own in reply
    for other in _others(own):
        assert other not in whole, f"{user['user_id']} saw {other} on the stream"
    assert chat_env == [True, True]              # tool round, then the answer


@pytest.mark.parametrize("user,own", [
    ({"user_id": OWNER, "role": "owner"}, MARKERS[OWNER]),
    ({"user_id": "member_a", "role": "member"}, MARKERS["member_a"]),
])
def test_non_streaming_route_serves_each_caller_their_own_brief(chat_env, user, own):
    out = asyncio.run(ui.chat({"message": "show my brief", "session_id": "s-2"}, user=user))
    assert own in out["reply"]
    for other in _others(own):
        assert other not in out["reply"]


def test_member_without_portfolio_on_the_stream_never_sees_the_owner(chat_env, portfolios):
    before = _tree(portfolios)
    events = _stream_events({"user_id": "member_c", "role": "member"})
    whole = json.dumps(events)
    for marker in ALL_MARKERS:
        assert marker not in whole
    assert "No brief yet" in whole
    assert _tree(portfolios) == before
