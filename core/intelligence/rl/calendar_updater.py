"""
core/intelligence/rl/calendar_updater.py
=========================================
Fetches NSE equity market holidays for the coming year and writes them to
data/nse_holidays.json.  Called automatically on Dec 31 by the scheduler.

Three-layer fallback (each tried if the previous fails):
  Layer 1 — NSE holiday master API   (official, most accurate)
  Layer 2 — yfinance reverse-lookup  (find missing weekdays in past year's data)
  Layer 3 — Fixed Indian holidays    (only Republic Day, Independence Day etc.
                                      that never move; moveable feasts omitted
                                      with a warning to update manually)

After writing the file, calls nse_calendar.reload_holidays() so the live
process immediately uses the new data without a restart.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_HOLIDAY_FILE = Path("data/nse_holidays.json")

# ── Fixed Indian market holidays that NEVER change date ─────────────────────
# Moveable feasts (Holi, Eid, Diwali, etc.) are NOT included here because
# they shift each year — Layer 1 / Layer 2 handle them.
_FIXED_HOLIDAYS_MD: list[tuple[int, int]] = [
    (1, 26),   # Republic Day
    (4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    (5,  1),   # Maharashtra Day
    (8, 15),   # Independence Day
    (10, 2),   # Mahatma Gandhi Jayanti
    (12, 25),  # Christmas Day
]


# ---------------------------------------------------------------------------
# Layer 1 — NSE Holiday Master API
# ---------------------------------------------------------------------------

def _fetch_from_nse_api(year: int) -> list[date] | None:
    """
    Try NSE's public holiday-master JSON endpoint.
    Returns list of holiday dates or None if the request fails.

    NSE blocks automated requests without browser-like headers.
    We use a short timeout and treat any failure as non-fatal.
    """
    try:
        import requests
        url = "https://www.nseindia.com/api/holiday-master?type=trading"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.nseindia.com/",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # CM = Capital Market (equity segment)
        cm_holidays: list[dict] = data.get("CM", [])
        dates: list[date] = []
        for item in cm_holidays:
            raw = item.get("tradingDate", "")
            try:
                # Format from NSE: "09-Jan-2025"
                d = date.fromisoformat(
                    _normalize_nse_date(raw)
                )
                if d.year == year:
                    dates.append(d)
            except Exception:
                continue

        if dates:
            logger.info("[calendar_updater] NSE API: %d holidays found for %d", len(dates), year)
            return sorted(dates)

        logger.warning("[calendar_updater] NSE API returned 0 holidays for %d", year)
        return None

    except Exception as exc:
        logger.warning("[calendar_updater] NSE API failed: %s", exc)
        return None


def _normalize_nse_date(raw: str) -> str:
    """Convert '09-Jan-2025' or '2025-01-09' to ISO '2025-01-09'."""
    raw = raw.strip()
    if len(raw) == 10 and raw[4] == "-":
        return raw   # already ISO
    # Try "DD-Mon-YYYY"
    months = {
        "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
        "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12",
    }
    parts = raw.split("-")
    if len(parts) == 3 and len(parts[2]) == 4 and parts[1] in months:
        return f"{parts[2]}-{months[parts[1]]}-{parts[0].zfill(2)}"
    raise ValueError(f"Unknown date format from NSE: {raw!r}")


# ---------------------------------------------------------------------------
# Layer 2 — yfinance reverse-lookup (works for completed years)
# ---------------------------------------------------------------------------

def _fetch_from_yfinance(year: int) -> list[date] | None:
    """
    Download Nifty 50 (^NSEI) OHLCV for `year` and find weekdays with no data.
    Those missing weekdays are NSE holidays.

    Only works for past / in-progress years (yfinance can't see the future).
    Returns None if download fails or year is in the future.
    """
    today = date.today()
    if year > today.year:
        return None   # Can't look up a future year via yfinance

    try:
        import yfinance as yf
        start = f"{year}-01-01"
        # For current year: end = today; for past years: end = Dec 31
        end   = today.isoformat() if year == today.year else f"{year}-12-31"

        df = yf.download("^NSEI", start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            logger.warning("[calendar_updater] yfinance returned empty data for ^NSEI %d", year)
            return None

        trading_days: set[date] = set(d.date() for d in df.index)

        # All weekdays in the range
        all_weekdays: set[date] = set()
        d = date(year, 1, 1)
        end_date = today if year == today.year else date(year, 12, 31)
        while d <= end_date:
            if d.weekday() < 5:
                all_weekdays.add(d)
            d += timedelta(days=1)

        holidays = sorted(all_weekdays - trading_days)
        logger.info(
            "[calendar_updater] yfinance: %d missing weekdays (holidays) for %d",
            len(holidays), year,
        )
        return holidays if holidays else None

    except Exception as exc:
        logger.warning("[calendar_updater] yfinance lookup failed for %d: %s", year, exc)
        return None


# ---------------------------------------------------------------------------
# Layer 3 — Fixed holidays only (future years where neither above works)
# ---------------------------------------------------------------------------

def _generate_fixed_holidays(year: int) -> list[date]:
    """
    Return only the fixed-date Indian market holidays for `year`.
    Moveable feasts (Holi, Eid, Diwali, Shivratri, etc.) are NOT included
    because their dates change annually.

    Always logs a prominent warning so the operator knows manual review is needed.
    """
    fixed = [date(year, m, d) for m, d in _FIXED_HOLIDAYS_MD]
    logger.warning(
        "[calendar_updater] Using fixed-holidays-only fallback for %d. "
        "Moveable feasts (Holi, Eid, Diwali, Shivratri, Ganesh Chaturthi, Gurpurb) "
        "are NOT included. Update data/nse_holidays.json manually after NSE releases "
        "the official circular: https://www.nseindia.com/resources/exchange-communication-holidays",
        year,
    )
    return fixed


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_calendar(target_year: int | None = None) -> dict[str, list[str]]:
    """
    Fetch holidays for `target_year` (default: next calendar year) using the
    3-layer fallback chain, merge with existing file data, and write to disk.

    Also tries to verify / backfill the current year via yfinance.

    Returns the full holiday map that was written: {year_str: [iso_date, ...]}
    """
    today = date.today()
    if target_year is None:
        target_year = today.year + 1

    logger.info("[calendar_updater] Starting holiday update for year %d", target_year)

    # Load existing file data so we don't lose previously fetched years
    existing: dict[str, list[str]] = {}
    if _HOLIDAY_FILE.exists():
        try:
            existing = json.loads(_HOLIDAY_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[calendar_updater] Could not read existing file: %s", exc)

    # ── Fetch for target_year ────────────────────────────────────────────────
    holidays_for_year = (
        _fetch_from_nse_api(target_year)
        or _fetch_from_yfinance(target_year)
        or _generate_fixed_holidays(target_year)
    )
    existing[str(target_year)] = [d.isoformat() for d in holidays_for_year]
    logger.info(
        "[calendar_updater] %d holidays recorded for %d (via %s)",
        len(holidays_for_year), target_year,
        "NSE API" if _fetch_from_nse_api.__doc__ and len(holidays_for_year) > 6
        else "yfinance or fixed",
    )

    # ── Backfill current year if not already in file (first-run case) ────────
    cur_str = str(today.year)
    if cur_str not in existing:
        cur_holidays = (
            _fetch_from_nse_api(today.year)
            or _fetch_from_yfinance(today.year)
            or _generate_fixed_holidays(today.year)
        )
        existing[cur_str] = [d.isoformat() for d in cur_holidays]
        logger.info("[calendar_updater] Also recorded %d holidays for current year %d", len(cur_holidays), today.year)

    # ── Write file (atomic — AUD-057) ────────────────────────────────────────
    from core.utils.atomic_io import atomic_write_json
    atomic_write_json(_HOLIDAY_FILE, existing, indent=2, sort_keys=True)
    logger.info("[calendar_updater] Written to %s", _HOLIDAY_FILE)

    # ── Hot-reload the in-memory calendar ────────────────────────────────────
    try:
        from core.intelligence.rl.nse_calendar import reload_holidays
        reload_holidays()
    except Exception as exc:
        logger.warning("[calendar_updater] Could not reload nse_calendar module: %s", exc)

    return existing


def run_dec31_update() -> None:
    """
    Scheduler entry point for the Dec 31 job.
    Updates the calendar for the coming year so the RL system starts
    January 1 with accurate holiday data — no code changes required.
    """
    today = date.today()
    next_year = today.year + 1
    logger.info("[calendar_updater] Dec 31 annual update — fetching holidays for %d", next_year)
    result = update_calendar(target_year=next_year)
    logger.info(
        "[calendar_updater] Dec 31 update complete — %d years in file: %s",
        len(result), list(result.keys()),
    )
