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
import calendar as _cal
from datetime import date, datetime, time as _time, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# India Standard Time — fixed UTC+5:30 (India observes no DST).
IST = timezone(timedelta(hours=5, minutes=30))

# NSE equity-market session boundaries (IST).
_PRE_OPEN_START = _time(9, 0)    # pre-open auction begins
_MARKET_OPEN    = _time(9, 15)   # continuous trading begins
_MARKET_CLOSE   = _time(15, 30)  # continuous trading ends

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
    # 2026 — official NSE trading-holiday circular (AUD-023: the earlier
    # preliminary guesses marked real sessions Mar 4 / Mar 20 as holidays and
    # missed Sep 14, Oct 20, Nov 10, Nov 24 entirely).
    date(2026,  1, 15),   # Maharashtra municipal elections
    date(2026,  1, 26),   # Republic Day
    date(2026,  3,  3),   # Holi
    date(2026,  3, 26),   # Shri Ram Navami
    date(2026,  3, 31),   # Shri Mahavir Jayanti
    date(2026,  4,  3),   # Good Friday
    date(2026,  4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026,  5,  1),   # Maharashtra Day
    date(2026,  5, 28),   # Bakri Id
    date(2026,  6, 26),   # Muharram
    date(2026,  8, 15),   # Independence Day (Saturday)
    date(2026,  9, 14),   # Ganesh Chaturthi
    date(2026, 10,  2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),   # Dussehra
    date(2026, 11, 10),   # Diwali Balipratipada
    date(2026, 11, 24),   # Prakash Gurpurb Sri Guru Nanak Dev
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
            if year_str.startswith("_") or not isinstance(date_list, list):
                continue    # metadata / malformed entries are not holiday years
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
    """UNION of the hardcoded fallback and the file (AUD-023).

    Not file-wins-per-year: a file year built by the yfinance layer only
    contains holidays up to the day it was written, so letting it replace the
    hardcoded year silently DROPS every future holiday. Union keeps both.
    Tradeoff: if the exchange ever cancels a hardcoded holiday, the union
    keeps the stale date until the hardcoded list is corrected — a rarer and
    safer failure (one skipped session) than trading-day logic running on
    real holidays."""
    merged = _HARDCODED_HOLIDAYS | _load_from_file()
    logger.debug("[nse_calendar] Holiday set: %d dates (hardcoded ∪ file)", len(merged))
    return merged


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


def trading_days_after(reference: date, n: int) -> date:
    """
    Return the calendar date exactly N NSE trading days after reference.
    Skips weekends and NSE holidays. n=0 returns reference unchanged.

    The forward twin of trading_days_ago — the verification layer needs to ask
    "what date is +30 trading days from this advice?" and approximating with
    calendar days would misdate every horizon across a holiday.
    """
    if n <= 0:
        return reference
    count = 0
    d = reference
    while count < n:
        d += timedelta(days=1)
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


def _last_trading_day_on_or_before(d: date) -> date:
    """Most recent NSE trading day on or before d (d itself if it is one)."""
    cur = d
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


# ── Intraday market session (IST-aware) ──────────────────────────────────────

def now_ist() -> datetime:
    """Current wall-clock time in IST (timezone-aware)."""
    return datetime.now(IST)


def market_session(now: datetime | None = None) -> dict:
    """
    Resolve the NSE equity-market session state for a given moment, in IST.

    This is the time-aware companion to ``is_trading_day`` (which only knows the
    date). Use it anywhere the assistant must reason about whether the market is
    actually trading *right now* — not merely whether today is a trading day.

    Parameters
    ----------
    now : datetime | None
        The moment to evaluate. ``None`` → current IST time. A naive datetime is
        interpreted as IST; an aware datetime is converted to IST. Accepting an
        explicit ``now`` keeps this function deterministic and unit-testable.

    Returns
    -------
    dict with keys:
        state           : "HOLIDAY" | "PRE_MARKET" | "PRE_OPEN" | "OPEN" | "CLOSED"
        is_live         : bool   — True only during the continuous OPEN session
        date            : date   — the IST calendar date evaluated
        last_close_day  : date   — the session whose close is the latest *settled*
                                   price (today if already closed; else the prior
                                   trading day)
        opens_at        : "09:15 IST"   (informational)
        closes_at       : "15:30 IST"   (informational)

    State definitions
    -----------------
        HOLIDAY     today is a weekend / NSE holiday — market does not trade
        PRE_MARKET  trading day, before 09:00 IST — not yet in pre-open
        PRE_OPEN    trading day, 09:00–09:15 IST — pre-open auction window
        OPEN        trading day, 09:15–15:30 IST — continuous trading (live)
        CLOSED      trading day, after 15:30 IST — session done for the day
    """
    if now is None:
        now = now_ist()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    d = now.date()
    t = now.time()

    opens_at, closes_at = "09:15 IST", "15:30 IST"

    if not is_trading_day(d):
        return {
            "state": "HOLIDAY",
            "is_live": False,
            "date": d,
            "last_close_day": _last_trading_day_on_or_before(d),
            "opens_at": opens_at,
            "closes_at": closes_at,
        }

    prev_td = trading_days_ago(d, 1)  # strictly-before trading day

    if t < _PRE_OPEN_START:
        state, is_live, last_close = "PRE_MARKET", False, prev_td
    elif t < _MARKET_OPEN:
        state, is_live, last_close = "PRE_OPEN", False, prev_td
    elif t < _MARKET_CLOSE:
        state, is_live, last_close = "OPEN", True, prev_td
    else:
        state, is_live, last_close = "CLOSED", False, d

    return {
        "state": state,
        "is_live": is_live,
        "date": d,
        "last_close_day": last_close,
        "opens_at": opens_at,
        "closes_at": closes_at,
    }


# ── F&O Monthly Expiry Calendar ──────────────────────────────────────────────

def fno_expiry_date(year: int, month: int) -> date:
    """Last Thursday of month; if NSE holiday, walks back to Wednesday, then Tuesday."""
    last_day = _cal.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != 3:   # 3 = Thursday
        d -= timedelta(days=1)
    # If NSE holiday, step back day by day until a trading day (max 3 steps)
    for _ in range(3):
        if is_trading_day(d):
            break
        d -= timedelta(days=1)
    return d


def is_fno_expiry_day(d: date) -> bool:
    """Return True if d is the monthly F&O expiry date."""
    return d == fno_expiry_date(d.year, d.month)


def is_fno_expiry_week(d: date) -> bool:
    """True if d is within 5 trading days of (and including) monthly expiry."""
    expiry = fno_expiry_date(d.year, d.month)
    if d > expiry:
        return False
    count, cur = 0, d
    while cur <= expiry:
        if is_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count <= 5


def days_to_fno_expiry(d: date) -> int | None:
    """Trading days to next monthly expiry. None if d is past expiry for this month."""
    expiry = fno_expiry_date(d.year, d.month)
    if d > expiry:
        return None
    count, cur = 0, d
    while cur < expiry:
        if is_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count
