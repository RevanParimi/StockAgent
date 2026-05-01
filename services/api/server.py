"""
api/server.py
=============
FastAPI application — Phase 2 bridge between Python agents and external consumers
(TypeScript gateway on port 3000).

Ports:
  HTTP  :  0.0.0.0:8001  (INTERNAL — not exposed to browser)
  WS    :  0.0.0.0:8001/ws/stream

Start with:
    uvicorn services.api.server:app --host 0.0.0.0 --port 8001 --reload

Or via the helper script:
    python -m services.api.server
"""

from __future__ import annotations

import logging
import sys
import pathlib
from datetime import datetime, timezone

# Ensure repo root is on sys.path so `agents`, `tools`, `config` resolve
# whether this is run from the project root or the api/ subdirectory.
_ROOT = pathlib.Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.api.routes.analyse import router as analyse_router
from services.api.routes.history import router as history_router
from services.api.routes.stream import router as stream_router
from services.api.routes.ui_data import router as ui_router

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
        "FastAPI bridge exposing the 9-agent automobile stock analysis pipeline. "
        "Also serves the prototype UI at /app and UI data routes at /ui/*."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the TypeScript gateway (3000) AND direct browser access to the prototype (8001).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
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
app.include_router(ui_router,     tags=["UI"])


@app.get("/", tags=["UI"], include_in_schema=False)
async def root():
    """Redirect root to the prototype UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/index.html")


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
    from core.config import settings
    return {"tickers": getattr(settings, "SCHEDULER_TICKERS", [])}


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

_PROTO_DIR = _ROOT / "prototypes" / "beginner"
if _PROTO_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(_PROTO_DIR), html=True), name="prototype")
else:
    logger.warning("[server] Prototype directory not found at %s — /app not mounted", _PROTO_DIR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.api.server:app", host="0.0.0.0", port=8001, reload=True)
