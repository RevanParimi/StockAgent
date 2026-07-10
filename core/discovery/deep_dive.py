"""
Compass Phase B — Stage-3 LLM deep-dive (spec §6.3).

Top weekly candidates run the existing orchestrator path (unified analyst,
ONE reasoning call per name — generic graph for sectors without a native
one). Deterministic entry zone and ATR-scaled invalidation level are
computed here, NOT by the LLM (spec §9.4: every idea carries "thesis dead
below X").

LLM cost cap: at most DISCOVERY_DEEP_DIVE_COUNT dives per weekly run;
symbols already managed or already on the shelf are skipped BEFORE any
LLM call.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.config import settings
from backend.shared.schemas.discovery import DeepDiveResult, DiscoveryCandidate
from core.discovery.shelf import ShelfStore
from core.intelligence.rl.workflows.sector_router import NATIVE_SECTORS, get_orchestrator
from services.api.log_buffer import load_managed_tickers
from services.data.fetchers.surveillance import get_symbol_meta
from services.data.stores.eod_store import EodStore

logger = logging.getLogger(__name__)

# NSE meta "industry" keyword -> our sector key (lowercase substring match,
# first hit wins). Keys must satisfy promotion._SECTOR_RE.
_INDUSTRY_SECTOR_KEYWORDS: list[tuple[str, str]] = [
    ("pharma", "pharma"), ("healthcare", "pharma"), ("hospital", "pharma"),
    ("bank", "banking_bfsi"), ("financ", "banking_bfsi"), ("nbfc", "banking_bfsi"),
    ("software", "it_sector"), ("information technology", "it_sector"), ("it services", "it_sector"),
    ("power", "renewable_energy"), ("renewable", "renewable_energy"), ("electric utilit", "renewable_energy"),
    ("auto", "automobile"), ("tyre", "automobile"),
    ("fmcg", "fmcg"), ("consumer", "fmcg"), ("food", "fmcg"), ("beverage", "fmcg"),
    ("steel", "metals"), ("metal", "metals"), ("mining", "metals"), ("aluminium", "metals"),
    ("oil", "oilgas"), ("gas", "oilgas"), ("petro", "oilgas"), ("refin", "oilgas"),
    ("cement", "infra"), ("construction", "infra"), ("infrastructure", "infra"),
    ("chemical", "chemicals"), ("fertil", "agrochem"), ("agro", "agrochem"),
    ("defence", "defence"), ("aerospace", "defence"),
    ("insurance", "insurance"), ("logistic", "logistics"), ("transport", "logistics"),
    ("media", "media"), ("entertainment", "media"),
    ("realty", "realestate"), ("real estate", "realestate"),
    ("retail", "retail"), ("e-commerce", "retail"),
    ("hotel", "hospitality"), ("tourism", "hospitality"),
    ("telecom", "telecom"),
    ("capital goods", "capgoods"), ("electrical equipment", "capgoods"), ("engineering", "capgoods"),
]


def infer_sector(symbol: str) -> str:
    """Best-effort sector key: registry exact hit -> NSE meta industry
    keyword -> 'generic'. Never raises."""
    symbol = symbol.strip().upper()
    try:
        from backend.sectors.registry import TICKER_SECTOR
        if symbol in TICKER_SECTOR:
            return TICKER_SECTOR[symbol]
    except Exception as exc:
        logger.debug("[deep_dive] registry lookup failed for %s: %s", symbol, exc)

    try:
        meta = get_symbol_meta(symbol)
        industry = (meta.get("industry") or "").lower()
        for keyword, sector in _INDUSTRY_SECTOR_KEYWORDS:
            if keyword in industry:
                return sector
    except Exception as exc:
        logger.debug("[deep_dive] meta industry lookup failed for %s: %s", symbol, exc)

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


def run_deep_dives(
    candidates: list[DiscoveryCandidate], on: date, max_n: int | None = None
) -> list[DeepDiveResult]:
    """Run at most max_n (default DISCOVERY_DEEP_DIVE_COUNT) one-call dives
    over the ranked candidates, skipping managed/shelved names. Per-candidate
    failures are non-fatal."""
    limit = max_n or settings.DISCOVERY_DEEP_DIVE_COUNT
    try:
        managed = {t["sym"] for t in load_managed_tickers() if t.get("enabled", True)}
    except Exception:
        managed = set()
    try:
        shelved = {i.symbol for i in ShelfStore().load().ideas if i.status == "active"}
    except Exception:
        shelved = set()

    window = EodStore().load_window(end=on, sessions=90)
    results: list[DeepDiveResult] = []

    for cand in candidates:
        if len(results) >= limit:
            break
        if cand.symbol in managed or cand.symbol in shelved:
            logger.debug("[deep_dive] %s skipped (managed/shelved)", cand.symbol)
            continue
        if any(r.symbol == cand.symbol for r in results):
            continue        # IPO candidate may also pass the quant screen
        try:
            sector = infer_sector(cand.symbol)
            report = get_orchestrator(sector).analyse(cand.symbol)
            sym_win = window[window["symbol"] == cand.symbol]
            atr = _atr_pct(sym_win)
            stop_pct = max(8.0, min(22.0, settings.ADVISOR_STOP_ATR_MULT * atr))
            results.append(DeepDiveResult(
                symbol=cand.symbol,
                sector=sector,
                graph="native" if sector in NATIVE_SECTORS else "generic",
                conviction=float(report.final_score),
                verdict=str(report.verdict),
                thesis=str(report.investment_thesis)[:800],
                entry_low=round(cand.close * 0.97, 2),
                entry_high=round(cand.close * 1.02, 2),
                invalidation_level=round(cand.close * (1 - stop_pct / 100.0), 2),
                close=cand.close,
                composite=cand.composite,
                dive_date=on.isoformat(),
            ))
            logger.info("[deep_dive] %s sector=%s conviction=%.2f verdict=%s",
                        cand.symbol, sector, report.final_score, report.verdict)
        except Exception as exc:
            logger.warning("[deep_dive] %s failed (non-fatal): %s", cand.symbol, exc)
    return results
