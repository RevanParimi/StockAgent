"""
Compass Phase B — Stage-3 LLM deep-dive (spec §6.3).

Top weekly candidates run the existing orchestrator path (unified analyst,
ONE reasoning call per name — generic graph for sectors without a native
one). Deterministic entry zone and ATR-scaled invalidation level are
computed here, NOT by the LLM (spec §9.4: every idea carries "thesis dead
below X").

LLM cost cap: at most DISCOVERY_DEEP_DIVE_COUNT analyst calls per weekly
run, a failed call included. Skipped BEFORE any call: a symbol NSE does not
list as a company, a managed symbol unless the autopilot sold it (flag "sold",
FIX-025), and one already on the shelf unless the candidate is a re-dive (flag
"redive", PR-004).

FIX-026: the same analyst call names the stock's sector key from the
configured list (core/discovery/sector_naming.py). Yahoo Finance's
classification (FIX-011's one industry source: it tells an insurer from a
bank and a defence maker from other capital goods) goes into the question as
evidence and is stored beside the key; no fixed table maps it to a key.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.config import settings
from backend.shared.pipeline import decision_gate as dg
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate
from core.discovery.sector_naming import (
    configured_sectors, decide_key, graph_guess, known_key, read_answer, sector_question,
    unnamed_why)
from core.discovery.shelf import ShelfStore
from core.discovery.universe import COMPANY, instrument_kind
from core.intelligence.rl.workflows.sector_router import NATIVE_SECTORS, get_orchestrator
from services.api.log_buffer import load_managed_tickers
from services.data.fetchers.bhavcopy import load_listing
from services.data.fetchers.surveillance import market_classification
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)


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
    nothing is dived), for a managed symbol unless the candidate is flagged
    "sold" (the autopilot sold it, FIX-025), for a repeat, or for one already
    on the shelf unless the candidate is flagged "redive". Every answered
    call is returned, an abstained one included in either gate mode: the
    dive memo remembers it, the shelf refuses a new idea from it under the
    enforced gate (`ShelfStore.apply_deep_dives`) and drops a re-dived idea
    with the reason. A candidate without a close (a re-dive carries 0.0)
    takes its latest close in the EOD window.

    Each call also names the stock's sector key (FIX-026): a stock that has
    one keeps it (its managed record's, the ticker map's, or its idea's
    named key) and runs that key's graph; another runs `graph_guess`'s graph
    and takes the answer, checked against the configured keys. The dive
    records how (`sector_reading`)."""
    limit = max_n or settings.DISCOVERY_DEEP_DIVE_COUNT
    try:
        tickers = [t for t in load_managed_tickers() if isinstance(t, dict)]
    except Exception:
        tickers = []
    managed = {t["sym"] for t in tickers if t.get("sym") and t.get("enabled", True)}
    # Every managed record's key, enabled or not, read as the daily review
    # reads it (default "automobile"), the key its forecasts live under.
    managed_keys = {str(t.get("sym") or "").strip().upper(): str(t.get("sector", "automobile") or "")
                    for t in tickers if str(t.get("sym") or "").strip()}
    try:
        ideas = {i.symbol: i for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception:
        ideas = {}
    shelved = set(ideas)
    keys = configured_sectors()
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
        # FIX-025: a stock the autopilot bought stays managed after its sale,
        # and a new dive is all that can bring it back.
        sold = "sold" in cand.flags
        if (cand.symbol in managed and not sold) or (cand.symbol in shelved and not redive):
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
            known = known_key(cand.symbol, managed=managed_keys,
                              idea=ideas.get(cand.symbol), keys=keys)
            route = known[0] or graph_guess(classified)
            report = get_orchestrator(route).analyse(
                cand.symbol, sector_question=sector_question(classified, keys))
            reading = read_answer(getattr(report, "sector_answer", None), keys, classified)
            sector, reading = decide_key(reading, known)
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
            result = DeepDiveResult(
                symbol=cand.symbol,
                sector=sector,
                graph="native" if route in NATIVE_SECTORS else "generic",
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
                sector_reading=reading,
            )
            results.append(result)
            logger.info("[deep_dive] %s sector=%s (%s) conviction=%.2f verdict=%s",
                        cand.symbol, sector, reading.source, report.final_score, report.verdict)
            # Loud in the week's summary and the watchdog's sector_keys check;
            # INFO here so one problem does not also open an error-backlog issue.
            unnamed = unnamed_why(result, keys)
            if unnamed:
                logger.info("[deep_dive] %s has no sector key: %s; filed under the generic "
                            "graph, not bought until an analysis names one",
                            cand.symbol, unnamed)
        except Exception as exc:
            logger.warning("[deep_dive] %s failed (non-fatal): %s", cand.symbol, exc)
    return results
