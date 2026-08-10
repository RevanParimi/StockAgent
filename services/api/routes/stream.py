"""
api/routes/stream.py
====================
WebSocket /ws/stream?ticker=MARUTI

Streams real-time agent progress events to the dashboard:

  {"event": "agent_progress", "agent": "pattern_analysis", "score": 0.73}
  {"event": "agent_progress", "agent": "fundamentals",      "score": 0.68}
  ...
  {"event": "complete", "report": {<FinalReport JSON>}}

The orchestrator's analyse_async() fires progress_callback from within
the event loop as each of the 8 agent coroutines completes, so no
call_soon_threadsafe is needed — queue.put_nowait() is safe here.

Two properties this endpoint must hold, both restored here:

1. **Authenticated + metered.** One connection triggers a full 8-agent LLM
   pipeline. Identity comes from the bearer session (see auth.get_ws_user)
   and each connection is charged against the caller's daily quota.

2. **One pipeline per ticker, fanned out to N viewers.** The deleted
   TypeScript gateway (`wsHub.ts`, removed in 931da78) multiplexed a single
   upstream run per ticker to every subscribed client. Without that, N
   viewers of one ticker meant N concurrent 8-agent runs. `_hub` below is
   that multiplexer: concurrent connections for the same ticker attach to
   the in-flight run and replay the progress it has already emitted.

Concurrency note: `_hub` is guarded by nothing, deliberately. Every mutation
below happens inside an await-free block, and asyncio is cooperatively
scheduled on a single thread, so those blocks cannot interleave. Adding a
lock would require awaiting from the sync progress_callback, which is not
possible.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.sectors import detect_sector, get_orchestrator
from services.api.auth import (WS_BEARER_SUBPROTOCOL, check_analyse_quota,
                               get_ws_user)

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket close codes (RFC 6455 + app range).
_WS_POLICY_VIOLATION = 1008
_WS_TRY_AGAIN_LATER = 1013

_STREAM_TIMEOUT_SECONDS = 150.0


class _TickerRun:
    """One in-flight pipeline for a ticker, shared by all its viewers."""

    __slots__ = ("ticker", "task", "subscribers", "history", "done")

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self.task: asyncio.Task | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.history: list[str] = []      # events already emitted, for late joiners
        self.done = False


# ticker -> the run currently streaming for it
_hub: dict[str, _TickerRun] = {}


def _publish(run: _TickerRun, event: str) -> None:
    """Fan one event out to every viewer and record it for late joiners.

    Await-free by construction — see the concurrency note in the module
    docstring.
    """
    run.history.append(event)
    for queue in run.subscribers:
        queue.put_nowait(event)


def _subscribe(ticker: str) -> tuple[_TickerRun, asyncio.Queue, bool]:
    """Attach a viewer to the run for `ticker`, starting one if needed.

    Returns (run, queue, is_new_run). A viewer joining mid-run is replayed
    the events already emitted, so its progress bars are not stuck at zero.
    Await-free by construction.
    """
    run = _hub.get(ticker)
    is_new_run = run is None
    if run is None:
        run = _TickerRun(ticker)
        _hub[ticker] = run

    queue: asyncio.Queue = asyncio.Queue()
    for event in run.history:
        queue.put_nowait(event)
    run.subscribers.add(queue)
    return run, queue, is_new_run


def _unsubscribe(run: _TickerRun, queue: asyncio.Queue) -> None:
    """Detach a viewer; cancel the pipeline once the last one leaves.

    Nobody is waiting for the result at that point, so finishing the run
    would burn LLM spend for output no client will ever receive.
    """
    run.subscribers.discard(queue)
    if run.subscribers or run.done:
        return
    if run.task is not None and not run.task.done():
        run.task.cancel()
        logger.info("[WS /ws/stream] last viewer left %s — pipeline cancelled",
                    run.ticker)
    if _hub.get(run.ticker) is run:
        del _hub[run.ticker]


async def _run_pipeline(run: _TickerRun) -> None:
    """Drive one analysis and broadcast its events to all viewers."""
    def progress_callback(agent_name: str, score: float) -> None:
        _publish(run, json.dumps({"event": "agent_progress",
                                  "agent": agent_name,
                                  "score": round(score, 4)}))

    try:
        sector = detect_sector(run.ticker)
        orchestrator = get_orchestrator(sector)()
        report = await orchestrator.analyse_async(
            run.ticker, progress_callback=progress_callback)
        _publish(run, json.dumps({"event": "complete",
                                  "report": report.model_dump()}))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("[WS /ws/stream] pipeline failed for %s: %s",
                     run.ticker, exc, exc_info=True)
        _publish(run, json.dumps({
            "event": "error",
            "detail": "Analysis pipeline failed. Please try again later.",
        }))
    finally:
        # Terminal: retire the run so the next viewer gets a fresh analysis
        # rather than an indefinitely replayed stale report.
        run.done = True
        if _hub.get(run.ticker) is run:
            del _hub[run.ticker]


async def _reject(websocket: WebSocket, detail: str, code: int) -> None:
    """Refuse a connection before accepting it (handshake fails with 403)."""
    await websocket.close(code=code, reason=detail)


@router.websocket("/ws/stream")
async def stream(websocket: WebSocket, ticker: str = ""):
    """
    WebSocket endpoint.  Connect with:
        ws://localhost:8000/ws/stream?ticker=MARUTI

    Browsers pass the session token as a subprotocol pair:
        new WebSocket(url, ['sa.bearer', token])
    """
    user = await get_ws_user(websocket)
    if user is None:
        await _reject(websocket, "Login required.", _WS_POLICY_VIOLATION)
        return

    ticker = ticker.strip().upper()
    if not ticker:
        # Accept first so the client reads a structured error rather than a
        # bare handshake failure (pre-existing contract — tests rely on it).
        await _accept(websocket)
        await websocket.send_text(json.dumps({"event": "error",
                                              "detail": "ticker required"}))
        await _safe_close(websocket)
        return

    over_quota = check_analyse_quota(user)
    if over_quota:
        await _reject(websocket, over_quota, _WS_TRY_AGAIN_LATER)
        return

    await _accept(websocket)
    logger.info("[WS /ws/stream] Connection for %s (user=%s)",
                ticker, user.get("user_id"))

    run, queue, is_new_run = _subscribe(ticker)
    if is_new_run:
        run.task = asyncio.create_task(_run_pipeline(run))
    else:
        logger.info("[WS /ws/stream] %s already running — attached viewer #%d",
                    ticker, len(run.subscribers))

    try:
        while True:
            event = await asyncio.wait_for(queue.get(),
                                           timeout=_STREAM_TIMEOUT_SECONDS)
            await websocket.send_text(event)
            if json.loads(event).get("event") in ("complete", "error"):
                break
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps({"event": "error",
                                              "detail": "pipeline timeout"}))
    except WebSocketDisconnect:
        logger.info("[WS /ws/stream] Client disconnected for %s", ticker)
    finally:
        _unsubscribe(run, queue)
        await _safe_close(websocket)


async def _accept(websocket: WebSocket) -> None:
    """Accept, echoing the bearer subprotocol when the client offered it.

    A browser aborts the connection unless the server selects one of the
    subprotocols it advertised.
    """
    offered = list(websocket.scope.get("subprotocols") or [])
    if WS_BEARER_SUBPROTOCOL in offered:
        await websocket.accept(subprotocol=WS_BEARER_SUBPROTOCOL)
    else:
        await websocket.accept()


async def _safe_close(websocket: WebSocket) -> None:
    """Close, tolerating an already-closed or already-disconnected socket."""
    try:
        await websocket.close()
    except RuntimeError:
        pass
