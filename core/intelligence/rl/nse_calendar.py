"""
core/intelligence/rl/nse_calendar.py
=====================================
NSE trading-day calendar.

Public functions
----------------
    is_trading_day(d)          → bool
    trading_days_ago(ref, n)   → date   (ref minus N trading days)
    trading_dates(start, end)  → list[date]
    next_trading_day(d)        → date
    reload_holidays()          → None   (re-reads data/nse_holidays.json — called after Dec 31 update)

Holiday source priority
-----------------------
1. data/nse_holidays.json  — written by calendar_updater.py every Dec 31
   Format: {"2025": ["2025-01-26", ...], "2026": [...], "2027": [...]}
2. Hardcoded fallback below — always present so the system works even if the
   file doesn't exist or the update job hasn't run yet.

Hardcoded values cover 2025 and 2026 (preliminary).
The Dec 31 auto-update job fills in accurate dates for the next year.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Path where calendar_updater.py writes fetched holidays
_HOLIDAY_FILE = Path("data/nse_holidays.json")

# ── Hardcoded fallback (2025 + 2026 preliminary) ────────────────────────────
_HARDCODED_HOLIDAYS: frozenset[date] = frozenset({
    # 2025
    date(2025,  1, 26),   # Republic Day
    date(2025,  2, 26),   # Maha Shivratri
    date(2025,  3, 14),   # Holi
    date(2025,  3, 31),   # Id-Ul-Fitr (Ramadan Eid)
    date(2025,  4, 10),   # Shri Mahavir Jayanti
    date(2025,  4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2025,  4, 18),   # Good Friday
    date(2025,  5,  1),   # Maharashtra Day
    date(2025,  8, 15),   # Independence Day
    date(2025,  8, 27),   # Ganesh Chaturthi
    date(2025, 10,  2),   # Mahatma Gandhi Jayanti / Dussehra
    date(2025, 10, 20),   # Diwali Laxmi Pujan
    date(2025, 10, 21),   # Diwali Balipratipada
    date(2025, 11,  5),   # Prakash Gurpurb Sri Guru Nanak Dev Ji
    date(2025, 12, 25),   # Christmas
    # 2026 (preliminary — updated by calendar_updater on Dec 31 2025)
    date(2026,  1, 26),   # Republic Day
    date(2026,  3,  4),   # Maha Shivratri (approx)
    date(2026,  3, 20),   # Holi (approx)
    date(2026,  4,  3),   # Good Friday (approx)
    date(2026,  4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026,  5,  1),   # Maharashtra Day
    date(2026,  8, 15),   # Independence Day
    date(2026, 10,  2),   # Mahatma Gandhi Jayanti
    date(2026, 12, 25),   # Christmas
})


def _load_from_file() -> frozenset[date]:
    """
    Load holidays from data/nse_holidays.json.
    Returns empty frozenset if file doesn't exist or is malformed.
    """
    if not _HOLIDAY_FILE.exists():
        return frozenset()
    try:
        raw: dict[str, list[str]] = json.loads(_HOLIDAY_FILE.read_text(encoding="utf-8"))
        holidays: set[date] = set()
        for year_str, date_list in raw.items():
            for ds in date_list:
                try:
                    holidays.add(date.fromisoformat(ds))
                except ValueError:
                    logger.debug("[nse_calendar] Skipping malformed date in file: %r", ds)
        logger.info("[nse_calendar] Loaded %d holidays from %s", len(holidays), _HOLIDAY_FILE)
        return frozenset(holidays)
    except Exception as exc:
        logger.warning("[nse_calendar] Could not read %s: %s — using hardcoded fallback", _HOLIDAY_FILE, exc)
        return frozenset()


def _build_holiday_set() -> frozenset[date]:
    """Merge hardcoded fallback with file-based holidays (file wins on overlap)."""
    file_holidays = _load_from_file()
    if file_holidays:
        # File exists: use file for years it covers, hardcoded for any year not in file
        file_years = {d.year for d in file_holidays}
        extra = frozenset(d for d in _HARDCODED_HOLIDAYS if d.year not in file_years)
        merged = file_holidays | extra
        logger.debug("[nse_calendar] Holiday set: %d from file + %d hardcoded fill-in", len(file_holidays), len(extra))
        return merged
    # No file: use hardcoded only
    return _HARDCODED_HOLIDAYS


# Module-level holiday set — initialised once at import
_NSE_HOLIDAYS: frozenset[date] = _build_holiday_set()


def reload_holidays() -> None:
    """
    Re-read data/nse_holidays.json and rebuild the in-memory set.
    Called by calendar_updater.py after writing updated holiday data.
    """
    global _NSE_HOLIDAYS
    _NSE_HOLIDAYS = _build_holiday_set()
    logger.info("[nse_calendar] Holiday set reloaded — %d holidays active", len(_NSE_HOLIDAYS))


# ── Public API ───────────────────────────────────────────────────────────────

def is_trading_day(d: date) -> bool:
    """Return True if d is an NSE trading day (Mon–Fri, not a holiday)."""
    return d.weekday() < 5 and d not in _NSE_HOLIDAYS


def trading_days_ago(reference: date, n: int) -> date:
    """
    Return the calendar date exactly N NSE trading days before reference.
    Skips weekends and NSE holidays.
    """
    count = 0
    d = reference
    while count < n:
        d -= timedelta(days=1)
        if is_trading_day(d):
            count += 1
    return d


def trading_dates(start: date, end: date) -> list[date]:
    """Return all NSE trading days in [start, end] inclusive, ascending."""
    result: list[date] = []
    d = start
    while d <= end:
        if is_trading_day(d):
            result.append(d)
        d += timedelta(days=1)
    return result


def next_trading_day(d: date) -> date:
    """Return the next NSE trading day strictly after d."""
    candidate = d + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate
