"""
Compass Phase A — auto-promotion into the managed universe (spec §4.3).

Any held or watchlisted symbol is promoted into managed_tickers.json so the
existing crons give it envelopes, daily reviews and dossiers — identical
treatment to the original tickers.

Phase B: the generic sector graph shipped — any well-formed sector key is
accepted; sectors outside NATIVE_SECTORS are analysed via the generic graph
(sector_router routes them). Malformed keys are rejected (invalid_sector).

Cap governance: portfolio.max_managed_tickers (default 40) guards LLM spend.
Only watchlist-origin entries are ever evicted (oldest first); held and manual
entries are never rotated out.
Cadence tiers govern review cost: held=daily, watchlist=weekly (spec §4.3).

FIX-028: a `held` entry is enabled only while some portfolio holds the stock.
When none does, `release_unheld` disables it, or turns it into a `watchlist`
entry while a user's own watchlist still lists the stock (a watchlist item
the autopilot wrote on its own exit does not count). `manual` entries, the
original universe, are never touched. A disabled entry keeps its sector, and
`promote_symbol` re-enables it when the stock is bought again. Every
read-modify-write here holds `managed_tickers_lock` (the owner's dashboard
edits of the list do not).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from core.config import settings
from services.api.log_buffer import (
    load_managed_tickers, managed_tickers_lock, read_managed_tickers, save_managed_tickers)
from backend.shared.data.fetchers.symbol_resolver import resolve_company_name
from backend.sectors.registry import NATIVE_SECTORS

logger = logging.getLogger(__name__)

# NATIVE_SECTORS is imported from the registry, not re-declared: this module
# used to hand-mirror sector_router.NATIVE_SECTORS, and PI task A1 collapsed
# every sector map onto the registry so a sector cannot be half-added.
# Back-compat alias (Phase A name; portfolio_api and older tests import it).
SUPPORTED_SECTORS = NATIVE_SECTORS

# Any other well-formed sector key routes via the GENERIC sector graph
# (Compass Phase B). Format guard only — a typo'd key would silently fragment
# PredictionStore directories, so reject anything that isn't a clean
# lowercase token.
_SECTOR_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

# The watchlist source the autopilot writes when it sells a stock outright
# (autopilot._execute_sells); such an item is not a user's own.
AUTOPILOT_SOURCE = "autopilot"


def is_valid_sector(sector: str) -> bool:
    """True when `sector` is a well-formed sector key (native or generic)."""
    return bool(_SECTOR_RE.match(sector.strip().lower()))

_ORIGIN_CADENCE = {"held": "daily", "watchlist": "weekly"}


def _evict_for_capacity(tickers: list[dict], cap: int) -> bool:
    """Ensure there's room for one more active entry under `cap`.

    Returns True if room already exists or was made by evicting the oldest
    watchlist-origin entry (held and manual entries are never evicted).
    Returns False if the cap is full and nothing is evictable — callers
    must NOT enable/add the entry in that case.
    """
    active = [t for t in tickers if t.get("enabled", True)]
    if len(active) < cap:
        return True
    candidates = [t for t in active if t.get("origin") == "watchlist"]
    candidates.sort(key=lambda t: t.get("promoted_at", ""))
    if not candidates:
        return False
    evicted = candidates[0]
    evicted["enabled"] = False
    logger.info("[promotion] cap %d: evicted %s (origin=%s)",
                cap, evicted["sym"], evicted["origin"])
    return True


def promote_symbol(symbol: str, sector: str, origin: str) -> dict:
    symbol = symbol.strip().upper()
    sector = sector.strip().lower()
    if origin not in _ORIGIN_CADENCE:
        raise ValueError(f"origin must be one of {sorted(_ORIGIN_CADENCE)}: {origin!r}")

    if not _SECTOR_RE.match(sector):
        detail = (
            f"'{sector}' is not a valid sector key — use a lowercase token "
            f"(letters/digits/underscore, 2-32 chars), e.g. 'pharma'."
        )
        logger.info("[promotion] %s rejected: %s", symbol, detail)
        return {"status": "invalid_sector", "symbol": symbol, "detail": detail}
    graph = "native" if sector in NATIVE_SECTORS else "generic"

    with managed_tickers_lock():
        tickers = list(load_managed_tickers())
        existing = next((t for t in tickers if t.get("sym") == symbol), None)
        if existing:
            changed = False
            if not existing.get("enabled", True):
                cap = settings.PORTFOLIO_MAX_MANAGED_TICKERS
                if not _evict_for_capacity(tickers, cap):
                    logger.warning(
                        "[promotion] cap %d reached and nothing evictable — "
                        "%s NOT re-enabled", cap, symbol,
                    )
                    return {"status": "cap_full", "symbol": symbol,
                            "detail": f"managed-ticker cap {cap} reached"}
                existing["enabled"] = True
                changed = True
            # A held position outranks a watchlist promotion of the same symbol.
            if existing.get("origin") in _ORIGIN_CADENCE and origin == "held" \
                    and existing.get("origin") != "held":
                existing["origin"], existing["cadence"] = "held", "daily"
                changed = True
            if changed:
                save_managed_tickers(tickers)
            return {"status": "already_managed", "symbol": symbol, "graph": graph}

        cap = settings.PORTFOLIO_MAX_MANAGED_TICKERS
        if not _evict_for_capacity(tickers, cap):
            logger.warning(
                "[promotion] cap %d reached and nothing evictable — %s NOT promoted",
                cap, symbol,
            )
            return {"status": "cap_full", "symbol": symbol,
                    "detail": f"managed-ticker cap {cap} reached"}

        try:
            name = resolve_company_name(symbol) or symbol
        except Exception:
            name = symbol
        tickers.append({
            "sym": symbol,
            "name": name,
            "sector": sector,
            "enabled": True,
            "origin": origin,
            "cadence": _ORIGIN_CADENCE[origin],
            "promoted_at": date.today().isoformat(),
        })
        save_managed_tickers(tickers)
    logger.info("[promotion] %s promoted (sector=%s origin=%s cadence=%s)",
                symbol, sector, origin, _ORIGIN_CADENCE[origin])
    return {"status": "promoted", "symbol": symbol,
            "cadence": _ORIGIN_CADENCE[origin], "graph": graph}


def demote_symbol(symbol: str) -> bool:
    """Disable a portfolio-origin managed entry (holding/watchlist removed).
    Manual entries — the original universe — are never touched."""
    symbol = symbol.strip().upper()
    with managed_tickers_lock():
        tickers = list(load_managed_tickers())
        entry = next((t for t in tickers if t.get("sym") == symbol), None)
        if not entry or entry.get("origin") not in _ORIGIN_CADENCE:
            return False
        entry["enabled"] = False
        save_managed_tickers(tickers)
    logger.info("[promotion] %s demoted (enabled=False)", symbol)
    return True


def _portfolios_now(current=None) -> tuple[set[str], set[str]]:
    """(every symbol some portfolio holds, every symbol on a user's own
    watchlist), over every portfolio on disk and `current`, the portfolio a
    caller has just saved (counted wherever it is stored). Read straight from
    each portfolio.json, so a corrupt one raises here rather than reading as
    empty (PortfolioStore.load would quarantine it and answer "holds
    nothing")."""
    from backend.shared.schemas.portfolio import Portfolio
    from core.portfolio.store import list_user_ids
    root = Path(settings.PORTFOLIO_DATA_DIR)
    portfolios = [Portfolio(**json.loads((root / user_id / "portfolio.json").read_text(
        encoding="utf-8"))) for user_id in list_user_ids()]
    held: set[str] = set()
    watched: set[str] = set()
    for p in portfolios + ([current] if current is not None else []):
        held |= {h.symbol.strip().upper() for h in p.holdings}
        watched |= {w.symbol.strip().upper() for w in p.watchlist
                    if w.source != AUTOPILOT_SOURCE}
    return held, watched


def release_unheld(current=None) -> dict:
    """FIX-028: the managed list follows the holdings. Each enabled `held`
    entry that no portfolio holds is disabled, or becomes a `watchlist`
    entry (weekly cadence) when a user's own watchlist lists the stock.
    `current` is the portfolio the caller has just saved: it counts even when
    it is stored outside the data folder.

    Returns {"released": [...], "to_watchlist": [...]}, plus "error" when
    nothing was changed because the list or a portfolio could not be read.
    The portfolios are read under the list's lock, so a buy saved before a
    concurrent promotion is always seen, and a promotion after this release
    re-enables its stock. Never seeds the list: with no file, nothing to do
    and nothing written, not even the lock."""
    out: dict = {"released": [], "to_watchlist": []}
    if not read_managed_tickers():
        return out
    with managed_tickers_lock():
        tickers = read_managed_tickers()
        if not tickers:
            return out
        try:
            held, watched = _portfolios_now(current)
        except Exception as exc:
            logger.warning("[promotion] portfolios unreadable, no managed entry released: %s",
                           exc)
            out["error"] = f"portfolios unreadable: {exc}"
            return out
        for entry in tickers:
            if not isinstance(entry, dict) or entry.get("origin") != "held" \
                    or not entry.get("enabled", True):
                continue
            symbol = str(entry.get("sym") or "").strip().upper()
            if not symbol or symbol in held:
                continue
            if symbol in watched:
                entry["origin"], entry["cadence"] = "watchlist", _ORIGIN_CADENCE["watchlist"]
                out["to_watchlist"].append(symbol)
            else:
                entry["enabled"] = False
                out["released"].append(symbol)
        if out["released"] or out["to_watchlist"]:
            save_managed_tickers(tickers)
    if out["released"] or out["to_watchlist"]:
        logger.info("[promotion] no portfolio holds %s: disabled %s; kept for a user's "
                    "watchlist (weekly) %s",
                    sorted(out["released"] + out["to_watchlist"]),
                    out["released"] or "none", out["to_watchlist"] or "none")
    return out


def without_daily_review(symbols) -> set[str] | None:
    """Those of `symbols` (held stocks) whose promotion the list is waiting
    for: no entry at all (a promotion the cap refused, or one that failed), a
    disabled `held` or `watchlist` entry, or an enabled `watchlist` entry,
    which the cap may evict. An original-universe entry that is disabled is
    left out: only the owner disables one. None when the list cannot be read
    (no file, or an unreadable one)."""
    tickers = read_managed_tickers()
    if tickers is None:
        return None
    entries = {str(t.get("sym") or "").strip().upper(): t for t in tickers
               if isinstance(t, dict)}
    out = set()
    for s in symbols:
        entry = entries.get(s.strip().upper())
        if entry is None:
            out.add(s)
        elif entry.get("origin") in _ORIGIN_CADENCE and (
                not entry.get("enabled", True) or entry.get("origin") == "watchlist"):
            out.add(s)
    return out


def due_for_review(entry: dict, review_date: date) -> bool:
    """Cadence gate for the daily review job: held names review daily,
    watchlist names weekly (config portfolio.weekly_review_weekday)."""
    if entry.get("cadence", "daily") != "weekly":
        return True
    return review_date.weekday() == settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY
