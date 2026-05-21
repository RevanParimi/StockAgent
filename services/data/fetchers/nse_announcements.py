"""
services/data/fetchers/nse_announcements.py
============================================
NseIndiaApi pre-fetch for per-ticker company data.

Called ONCE per analysis run before LangGraph fan-out.
Result stored in StockQuery.nse_data and shared read-only
across all 8 parallel agents via ContextBuilder.

Public API
----------
prefetch_nse_data(ticker)    → dict  (stored in query.nse_data)
format_nse_context(nse_data, agent_type) → str  (injected into agent prompt)
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Tickers where NseIndiaApi consistently returns 0 announcements.
# Agents fall back to Serper-only for these tickers.
NSE_SYMBOL_OVERRIDES: dict[str, None] = {
    "TATAMOTORS": None,
}

_SLEEP_BETWEEN_CALLS = 0.5  # tested: 0.3s works; 0.5s is safe margin


def prefetch_nse_data(ticker: str) -> dict:
    """
    Pre-fetch announcements, board meetings, and corporate actions from NseIndiaApi.

    Creates one NSE() session per call, makes 3 sequential requests with 0.5s sleep
    between each (NSE website rate: ~2-3 req/sec max), then exits cleanly.

    Returns a dict — always; never raises. On failure returns the dict with error key set
    so agents can fall back to Serper-only without crashing.

    Parameters
    ----------
    ticker : NSE symbol e.g. "MARUTI", "HDFCBANK"
    """
    if ticker in NSE_SYMBOL_OVERRIDES:
        logger.warning(
            "[NseIndiaApi] %s: in NSE_SYMBOL_OVERRIDES — skipping prefetch, Serper-only fallback",
            ticker,
        )
        return {
            "announcements": [], "board_meetings": [], "actions": [],
            "symbol_used": ticker, "fetched_at": datetime.utcnow().isoformat(), "error": "symbol_override",
        }

    result: dict = {
        "announcements": [], "board_meetings": [], "actions": [],
        "symbol_used": ticker, "fetched_at": datetime.utcnow().isoformat(), "error": None,
    }

    try:
        from nse import NSE
    except ImportError:
        logger.warning("[NseIndiaApi] nse package not installed — Serper-only fallback for %s", ticker)
        result["error"] = "nse_not_installed"
        return result

    dl_folder = pathlib.Path(tempfile.mkdtemp())
    nse = NSE(download_folder=dl_folder)

    try:
        # --- announcements() ---
        raw = nse.announcements(symbol=ticker)
        if isinstance(raw, list):
            result["announcements"] = raw[:10]
        elif isinstance(raw, dict):
            items = raw.get("data", raw.get("announcements", []))
            result["announcements"] = items[:10] if isinstance(items, list) else []

        time.sleep(_SLEEP_BETWEEN_CALLS)

        # --- boardMeetings() ---
        raw = nse.boardMeetings(symbol=ticker)
        if isinstance(raw, list):
            result["board_meetings"] = raw[:5]
        elif isinstance(raw, dict):
            result["board_meetings"] = raw.get("data", [])[:5]

        time.sleep(_SLEEP_BETWEEN_CALLS)

        # --- actions() corporate: dividends, splits, bonuses ---
        raw = nse.actions(symbol=ticker)
        if isinstance(raw, list):
            result["actions"] = raw[:5]
        elif isinstance(raw, dict):
            result["actions"] = raw.get("data", [])[:5]

        logger.info(
            "[NseIndiaApi] %s: %d announcements, %d board meetings, %d corporate actions fetched",
            ticker,
            len(result["announcements"]),
            len(result["board_meetings"]),
            len(result["actions"]),
        )

    except Exception as exc:
        logger.warning(
            "[NseIndiaApi] %s: prefetch failed — agents will use Serper-only: %s", ticker, exc
        )
        result["error"] = str(exc)
    finally:
        try:
            nse.exit()
        except Exception:
            pass

    return result


def format_nse_context(nse_data: dict, agent_type: str = "general") -> str:
    """
    Convert pre-fetched NseIndiaApi data to a formatted string for agent prompt injection.

    Parameters
    ----------
    nse_data   : dict returned by prefetch_nse_data() (from query.nse_data)
    agent_type : "fundamentals" | "valuation_catalyst" | "risk_macro" | "earnings" | "general"

    Returns "" when nse_data is empty or failed — agents silently skip injection.
    """
    if not nse_data or nse_data.get("error") in ("nse_not_installed", "symbol_override"):
        return ""

    lines: list[str] = []

    # Board meetings: relevant for fundamentals, earnings, valuation_catalyst
    if agent_type in ("fundamentals", "earnings", "valuation_catalyst", "general"):
        bm = nse_data.get("board_meetings", [])[:3]
        if bm:
            lines.append("[NSE BOARD MEETINGS — official dates]")
            for item in bm:
                purpose = item.get("purpose", item.get("desc", ""))
                dt = item.get("bm_date", item.get("meetingDate", ""))
                lines.append(f"  [{dt}] {str(purpose)[:100]}")

    # Announcements: relevant for fundamentals, earnings, risk_macro
    if agent_type in ("fundamentals", "earnings", "risk_macro", "general"):
        ann = nse_data.get("announcements", [])[:5]
        if ann:
            lines.append("[NSE ANNOUNCEMENTS — official filings]")
            for item in ann:
                desc = item.get("desc", item.get("subject", item.get("description", "")))
                dt = item.get("an_dt", item.get("date", ""))
                lines.append(f"  [{dt}] {str(desc)[:100]}")

    # Corporate actions: dividends, splits — relevant for valuation_catalyst
    if agent_type in ("valuation_catalyst", "general"):
        act = nse_data.get("actions", [])[:3]
        if act:
            lines.append("[NSE CORPORATE ACTIONS — dividends / splits / bonuses]")
            for item in act:
                subject = item.get("subject", item.get("desc", ""))
                ex_date = item.get("exDate", item.get("ex_date", ""))
                lines.append(f"  [ex-date: {ex_date}] {str(subject)[:100]}")

    return "\n".join(lines) if lines else ""
