"""
Compass Phase B — Stage-3 LLM deep-dive (spec §6.3).

Top weekly candidates run the existing orchestrator path (unified analyst,
ONE reasoning call per name — generic graph for sectors without a native
one). Deterministic entry zone and ATR-scaled invalidation level are
computed here, NOT by the LLM (spec §9.4: every idea carries "thesis dead
below X").

LLM cost cap: at most DISCOVERY_DEEP_DIVE_COUNT analyst calls per weekly
run, a failed call included. Skipped BEFORE any call: a symbol NSE does not
list as a company, a managed symbol, and one already on the shelf unless the
candidate is a re-dive (flag "redive", PR-004).
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.config import settings
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate
from core.discovery.shelf import ShelfStore
from core.discovery.universe import COMPANY, instrument_kind
from core.intelligence.rl.workflows.sector_router import NATIVE_SECTORS, get_orchestrator
from services.api.log_buffer import load_managed_tickers
from services.data.fetchers.bhavcopy import load_listing
from services.data.fetchers.surveillance import market_classification
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)

# The one industry source (FIX-011) is Yahoo Finance's classification, the
# one PR-004's shelf sector cap stores: it answers for nearly every NSE
# company, and its industries tell an insurer from a bank and a defence maker
# from other capital goods. NSE's own industry is in its index lists only
# (750 companies) and is coarser; its per-symbol meta API answers 404.
# Probed 2026-11-01 over the registry's 202 tickers: Yahoo classified 193,
# NSE's Nifty Total Market list held 176.
#
# Yahoo industry -> our sector key, exact match; then Yahoo sector -> key for
# the sectors that name one key whatever the industry. Anything else is
# "generic". The keys follow the registry's curated map, so power utilities
# are "renewable_energy" and coal is "metals"; every key is a registry sector.
_YAHOO_INDUSTRY_SECTOR: dict[str, str] = {
    **dict.fromkeys(("Auto Manufacturers", "Auto Parts", "Auto & Truck Dealerships",
                     "Recreational Vehicles", "Farm & Heavy Construction Machinery"),
                    "automobile"),
    **dict.fromkeys(("Insurance - Life", "Insurance - Diversified",
                     "Insurance - Property & Casualty", "Insurance - Reinsurance",
                     "Insurance - Specialty", "Insurance Brokers"), "insurance"),
    **dict.fromkeys(("Information Technology Services", "Software - Application",
                     "Software - Infrastructure"), "it_sector"),
    **dict.fromkeys(("Consumer Electronics", "Electronic Components", "Semiconductors",
                     "Semiconductor Equipment & Materials", "Computer Hardware",
                     "Communication Equipment", "Scientific & Technical Instruments",
                     "Electronics & Computer Distribution",
                     "Furnishings, Fixtures & Appliances"), "tech"),
    **dict.fromkeys(("Solar", "Utilities - Renewable", "Utilities - Independent Power Producers",
                     "Utilities - Regulated Electric", "Utilities - Diversified"),
                    "renewable_energy"),
    "Utilities - Regulated Gas": "oilgas",
    **dict.fromkeys(("Steel", "Aluminum", "Copper", "Other Industrial Metals & Mining", "Gold",
                     "Silver", "Other Precious Metals & Mining", "Thermal Coal", "Coking Coal"),
                    "metals"),
    **dict.fromkeys(("Specialty Chemicals", "Chemicals"), "chemicals"),
    "Agricultural Inputs": "agrochem",
    **dict.fromkeys(("Building Materials", "Engineering & Construction",
                     "Infrastructure Operations"), "infra"),
    "Residential Construction": "realestate",
    "Aerospace & Defense": "defence",
    **dict.fromkeys(("Specialty Industrial Machinery", "Electrical Equipment & Parts",
                     "Industrial Distribution", "Building Products & Equipment", "Conglomerates",
                     "Tools & Accessories", "Metal Fabrication",
                     "Pollution & Treatment Controls"), "capgoods"),
    **dict.fromkeys(("Integrated Freight & Logistics", "Railroads", "Marine Shipping",
                     "Airlines", "Airports & Air Services", "Trucking"), "logistics"),
    "Telecom Services": "telecom",
    **dict.fromkeys(("Broadcasting", "Entertainment", "Electronic Gaming & Multimedia",
                     "Publishing", "Advertising Agencies"), "media"),
    **dict.fromkeys(("Lodging", "Resorts & Casinos", "Restaurants", "Travel Services"),
                    "hospitality"),
    **dict.fromkeys(("Apparel Retail", "Apparel Manufacturing", "Department Stores",
                     "Internet Retail", "Specialty Retail", "Home Improvement Retail",
                     "Luxury Goods", "Footwear & Accessories", "Discount Stores",
                     "Grocery Stores"), "retail"),
    **dict.fromkeys(("Household & Personal Products", "Packaged Foods",
                     "Beverages - Non-Alcoholic", "Beverages - Brewers",
                     "Beverages - Wineries & Distilleries", "Tobacco", "Confectioners",
                     "Farm Products", "Food Distribution"), "fmcg"),
}
_YAHOO_SECTOR_SECTOR: dict[str, str] = {
    "Healthcare": "pharma", "Financial Services": "banking_bfsi",
    "Real Estate": "realestate", "Energy": "oilgas",
}


def sector_from_classification(classification: dict | None) -> str:
    """Our sector key for a Yahoo classification ({"sector", "industry"}),
    "generic" when neither names one. Example: {"sector": "Healthcare",
    "industry": "Drug Manufacturers - Specialty & Generic"} is "pharma";
    {"sector": "Industrials", "industry": "Aerospace & Defense"} is "defence";
    {"sector": "Industrials", "industry": "Staffing & Employment Services"}
    is "generic"."""
    classification = classification or {}
    industry = str(classification.get("industry") or "").strip()
    sector = str(classification.get("sector") or "").strip()
    return (_YAHOO_INDUSTRY_SECTOR.get(industry)
            or _YAHOO_SECTOR_SECTOR.get(sector) or "generic")


def infer_sector(symbol: str, classification: dict | None = None) -> str:
    """Best-effort sector key: the registry's ticker map, else the market
    classification (`classification` when the caller has it, else Yahoo's,
    fetched here), else "generic". Never raises.

    A key decides the graph (automobile, banking_bfsi, it_sector and
    renewable_energy have native graphs; every other key runs the generic
    graph) and the prediction-store directory. It is read only for a stock
    with no managed record: a managed stock's own sector always wins
    (`candidates.holding_sector`), and the deep dive skips managed stocks."""
    symbol = symbol.strip().upper()
    try:
        from backend.sectors.registry import TICKER_SECTOR
        if symbol in TICKER_SECTOR:
            return TICKER_SECTOR[symbol]
    except Exception as exc:
        logger.debug("[deep_dive] registry lookup failed for %s: %s", symbol, exc)

    try:
        if classification is None:
            classification = market_classification(symbol)
        return sector_from_classification(classification)
    except Exception as exc:
        logger.debug("[deep_dive] classification lookup failed for %s: %s", symbol, exc)
    return "generic"


def _atr_pct(sym_win: pd.DataFrame, period: int = 20) -> float:
    """period-day mean True Range as % of latest close. 15.0 fallback."""
    try:
        w = sym_win.sort_values("date").tail(period + 1)
        prev_close = w["close"].shift(1)
        tr = pd.concat([
            w["high"] - w["low"],
            (w["high"] - prev_close).abs(),
            (w["low"] - prev_close).abs(),
        ], axis=1).max(axis=1).dropna()
        close = float(w["close"].iloc[-1])
        if tr.empty or close <= 0:
            return 15.0
        return float(tr.mean() / close * 100.0)
    except Exception:
        return 15.0


def entry_levels(close: float, sym_win: pd.DataFrame) -> tuple[float, float, float]:
    """(entry_low, entry_high, invalidation_level) around `close`: the band an
    autopilot buy must sit in (SA-050) and the ATR-scaled "thesis dead below
    X". Shared by the deep dive and a watchlist BUY candidate."""
    atr = _atr_pct(sym_win)
    stop_pct = max(8.0, min(22.0, settings.ADVISOR_STOP_ATR_MULT * atr))
    return (round(close * 0.97, 2), round(close * 1.02, 2),
            round(close * (1 - stop_pct / 100.0), 2))


