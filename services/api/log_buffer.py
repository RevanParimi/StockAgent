"""
services/api/log_buffer.py
==========================
Shared in-memory ring buffer for live server-log streaming.

Imported by:
  - services/api/server.py            → registers _handler at startup
  - services/api/routes/ui_data.py    → exposes GET /ui/logs and GET /ui/logs/stream

Thread model
------------
The logging framework calls handler.emit() from whichever thread logs the message
(uvicorn workers, scheduler thread, self-heal daemon thread, etc.).
We use threading.Queue per SSE subscriber so emit() can do a lock-free put_nowait()
from any thread, and the asyncio SSE generator reads it via asyncio.to_thread().
"""

from __future__ import annotations

import collections
import json
import logging
import queue as _tq
import threading
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ring buffer — last 1 000 log records
# ---------------------------------------------------------------------------

BUFFER_SIZE = 1_000
_BUFFER: collections.deque = collections.deque(maxlen=BUFFER_SIZE)
_BUFFER_LOCK = threading.Lock()

# Live SSE subscribers — each is a threading.Queue
_SUBSCRIBERS: list[_tq.Queue] = []
_SUB_LOCK = threading.Lock()

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}


def _make_entry(record: logging.LogRecord) -> dict:
    return {
        "ts":    datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S"),
        "level": record.levelname,
        "name":  record.name.split(".")[-1][:20],
        "msg":   record.getMessage(),
    }


class RingBufferHandler(logging.Handler):
    """Append every log record to the ring buffer and fan-out to SSE subscribers."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = _make_entry(record)
            with _BUFFER_LOCK:
                _BUFFER.append(entry)
            dead: list[_tq.Queue] = []
            with _SUB_LOCK:
                for q in _SUBSCRIBERS:
                    try:
                        q.put_nowait(entry)
                    except _tq.Full:
                        pass
                    except Exception:
                        dead.append(q)
                for q in dead:
                    try:
                        _SUBSCRIBERS.remove(q)
                    except ValueError:
                        pass
        except Exception:
            pass  # never raise from a logging handler


# Singleton handler — imported and attached in server.py
handler = RingBufferHandler()


def snapshot(level: str = "DEBUG", limit: int = 500) -> list[dict]:
    """Return the most-recent `limit` entries at or above `level`."""
    min_ord = _LEVEL_ORDER.get(level.upper(), 0)
    with _BUFFER_LOCK:
        entries = list(_BUFFER)
    filtered = [e for e in entries if _LEVEL_ORDER.get(e["level"], 0) >= min_ord]
    return filtered[-limit:]


def subscribe() -> _tq.Queue:
    """Create and register a new per-subscriber queue. Caller must unsubscribe."""
    q: _tq.Queue = _tq.Queue(maxsize=500)
    with _SUB_LOCK:
        _SUBSCRIBERS.append(q)
    return q


def unsubscribe(q: _tq.Queue) -> None:
    with _SUB_LOCK:
        try:
            _SUBSCRIBERS.remove(q)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Managed tickers helper — used by server.py self-heal and scheduler.py jobs
# ---------------------------------------------------------------------------

_MANAGED_TICKERS_PATH = Path("data/managed_tickers.json")

# NSE symbol → display name for common tickers
_KNOWN_NAMES: dict[str, str] = {
    "MARUTI":     "Maruti Suzuki India Ltd",
    "TATAMOTORS": "Tata Motors Ltd",
    "M&M":        "Mahindra & Mahindra Ltd",
    "BAJAJ-AUTO": "Bajaj Auto Ltd",
    "HEROMOTOCO": "Hero MotoCorp Ltd",
    "EICHERMOT":  "Eicher Motors Ltd",
    "TVSMOTORS":  "TVS Motor Company Ltd",
    "ASHOKLEY":   "Ashok Leyland Ltd",
    "HDFCBANK":   "HDFC Bank Ltd",
    "ICICIBANK":  "ICICI Bank Ltd",
    "SBIN":       "State Bank of India",
    "KOTAKBANK":  "Kotak Mahindra Bank Ltd",
    "AXISBANK":   "Axis Bank Ltd",
    "TCS":        "Tata Consultancy Services Ltd",
    "INFY":       "Infosys Ltd",
    "HCLTECH":    "HCL Technologies Ltd",
    "WIPRO":      "Wipro Ltd",
    "TECHM":      "Tech Mahindra Ltd",
    "ADANIGREEN": "Adani Green Energy Ltd",
    "TATAPOWER":  "Tata Power Company Ltd",
    "NTPC":       "NTPC Ltd",
    "RECLTD":     "REC Ltd",
    "JSWENERGY":  "JSW Energy Ltd",
}


def load_managed_tickers() -> list[dict]:
    """
    Return the managed ticker list from data/managed_tickers.json.
    If the file doesn't exist, seeds it from settings.SCHEDULER_TICKERS.
    """
    if _MANAGED_TICKERS_PATH.exists():
        try:
            raw = json.loads(_MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                return raw
        except Exception:
            pass

    # Bootstrap from settings
    try:
        from core.config import settings
        seed = settings.SCHEDULER_TICKERS
    except Exception:
        seed = ["MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO", "BAJAJ-AUTO"]

    default = [
        {
            "sym":     sym,
            "name":    _KNOWN_NAMES.get(sym, sym),
            "sector":  "automobile",
            "enabled": True,
        }
        for sym in seed
    ]
    save_managed_tickers(default)
    return default


def save_managed_tickers(tickers: list[dict]) -> None:
    _MANAGED_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MANAGED_TICKERS_PATH.write_text(json.dumps(tickers, indent=2), encoding="utf-8")


def get_active_tickers() -> list[str]:
    """Return only the enabled ticker symbols from the managed list."""
    return [t["sym"] for t in load_managed_tickers() if t.get("enabled", True)]
