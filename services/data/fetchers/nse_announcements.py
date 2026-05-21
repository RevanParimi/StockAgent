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
     parallel agents can share them without re-reading the registry file.

  3. On subsequent calls: get_mapping() returns the cached keys; no
     discovery overhead.

  4. format_nse_context() uses resolve_field() which tries the cached
     key first, then the full candidate chain as a last resort.

Category filtering design
-------------------------
format_nse_context() accepts an agent_type that controls:
  • Which sections (board_meetings / announcements / actions) are shown
  • Which NSE announcement categories are included per section
  • Whether attachment text (attchmntText) is included

Filtering is case-insensitive substring matching against the announcement
desc (NSE category label, e.g. "Commencement of commercial production/operations").
An empty filter list means "show all" for that agent_type.

Public API
----------
prefetch_nse_data(ticker)                 → dict  (stored in query.nse_data)
format_nse_context(nse_data, agent_type)  → str   (injected into agent prompt)
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tickers with known NseIndiaApi data gaps
# ---------------------------------------------------------------------------

# Tickers where NseIndiaApi consistently returns 0 announcements.
# Agents fall back to Serper-only for these tickers.
NSE_SYMBOL_OVERRIDES: dict[str, None] = {
    "TATAMOTORS": None,
}

_SLEEP_BETWEEN_CALLS = 0.5  # tested: 0.3s works; 0.5s is the safe margin

# ---------------------------------------------------------------------------
# Category-filter configuration per agent_type
# ---------------------------------------------------------------------------

# Keywords matched against the announcement desc (NSE category label).
# Case-insensitive substring match.  Empty list = no filter (show all).
_ANN_FILTERS: dict[str, list[str]] = {
    # Automobile sector — no filter, show all categories
    "fundamentals":       [],
    "earnings":           [],
    "risk_macro":         [],
    "valuation_catalyst": [],

    # Renewable Energy sector
    # commissioning keywords broadened: "trial operation" is the NSE filing
    # for COD precursor — "Completion of Trial Operation" → same as COD signal
    "re_fundamentals":    [
        "commencement of commercial production",
        "trial operation",
        "commercial operation",
        "financial results",
        "updates",           # catches operational updates that signal COD progress
    ],
    "re_business":        [
        "commencement of commercial production",
        "trial operation",
        "commercial operation",
        "updates",
        "press release",
        "acquisition",       # capacity acquisitions / project wins
    ],
    "re_valuation":       ["fund raising", "dividend", "rights", "bonus", "financial results"],
    "re_risk":            [
        "general updates",
        "press release",
        "regulatory",
        "change in management",  # senior management changes = governance risk signal
        "acquisition",           # distressed asset acquisitions = leverage risk
        "disclosure",            # promoter pledge / takeover disclosures
    ],

    # Banking/BFSI sector — defined for future sprint
    "bfsi_fundamentals":  [],
    "bfsi_institutional": ["esop", "esos", "esps", "sast", "shareholders"],
    "bfsi_risk":          ["regulatory", "press release", "general updates"],
    "bfsi_universe":      ["dividend", "rights", "bonus", "buyback"],

    # IT sector — defined for future sprint
    "it_fundamentals":    [],
    "it_insider":         ["esop", "esos", "esps", "sast", "shareholders"],
    "it_sentiment":       ["analysts", "institutional investor", "press release", "general updates"],
    "it_transcript":      [],

    # General passthrough — no filter
    "general":            [],
}

# Agent_types that include the board meetings section
_SHOW_BOARD_MEETINGS: frozenset[str] = frozenset({
    "fundamentals", "earnings", "valuation_catalyst", "general",
    "re_fundamentals", "re_valuation",
    "bfsi_fundamentals",
    "it_fundamentals", "it_transcript",
})

# Optional keyword filter on board meeting purpose per agent_type.
# Empty = show all board meetings for that agent_type.
_BM_FILTERS: dict[str, list[str]] = {
    # RE: only results/dividend meetings are useful for fundamentals scoring
    "re_fundamentals": ["results", "financial", "dividend", "annual"],
    # RE: fund raising meetings signal equity dilution risk
    "re_valuation":    ["fund raising", "dividend", "rights", "results", "financial"],
}

# Agent_types that include the announcements section
_SHOW_ANNOUNCEMENTS: frozenset[str] = frozenset({
    "fundamentals", "earnings", "risk_macro", "general",
    "re_fundamentals", "re_business", "re_valuation", "re_risk",
    "bfsi_fundamentals", "bfsi_institutional", "bfsi_risk", "bfsi_universe",
    "it_fundamentals", "it_insider", "it_sentiment",
})

# Agent_types that include the corporate actions section (actions())
_SHOW_ACTIONS: frozenset[str] = frozenset({
    "valuation_catalyst", "general",
    "re_valuation",
    "bfsi_universe",
})

# Agent_types that should append attachment text when present and short.
# Useful for RE commissioning (MW + location detail) and IT ESOP (tranche detail).
_SHOW_ATTACHMENT: frozenset[str] = frozenset({
    "re_fundamentals",
    "re_business",
    "it_insider",
})