def _latest_close(sym_win: pd.DataFrame) -> float:
    if sym_win.empty:
        return 0.0
    close = float(sym_win.sort_values("date")["close"].iloc[-1])
    return close if close > 0 else 0.0


def run_deep_dives(
    candidates: list[DiscoveryCandidate], on: date, max_n: int | None = None,
    listing: dict | None = None,
) -> list[DeepDiveResult]:
    """Make at most max_n (default DISCOVERY_DEEP_DIVE_COUNT) analyst calls
    over the ranked candidates. Every call counts, a failed one included, so
    the budget is a bound on LLM spend. Per-candidate failures are non-fatal.

    No call is made for a symbol NSE does not list as a company (`listing`,
    default the cached one; no listing means no symbol can be verified, so
    nothing is dived), for a managed symbol, for a repeat, or for one already
    on the shelf unless the candidate is flagged "redive". Every answered
    call is returned, an abstained one included in either gate mode: the
    dive memo remembers it, the shelf refuses a new idea from it under the
    enforced gate (`ShelfStore.apply_deep_dives`) and drops a re-dived idea
    with the reason. A candidate without a close (a re-dive carries 0.0)
    takes its latest close in the EOD window."""
    limit = max_n or settings.DISCOVERY_DEEP_DIVE_COUNT
    try:
        managed = {t["sym"] for t in load_managed_tickers() if t.get("enabled", True)}
    except Exception:
        managed = set()
    try:
        shelved = {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception:
        shelved = set()
    if listing is None:
        listing = load_listing()
    if listing is None:
        logger.warning("[deep_dive] no instrument listing: no symbol can be verified as "
                       "a company, so no deep dive runs")

    window = EodStore().load_window(end=on, sessions=90)
    results: list[DeepDiveResult] = []
    attempted: set[str] = set()

    for cand in candidates:
        if len(attempted) >= limit:
            break
        redive = "redive" in cand.flags
        if cand.symbol in managed or (cand.symbol in shelved and not redive):
            logger.debug("[deep_dive] %s skipped (managed/shelved)", cand.symbol)
            continue
        if cand.symbol in attempted:
            continue        # IPO candidate may also pass the quant screen
        kind = instrument_kind(cand.symbol, listing)
        if kind != COMPANY:
            logger.info("[deep_dive] %s skipped: NSE listing says %s, not a company",
                        cand.symbol, kind)
            continue
        sym_win = (window[window["symbol"] == cand.symbol] if "symbol" in window.columns
                   else window.iloc[0:0])
        close = cand.close if cand.close > 0 else _latest_close(sym_win)
        if close <= 0:
            logger.info("[deep_dive] %s skipped: no close to set an entry band", cand.symbol)
            continue
        attempted.add(cand.symbol)
        try:
            classified = market_classification(cand.symbol)
            sector = infer_sector(cand.symbol, classified)
            report = get_orchestrator(sector).analyse(cand.symbol)
            # SA-003: a shelf idea is a future SWITCH destination (a buy), so
            # it must not be minted from an abstained analysis. The shelf
            # applies that; the result is still returned so the memo keeps it.
            gate_status, gate_run_id, gate_reasons = dg.report_gate(report)
            if not dg.is_actionable(gate_status):
                dg.record_gate_decision(
                    consumer="discovery", ticker=cand.symbol, skipped="shelf idea",
                    status=gate_status, reasons=gate_reasons, run_id=gate_run_id,
                    enforced=dg.enforcing(), on_date=on.isoformat(),
                )
            entry_low, entry_high, invalidation = entry_levels(close, sym_win)
            results.append(DeepDiveResult(
                symbol=cand.symbol,
                sector=sector,
                graph="native" if sector in NATIVE_SECTORS else "generic",
                conviction=float(report.final_score),
                verdict=str(report.verdict),
                thesis=str(report.investment_thesis)[:800],
                entry_low=entry_low,
                entry_high=entry_high,
                invalidation_level=invalidation,
                close=close,
                composite=cand.composite,
                dive_date=on.isoformat(),
                data_gate=gate_status,
                market_sector=classified.get("sector", ""),
                industry=classified.get("industry", ""),
            ))
            logger.info("[deep_dive] %s sector=%s conviction=%.2f verdict=%s",
                        cand.symbol, sector, report.final_score, report.verdict)
        except Exception as exc:
            logger.warning("[deep_dive] %s failed (non-fatal): %s", cand.symbol, exc)
    return results
