"""
core/portfolio/narrative_cache.py
=================================
M0 (spec 2026-07-26 §4.4): day-scoped cache of ticker-level narrator output,
keyed by verdict context — the same (symbol, verdict, triggers, notes, regime,
date) produces the same narration for every user, so the LLM runs once per
context per day instead of once per user-holding. File-backed on the volume
(atomic writes) with an in-process dict in front. Failures degrade to a miss.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

_CACHE_PATH = Path("data/narrative_cache.json")
_mem: dict[str, str] = {}
_KEEP_DAYS = 2
_IST = ZoneInfo("Asia/Kolkata")


def ist_today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def context_key(symbol: str, verdict: str, triggers: list[str],
                notes: list[str], regime_label: str, ist_date: str) -> str:
    blob = "|".join([symbol, verdict, ",".join(sorted(triggers)),
                     ",".join(sorted(notes)), regime_label, ist_date])
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _load_disk() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key: str) -> str | None:
    if key in _mem:
        return _mem[key]
    day_map = _load_disk().get(ist_today(), {})
    if key in day_map:
        _mem[key] = day_map[key]
        return day_map[key]
    return None


def put(key: str, text: str) -> None:
    _mem[key] = text
    try:
        disk = _load_disk()
        today = ist_today()
        disk.setdefault(today, {})[key] = text
        keep = sorted(disk.keys())[-_KEEP_DAYS:]
        disk = {d: v for d, v in disk.items() if d in keep}
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(_CACHE_PATH, disk)
    except Exception as exc:  # cache write failure must never block narration
        logger.warning("[narrative_cache] persist failed (non-fatal): %s", exc)
