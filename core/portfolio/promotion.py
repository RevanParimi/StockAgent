"""
Compass Phase A — auto-promotion into the managed universe (spec §4.3).

Any held or watchlisted symbol is promoted into managed_tickers.json so the
existing crons give it envelopes, daily reviews and dossiers — identical
treatment to the original tickers.

Phase A reality check: sector_router supports exactly 4 sectors and silently
falls back to the automobile orchestrator for anything else — an auto-promoted
pharma stock would be analyzed as a car company. Promotion therefore REJECTS
unsupported sectors until the generic sector graph ships (Phase B).

Cap governance: portfolio.max_managed_tickers (default 40) guards LLM spend.
Priority held > watchlist; pre-existing manual entries are never evicted.
Cadence tiers govern review cost: held=daily, watchlist=weekly (spec §4.3).
"""
from __future__ import annotations

import logging
from datetime import date

from core.config import settings
from services.api.log_buffer import load_managed_tickers, save_managed_tickers
from backend.shared.data.fetchers.symbol_resolver import resolve_company_name

logger = logging.getLogger(__name__)

# Must mirror core/intelligence/rl/workflows/sector_router.py _ORCHESTRATORS.
SUPPORTED_SECTORS: frozenset[str] = frozenset(
    {"automobile", "banking_bfsi", "it_sector", "renewable_energy"}
)

_ORIGIN_CADENCE = {"held": "daily", "watchlist": "weekly"}
# Eviction preference under cap pressure (lower value evicted first).
_EVICTION_ORDER = {"watchlist": 0, "held": 1}


def promote_symbol(symbol: str, sector: str, origin: str) -> dict:
    symbol = symbol.strip().upper()
    sector = sector.strip().lower()
    if origin not in _ORIGIN_CADENCE:
        raise ValueError(f"origin must be one of {sorted(_ORIGIN_CADENCE)}: {origin!r}")

    if sector not in SUPPORTED_SECTORS:
        detail = (
            f"Sector '{sector}' not yet supported — Phase A promotion covers "
            f"{sorted(SUPPORTED_SECTORS)} only (generic sector graph is Phase B)."
        )
        logger.info("[promotion] %s rejected: %s", symbol, detail)
        return {"status": "unsupported_sector", "symbol": symbol, "detail": detail}

    tickers = list(load_managed_tickers())
    existing = next((t for t in tickers if t.get("sym") == symbol), None)
    if existing:
        changed = False
        if not existing.get("enabled", True):
            existing["enabled"] = True
            changed = True
        # A held position outranks a watchlist promotion of the same symbol.
        if existing.get("origin") in _ORIGIN_CADENCE and origin == "held" \
                and existing.get("origin") != "held":
            existing["origin"], existing["cadence"] = "held", "daily"
            changed = True
        if changed:
            save_managed_tickers(tickers)
        return {"status": "already_managed", "symbol": symbol}

    cap = settings.PORTFOLIO_MAX_MANAGED_TICKERS
    active = [t for t in tickers if t.get("enabled", True)]
    if len(active) >= cap:
        # Evict the lowest-priority portfolio-origin entry. Manual entries
        # (no origin field — the original universe) are never evicted.
        candidates = [
            t for t in active
            if t.get("origin") in _EVICTION_ORDER
            and _EVICTION_ORDER[t["origin"]] < _EVICTION_ORDER.get(origin, 1)
        ]
        candidates.sort(key=lambda t: (
            _EVICTION_ORDER[t["origin"]], t.get("promoted_at", "")
        ))
        if not candidates:
            logger.warning(
                "[promotion] cap %d reached and nothing evictable — %s NOT promoted",
                cap, symbol,
            )
            return {"status": "cap_full", "symbol": symbol,
                    "detail": f"managed-ticker cap {cap} reached"}
        evicted = candidates[0]
        evicted["enabled"] = False
        logger.info("[promotion] cap %d: evicted %s (origin=%s) for %s",
                    cap, evicted["sym"], evicted["origin"], symbol)

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
    return {"status": "promoted", "symbol": symbol, "cadence": _ORIGIN_CADENCE[origin]}


def demote_symbol(symbol: str) -> bool:
    """Disable a portfolio-origin managed entry (holding/watchlist removed).
    Manual entries — the original universe — are never touched."""
    symbol = symbol.strip().upper()
    tickers = list(load_managed_tickers())
    entry = next((t for t in tickers if t.get("sym") == symbol), None)
    if not entry or entry.get("origin") not in _ORIGIN_CADENCE:
        return False
    entry["enabled"] = False
    save_managed_tickers(tickers)
    logger.info("[promotion] %s demoted (enabled=False)", symbol)
    return True


def due_for_review(entry: dict, review_date: date) -> bool:
    """Cadence gate for the daily review job: held names review daily,
    watchlist names weekly (config portfolio.weekly_review_weekday)."""
    if entry.get("cadence", "daily") != "weekly":
        return True
    return review_date.weekday() == settings.PORTFOLIO_WEEKLY_REVIEW_WEEKDAY
