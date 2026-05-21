"""
services/data/stores/api_usage.py
==================================
Persistent monthly call counter for external search APIs.

Counters are stored in logs/api_usage.json and reset automatically
when the calendar month changes. Thread-safe via a lock.

Per-run events are appended to logs/api_usage_events.jsonl — each record
contains this-run call counts + monthly totals, ready for UI / Arize / Helicone.

Usage
-----
    from services.data.stores.api_usage import record_call, get_usage, snapshot_usage, log_run_api_usage

    before = snapshot_usage()          # capture before agents run
    record_call("serper")              # called automatically inside search_serper()
    record_call("tavily")
    log_run_api_usage(run_id, ticker, before)   # appends JSONL event at run end

    usage = get_usage()
    # {"month": "2026-04", "serper": {"calls": 12, "limit": 2500, "remaining": 2488},
    #  "tavily": {"calls": 3, "limit": 1000, "remaining": 997}}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(os.getenv("LOGS_DIR", "logs"))
_USAGE_FILE = _LOGS_DIR / "api_usage.json"
_EVENTS_FILE = _LOGS_DIR / "api_usage_events.jsonl"
_lock = threading.Lock()

# Monthly limits (override via env vars). 0 = free / unlimited — track volume only.
_LIMITS: dict[str, int] = {
    "serper":    int(os.getenv("SERPER_MONTHLY_LIMIT", "2500")),
    "tavily":    int(os.getenv("TAVILY_MONTHLY_LIMIT", "1000")),
    "nse_india": 0,   # free — NSE website scraper, no documented limit
    "rss":       0,   # free — feedparser RSS, no limit
}

ApiName = Literal["serper", "tavily", "nse_india", "rss"]


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load() -> dict:
    if _USAGE_FILE.exists():
        try:
            return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[api_usage] Failed to load %s: %s — resetting monthly counters",
                _USAGE_FILE, exc,
            )
    return {}


def _save(data: dict) -> None:
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[api_usage] Failed to save usage file: %s", exc)


def _ensure_month(data: dict, month: str) -> dict:
    """Reset counters if the stored month differs from the current month."""
    if data.get("month") != month:
        data = {"month": month}
    for api in _LIMITS:
        data.setdefault(api, {"calls": 0})
    data["month"] = month
    return data


def record_call(api: ApiName, count: int = 1) -> None:
    """Increment the call counter for the given API. Thread-safe."""
    month = _current_month()
    with _lock:
        data = _load()
        data = _ensure_month(data, month)
        data[api]["calls"] = data[api].get("calls", 0) + count
        _save(data)


def get_usage() -> dict:
    """
    Return current usage for all tracked APIs.

    Returns
    -------
    dict with keys: month, serper, tavily
    Each API entry: {calls, limit, remaining, pct_used}
    """
    month = _current_month()
    with _lock:
        data = _load()
        data = _ensure_month(data, month)

    result: dict = {"month": month}
    for api, limit in _LIMITS.items():
        calls = data[api].get("calls", 0)
        result[api] = {
            "calls":     calls,
            "limit":     limit,
            "remaining": max(0, limit - calls),
            "pct_used":  round(calls / limit * 100, 1) if limit else 0.0,
        }
    return result


def snapshot_usage() -> dict[str, int]:
    """
    Capture current raw call counts for all APIs.
    Pass the result to log_run_api_usage() after the run to compute per-run deltas.

    Returns {api_name: calls_so_far_this_month}
    """
    usage = get_usage()
    return {api: usage[api]["calls"] for api in _LIMITS}


def log_run_api_usage(run_id: str, ticker: str, before: dict[str, int]) -> None:
    """
    Append a structured JSONL record to logs/api_usage_events.jsonl.

    Parameters
    ----------
    run_id  : str              pipeline run identifier
    ticker  : str              stock ticker analysed
    before  : dict[str, int]   snapshot from snapshot_usage() taken before the run
    """
    usage = get_usage()
    record: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "ticker": ticker,
        "month": usage["month"],
    }
    for api in _LIMITS:
        calls_after = usage[api]["calls"]
        calls_before = before.get(api, 0)
        record[api] = {
            "this_run":  max(0, calls_after - calls_before),
            "monthly":   usage[api],
        }

    _EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _lock:
            with open(_EVENTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning("[api_usage] Failed to write events log: %s", exc)

    serper = usage["serper"]
    tavily = usage["tavily"]
    nse    = usage.get("nse_india", {"calls": 0})
    rss    = usage.get("rss", {"calls": 0})
    logger.info(
        "[api_usage] %s  |  Serper: %d/%d (%.1f%%)  |  Tavily: %d/%d (%.1f%%)  "
        "|  NseIndia: %d (free)  |  RSS: %d (free)",
        usage["month"],
        serper["calls"], serper["limit"], serper["pct_used"],
        tavily["calls"], tavily["limit"], tavily["pct_used"],
        nse["calls"], rss["calls"],
    )


def log_usage_summary() -> None:
    """Backwards-compatible alias — logs monthly totals only (no per-run delta)."""
    log_run_api_usage(run_id="", ticker="", before={})
