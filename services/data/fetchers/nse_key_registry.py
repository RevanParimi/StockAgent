"""
services/data/fetchers/nse_key_registry.py
==========================================
Persistent key-mapping registry for NseIndiaApi responses.

Problem: NseIndiaApi returns different field names for the same semantic
concept depending on the endpoint and (sometimes) the ticker.
  announcements  → "desc" or "subject" or "description"
  board_meetings → "purpose" or "desc" or "bm_desc"
  actions        → "subject" or "desc" or "purpose"
  dates          → "an_dt" or "sort_date" or "bm_date" or "exDate"

Solution: First time we see a ticker's response, inspect the first item
to find which actual key carries each semantic field (first non-empty
value wins). Save the result to data/nse/key_registry.json. Every
subsequent call uses the cached mapping — no guessing, no empty fields.

If a ticker is not in the registry, format_nse_context() falls back to
the priority-ordered candidate chains until discovery has run.

Public API
----------
discover_mapping(items, endpoint)            → dict[semantic_field → key]
resolve_field(item, mapping, semantic_field, endpoint) → str
get_mapping(ticker, endpoint)                → dict (from registry file)
update_registry(ticker, endpoint, mapping)   → None (saves to file)
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate keys — ordered by likelihood; first non-empty value wins
# ---------------------------------------------------------------------------

FIELD_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "announcements": {
        "desc": [
            "desc",
            "subject",
            "description",
            "attchmntText",
            "bm_desc",
            "an_desc",
        ],
        "date": [
            "an_dt",
            "sort_date",
            "date",
            "bm_date",
            "updatedAt",
        ],
        "attachment": [
            "attchmntText",
            "attachment_text",
            "desc",
        ],
    },
    "board_meetings": {
        "desc": [
            "purpose",
            "desc",
            "subject",
            "bm_desc",
            "attchmntText",
            "description",
        ],
        "date": [
            "bm_date",
            "meetingDate",
            "meeting_date",
            "date",
            "an_dt",
        ],
    },
    "actions": {
        "desc": [
            "subject",
            "desc",
            "purpose",
            "action",
            "description",
        ],
        "date": [
            "exDate",
            "ex_date",
            "exdate",
            "record_date",
            "date",
        ],
    },
}

# ---------------------------------------------------------------------------
# Registry file — persists discovered mappings across runs
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path("data/nse/key_registry.json")
_lock = threading.Lock()


def _load_registry() -> dict:
    if _REGISTRY_PATH.exists():
        try:
            return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[NseKeyRegistry] Could not load registry: %s — returning empty", exc)
    return {}


def _save_registry(registry: dict) -> None:
    try:
        from core.utils.atomic_io import atomic_write_json
        atomic_write_json(_REGISTRY_PATH, registry, indent=2)   # AUD-057
    except OSError as exc:
        logger.warning("[NseKeyRegistry] Could not save registry: %s", exc)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def discover_mapping(items: list[dict], endpoint: str) -> dict[str, str]:
    """
    Inspect the first item of an NseIndiaApi response and return the
    actual key name that carries each semantic field.

    Parameters
    ----------
    items    : raw list returned by nse.announcements() / boardMeetings() / actions()
    endpoint : "announcements" | "board_meetings" | "actions"

    Returns
    -------
    {semantic_field: actual_key} — only fields where a non-empty value was found.
    Empty dict if items is empty.
    """
    if not items or not isinstance(items, list):
        return {}

    sample = items[0]
    candidates = FIELD_CANDIDATES.get(endpoint, {})
    mapping: dict[str, str] = {}

    for semantic_field, key_options in candidates.items():
        for key in key_options:
            val = sample.get(key)
            if val and str(val).strip():
                mapping[semantic_field] = key
                break

    logger.debug(
        "[NseKeyRegistry] Discovered mapping for %s: %s", endpoint, mapping
    )
    return mapping


def resolve_field(
    item: dict,
    mapping: dict[str, str],
    semantic_field: str,
    endpoint: str,
) -> str:
    """
    Extract the value for a semantic field from a single NseIndiaApi item.

    Uses the discovered/cached key if available. Falls back to the full
    candidate chain if the mapping is incomplete (e.g., a new ticker with
    an unexpected schema before discovery has run).
    """
    # Preferred: use the cached discovered key
    known_key = mapping.get(semantic_field)
    if known_key:
        val = item.get(known_key, "")
        if val and str(val).strip():
            return str(val).strip()

    # Fallback: try all candidates in priority order
    for key in FIELD_CANDIDATES.get(endpoint, {}).get(semantic_field, []):
        val = item.get(key, "")
        if val and str(val).strip():
            return str(val).strip()

    return ""


def get_mapping(ticker: str, endpoint: str) -> dict[str, str]:
    """
    Return the cached key mapping for ticker + endpoint from the registry.
    Returns {} if this ticker/endpoint combination has not been discovered yet.
    """
    registry = _load_registry()
    return registry.get(ticker, {}).get(endpoint, {})


def update_registry(ticker: str, endpoint: str, mapping: dict[str, str]) -> None:
    """
    Persist a discovered mapping for ticker + endpoint.

    Thread-safe: uses a module-level lock so concurrent analysis runs
    don't corrupt the registry file.

    Only saves if the mapping is non-empty. Merges with existing entries
    so partial mappings from earlier discovery don't get overwritten.
    """
    if not mapping:
        return

    with _lock:
        registry = _load_registry()
        ticker_entry = registry.setdefault(ticker, {})
        existing = ticker_entry.get(endpoint, {})

        # Merge: new discovery wins over old (in case a key changed in NSE's API)
        merged = {**existing, **mapping}
        if merged == existing:
            return  # nothing new — skip the file write

        ticker_entry[endpoint] = merged
        _save_registry(registry)
        logger.info(
            "[NseKeyRegistry] Saved %s.%s mapping: %s",
            ticker, endpoint, merged,
        )


def seed_registry(tickers: list[str]) -> None:
    """
    Run live discovery for a list of tickers and populate the registry.

    Call this once after initial deployment or whenever new tickers are
    added to SCHEDULER_TICKERS. Safe to call multiple times — only
    writes when a new mapping is discovered.

    Parameters
    ----------
    tickers : list of NSE symbols, e.g. ["HDFCBANK", "TCS", "MARUTI"]
    """
    import pathlib
    import tempfile
    import time

    try:
        from nse import NSE
    except ImportError:
        logger.warning("[NseKeyRegistry] nse package not installed — cannot seed registry")
        return

    dl_folder = pathlib.Path(tempfile.mkdtemp())
    nse = NSE(download_folder=dl_folder)

    try:
        for ticker in tickers:
            logger.info("[NseKeyRegistry] Seeding %s...", ticker)

            # announcements
            try:
                raw = nse.announcements(symbol=ticker)
                items = raw if isinstance(raw, list) else raw.get("data", [])
                mapping = discover_mapping(items, "announcements")
                update_registry(ticker, "announcements", mapping)
            except Exception as exc:
                logger.warning("[NseKeyRegistry] %s announcements failed: %s", ticker, exc)

            time.sleep(0.5)

            # boardMeetings
            try:
                raw = nse.boardMeetings(symbol=ticker)
                items = raw if isinstance(raw, list) else raw.get("data", [])
                mapping = discover_mapping(items, "board_meetings")
                update_registry(ticker, "board_meetings", mapping)
            except Exception as exc:
                logger.warning("[NseKeyRegistry] %s boardMeetings failed: %s", ticker, exc)

            time.sleep(0.5)

            # actions
            try:
                raw = nse.actions(symbol=ticker)
                items = raw if isinstance(raw, list) else raw.get("data", [])
                mapping = discover_mapping(items, "actions")
                update_registry(ticker, "actions", mapping)
            except Exception as exc:
                logger.warning("[NseKeyRegistry] %s actions failed: %s", ticker, exc)

            time.sleep(0.8)  # slightly longer between tickers

    finally:
        from services.data.fetchers.nse_client import close_nse
        close_nse(nse)  # exit() + rmtree(download_folder) — AUD-017
