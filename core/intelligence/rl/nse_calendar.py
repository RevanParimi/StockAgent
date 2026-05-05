"""
core/intelligence/rl/nse_calendar.py
=====================================
Minimal NSE trading-day calendar.

Provides two public functions used by the RL system wherever rolling windows
of "trading days" need to be computed accurately:

    is_trading_day(d)        → bool
    trading_days_ago(ref, n) → date   (ref minus N trading days)
    trading_dates(start, end) → list[date]  (all trading days in [start, end])

NSE holidays for 2025 and 2026 are hardcoded below. Update _NSE_HOLIDAYS
each year by checking the official NSE circular:
  https://www.nseindia.com/resources/exchange-communication-holidays

Only includes equity segment holidays. Muhurat trading sessions are NOT
included (treated as normal trading days for RL purposes).
"""

from __future__ import annotations

from datetime import date, timedelta

# ── NSE equity market holidays ──────────────────────────────────────────────
# Format: date(YYYY, MM, DD)
# Source: NSE holiday circulars for 2025 and 2026
_NSE_HOLIDAYS: frozenset[date] = frozenset({
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
    # 2026 (preliminary — update when NSE releases official circular)
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


def is_trading_day(d: date) -> bool:
    """Return True if d is an NSE trading day (Mon–Fri excluding NSE holidays)."""
    return d.weekday() < 5 and d not in _NSE_HOLIDAYS


def trading_days_ago(reference: date, n: int) -> date:
    """
    Return the calendar date that is exactly N NSE trading days before reference.
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
    result = []
    d = start
    while d <= end:
        if is_trading_day(d):
            result.append(d)
        d += timedelta(days=1)
    return result


def next_trading_day(d: date) -> date:
    """Return the next NSE trading day after d."""
    candidate = d + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate
