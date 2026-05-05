"""
Railway / local entry point.
Adds repo root to sys.path before uvicorn imports anything,
so pipeline/, data/, sectors/ are always importable.
Single-worker async mode — sufficient for personal use (1-5 runs/day).
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(
        "services.api.server:app",
        host="0.0.0.0",
        port=port,
        # Single worker — no subprocess spawning, sys.path stays correct.
        # FastAPI/asyncio handles concurrent requests fine at this scale.
    )
