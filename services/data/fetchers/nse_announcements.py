"""
services/data/fetchers/nse_announcements.py
============================================
NseIndiaApi pre-fetch for per-ticker company data.

Called ONCE per analysis run before LangGraph fan-out.
Result stored in StockQuery.nse_data and shared read-only
across all 8 parallel agents via ContextBuilder.

Key-mapping design
------------------
NseIndiaApi returns different field names for the same semantic concept
depending on the endpoint (and sometimes the ticker). Rather than
maintaining fragile hardcoded fallback chains, we:

  1. On first call for a ticker: inspect the real response, find which
     actual key name carries each semantic field, save to
     data/nse/key_registry.json  (via nse_key_registry.update_registry).

  2. Embed the discovered mappings in nse_data["key_mappings"] so all
     9 parallel agents can use them without re-reading the registry file.

  3. On subsequent calls: get_mapping() returns the cached keys; no
     discovery overhead.

  4. format_nse_context() uses resolve_field() which tries the cached
     key first, then the full candidate chain as a last resort.

Public API
----------
prefetch_nse_data(ticker)                          → dict  (stored in query.nse_data)
format_nse_context(nse_data, agent_type)           → str   (injected into agent prompt)
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

_SLEEP_BETWEEN_CALLS = 0.5  # tested: 0.3s works; 0.5s is the safe margin


def prefetch_nse_data(ticker: str) -> dict:
    """
    Pre-fetch announcements, board meetings, and corporate actions from NseIndiaApi.

    After each successful fetch, runs key-mapping discovery so the correct
    field names are embedded in nse_data["key_mappings"] and persisted to
    data/nse/key_registry.json for future runs.

    Returns a dict — always; never raises.
    """
    if ticker in NSE_SYMBOL_OVERRIDES:
        logger.warning(
            "[NseIndiaApi] %s: in NSE_SYMBOL_OVERRIDES — skipping prefetch, Serper-only fallback",
            ticker,
        )
        return {
            "announcements": [], "board_meetings": [], "actions": [],
            "key_mappings": {},
            "symbol_used": ticker, "fetched_at": datetime.utcnow().isoformat(),
            "error": "symbol_override",
        }

    result: dict = {
        "announcements": [], "board_meetings": [], "actions": [],
        "key_mappings": {},
        "symbol_used": ticker, "fetched_at": datetime.utcnow().isoformat(),
        "error": None,
    }

    try:
        from nse import NSE
    except ImportError:
        logger.warning("[NseIndiaApi] nse package not installed — Serper-only fallback for %s", ticker)
        result["error"] = "nse_not_installed"
        return result

    from services.data.fetchers.nse_key_registry import (
        discover_mapping,
        get_mapping,
        update_registry,
    )

    dl_folder = pathlib.Path(tempfile.mkdtemp())
    nse = NSE(download_folder=dl_folder)

    try:
        # --- announcements() ---
        raw = nse.announcements(symbol=ticker)
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("announcements", []))
        if isinstance(items, list):
            result["announcements"] = items[:10]

        mapping = get_mapping(ticker, "announcements")
        if not mapping and result["announcements"]:
            mapping = discover_mapping(result["announcements"], "announcements")
            update_registry(ticker, "announcements", mapping)
        result["key_mappings"]["announcements"] = mapping

        time.sleep(_SLEEP_BETWEEN_CALLS)

        # --- boardMeetings() ---
        raw = nse.boardMeetings(symbol=ticker)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        if isinstance(items, list):
            result["board_meetings"] = items[:5]

        mapping = get_mapping(ticker, "board_meetings")
        if not mapping and result["board_meetings"]:
            mapping = discover_mapping(result["board_meetings"], "board_meetings")
            update_registry(ticker, "board_meetings", mapping)
        result["key_mappings"]["board_meetings"] = mapping

        time.sleep(_SLEEP_BETWEEN_CALLS)

        # --- actions() — dividends, splits, bonuses ---
        raw = nse.actions(symbol=ticker)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        if isinstance(items, list):
            result["actions"] = items[:5]

        mapping = get_mapping(ticker, "actions")
        if not mapping and result["actions"]:
            mapping = discover_mapping(result["actions"], "actions")
            update_registry(ticker, "actions", mapping)
        result["key_mappings"]["actions"] = mapping

        logger.info(
            "[NseIndiaApi] %s: %d announcements, %d board meetings, %d actions | "
            "key_mappings=%s",
            ticker,
            len(result["announcements"]),
            len(result["board_meetings"]),
            len(result["actions"]),
            {k: v for k, v in result["key_mappings"].items() if v},
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

    Uses the key mappings embedded in nse_data["key_mappings"] by prefetch_nse_data()
    so the correct field name for this ticker is always used. Falls back to the full
    candidate chain (via resolve_field) if mappings are absent.

    Parameters
    ----------
    nse_data   : dict from query.nse_data (set by prefetch_nse_data)
    agent_type : "fundamentals" | "valuation_catalyst" | "risk_macro" | "earnings" | "general"

    Returns "" when nse_data is empty or failed — agents silently skip injection.
    """
    if not nse_data or nse_data.get("error") in ("nse_not_installed", "symbol_override"):
        return ""

    from services.data.fetchers.nse_key_registry import resolve_field

    key_mappings: dict[str, dict[str, str]] = nse_data.get("key_mappings", {})
    lines: list[str] = []

    # Board meetings — fundamentals / earnings / valuation_catalyst
    if agent_type in ("fundamentals", "earnings", "valuation_catalyst", "general"):
        bm = nse_data.get("board_meetings", [])[:3]
        bm_mapping = key_mappings.get("board_meetings", {})
        if bm:
            lines.append("[NSE BOARD MEETINGS — official dates]")
            for item in bm:
                desc = resolve_field(item, bm_mapping, "desc", "board_meetings")
                dt   = resolve_field(item, bm_mapping, "date", "board_meetings")
                if desc or dt:
                    lines.append(f"  [{dt}] {desc[:100]}")

    # Announcements — fundamentals / earnings / risk_macro
    if agent_type in ("fundamentals", "earnings", "risk_macro", "general"):
        ann = nse_data.get("announcements", [])[:5]
        ann_mapping = key_mappings.get("announcements", {})
        if ann:
            lines.append("[NSE ANNOUNCEMENTS — official filings]")
            for item in ann:
                desc = resolve_field(item, ann_mapping, "desc", "announcements")
                dt   = resolve_field(item, ann_mapping, "date", "announcements")
                if desc or dt:
                    lines.append(f"  [{dt}] {desc[:100]}")

    # Corporate actions — valuation_catalyst
    if agent_type in ("valuation_catalyst", "general"):
        act = nse_data.get("actions", [])[:3]
        act_mapping = key_mappings.get("actions", {})
        if act:
            lines.append("[NSE CORPORATE ACTIONS — dividends / splits / bonuses]")
            for item in act:
                desc    = resolve_field(item, act_mapping, "desc", "actions")
                ex_date = resolve_field(item, act_mapping, "date", "actions")
                if desc or ex_date:
                    lines.append(f"  [ex-date: {ex_date}] {desc[:100]}")

    return "\n".join(lines) if lines else ""
