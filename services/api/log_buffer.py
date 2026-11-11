"""
services/api/log_buffer.py
==========================
Shared in-memory ring buffer for live server-log streaming.

Imported by:
  - services/api/server.py            → registers _handler at startup
  - services/api/routes/ui_data.py    → exposes GET /ui/logs and GET /ui/logs/stream,
                                        to the owner or the machine key only (FIX-007)

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filelock import FileLock

from core.utils.atomic_io import atomic_write_text

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
_IST = timezone(timedelta(hours=5, minutes=30))


def _make_entry(record: logging.LogRecord) -> dict:
    return {
        "ts":    datetime.fromtimestamp(record.created, tz=_IST).strftime("%Y-%m-%d %H:%M:%S IST"),
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


_log = logging.getLogger(__name__)


def load_managed_tickers() -> list[dict]:
    """
    Return the managed ticker list from data/managed_tickers.json.
    If the file doesn't exist, seeds it from settings.SCHEDULER_TICKERS.
    """
    abs_path = _MANAGED_TICKERS_PATH.resolve()
    if _MANAGED_TICKERS_PATH.exists():
        try:
            raw = json.loads(_MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                _log.debug(
                    "[managed_tickers] Read %d tickers from %s: %s",
                    len(raw), abs_path, [t.get("sym") for t in raw],
                )
                return raw
            _log.warning("[managed_tickers] %s is empty or malformed — bootstrapping", abs_path)
        except Exception as exc:
            _log.warning("[managed_tickers] Could not parse %s: %s — bootstrapping", abs_path, exc)
    else:
        _log.warning(
            "[managed_tickers] %s NOT FOUND — bootstrapping from SCHEDULER_TICKERS env var. "
            "If volume is mounted at /app/data this should only happen on first ever deploy.",
            abs_path,
        )

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
    _log.info(
        "[managed_tickers] Bootstrap seed: %d tickers from SCHEDULER_TICKERS: %s",
        len(default), [t["sym"] for t in default],
    )
    save_managed_tickers(default)
    return default


def save_managed_tickers(tickers: list[dict]) -> None:
    # Temp file + rename (FIX-028): a write cut short must never leave a torn
    # file, which load_managed_tickers would replace with the five-ticker seed.
    atomic_write_text(_MANAGED_TICKERS_PATH, json.dumps(tickers, indent=2))
    abs_path = _MANAGED_TICKERS_PATH.resolve()
    _log.info(
        "[managed_tickers] Written %d tickers to %s: %s",
        len(tickers), abs_path, [t.get("sym") for t in tickers],
    )


_MANAGED_LOCKS: dict[str, FileLock] = {}
_MANAGED_LOCKS_GUARD = threading.Lock()


def managed_tickers_lock() -> FileLock:
    """
    The lock promotion's reads and writes of the managed list hold (FIX-028),
    one instance per file so a holder may take it again. The API's promotions
    and demotions run beside the scheduler's pipeline; without it, two writers
    that read the same list each save their own copy, and one change is lost.
    The owner's dashboard routes (ui_data `/tickers/managed`) do not take it.
    """
    path = str(_MANAGED_TICKERS_PATH.resolve()) + ".lock"
    _MANAGED_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _MANAGED_LOCKS_GUARD:
        lock = _MANAGED_LOCKS.get(path)
        if lock is None:
            lock = _MANAGED_LOCKS[path] = FileLock(path, timeout=30)
    return lock


def read_managed_tickers() -> list[dict] | None:
    """
    The managed list as stored, or None when there is no file or it cannot be
    read as a list (FIX-028). Unlike load_managed_tickers it never seeds or
    replaces the file, so a caller that only narrows the list cannot create one.
    """
    try:
        raw = json.loads(_MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _log.warning("[managed_tickers] %s unreadable: %s", _MANAGED_TICKERS_PATH, exc)
        return None
    if not isinstance(raw, list):
        _log.warning("[managed_tickers] %s is not a list", _MANAGED_TICKERS_PATH)
        return None
    return raw


def managed_symbols() -> set[str]:
    """
    Every managed symbol, enabled or not, uppercased (FIX-002: the ticker
    resolver's short cut). Read-only: unlike load_managed_tickers, a missing
    or unreadable file gives an empty set and is never seeded, so resolving a
    ticker cannot write the managed list.
    """
    try:
        raw = json.loads(_MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as exc:
        # The resolver then sends managed tickers to the LLM again: say so.
        _log.warning("[managed_tickers] %s unreadable for symbols: %s", _MANAGED_TICKERS_PATH, exc)
        return set()
    if not isinstance(raw, list):
        _log.warning("[managed_tickers] %s is not a list: no managed symbols", _MANAGED_TICKERS_PATH)
        return set()
    return {
        str(t.get("sym") or "").strip().upper()
        for t in raw
        if isinstance(t, dict) and str(t.get("sym") or "").strip()
    }


def managed_sectors() -> dict[str, str]:
    """
    {symbol: sector} for every managed ticker, enabled or not, read-only like
    managed_symbols. The sector is read as the daily review and the monthly
    forecast read it (get_active_tickers_with_sector: `sector`, default
    "automobile"), so it is the key a managed stock's predictions are written
    under; promote_symbol keeps it when the stock is promoted again (PR-004).
    """
    try:
        raw = json.loads(_MANAGED_TICKERS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        _log.warning("[managed_tickers] %s unreadable for sectors: %s", _MANAGED_TICKERS_PATH, exc)
        return {}
    if not isinstance(raw, list):
        _log.warning("[managed_tickers] %s is not a list: no managed sectors", _MANAGED_TICKERS_PATH)
        return {}
    return {
        str(t.get("sym") or "").strip().upper(): str(t.get("sector", "automobile") or "")
        for t in raw
        if isinstance(t, dict) and str(t.get("sym") or "").strip()
    }


def get_active_tickers() -> list[str]:
    """Return only the enabled ticker symbols from the managed list."""
    return [t["sym"] for t in load_managed_tickers() if t.get("enabled", True)]


def get_active_tickers_with_sector() -> list[dict]:
    """
    Return active tickers with sector metadata.
    Format: [{"sym": "MARUTI", "sector": "automobile"}, ...]
    Used by scheduler to pass correct sector to daily_review and generate_forecast.
    """
    return [
        {
            "sym": t["sym"],
            "sector": t.get("sector", "automobile"),
            "cadence": t.get("cadence", "daily"),
        }
        for t in load_managed_tickers()
        if t.get("enabled", True)
    ]


def get_disabled_tickers() -> list[str]:
    """Managed tickers switched off on purpose (enabled: false). The daily
    review reports them as excluded, not as required work (SA-004)."""
    return [t["sym"] for t in load_managed_tickers() if not t.get("enabled", True)]
