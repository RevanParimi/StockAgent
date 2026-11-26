"""
Compass Phase B — Stage-3 LLM deep-dive (spec §6.3).

Top weekly candidates run the existing orchestrator path (unified analyst,
ONE reasoning call per name — generic graph for sectors without a native
one). Deterministic entry zone and ATR-scaled invalidation level are
computed here, NOT by the LLM (spec §9.4: every idea carries "thesis dead
below X").

LLM cost cap: at most DISCOVERY_DEEP_DIVE_COUNT analyst calls per weekly
run, a failed call included.

FIX-033: the dive asks for the exact NSE symbol (`exact_symbol`), so no model
is asked which company it means, and keeps a result only when the report is
of that symbol (`analysed_symbol`, read by every buy door): on 14 Nov a dive
asked for DEEPA analysed Deepak Nitrite (DEEPAKNTR) and the shelf filed its
BUY under DEEPA. Skipped BEFORE any call: a symbol NSE does not
list as a company, a managed symbol unless the autopilot sold it (flag "sold",
FIX-025), and one already on the shelf unless the candidate is a re-dive (flag
"redive", PR-004).

PR-047: a result keeps the model's own verdict (`model_verdict`) beside the
composite's band (`verdict`); the shelf takes it only when both are a BUY.

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
from backend.shared.pipeline.no_analysis import AnalysisUnavailable, UnlistedSymbol
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate
from core.discovery.sector_naming import (
    analysis_named_on, configured_sectors, decide_key, graph_guess, known_key, read_answer,
    sector_question, unnamed_why)
from core.discovery.shelf import ShelfStore, other_company, plain_symbol
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
    listing: dict | None = None, redive_room: int | None = None,
    tally: dict | None = None, evidence: dict | None = None,
) -> list[DeepDiveResult]:
    """Make at most max_n (default DISCOVERY_DEEP_DIVE_COUNT) analyst calls
    over the ranked candidates. Every call counts, a failed one included, so
    the budget is a bound on LLM spend. Per-candidate failures are non-fatal.

    `redive_room` (PR-037; None = no limit): at most that many calls go to
    candidates flagged "redive" in list order. A later re-dive is held back
    and offered after the last candidate, in its order, with the calls the
    others leave. Only a call counts: a re-dive skipped below (a held stock's
    idea) takes no room. `tally`, when given, receives `calls` (made),
    `redive_calls`, `late` (held back, then called), `deferred` (a re-dive
    that would have been called, held back or past the budget, and never
    called) and `other_company` ({symbol asked for: symbol the report is of},
    FIX-033: no result, no idea and no memo entry; the call still counts). Example: room 2, re-dives A, B, C then screen ranks X, Y,
    budget 4: calls A, B, X, Y; C is deferred.

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
    one keeps it (its managed record's, the ticker map's, or the key an
    earlier analysis named for its idea) and runs that key's graph; another
    runs `graph_guess`'s graph and takes the answer, checked against the
    configured keys. The dive records how (`sector_reading`), and which
    dive's analysis named the key (`named_on`, FIX-030).

    `evidence`, when given, receives each returned dive's data bundle by
    symbol (PR-017: the bare judge reads the same evidence)."""
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
    # (candidate, held back): a held-back re-dive returns at the end once.
    queue: list[tuple[DiscoveryCandidate, bool]] = [(c, False) for c in candidates]
    redive_calls = 0
    late: list[str] = []
    misfiled: dict[str, str] = {}

    k = 0
    while k < len(queue):
        cand, held_back = queue[k]
        k += 1
        spent = len(attempted) >= limit
        redive = "redive" in cand.flags
        if spent and not redive:
            continue        # PR-037: past the budget a re-dive is only looked at, to report it
        # FIX-025: a stock the autopilot sold can still have an enabled
        # managed entry: an original entry, one another portfolio still
        # holds, or one a user's own watchlist keeps (FIX-028 releases the
        # rest). A new dive is all that can bring it back to the shelf.
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
        if redive and not held_back and (
                spent or (redive_room is not None and redive_calls >= redive_room)):
            queue.append((cand, True))      # PR-037: behind the other candidates
            continue
        if spent:
            continue
        attempted.add(cand.symbol)
        if redive:
            redive_calls += 1
            if held_back:
                late.append(cand.symbol)
        try:
            classified = market_classification(cand.symbol)
            idea = ideas.get(cand.symbol)
            known = known_key(cand.symbol, managed=managed_keys, idea=idea, keys=keys)
            route = known[0] or graph_guess(classified)
            orchestrator = get_orchestrator(route)
            report = orchestrator.analyse(
                cand.symbol, sector_question=sector_question(classified, keys),
                exact_symbol=True)
            # FIX-033: the analysis must be of the stock asked for. One of
            # another company keeps no idea and no memo entry.
            analysed = plain_symbol(getattr(report, "ticker", ""))
            wrong = (other_company(cand.symbol, analysed) if analysed
                     else "the report names no symbol")
            if wrong:
                misfiled[cand.symbol] = analysed or "?"
                logger.warning("[deep_dive] %s: %s; not shelved", cand.symbol, wrong)
                continue
            reading = read_answer(getattr(report, "sector_answer", None), keys, classified)
            sector, reading = decide_key(reading, known, on=on.isoformat(),
                                         named_on=analysis_named_on(idea, keys))
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
                model_verdict=str(getattr(report, "model_verdict", "") or ""),
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
                analysed_symbol=analysed,
            )
            results.append(result)
            if evidence is not None:
                evidence[cand.symbol] = getattr(orchestrator, "_last_bundle", None)
            logger.info("[deep_dive] %s sector=%s (%s) conviction=%.2f verdict=%s model=%s",
                        cand.symbol, sector, reading.source, report.final_score, report.verdict,
                        result.model_verdict or "?")
            # Loud in the week's summary and the watchdog's sector_keys check;
            # INFO here so one problem does not also open an error-backlog issue.
            unnamed = unnamed_why(result, keys)
            if unnamed:
                logger.info("[deep_dive] %s has no sector key: %s; filed under the generic "
                            "graph, not bought until an analysis names one",
                            cand.symbol, unnamed)
        except AnalysisUnavailable:
            # CLEAN-005: no analysis, no idea and no memo entry, so a later
            # run can dive it again; the orchestrator logged and counted it.
            continue
        except UnlistedSymbol as exc:
            # FIX-033: the listing checked above holds it, so only a listing
            # that changed in between gets here.
            logger.warning("[deep_dive] %s not analysed: %s", cand.symbol, exc)
        except Exception as exc:
            logger.warning("[deep_dive] %s failed (non-fatal): %s", cand.symbol, exc)
    if tally is not None:
        tally.update(
            calls=len(attempted), redive_calls=redive_calls, late=late,
            deferred=[c.symbol for c, back in queue
                      if back and c.symbol not in attempted],
            other_company=misfiled)
    return results
