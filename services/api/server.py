"""
api/server.py
=============
FastAPI application — StockAgent Python API.

Startup sequence (lifespan)
---------------------------
1. Calendar first-run: if data/nse_holidays.json doesn't exist, fetch it now
   so the RL system has accurate holiday data before anything else runs.
2. RL self-heal (background thread): for each configured ticker —
     a. If no prediction envelope exists for this month → generate_forecast()
     b. If feedback entries are missing for past trading days → backfill reviews
   This makes every fresh deployment fully self-bootstrapping.
3. BackgroundScheduler start: registers the 3 recurring jobs:
     - Daily RL review       (weekdays 4:30 pm IST)
     - Monthly forecast      (1st of month 9:00 am IST)
     - Dec 31 calendar update (Dec 31 11:00 pm IST)

Shutdown: BackgroundScheduler stopped cleanly.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import pathlib
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

_ROOT = pathlib.Path(__file__).parent.parent.parent
_SRC  = _ROOT / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.api.routes.analyse import router as analyse_router
from services.api.routes.history import router as history_router
from services.api.routes.stream import router as stream_router
from services.api.routes.ui_data import router as ui_router
from services.api.routes.scheduler_api import router as scheduler_router
from services.api.routes.prompts import router as prompts_router
from services.api.routes.analytics import router as analytics_router

_IST = timezone(timedelta(hours=5, minutes=30))


class _ISTFormatter(logging.Formatter):
    """Formats log timestamps in IST (UTC+5:30) with full date."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=_IST)
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")


logging.basicConfig(level=logging.INFO)
_ist_fmt = _ISTFormatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s")
for _h in logging.root.handlers:
    _h.setFormatter(_ist_fmt)

logger = logging.getLogger(__name__)

# Register in-memory ring buffer handler so all log records are capturable via /ui/logs
from services.api.log_buffer import handler as _ring_handler
logging.getLogger().addHandler(_ring_handler)

# ---------------------------------------------------------------------------
# Scheduler singleton
# ---------------------------------------------------------------------------

_scheduler_instance = None

def _get_scheduler():
    global _scheduler_instance
    if _scheduler_instance is None:
        from services.scheduler.python.scheduler import AutomobileScheduler
        _scheduler_instance = AutomobileScheduler()
    return _scheduler_instance


# ---------------------------------------------------------------------------
# RL self-heal — runs in a background thread so startup isn't blocked
# ---------------------------------------------------------------------------

def _self_heal_rl() -> None:
    """
    Check RL state for each ticker and fill in whatever is missing:
      - No prediction envelope for this month → run generate_forecast
      - Missing feedback entries for past trading days → run daily_review backfill

    Called once on server startup in a daemon thread.
    All errors are caught and logged — never crashes the server.
    """
    import time
    time.sleep(10)   # Let uvicorn finish binding and log its startup banner first

    try:
        from core.config import settings
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        from core.intelligence.rl.nse_calendar import is_trading_day
        from core.intelligence.rl.workflows.generate_forecast import generate_forecast
        from core.intelligence.rl.workflows.daily_review import run_daily_review
    except Exception as exc:
        logger.warning("[startup] RL imports failed — self-heal skipped: %s", exc)
        return

    from services.api.log_buffer import get_active_tickers
    today = date.today()
    month_start = today.replace(day=1)

    for ticker in get_active_tickers():
        try:
            store    = PredictionStore(ticker, sector="automobile")
            cycle_id = store.current_cycle_id()

            # ── Step a: ensure forecast envelope exists ───────────────────
            envelope = store.load_envelope(cycle_id)
            if envelope is None:
                logger.info(
                    "[startup] No envelope for %s %s — generating (this takes ~2 min)…",
                    ticker, cycle_id,
                )
                try:
                    import time as _t
                    _t.sleep(3)   # brief stagger so yfinance isn't burst-hit for 5 tickers at once
                    envelope = generate_forecast(ticker)
                    logger.info(
                        "[startup] Envelope generated: %s horizon=%dd base=₹%.2f",
                        ticker, len(envelope.daily_forecasts), envelope.base_close,
                    )
                except Exception as exc:
                    logger.error("[startup] generate_forecast failed for %s: %s", ticker, exc)
                    continue   # Can't backfill without an envelope

            # ── Step b: backfill missing daily reviews ────────────────────
            fb_log = store.load_feedback_log(cycle_id)
            reviewed_dates = {e.date for e in (fb_log.entries if fb_log else [])}

            missing: list[date] = []
            d = month_start
            while d < today:
                if is_trading_day(d) and d.isoformat() not in reviewed_dates:
                    missing.append(d)
                d += timedelta(days=1)

            if missing:
                logger.info(
                    "[startup] Backfilling %d missing trading days for %s: %s … %s",
                    len(missing), ticker, missing[0].isoformat(), missing[-1].isoformat(),
                )
                for review_date in missing:
                    try:
                        summary = run_daily_review(ticker, review_date)
                        logger.info(
                            "[startup] Backfill %s %s — status=%s direction=%s",
                            ticker, review_date,
                            summary.get("status"), summary.get("direction_correct"),
                        )
                    except Exception as exc:
                        logger.error(
                            "[startup] Backfill FAILED %s %s: %s", ticker, review_date, exc
                        )
            else:
                logger.info("[startup] %s — feedback log up to date (%d entries)", ticker, len(reviewed_dates))

        except Exception as exc:
            logger.error("[startup] Self-heal FAILED for %s: %s", ticker, exc, exc_info=True)

    logger.info("[startup] RL self-heal complete")


