"""
api/routes/stream.py
====================
WebSocket /ws/stream?ticker=MARUTI

Streams real-time agent progress events to the TypeScript dashboard:

  {"event": "agent_progress", "agent": "pattern_analysis", "score": 0.73}
  {"event": "agent_progress", "agent": "fundamentals",      "score": 0.68}
  ...
  {"event": "complete", "report": {<FinalReport JSON>}}

The orchestrator's analyse_async() fires progress_callback from within
the event loop as each of the 8 agent coroutines completes, so no
call_soon_threadsafe is needed — queue.put_nowait() is safe here.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.pipeline.orchestrator import AutomobileAgentOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/stream")
async def stream(websocket: WebSocket, ticker: str = ""):
    """
    WebSocket endpoint.  Connect with:
        ws://localhost:8000/ws/stream?ticker=MARUTI
    """
    await websocket.accept()
    ticker = ticker.strip().upper()

    if not ticker:
        await websocket.send_text(json.dumps({"event": "error", "detail": "ticker required"}))
        await websocket.close()
        return

    logger.info("[WS /ws/stream] Connection for %s", ticker)

    queue: asyncio.Queue = asyncio.Queue()

    def progress_callback(agent_name: str, score: float) -> None:
        """
        Called from within the asyncio event loop (inside a gather coroutine),
        so put_nowait is safe — no call_soon_threadsafe needed.
        """
        event = json.dumps({"event": "agent_progress", "agent": agent_name, "score": round(score, 4)})
        queue.put_nowait(event)

    orchestrator = AutomobileAgentOrchestrator()

    async def run_pipeline() -> None:
        try:
            report = await orchestrator.analyse_async(ticker, progress_callback=progress_callback)
            complete_event = json.dumps({"event": "complete", "report": report.model_dump()})
            await queue.put(complete_event)
        except Exception as exc:
            err_event = json.dumps({"event": "error", "detail": str(exc)})
            await queue.put(err_event)

    pipeline_task = asyncio.create_task(run_pipeline())

    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=150.0)
            await websocket.send_text(event)
            if json.loads(event).get("event") in ("complete", "error"):
                break
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps({"event": "error", "detail": "pipeline timeout"}))
    except WebSocketDisconnect:
        logger.info("[WS /ws/stream] Client disconnected for %s", ticker)
        pipeline_task.cancel()
    finally:
        await websocket.close()
