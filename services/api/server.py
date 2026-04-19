"""
api/server.py
=============
FastAPI application — Phase 2 bridge between Python agents and external consumers
(TypeScript dashboard, C# scheduler).

Ports:
  HTTP  :  0.0.0.0:8000
  WS    :  0.0.0.0:8000/ws/stream

Start with:
    uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload

Or via the helper script:
    python -m api.server
"""

from __future__ import annotations

import logging
import sys
import pathlib
from datetime import datetime, timezone

# Ensure repo root is on sys.path so `agents`, `tools`, `config` resolve
# whether this is run from the project root or the api/ subdirectory.
_ROOT = pathlib.Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.routes.analyse import router as analyse_router
from services.api.routes.history import router as history_router
from services.api.routes.stream import router as stream_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StockAgent Python API",
    description=(
        "FastAPI bridge exposing the 8-agent automobile stock analysis pipeline. "
        "Consumed by the TypeScript dashboard (port 3000) and C# scheduler (port 5000)."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow TypeScript dashboard (localhost:3000) and C# service (localhost:5000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(analyse_router, tags=["Analysis"])
app.include_router(history_router, tags=["History"])
app.include_router(stream_router, tags=["Streaming"])


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Health check — used by C# scheduler to verify Python API is up before firing jobs."""
    return {
        "status": "ok",
        "service": "StockAgent Python API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/tickers", tags=["Meta"])
async def list_tickers() -> dict:
    """Returns the configured scheduler tickers."""
    from config import settings
    return {"tickers": getattr(settings, "SCHEDULER_TICKERS", [])}


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