# ---------------------------------------------------------------------------
# Volume / data directory check — run once at startup
# ---------------------------------------------------------------------------

def _log_volume_check() -> None:
    """
    Log the absolute path of data/ and the state of managed_tickers.json.
    Confirms whether the Railway Volume is correctly mounted at /app/data.
    """
    import os, json as _json
    data_dir = pathlib.Path("data").resolve()
    mt_path  = pathlib.Path("data/managed_tickers.json").resolve()

    is_mount = os.path.ismount(str(data_dir))
    logger.info("[startup] data/ abs path  : %s", data_dir)
    logger.info("[startup] volume mounted  : %s  (os.path.ismount)", is_mount)

    if mt_path.exists():
        try:
            raw = _json.loads(mt_path.read_text(encoding="utf-8"))
            syms = [t.get("sym") for t in raw] if isinstance(raw, list) else []
            logger.info(
                "[startup] managed_tickers.json EXISTS — %d tickers on volume: %s",
                len(syms), syms,
            )
        except Exception as exc:
            logger.warning("[startup] managed_tickers.json unreadable: %s", exc)
    else:
        logger.warning(
            "[startup] managed_tickers.json NOT found at %s — "
            "will bootstrap from SCHEDULER_TICKERS on first load. "
            "Volume gap if this is not the very first deploy.",
            mt_path,
        )


# ---------------------------------------------------------------------------
# Calendar first-run
# ---------------------------------------------------------------------------

def _ensure_calendar_file() -> None:
    """
    If data/nse_holidays.json doesn't exist yet, fetch it now so the RL
    system starts with accurate holiday data rather than only the hardcoded fallback.
    Non-fatal — hardcoded holidays are always the safety net.
    """
    holiday_file = _ROOT / "data" / "nse_holidays.json"
    if holiday_file.exists():
        return
    logger.info("[startup] data/nse_holidays.json not found — running first-time calendar fetch…")
    try:
        from core.intelligence.rl.calendar_updater import update_calendar
        result = update_calendar()
        logger.info("[startup] Calendar file created with %d years: %s", len(result), list(result.keys()))
    except Exception as exc:
        logger.warning("[startup] Calendar fetch failed (using hardcoded fallback): %s", exc)


# ---------------------------------------------------------------------------
# Lifespan — startup + shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("[startup] === StockAgent startup sequence ===")

    # 0. Volume / data directory verification
    _log_volume_check()

    # 1. Calendar file (sync, fast — just a file check + possible HTTP call)
    _ensure_calendar_file()

    # 2. RL self-heal (heavy — 9-agent pipeline per ticker)
    #    Run in a daemon thread so the server accepts requests immediately.
    heal_thread = threading.Thread(target=_self_heal_rl, name="rl-self-heal", daemon=True)
    heal_thread.start()
    logger.info("[startup] RL self-heal thread started (runs in background)")

    # 3. Background scheduler
    try:
        _get_scheduler().start()
    except Exception as exc:
        logger.warning("[startup] Scheduler failed to start (non-fatal): %s", exc)

    logger.info("[startup] === Startup complete — accepting requests ===")

    yield  # Server is running here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("[shutdown] Stopping scheduler…")
    try:
        _get_scheduler().stop()
    except Exception as exc:
        logger.warning("[shutdown] Scheduler stop error (non-fatal): %s", exc)
    logger.info("[shutdown] Clean shutdown complete")


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
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Frontend is same-origin; broad allow for API clients
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(analyse_router,   tags=["Analysis"])
app.include_router(history_router,   tags=["History"])
app.include_router(stream_router,    tags=["Streaming"])
app.include_router(ui_router,        tags=["UI"])
app.include_router(scheduler_router, tags=["Scheduler"])
app.include_router(prompts_router,   tags=["Prompts"])
app.include_router(analytics_router, tags=["Analytics"])


@app.get("/", tags=["UI"], include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/index.html")


@app.get("/health", tags=["Health"])
async def health() -> dict:
    from datetime import datetime, timezone
    return {
        "status":    "ok",
        "service":   "StockAgent Python API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/tickers", tags=["Meta"])
async def list_tickers() -> dict:
    from core.config import settings
    return {"tickers": getattr(settings, "SCHEDULER_TICKERS", [])}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

_FRONTEND_DIR = _ROOT / "frontend" / "prototypes"
if _FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning("[server] Frontend not found at %s — /app not mounted", _FRONTEND_DIR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.api.server:app", host="0.0.0.0", port=8001, reload=True)