_MAX_ANN_ITEMS = 6   # announcements shown per agent context
_MAX_BM_ITEMS  = 3   # board meeting rows shown
_MAX_ACT_ITEMS = 3   # corporate action rows shown
_MAX_ATTACH_LEN = 120  # chars of attchmntText shown when included


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches_filter(value: str, keywords: list[str]) -> bool:
    """Return True if any keyword is a substring of value (case-insensitive)."""
    if not keywords:
        return True
    v = value.lower()
    return any(kw.lower() in v for kw in keywords)


# ---------------------------------------------------------------------------
# Pre-fetch
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

def format_nse_context(nse_data: dict, agent_type: str = "general") -> str:
    """
    Convert pre-fetched NseIndiaApi data to a formatted string for agent prompt injection.

    Uses the key mappings embedded in nse_data["key_mappings"] (set by
    prefetch_nse_data) so the correct field name for this ticker is always
    used. Falls back to the full candidate chain via resolve_field if mappings
    are absent.

    Each agent_type controls which sections appear and which NSE announcement
    categories are included — see _ANN_FILTERS, _SHOW_BOARD_MEETINGS, etc.

    Parameters
    ----------
    nse_data   : dict from query.nse_data (set by prefetch_nse_data)
    agent_type : sector-aware agent identifier, e.g. "re_fundamentals",
                 "it_insider", "bfsi_risk", or legacy "fundamentals"

    Returns "" when nse_data is empty, failed, or all sections filter to zero
    items — agents silently fall back to Serper-only in that case.
    """
    if not nse_data or nse_data.get("error") in ("nse_not_installed", "symbol_override"):
        return ""

    from services.data.fetchers.nse_key_registry import resolve_field

    key_mappings: dict[str, dict[str, str]] = nse_data.get("key_mappings", {})
    lines: list[str] = []

    # ------------------------------------------------------------------
    # Board meetings section
    # ------------------------------------------------------------------
    if agent_type in _SHOW_BOARD_MEETINGS:
        bm_all = nse_data.get("board_meetings", [])
        bm_mapping = key_mappings.get("board_meetings", {})
        bm_kw = _BM_FILTERS.get(agent_type, [])

        bm_rows = []
        for item in bm_all:
            desc = resolve_field(item, bm_mapping, "desc", "board_meetings")
            dt   = resolve_field(item, bm_mapping, "date", "board_meetings")
            if not (desc or dt):
                continue
            if _matches_filter(desc, bm_kw):
                bm_rows.append((dt, desc))
            if len(bm_rows) >= _MAX_BM_ITEMS:
                break

        if bm_rows:
            lines.append("[NSE BOARD MEETINGS — official dates]")
            for dt, desc in bm_rows:
                lines.append(f"  [{dt}] {desc[:120]}")

    # ------------------------------------------------------------------
    # Announcements section
    # ------------------------------------------------------------------
    if agent_type in _SHOW_ANNOUNCEMENTS:
        ann_all    = nse_data.get("announcements", [])
        ann_mapping = key_mappings.get("announcements", {})
        ann_kw     = _ANN_FILTERS.get(agent_type, [])
        show_attach = agent_type in _SHOW_ATTACHMENT

        ann_rows = []
        for item in ann_all:
            desc   = resolve_field(item, ann_mapping, "desc",       "announcements")
            dt     = resolve_field(item, ann_mapping, "date",       "announcements")
            attach = resolve_field(item, ann_mapping, "attachment", "announcements") if show_attach else ""

            if not (desc or dt):
                continue
            if _matches_filter(desc, ann_kw):
                ann_rows.append((dt, desc, attach))
            if len(ann_rows) >= _MAX_ANN_ITEMS:
                break

        if ann_rows:
            lines.append("[NSE ANNOUNCEMENTS — official filings]")
            for dt, desc, attach in ann_rows:
                line = f"  [{dt}] {desc[:100]}"
                # Append attachment text when it adds more detail than the category label
                if attach and attach.lower() != desc.lower() and len(attach.strip()) > 10:
                    line += f" | {attach[:_MAX_ATTACH_LEN]}"
                lines.append(line)

    # ------------------------------------------------------------------
    # Corporate actions section
    # ------------------------------------------------------------------
    if agent_type in _SHOW_ACTIONS:
        act_all    = nse_data.get("actions", [])
        act_mapping = key_mappings.get("actions", {})

        # NSE actions() can include non-financial entries like AGM/EGM.
        # Only keep genuine financial corporate actions.
        _NON_FINANCIAL_ACTIONS = {"annual general meeting", "agm", "egm",
                                   "extraordinary general meeting", "postal ballot"}

        act_rows = []
        for item in act_all:
            desc    = resolve_field(item, act_mapping, "desc", "actions")
            ex_date = resolve_field(item, act_mapping, "date", "actions")
            if not (desc or ex_date):
                continue
            # Skip AGM/EGM entries — not financial corporate actions
            if any(nf in desc.lower() for nf in _NON_FINANCIAL_ACTIONS):
                continue
            act_rows.append((ex_date, desc))
            if len(act_rows) >= _MAX_ACT_ITEMS:
                break

        if act_rows:
            lines.append("[NSE CORPORATE ACTIONS — dividends / splits / bonuses]")
            for ex_date, desc in act_rows:
                lines.append(f"  [ex-date: {ex_date}] {desc[:100]}")

    return "\n".join(lines) if lines else ""
