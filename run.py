"""
Railway entry point.
Sets PYTHONPATH before uvicorn spawns any worker subprocesses,
so pipeline/, data/, sectors/ are importable in all processes.
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.resolve()
os.environ["PYTHONPATH"] = str(ROOT)          # inherited by all subprocesses
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(
        "services.api.server:app",
        host="0.0.0.0",
        port=port,
        workers=2,
    )
