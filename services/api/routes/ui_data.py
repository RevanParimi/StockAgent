"""
services/api/routes/ui_data.py
==============================
FastAPI routes that feed the beginner prototype UI.

All endpoints are prefixed /ui/* and are served from port 8001.
The prototype HTML is mounted at /app (via StaticFiles in server.py).

Since the prototype is served from the same origin (:8001) as these routes,
there are no CORS complications for the prototype itself.

Endpoints
---------
GET  /ui/bootstrap           — all data in one shot (agents + tickers + market)
GET  /ui/agents              — 9 agent definitions + current weights
PUT  /ui/agents/weights      — persist user-adjusted agent weights
GET  /ui/tickers             — all tickers with latest score + live price
GET  /ui/trending            — tickers ranked by score delta between last two runs
GET  /ui/market/summary      — market pulse, drivers, sector changes, sparkline
POST /ui/chat                — conversational AI assistant reply
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from services.api.auth import check_scheduler_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui", tags=["UI"])

# User-overridden agent weights persisted between server restarts
_CUSTOM_WEIGHTS_PATH = Path("data/agent_weights.json")
# User-overridden agent task flags persisted between server restarts
_CUSTOM_TASKS_PATH   = Path("data/agent_tasks.json")
# User-curated watchlist (overrides the hardcoded default)
_WATCHLIST_PATH      = Path("data/watchlist.json")
# User-customised category ticker lists (overrides hardcoded _CATEGORIES tickers)
_CATEGORY_TICKERS_PATH = Path("data/category_tickers.json")
# Root directory where RL prediction envelopes are stored (sector/ticker/cycle.json)
_PREDICTIONS_DIR = Path("data/predictions")
_RL_INDEX_NAMES = frozenset({"SENSEX", "NIFTY", "NIFTY50", "NSEI", "BSESN"})


# ---------------------------------------------------------------------------
# Static agent metadata
# Kept here so the UI always has consistent labels, icons, and descriptions
# even before any analyses have run.
# ---------------------------------------------------------------------------

_AGENT_META_BY_SECTOR: dict[str, list[dict]] = {

    "automobile": [
        {"key":"sales_demand",      "name":"Sales & Demand",      "icon":"📊",
         "beginner":"How many cars are actually selling each month.",
         "desc":"Tracks FADA/SIAM dispatches, EV Vahan registrations, dealer inventory, DGFT exports, used car price index.",
         "sources":["Serper news","FADA","SIAM","Vahan"]},
        {"key":"fundamentals",      "name":"Fundamentals",        "icon":"📈",
         "beginner":"Whether the company makes more money each quarter.",
         "desc":"Revenue & EBITDA delta, margin vs peers, order book, headcount, FII/DII flow.",
         "sources":["yfinance","Serper news","NSE filings"]},
        {"key":"pattern_analysis",  "name":"Pattern Analysis",    "icon":"🔍",
         "beginner":"Reads the price chart for buying/selling pressure.",
         "desc":"Price cycle, RSI/MACD/Bollinger, support/resistance, Nifty Auto relative strength.",
         "sources":["yfinance OHLCV","RSI/MACD indicators"]},
        {"key":"raw_materials",     "name":"Raw Materials",       "icon":"⚙️",
         "beginner":"How costly the metals & oil they buy are right now.",
         "desc":"Steel, aluminium, palladium, crude — input cost stack.",
         "sources":["yfinance commodities","Serper news"]},
        {"key":"sentiment",         "name":"Sentiment",           "icon":"💬",
         "beginner":"What the news, social media & forums are saying.",
         "desc":"News tone, mgmt commentary, Twitter/Reddit/YouTube spikes.",
         "sources":["Serper news","Twitter/Reddit","YouTube"]},
        {"key":"policy_regulatory", "name":"Policy & Regulatory", "icon":"📋",
         "beginner":"Government rules helping or hurting the company.",
         "desc":"FAME/EV subsidies, BS6 emissions, PLI scheme, state incentives.",
         "sources":["Tavily","Serper","gov circulars"]},
        {"key":"competitive_intel", "name":"Competitive Intel",   "icon":"🎯",
         "beginner":"How rivals like Tata, Hyundai, Kia are doing.",
         "desc":"EV market share, model pipeline, JV/M&A, ADAS ratings.",
         "sources":["Serper news","peer baskets"]},
        {"key":"risk_macro",        "name":"Risk & Macro",        "icon":"⚠️",
         "beginner":"Big-picture risks: currency, oil, interest rates.",
         "desc":"INR/USD, crude, RBI repo, geopolitics, China supply chain.",
         "sources":["yfinance INR/crude","macro cache"]},
        {"key":"valuation_catalyst","name":"Valuation & Catalyst","icon":"💎",
         "beginner":"Whether the stock is cheap or expensive right now.",
         "desc":"P/E vs peers, earnings yield vs G-Sec, 60–90 day event catalysts.",
         "sources":["LLM knowledge","peer P/E","earnings calendar"]},
    ],

    "banking_bfsi": [
        {"key":"fundamentals",    "name":"Fundamentals",        "icon":"📈",
         "beginner":"Whether the bank earns quality money — not just one-time gains.",
         "desc":"Earnings quality (NII vs treasury), NIM, CRAR, RoA/RoE, loan book mix.",
         "sources":["yfinance quarterly","RBI filings","Serper"]},
        {"key":"risk",            "name":"Credit Risk",         "icon":"⚠️",
         "beginner":"How many loans are going bad and how fast.",
         "desc":"GNPA%, slippage ratio, SMA-1/2 build-up, concentration risk, cyber fraud exposure.",
         "sources":["yfinance","RBI","Serper"]},
        {"key":"macro_policy",    "name":"Macro & Policy",      "icon":"📋",
         "beginner":"How RBI's interest rate decisions affect the bank.",
         "desc":"RBI MPC repo rate cycle, system credit growth, LAF liquidity, regulatory circulars.",
         "sources":["RBI website","Serper","Tavily"]},
        {"key":"institutional",   "name":"Institutional Flow",  "icon":"🏦",
         "beginner":"What big investors and funds are doing with this bank.",
         "desc":"FII/DII shareholding delta, promoter pledge changes, AMFI MF flows, bulk/block deals.",
         "sources":["BSE/NSE filings","AMFI","Serper"]},
        {"key":"pattern_analysis","name":"Pattern Analysis",    "icon":"🔍",
         "beginner":"Reads the price chart for rate-cycle patterns.",
         "desc":"Price cycle vs RBI regimes, RSI/MACD, Nifty Bank relative strength.",
         "sources":["yfinance OHLCV","RSI/MACD indicators"]},
        {"key":"universe_setup",  "name":"Universe Setup",      "icon":"🗺️",
         "beginner":"How important this bank is in the Nifty Bank index.",
         "desc":"Index weight, PSU vs private peer rank, market-cap tier, corporate actions, rebalancing risk.",
         "sources":["NSE/BSE index data","AMFI"]},
    ],

    "it_sector": [
        {"key":"fundamentals",        "name":"Fundamentals",        "icon":"📈",
         "beginner":"Revenue growth, margins, deals won, and staff turnover.",
         "desc":"Constant-currency revenue growth, EBIT margins, TCV deal wins, attrition, valuation vs peers.",
         "sources":["yfinance quarterly","Serper press releases","NSE filings"]},
        {"key":"global_macro",        "name":"Global Macro",        "icon":"🌐",
         "beginner":"Whether US and European clients are cutting or spending on tech.",
         "desc":"US enterprise IT spend cycle, Fed rate impact, USD/INR, CHIPS Act, global M&A activity.",
         "sources":["Serper","Gartner/IDC headlines","yfinance forex"]},
        {"key":"risk_macro",          "name":"Risk Factors",        "icon":"⚠️",
         "beginner":"Specific risks: visa rules, AI disruption, client concentration.",
         "desc":"H1B/L1 visa denial trends, AI disruption risk, top-client concentration, FX hedging, talent supply.",
         "sources":["USCIS data","Serper","company filings"]},
        {"key":"peer_benchmark",      "name":"Peer Benchmark",      "icon":"🎯",
         "beginner":"How it ranks against TCS, Infosys, HCL, Wipro.",
         "desc":"Revenue growth rank, margin rank, TCV rank, attrition rank, P/E gap vs peer median.",
         "sources":["Serper quarterly comparisons","yfinance"]},
        {"key":"pattern_analysis",    "name":"Pattern Analysis",    "icon":"🔍",
         "beginner":"Price chart and Nifty IT relative performance.",
         "desc":"Price cycle, RSI/MACD momentum, support/resistance, Nifty IT beta.",
         "sources":["yfinance OHLCV","RSI/MACD indicators"]},
        {"key":"sentiment",           "name":"Sentiment",           "icon":"💬",
         "beginner":"How the AI narrative and management tone are being received.",
         "desc":"GenAI deal narrative strength, layoff signals, management tone, sector media coverage.",
         "sources":["Serper news","LinkedIn","company announcements"]},
        {"key":"transcript_nlp",      "name":"Transcript NLP",      "icon":"📝",
         "beginner":"What management actually said on the last earnings call.",
         "desc":"Guidance raised/cut, vertical mix, geography commentary, AI deal count, analyst pushback.",
         "sources":["Earnings call transcripts","Serper"]},
        {"key":"insider_smart_money", "name":"Institutional Flow",  "icon":"🏦",
         "beginner":"What funds and insiders are doing with this stock.",
         "desc":"FII F&O futures positioning, promoter SAST filings, AMFI MF holdings, bulk deals, director trades.",
         "sources":["BSE/NSE filings","AMFI","SEBI disclosures"]},
    ],

    "renewable_energy": [
        {"key":"fundamentals",    "name":"Fundamentals",        "icon":"📈",
         "beginner":"Whether plants produce efficiently and debt is under control.",
         "desc":"CUF vs benchmark, EBITDA/MW, DSCR (>1.2x healthy), DISCOM receivables, leverage.",
         "sources":["yfinance quarterly","company filings","Serper"]},
        {"key":"business",        "name":"Business Quality",    "icon":"🔋",
         "beginner":"Quality of energy assets and long-term contracts.",
         "desc":"Solar/wind mix, PPA counterparty quality, pipeline credibility, customer diversification.",
         "sources":["Serper","MNRE filings","company PPAs"]},
        {"key":"valuation",       "name":"Valuation",           "icon":"💎",
         "beginner":"Whether the stock is cheap vs peers on an asset basis.",
         "desc":"EV/MW vs Solar ₹4-6Cr/MW benchmark, EV/EBITDA 15-25x, implied IRR vs WACC.",
         "sources":["Serper","BloombergNEF proxies","peer comps"]},
        {"key":"sentiment_policy","name":"Policy & Sentiment",  "icon":"📋",
         "beginner":"Government auction health and renewable energy policy support.",
         "desc":"MNRE auctions awarded GW, Union Budget allocations, RPO/must-run, RBI rate WACC impact, module prices.",
         "sources":["Tavily","MNRE portal","BloombergNEF","Serper"]},
        {"key":"technical",       "name":"Pattern Analysis",    "icon":"🔍",
         "beginner":"Price chart and Nifty Energy index moves.",
         "desc":"Price cycle, RSI/MACD, support/resistance zones, Nifty Energy relative strength.",
         "sources":["yfinance OHLCV","RSI/MACD indicators"]},
        {"key":"risk",            "name":"Risk Monitor",        "icon":"⚠️",
         "beginner":"Whether DISCOMs are paying and plants are running.",
         "desc":"DISCOM credit health (PFC ratings), curtailment risk, PPA tariff protection, execution delay, promoter pledge.",
         "sources":["PFC reports","CERC","BSE/NSE","Serper"]},
    ],
}

# Backward-compat alias — existing code that reads _AGENT_META gets automobile agents
_AGENT_META: list[dict] = _AGENT_META_BY_SECTOR["automobile"]

_ALL_TICKERS: list[dict] = [
    {"sym": "MARUTI",      "name": "Maruti Suzuki India Ltd",        "yf": "MARUTI.NS"},
    {"sym": "TATAMOTORS",  "name": "Tata Motors (Passenger Veh) Ltd", "yf": "TMPV.NS"},
    {"sym": "M&M",         "name": "Mahindra & Mahindra Ltd",        "yf": "M&M.NS"},
    {"sym": "BAJAJ-AUTO",  "name": "Bajaj Auto Ltd",                 "yf": "BAJAJ-AUTO.NS"},
    {"sym": "HEROMOTOCO",  "name": "Hero MotoCorp Ltd",              "yf": "HEROMOTOCO.NS"},
    {"sym": "EICHERMOT",   "name": "Eicher Motors Ltd",              "yf": "EICHERMOT.NS"},
    {"sym": "TVSMOTORS",   "name": "TVS Motor Company Ltd",          "yf": "TVSMOTOR.NS"},  # fixed: was TVSMOTORS.NS
    {"sym": "ASHOKLEY",    "name": "Ashok Leyland Ltd",              "yf": "ASHOKLEY.NS"},
    # Extended universe — searchable and analysable, not fetched in every bootstrap
    {"sym": "APOLLOTYRE",  "name": "Apollo Tyres Ltd",               "yf": "APOLLOTYRE.NS"},
    {"sym": "MRF",         "name": "MRF Ltd",                        "yf": "MRF.NS"},
    {"sym": "CEATLTD",     "name": "CEAT Ltd",                       "yf": "CEATLTD.NS"},
    {"sym": "MOTHERSON",   "name": "Samvardhana Motherson Intl Ltd", "yf": "MOTHERSON.NS"},
    {"sym": "ESCORTS",     "name": "Escorts Kubota Ltd",             "yf": "ESCORTS.NS"},
    {"sym": "BOSCHLTD",    "name": "Bosch Ltd",                      "yf": "BOSCHLTD.NS"},
    {"sym": "BALKRISIND",  "name": "Balkrishna Industries Ltd",      "yf": "BALKRISIND.NS"},
    {"sym": "TIINDIA",     "name": "Tube Investments of India Ltd",  "yf": "TIINDIA.NS"},
]

# Core 8 tickers fetched in every bootstrap (price + score for all UI widgets).
# Extended tickers above are searchable/analysable but not batch-fetched on load.
_BOOTSTRAP_TICKERS = _ALL_TICKERS[:8]

_SECTOR_INDICES: list[dict] = [
    {"name": "Auto",    "yf": "^CNXAUTO"},
    {"name": "IT",      "yf": "^CNXIT"},
    {"name": "Banking", "yf": "^NSEBANK"},
    {"name": "Pharma",  "yf": "^CNXPHARMA"},
    {"name": "Energy",  "yf": "^CNXENERGY"},
    {"name": "FMCG",    "yf": "^CNXFMCG"},
]

_WATCHLIST_DEFAULT = ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "EICHERMOT"]

_CATEGORIES = [
    {
        "key": "ev", "icon": "⚡", "label": "EV-first", "count": 5, "color": "#7c3aed",
        "tickers": ["TATAMOTORS", "M&M", "TVSMOTORS", "BAJAJ-AUTO", "HEROMOTOCO"],
    },
    {
        "key": "mass", "icon": "🚗", "label": "Mass-market", "count": 8, "color": "#0891b2",
        "tickers": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "TVSMOTORS", "EICHERMOT", "ASHOKLEY"],
    },
    {
        "key": "premium", "icon": "💎", "label": "Premium", "count": 4, "color": "#d97706",
        "tickers": ["MARUTI", "EICHERMOT", "BAJAJ-AUTO", "M&M"],
    },
    {
        "key": "cv", "icon": "🚛", "label": "Commercial", "count": 3, "color": "#16a34a",
        "tickers": ["ASHOKLEY", "TATAMOTORS", "EICHERMOT"],
    },
    {
        "key": "2w", "icon": "🏍️", "label": "Two-wheelers", "count": 4, "color": "#dc2626",
        "tickers": ["HEROMOTOCO", "TVSMOTORS", "BAJAJ-AUTO", "EICHERMOT"],
    },
    {
        "key": "parts", "icon": "⚙️", "label": "Auto-parts", "count": 6, "color": "#475569",
        "tickers": ["BOSCHLTD", "MOTHERSON", "APOLLOTYRE", "CEATLTD", "MRF", "BALKRISIND"],
    },
]

_CHAT_SEEDS = [
    "Why is MARUTI rated STRONG BUY today?",
    "What does the Sales & Demand agent see this week?",
    "Compare Tata Motors vs M&M for EV exposure",
    "Which agent should I trust most for short-term moves?",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_store():
    from services.data.stores.score_store import ScoreStore
    return ScoreStore()


def _fetch_yf_price(yf_ticker: str) -> tuple[float, float]:
    """
    Return (current_price, change_pct). Sync — call via asyncio.to_thread.

    Uses period="1mo" — NSE tickers on yfinance frequently return empty on
    short periods due to exchange delays or weekend gaps.

    Fallback chain for NSE tickers (.NS):
      1. Try .NS with period="1mo"
      2. Try .BO (BSE) — Yahoo Finance sometimes serves BSE data when NSE is stale
      3. Return (0.0, 0.0) — caller handles gracefully
    """
    import yfinance as yf

    def _try(ticker: str) -> tuple[float, float] | None:
        try:
            hist = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)
            if hist.empty or len(hist) < 1:
                return None
            current = float(hist["Close"].iloc[-1])
            prev    = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            change  = (current - prev) / prev * 100 if prev else 0.0
            return round(current, 2), round(change, 2)
        except Exception:
            return None

    result = _try(yf_ticker)
    if result is not None:
        return result

    # BSE fallback for .NS tickers (Yahoo sometimes 404s NSE, BSE data is equivalent)
    if yf_ticker.endswith(".NS"):
        bse_ticker = yf_ticker[:-3] + ".BO"
        result = _try(bse_ticker)
        if result is not None:
            logger.debug("[ui_data] yfinance .NS failed, served %s via .BO fallback", yf_ticker)
            return result

    logger.debug("[ui_data] yfinance price unavailable for %s", yf_ticker)
    return 0.0, 0.0


def _fetch_yf_series(yf_ticker: str, days: int = 30) -> list[float]:
    """Return `days` closing prices for sparkline. Sync."""
    try:
        import yfinance as yf
        t = yf.Ticker(yf_ticker)
        hist = t.history(period=f"{days + 10}d", auto_adjust=True)
        if hist.empty:
            return []
        closes = hist["Close"].tail(days).tolist()
        return [round(v, 2) for v in closes]
    except Exception as exc:
        logger.debug("[ui_data] yfinance series fetch failed for %s: %s", yf_ticker, exc)
        return []


def _fetch_sector_changes() -> list[dict]:
    """Return sector daily % changes from NSE indices. Sync."""
    results = []
    for sector in _SECTOR_INDICES:
        price, pct = _fetch_yf_price(sector["yf"])
        results.append({"name": sector["name"], "pct": pct})
    return results


def _verdict_to_trend(verdict: str) -> str:
    if verdict in ("STRONG BUY", "BUY"):
        return "up"
    if verdict in ("STRONG SELL", "SELL"):
        return "down"
    return "flat"


def _pulse_from_scores(scores: list[float], sector_changes: list[dict] | None = None) -> str:
    """Derive market pulse. Uses DB scores when available; falls back to live sector data."""
    if scores:
        avg = sum(scores) / len(scores)
        if avg >= 0.70:
            return "Mostly green"
        if avg >= 0.55:
            return "Building strength"
        if avg >= 0.45:
            return "Mixed signals"
        return "Caution ahead"

    # No DB data — derive from live sector % changes
    if sector_changes:
        positives = sum(1 for s in sector_changes if s.get("pct", 0) > 0)
        negatives = sum(1 for s in sector_changes if s.get("pct", 0) < 0)
        total = len(sector_changes)
        if total == 0:
            return "Market closed"
        if positives >= total * 0.7:
            return "Mostly green"
        if positives >= total * 0.5:
            return "Building strength"
        if negatives >= total * 0.6:
            return "Caution ahead"
        return "Mixed signals"

    return "Market closed"


def _load_watchlist() -> list[str]:
    """Return user-saved watchlist from data/watchlist.json, or the default."""
    try:
        if _WATCHLIST_PATH.exists():
            raw = json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                return raw
    except Exception as exc:
        logger.debug("[ui_data] Could not load watchlist: %s", exc)
    return list(_WATCHLIST_DEFAULT)


def _load_agent_task_flags() -> dict[str, dict[str, bool]]:
    """Return persisted task-enabled flags {agent_key: {task_key: bool}}."""
    try:
        if _CUSTOM_TASKS_PATH.exists():
            raw = json.loads(_CUSTOM_TASKS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception as exc:
        logger.debug("[ui_data] Could not load task flags: %s", exc)
    return {}


def _get_base_weights(sector: str) -> dict[str, float]:
    """Return base (uncustomised) weights for a sector from its config/settings.py."""
    try:
        if sector == "automobile":
            from core.config import settings as _s
            return dict(_s.AGENT_WEIGHTS)
        if sector == "banking_bfsi":
            from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS
            return dict(AGENT_WEIGHTS)
        if sector == "it_sector":
            from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS
            return dict(AGENT_WEIGHTS)
        if sector == "renewable_energy":
            from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS
            return dict(AGENT_WEIGHTS)
    except Exception as exc:
        logger.warning("[ui_data] Could not load base weights for %s: %s", sector, exc)
    # Fallback: equal weights across all agents for the sector
    meta = _AGENT_META_BY_SECTOR.get(sector, _AGENT_META)
    n = len(meta)
    return {m["key"]: round(1.0 / n, 4) for m in meta}


def _load_custom_weights(sector: str = "automobile") -> dict[str, float]:
    """
    Return user-saved weight overrides from data/agent_weights.json.
    File format: {"automobile": {"key": float}, "banking_bfsi": {...}, ...}
    Migrates old flat format (all keys at root) as automobile weights.
    """
    try:
        if _CUSTOM_WEIGHTS_PATH.exists():
            raw = json.loads(_CUSTOM_WEIGHTS_PATH.read_text(encoding="utf-8"))
            # Detect old flat format (no sector nesting) → treat as automobile
            if raw and not any(k in raw for k in _AGENT_META_BY_SECTOR):
                raw = {"automobile": {k: float(v) for k, v in raw.items()}}
            sector_data = raw.get(sector, {})
            return {k: float(v) for k, v in sector_data.items()}
    except Exception as exc:
        logger.debug("[ui_data] Could not load custom weights for %s: %s", sector, exc)
    return {}


def _save_custom_weights(sector: str, overrides: dict[str, float]) -> None:
    """Persist sector-scoped weight overrides to data/agent_weights.json."""
    existing: dict = {}
    try:
        if _CUSTOM_WEIGHTS_PATH.exists():
            raw = json.loads(_CUSTOM_WEIGHTS_PATH.read_text(encoding="utf-8"))
            # Migrate old flat format
            if raw and not any(k in raw for k in _AGENT_META_BY_SECTOR):
                existing = {"automobile": {k: float(v) for k, v in raw.items()}}
            else:
                existing = raw
    except Exception:
        pass
    existing[sector] = overrides
    _CUSTOM_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_WEIGHTS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _build_agents_response(sector: str = "automobile") -> dict:
    meta_list = _AGENT_META_BY_SECTOR.get(sector, _AGENT_META)
    base_weights = _get_base_weights(sector)
    custom = _load_custom_weights(sector)
    weights = {**base_weights, **custom}
    agents = []
    for meta in meta_list:
        key = meta["key"]
        w = weights.get(key, round(1.0 / len(meta_list), 4))
        agents.append({**meta, "weight": round(w, 4), "enabled": w > 0})
    return {"agents": agents, "sector": sector}


def _build_ticker_row(
    ticker_def: dict,
    db_row: dict | None,
    price: float,
    change: float,
) -> dict:
    """Merge DB record + live price into one ticker object for the UI."""
    sym = ticker_def["sym"]

    if db_row:
        score   = round(float(db_row.get("final_score", 0.5)), 2)
        verdict = db_row.get("verdict", "NEUTRAL")
    else:
        score   = 0.5
        verdict = "NEUTRAL"

    return {
        "sym":     sym,
        "name":    ticker_def["name"],
        "price":   price if price else 0.0,
        "change":  change,
        "score":   score,
        "verdict": verdict,
        "trend":   _verdict_to_trend(verdict),
        "hasData": db_row is not None,
    }


def _rows_since(store, hours: int) -> list[dict]:
    """Return all DB rows from the last N hours, falling back to all-time latest if empty."""
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = store.get_by_date_range(since_iso=since)
    return rows if rows else store.get_all_latest()


def _freshness_label(rows: list[dict]) -> dict:
    """Return {label, runAt, isStale} based on the most recent run_at in the row set."""
    if not rows:
        return {"label": "No data yet", "runAt": None, "isStale": True}
    latest_run = max(r["run_at"] for r in rows)
    try:
        from datetime import datetime, timezone
        run_dt = datetime.fromisoformat(latest_run.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - run_dt).total_seconds() / 3600
        if age_hours < 1:
            label = "Live"
        elif age_hours < 6:
            label = f"Updated {int(age_hours)}h ago"
        elif age_hours < 24:
            label = f"Updated {int(age_hours)}h ago"
        else:
            days = int(age_hours / 24)
            label = f"Last analysis {days} day{'s' if days > 1 else ''} ago"
        return {"label": label, "runAt": latest_run, "isStale": age_hours > 12}
    except Exception:
        return {"label": "Updated recently", "runAt": latest_run, "isStale": False}


def _build_drivers_from_db(rows: list[dict]) -> list[dict]:
    """
    Derive 'What's moving the market' driver cards from recent FinalReport data.
    Each row has conviction_drivers (JSON list of strings).
    """
    import json
    drivers = []
    seen = set()

    for row in rows[:5]:
        raw = row.get("conviction_drivers") or "[]"
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            items = []

        verdict = row.get("verdict", "NEUTRAL")
        kind = "good" if verdict in ("STRONG BUY", "BUY") else "bad" if verdict in ("STRONG SELL", "SELL") else "mid"

        for driver in (items or [])[:2]:
            label = str(driver)[:80]
            if label in seen:
                continue
            seen.add(label)
            drivers.append({
                "kind":    kind,
                "label":   label,
                "impact":  "Multiple agents",
                "tickers": [row.get("ticker", "")],
            })
            if len(drivers) >= 4:
                return drivers

    # Always return 4 drivers; pad with generic ones if DB sparse
    fallback = [
        {"kind": "good", "label": "Auto sector broadly positive — EV registrations growing", "impact": "Sales & Demand", "tickers": ["TATAMOTORS", "M&M"]},
        {"kind": "good", "label": "Crude oil stable — raw material cost relief",              "impact": "Raw Materials",   "tickers": ["MARUTI", "BAJAJ-AUTO"]},
        {"kind": "mid",  "label": "INR mildly weak vs USD — watch import cost creep",         "impact": "Risk & Macro",   "tickers": ["MARUTI"]},
        {"kind": "bad",  "label": "Global macro uncertainty — monitor FII flows",             "impact": "Sentiment",      "tickers": []},
    ]
    while len(drivers) < 4:
        drivers.append(fallback[len(drivers)])
    return drivers[:4]


def _build_month_agent_scores(latest_rows: list[dict]) -> list[dict]:
    """Aggregate agent sub-scores across recent analyses for the 'This month' pane."""
    import json
    from core.config import settings

    agg: dict[str, list[float]] = {}
    for row in latest_rows:
        raw = row.get("agent_scores") or "{}"
        try:
            scores = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            scores = {}
        for agent, val in scores.items():
            agg.setdefault(agent, []).append(float(val))

    result = []
    weights = settings.AGENT_WEIGHTS
    for meta in _AGENT_META:
        key = meta["key"]
        vals = agg.get(key, [])
        avg = round(sum(vals) / len(vals), 2) if vals else round(weights.get(key, 0.5), 2)
        kind = "good" if avg >= 0.60 else "bad" if avg < 0.45 else "mid"
        result.append({"n": meta["name"], "v": avg, "k": kind})
    return result


# ---------------------------------------------------------------------------
# Expensive IO assembled once per request
# ---------------------------------------------------------------------------

async def _gather_ticker_data() -> tuple[list[dict], list[dict]]:
    """
    Fetch all ticker scores from DB + live prices from yfinance concurrently.
    Returns (ticker_rows, db_latest_map).
    """
    store = _score_store()
    db_latest = store.get_all_latest()                       # [{ticker, final_score, verdict, ...}]
    db_map    = {row["ticker"]: row for row in db_latest}

    # Fetch live prices concurrently
    async def fetch_one(t: dict) -> dict:
        price, change = await asyncio.to_thread(_fetch_yf_price, t["yf"])
        db_row = db_map.get(t["sym"])
        return _build_ticker_row(t, db_row, price, change)

    ticker_rows = await asyncio.gather(*(fetch_one(t) for t in _BOOTSTRAP_TICKERS))
    return list(ticker_rows), db_latest


async def _gather_market_data(db_latest: list[dict]) -> dict:
    """Fetch sector changes + Nifty Auto sparkline concurrently."""
    sector_changes, nifty_history = await asyncio.gather(
        asyncio.to_thread(_fetch_sector_changes),
        asyncio.to_thread(_fetch_yf_series, "^CNXAUTO", 30),
    )
    return {"sector_changes": sector_changes, "nifty_history": nifty_history}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_AGENT_SECTORS = set(_AGENT_META_BY_SECTOR.keys())  # sectors with UI agent definitions

@router.get("/agents", summary="Agent definitions + current weights for a sector")
async def get_agents(sector: str = Query(default="automobile", description="Sector key")) -> dict:
    if sector not in _AGENT_SECTORS:
        sector = "automobile"
    return _build_agents_response(sector)


class _WeightsBody(BaseModel):
    weights: dict[str, float]


@router.put("/agents/weights", summary="Persist user-adjusted agent weights for a sector")
async def update_agent_weights(
    body: _WeightsBody,
    sector: str = Query(default="automobile", description="Sector key"),
    x_scheduler_key: str | None = Header(default=None),
) -> dict:
    """
    Accepts {weights: {agent_key: float}} and persists only the changed keys as
    overrides on top of the sector's base AGENT_WEIGHTS.

    Rules:
      - Each weight must be 0.00–0.30
      - All final weights (base merged with overrides) must sum to 0.95–1.05
      - Only valid agent keys for the sector are accepted; unknown keys dropped
    """
    check_scheduler_key(x_scheduler_key, context="ui_data")
    if sector not in _AGENT_SECTORS:
        sector = "automobile"

    valid_keys = set(m["key"] for m in _AGENT_META_BY_SECTOR[sector])
    incoming = {k: float(v) for k, v in body.weights.items() if k in valid_keys}
    if not incoming:
        raise HTTPException(status_code=422, detail="No valid agent keys in request body")

    for k, v in incoming.items():
        if not (0.0 <= v <= 0.30):
            raise HTTPException(
                status_code=422,
                detail=f"Weight for '{k}' must be between 0.00 and 0.30, got {v:.4f}",
            )

    existing_custom = _load_custom_weights(sector)
    merged_custom = {**existing_custom, **incoming}

    # Validate final sum
    final = {**_get_base_weights(sector), **merged_custom}
    total = sum(final.values())
    if not (0.95 <= total <= 1.05):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Weights must sum to ~1.0 (got {total:.4f}). "
                "Adjust other agents so the total stays within 0.95–1.05."
            ),
        )

    _save_custom_weights(sector, merged_custom)
    logger.info("[ui/agents/weights] Saved %s custom weights: %s", sector, merged_custom)
    return _build_agents_response(sector)


@router.get("/trending", summary="Tickers ranked by score delta between last two analysis runs")
async def get_trending() -> dict:
    """
    Uses ScoreStore history to compute how much each ticker's composite score
    moved between its two most recent analysis runs.  Returns top 4 movers.

    Unlike /ui/tickers (which ranks by live price % change), this ranks by
    agent-score momentum — a different signal useful for spotting conviction shifts.
    """
    store = _score_store()
    results = []

    async def _delta_for(ticker_def: dict) -> dict | None:
        sym = ticker_def["sym"]
        latest   = await asyncio.to_thread(store.get_latest,   sym)
        if latest is None:
            return None
        previous = await asyncio.to_thread(store.get_previous, sym)
        score      = round(float(latest["final_score"]), 4)
        prev_score = round(float(previous["final_score"]), 4) if previous else score
        delta      = round(score - prev_score, 4)
        return {
            "sym":       sym,
            "name":      ticker_def["name"],
            "score":     score,
            "prevScore": prev_score,
            "delta":     delta,
            "verdict":   latest["verdict"],
            "direction": "up" if delta > 0.01 else "down" if delta < -0.01 else "flat",
            "why":       f"Score {'+' if delta >= 0 else ''}{delta:.3f} vs previous run · {latest['verdict']}",
            "runAt":     latest["run_at"],
        }

    rows = await asyncio.gather(*(_delta_for(t) for t in _ALL_TICKERS))
    results = [r for r in rows if r is not None]
    results.sort(key=lambda x: (abs(x["delta"]), x["score"]), reverse=True)
    return {"trending": results[:4], "all": results}


@router.get("/tickers", summary="All tickers with latest score + live price")
async def get_tickers() -> dict:
    ticker_rows, _ = await _gather_ticker_data()

    trending = sorted(
        [t for t in ticker_rows if t["hasData"]],
        key=lambda t: abs(t["change"]),
        reverse=True,
    )[:4]

    suggestions = [
        t for t in ticker_rows
        if t["sym"] not in _WATCHLIST_DEFAULT and t["hasData"]
    ][:3]

    return {
        "tickers":     ticker_rows,
        "watchlist":   _WATCHLIST_DEFAULT,
        "trending":    [
            {"sym": t["sym"], "delta": f"{t['change']:+.2f}%",
             "volume": "—", "why": f"Score {t['score']:.2f} · {t['verdict']}"}
            for t in trending
        ],
        "suggestions": [
            {"sym": t["sym"], "reason": t["name"],
             "score": t["score"], "why": "Based on recent agent scores"}
            for t in suggestions
        ],
    }


@router.get("/market/summary", summary="Market pulse, drivers, sector changes, sparkline")
async def get_market_summary() -> dict:
    store     = _score_store()
    db_latest = store.get_all_latest()

    market_data_pre = await _gather_market_data(db_latest)
    scores = [float(r["final_score"]) for r in db_latest if r.get("final_score") is not None]
    pulse  = _pulse_from_scores(scores, market_data_pre["sector_changes"])

    one_liner_today = (
        db_latest[0].get("investment_thesis", "")[:160] if db_latest else
        "Auto sector data will appear here after your first analysis runs."
    )
    one_liner_month = (
        "EV momentum + PLI benefits flowing through margins. Watch crude & INR."
        if not db_latest else
        "Multiple analyses available — check agent verdicts for the full picture."
    )

    market_data = market_data_pre  # already fetched above

    # Auto sector 1-day change for the hero
    auto_change = next(
        (s["pct"] for s in market_data["sector_changes"] if s["name"] == "Auto"), 0.0
    )

    return {
        "today": {
            "pulse":       pulse,
            "oneLiner":    one_liner_today,
            "autoChange":  auto_change,
            "drivers":     _build_drivers_from_db(db_latest),
            "sectorChange": market_data["sector_changes"],
        },
        "month": {
            "pulse":      pulse,
            "oneLiner":   one_liner_month,
            "drivers":    _build_drivers_from_db(db_latest),
            "agentVotes": _build_month_agent_scores(db_latest),
        },
        "niftyAutoHistory": market_data["nifty_history"],
    }


@router.get("/bootstrap", summary="All UI data in one shot — called on page load")
async def bootstrap() -> dict:
    """
    Fetches agents + tickers + market summary concurrently and returns
    a single JSON payload.  The prototype data.jsx calls this once on load
    to populate all window.* variables before React renders.
    """
    store = _score_store()
    ticker_rows, db_latest = await _gather_ticker_data()
    market_data = await _gather_market_data(db_latest)

    scores    = [float(r["final_score"]) for r in db_latest if r.get("final_score")]
    pulse     = _pulse_from_scores(scores, market_data["sector_changes"])
    auto_chg  = next(
        (s["pct"] for s in market_data["sector_changes"] if s["name"] == "Auto"), 0.0
    )

    # Date-filtered row sets for Today (24h) and This Month (current calendar month)
    today_rows = _rows_since(store, hours=24)
    month_rows = _rows_since(store, hours=24 * 31)
    today_freshness = _freshness_label(today_rows)
    month_freshness = _freshness_label(month_rows)

    # --- Score-delta trending (same logic as GET /ui/trending) ---
    async def _bootstrap_delta(ticker_def: dict) -> dict | None:
        sym = ticker_def["sym"]
        latest = await asyncio.to_thread(store.get_latest, sym)
        if latest is None:
            return None
        prev = await asyncio.to_thread(store.get_previous, sym)
        score = round(float(latest["final_score"]), 4)
        prev_score = round(float(prev["final_score"]), 4) if prev else score
        delta = round(score - prev_score, 4)
        return {
            "sym": sym, "name": ticker_def["name"],
            "score": score, "delta": delta, "verdict": latest["verdict"],
            "direction": "up" if delta > 0.01 else "down" if delta < -0.01 else "flat",
            "why": f"Score {'+' if delta >= 0 else ''}{delta:.3f} vs previous run · {latest['verdict']}",
            "runAt": latest["run_at"],
        }

    delta_rows = await asyncio.gather(*(_bootstrap_delta(t) for t in _BOOTSTRAP_TICKERS))
    delta_rows = [r for r in delta_rows if r is not None]
    delta_rows.sort(key=lambda x: (abs(x["delta"]), x["score"]), reverse=True)
    trending = delta_rows[:4]

    # --- Smarter suggestions: prefer improving tickers not in watchlist ---
    user_watchlist = set(_load_watchlist())
    suggestion_pool = [
        r for r in delta_rows
        if r["sym"] not in user_watchlist
        and r["verdict"] not in ("STRONG SELL", "SELL")
        and r["score"] >= 0.50
    ]
    # Sort by score descending so highest-conviction shows first
    suggestion_pool.sort(key=lambda x: x["score"], reverse=True)

    def _build_suggestion(r: dict) -> dict:
        ticker_row = next((t for t in ticker_rows if t["sym"] == r["sym"]), {})
        # Pull top conviction driver from DB for the "reason" line
        db_row = store.get_latest(r["sym"]) or {}
        try:
            drivers = json.loads(db_row.get("conviction_drivers") or "[]")
        except Exception:
            drivers = []
        reason = drivers[0][:90] if drivers else r["name"]
        # Pull top agent score for the "why" line
        try:
            agent_scores = json.loads(db_row.get("agent_scores") or "{}")
            top_agent_key = max(agent_scores, key=agent_scores.get)
            top_agent_name = next((m["name"] for m in _AGENT_META if m["key"] == top_agent_key), top_agent_key)
            top_score = agent_scores[top_agent_key]
            why = f"{top_agent_name} at {top_score:.2f} · score {'+' if r['delta'] >= 0 else ''}{r['delta']:.3f} this run"
        except Exception:
            why = f"Composite score {r['score']:.2f} · {r['verdict']}"
        return {
            "sym": r["sym"], "reason": reason,
            "score": r["score"], "why": why,
        }

    suggestions_raw = suggestion_pool[:3]
    suggestions = [_build_suggestion(r) for r in suggestions_raw]

    return {
        # Agent array — always automobile on initial bootstrap (sector switching via /ui/agents?sector=)
        "AGENTS": _build_agents_response("automobile")["agents"],
        # Available sectors for the sector switcher
        "AGENT_SECTORS": [
            {"key": k, "label": {
                "automobile":       "Automobile",
                "banking_bfsi":     "Banking",
                "it_sector":        "IT",
                "renewable_energy": "Renewable",
            }.get(k, k)}
            for k in _AGENT_META_BY_SECTOR
        ],

        # Tickers — window.TICKERS
        "TICKERS": ticker_rows,

        # Watchlist — window.WATCHLIST (user-persisted or default)
        "WATCHLIST": _load_watchlist(),

        # Agent task overrides — window.AGENT_TASK_FLAGS
        "AGENT_TASK_FLAGS": _load_agent_task_flags(),

        # Market today — window.MARKET_TODAY (24h filtered, falls back to all-time if empty)
        "MARKET_TODAY": {
            "pulse":       _pulse_from_scores([float(r["final_score"]) for r in today_rows if r.get("final_score")]),
            "oneLiner":    (today_rows[0].get("investment_thesis", "")[:160] if today_rows
                            else "Run your first analysis to see live market intelligence here."),
            "autoChange":  auto_chg,
            "drivers":     _build_drivers_from_db(today_rows),
            "sectorChange": market_data["sector_changes"],
            "freshness":   today_freshness,
        },

        # Market month — window.MARKET_MONTH (31-day window, falls back to all-time if empty)
        "MARKET_MONTH": {
            "pulse":      _pulse_from_scores([float(r["final_score"]) for r in month_rows if r.get("final_score")]),
            "oneLiner":   (month_rows[0].get("investment_thesis", "")[:160] if month_rows
                           else "EV momentum + PLI benefits flowing through margins. Watch crude & INR."),
            "drivers":    _build_drivers_from_db(month_rows),
            "agentVotes": _build_month_agent_scores(month_rows),
            "freshness":  month_freshness,
        },

        # Nifty Auto sparkline — window.NIFTY_AUTO_HISTORY
        "NIFTY_AUTO_HISTORY": market_data["nifty_history"] or _fallback_sparkline(),

        # Trending — window.TRENDING (score-delta movers, not price movers)
        "TRENDING": trending,

        # Suggestions — window.SUGGESTIONS (personalized, not in watchlist)
        "SUGGESTIONS": suggestions,

        # Categories — user-overridable tickers[], count auto-computed
        "CATEGORIES":  _resolved_categories(),
        "CHAT_SEEDS":  _CHAT_SEEDS,

        # Meta
        "AGENT_SOURCES": {m["key"]: m["sources"] for m in _AGENT_META},
        "_fetchedAt": datetime.now(timezone.utc).isoformat(),
        "_liveData": bool(db_latest),
    }


# ---------------------------------------------------------------------------
# T2.1  GET /ui/nifty-ranges — multi-timeframe Nifty Auto sparkline
# ---------------------------------------------------------------------------

_RANGE_CONFIG = {
    "1W": {"period": "1mo",  "days": 7,   "label": "1 week"},
    "1M": {"period": "1mo",  "days": 30,  "label": "1 month"},
    "3M": {"period": "3mo",  "days": 63,  "label": "3 months"},
    "6M": {"period": "6mo",  "days": 126, "label": "6 months"},
    "1Y": {"period": "1y",   "days": 252, "label": "1 year"},
}


@router.get("/nifty-ranges", summary="Nifty Auto sparkline for a given time range")
async def get_nifty_ranges(range: str = Query(default="1M")) -> dict:
    cfg = _RANGE_CONFIG.get(range.upper(), _RANGE_CONFIG["1M"])
    series = await asyncio.to_thread(_fetch_yf_series, "^CNXAUTO", cfg["days"] + 20)
    series = series[-cfg["days"]:]   # trim to exact count

    change = 0.0
    if len(series) >= 2:
        change = round((series[-1] - series[0]) / series[0] * 100, 2)

    return {
        "range":  range.upper(),
        "points": series,
        "label":  cfg["label"],
        "change": change,
    }


# ---------------------------------------------------------------------------
# T2.2  GET/PUT /ui/agents/tasks — persist task-enabled flags
# ---------------------------------------------------------------------------

class _TaskFlagsBody(BaseModel):
    flags: dict[str, dict[str, bool]]   # {agent_key: {task_key: enabled}}


@router.get("/agents/tasks", summary="Get persisted agent task enabled/disabled flags")
async def get_agent_tasks() -> dict:
    return {"flags": _load_agent_task_flags()}


@router.put("/agents/tasks", summary="Persist user task toggle state to data/agent_tasks.json")
async def update_agent_tasks(body: _TaskFlagsBody,
                             x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    _CUSTOM_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_TASKS_PATH.write_text(json.dumps(body.flags, indent=2), encoding="utf-8")
    logger.info("[ui/agents/tasks] Saved task flags: %d agents", len(body.flags))
    return {"status": "ok", "flags": body.flags}


# ---------------------------------------------------------------------------
# T2.3  GET/PUT /ui/watchlist — user watchlist persistence
# ---------------------------------------------------------------------------

class _WatchlistBody(BaseModel):
    watchlist: list[str]


@router.get("/watchlist", summary="Get current user watchlist with live ticker prices")
async def get_watchlist() -> dict:
    syms = _load_watchlist()
    store = _score_store()
    db_latest = store.get_all_latest()
    db_map = {row["ticker"]: row for row in db_latest}

    async def _fetch_one(sym: str) -> dict:
        ticker_def = next((t for t in _ALL_TICKERS if t["sym"] == sym), None)
        if not ticker_def:
            return {"sym": sym, "name": sym, "price": 0.0, "change": 0.0,
                    "score": 0.5, "verdict": "NEUTRAL", "trend": "flat", "hasData": False}
        price, change = await asyncio.to_thread(_fetch_yf_price, ticker_def["yf"])
        return _build_ticker_row(ticker_def, db_map.get(sym), price, change)

    tickers = await asyncio.gather(*(_fetch_one(s) for s in syms))
    return {"watchlist": syms, "tickers": list(tickers)}


@router.put("/watchlist", summary="Persist user watchlist to data/watchlist.json")
async def update_watchlist(body: _WatchlistBody,
                           x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    valid_syms = {t["sym"] for t in _ALL_TICKERS}
    sanitized = [s.strip().upper() for s in body.watchlist if s.strip().upper() in valid_syms]
    sanitized = list(dict.fromkeys(sanitized))   # deduplicate preserving order

    _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_PATH.write_text(json.dumps(sanitized), encoding="utf-8")
    logger.info("[ui/watchlist] Saved watchlist: %s", sanitized)
    return {"watchlist": sanitized}


# ---------------------------------------------------------------------------
# GET /ui/categories  +  PUT /ui/categories/{key}/tickers
# ---------------------------------------------------------------------------

def _load_category_overrides() -> dict[str, list[str]]:
    """Return {category_key: [tickers]} from data/category_tickers.json, or {} if absent."""
    try:
        if _CATEGORY_TICKERS_PATH.exists():
            raw = json.loads(_CATEGORY_TICKERS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception as exc:
        logger.debug("[ui/categories] Could not load overrides: %s", exc)
    return {}


def _resolved_categories() -> list[dict]:
    """Merge default _CATEGORIES with any user overrides; compute count from tickers[]."""
    overrides = _load_category_overrides()
    result = []
    for c in _CATEGORIES:
        tickers = overrides.get(c["key"], c.get("tickers", []))
        result.append({**c, "tickers": tickers, "count": len(tickers)})
    return result


@router.get("/categories", summary="All categories with their ticker lists")
async def get_categories() -> dict:
    return {"categories": _resolved_categories()}


class _CategoryTickersBody(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.put("/categories/{key}/tickers", summary="Add or remove tickers from a category")
async def update_category_tickers(key: str, body: _CategoryTickersBody,
                                  x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    valid_syms = {t["sym"] for t in _ALL_TICKERS}
    overrides = _load_category_overrides()

    # Start from the current resolved list for this key
    base = next((c.get("tickers", []) for c in _CATEGORIES if c["key"] == key), [])
    current = list(overrides.get(key, base))

    add_syms = [s.strip().upper() for s in body.add if s.strip().upper() in valid_syms]
    remove_syms = {s.strip().upper() for s in body.remove}

    updated = [s for s in current if s not in remove_syms]
    for sym in add_syms:
        if sym not in updated:
            updated.append(sym)

    overrides[key] = updated
    _CATEGORY_TICKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CATEGORY_TICKERS_PATH.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
    logger.info("[ui/categories] Updated %s tickers: %s", key, updated)

    cats = _resolved_categories()
    updated_cat = next((c for c in cats if c["key"] == key), None)
    invalid = [s.strip().upper() for s in body.add if s.strip().upper() not in valid_syms]
    return {
        "category": updated_cat,
        "invalid_syms": invalid,
    }


# ---------------------------------------------------------------------------
# T2.4  GET /ui/search — ticker + thesis text search
# ---------------------------------------------------------------------------

async def _yf_lookup(sym: str) -> dict | None:
    """Try to resolve an arbitrary NSE ticker via yfinance. Returns name or None."""
    try:
        import yfinance as yf
        t = yf.Ticker(sym.upper() + ".NS")
        info = await asyncio.to_thread(lambda: t.info)
        name = info.get("longName") or info.get("shortName")
        if name:
            return {"sym": sym.upper(), "name": name, "type": "unanalyzed"}
    except Exception:
        pass
    return None


@router.get("/search", summary="Search tickers by name/symbol and recent thesis text")
async def search(q: str = Query(default="")) -> dict:
    q_raw = q.strip()
    q = q_raw.lower()
    if len(q) < 2:
        return {"results": [], "query": q_raw}

    results = []
    known_syms: set[str] = set()

    # Search full ticker universe (core + extended)
    for t in _ALL_TICKERS:
        if q in t["sym"].lower() or q in t["name"].lower():
            results.append({"sym": t["sym"], "name": t["name"], "type": "ticker"})
            known_syms.add(t["sym"])

    # Search recent investment theses from DB
    try:
        store = _score_store()
        db_latest = store.get_all_latest()
        for row in db_latest:
            thesis = (row.get("investment_thesis") or "").lower()
            sym = row.get("ticker", "")
            if q in thesis and sym not in known_syms:
                snippet = (row.get("investment_thesis") or "")[:100]
                results.append({"sym": sym, "name": row.get("company_name", sym), "type": "thesis", "snippet": snippet})
                known_syms.add(sym)
    except Exception as exc:
        logger.debug("[ui/search] DB search failed: %s", exc)

    # If no matches yet, try yfinance for arbitrary NSE symbols (e.g. user types "ATHER")
    if not results and len(q_raw) >= 3:
        yf_result = await _yf_lookup(q_raw)
        if yf_result:
            results.append(yf_result)

    return {"results": results[:8], "query": q_raw}


# ---------------------------------------------------------------------------
# T2.5  GET /ui/learnings — RL feedback → lesson cards
# ---------------------------------------------------------------------------

def _severity_from_score(score: float) -> str:
    if score < 0.35: return "high"
    if score < 0.50: return "med"
    return "low"


def _kind_from_verdict_change(prev: str, cur: str) -> str:
    bullish = {"STRONG BUY", "BUY"}
    bearish = {"STRONG SELL", "SELL"}
    if prev in bullish and cur in bearish: return "missed-sell"
    if prev in bearish and cur in bullish: return "missed-buy"
    if cur in bullish: return "good-call"
    if cur in bearish: return "avoided-loss"
    return "sizing"


@router.get("/learnings", summary="Derive lesson cards from RL feedback logs and score history")
async def get_learnings() -> dict:
    """
    Reads from the RL prediction store (if available) and the score history DB
    to generate actionable lesson cards matching the PORTFOLIO_LEARNINGS shape.
    Falls back to an empty set if no data exists.
    """
    items = []
    patterns = []

    try:
        store = _score_store()
        db_latest   = store.get_all_latest()
        db_latest_m = {r["ticker"]: r for r in db_latest}

        # Pull up-to-3 historical records per ticker to spot verdict changes
        for ticker_def in _ALL_TICKERS:
            sym = ticker_def["sym"]
            history = await asyncio.to_thread(store.get_history, sym, 3)
            if len(history) < 2:
                continue
            newest, prev = history[0], history[1]

            kind = _kind_from_verdict_change(prev.get("verdict","NEUTRAL"), newest.get("verdict","NEUTRAL"))
            score = float(newest.get("final_score", 0.5))
            prev_score = float(prev.get("final_score", 0.5))
            score_delta = round(score - prev_score, 2)

            # Parse agent scores
            try:
                agent_scores_raw = newest.get("agent_scores") or "{}"
                agent_scores = json.loads(agent_scores_raw) if isinstance(agent_scores_raw, str) else agent_scores_raw
            except Exception:
                agent_scores = {}

            top_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            agent_snapshot = [
                {"n": next((m["name"] for m in _AGENT_META if m["key"] == k), k), "v": round(v, 2)}
                for k, v in top_agents
            ]

            thesis = (newest.get("investment_thesis") or "")[:160]
            when   = newest.get("run_at", "")[:10] if newest.get("run_at") else "Recent"
            verdict_label = newest.get("verdict","NEUTRAL")

            cost_text = (
                f"Score moved {'+' if score_delta >= 0 else ''}{score_delta:.2f} → now {verdict_label}"
            )

            items.append({
                "id":            f"{kind}-{sym.lower()}",
                "kind":          kind,
                "severity":      _severity_from_score(score),
                "sym":           sym,
                "title":         f"{sym}: {prev.get('verdict','NEUTRAL')} → {verdict_label}",
                "when":          when,
                "what":          thesis or f"Composite score {score:.2f}, verdict {verdict_label}",
                "cost":          cost_text,
                "costValue":     round(score_delta * 10000),
                "lesson":        (
                    f"When score crosses 0.70+, {sym} has shown sustained upside. Watch agent weights." if score >= 0.70
                    else f"Score below 0.50 on {sym} — tighten stop-loss or reduce position."
                ),
                "agentSnapshot": agent_snapshot,
                "action":        "Review agent details",
            })

        # Also try reading RL feedback logs from prediction store
        try:
            from core.intelligence.rl.stores.prediction_store import PredictionStore
            from core.schemas.feedback import MissType
            for ticker_def in _ALL_TICKERS:
                sym = ticker_def["sym"]
                ps = PredictionStore(ticker=sym, sector=_sector_for_ticker(sym))
                cycle = ps.current_cycle_id()
                fb_log = ps.load_feedback_log(cycle)
                for entry in (fb_log.entries if fb_log else [])[-5:]:
                    mt = entry.miss_type if hasattr(entry, "miss_type") else None
                    if mt and str(mt) not in ("MissType.data_gap", "MissType.external_shock"):
                        items.append({
                            "id":            f"rl-{sym.lower()}-{entry.date}",
                            "kind":          "missed-sell" if str(mt) in ("MissType.model_bias", "MissType.direction_flip") else "sizing",
                            "severity":      "high" if entry.direction_correct is False else "low",
                            "sym":           sym,
                            "title":         f"RL flag: {str(mt).replace('MissType.','').replace('_',' ')} on {sym}",
                            "when":          str(entry.date),
                            "what":          f"Agent {entry.primary_miss_agent or 'unknown'} flagged as primary miss. Direction correct: {entry.direction_correct}",
                            "cost":          f"Miss type: {str(mt).replace('MissType.','')}",
                            "costValue":     0,
                            "lesson":        "Review this agent's weight if it consistently misses direction.",
                            "agentSnapshot": [],
                            "action":        "Tune agent weight",
                        })
        except Exception as exc:
            logger.debug("[ui/learnings] RL store read skipped: %s", exc)

    except Exception as exc:
        logger.warning("[ui/learnings] DB read failed: %s", exc)

    # Summarise
    score_changes = [it["costValue"] for it in items]
    summary = {
        "missedGain":      sum(v for v in score_changes if v > 0),
        "avoidedLoss":     sum(-v for v in score_changes if v < 0),
        "realizedLoss":    0,
        "accuracyVsAgent": round(len([i for i in items if i["kind"] == "good-call"]) / max(len(items), 1), 2),
        "actionsReviewed": len(items),
    }

    # Simple patterns from items
    good_count = len([i for i in items if i["kind"] in ("good-call", "avoided-loss")])
    bad_count  = len([i for i in items if i["kind"] in ("missed-buy", "missed-sell", "missed-sell")])
    total = max(good_count + bad_count, 1)
    if items:
        patterns = [
            {"id":"p1", "label": "Correct verdict calls this period", "rate": round(good_count/total, 2), "kind": "good" if good_count > bad_count else "bad",
             "detail": f"{good_count} of {total} verdict changes were in the right direction."},
        ]

    return {
        "summary": summary,
        "items":   items[:10],
        "patterns": patterns,
    }


def _fallback_sparkline() -> list[float]:
    """Generate a plausible-looking 30-point series if yfinance is unavailable."""
    import math, random
    v = 22_000
    out = []
    for i in range(30):
        v += math.sin(i / 3) * 60 + (random.random() - 0.45) * 90
        out.append(round(v, 2))
    return out


# ---------------------------------------------------------------------------
# Chat context builders — each fetches one slice of relevant data
# ---------------------------------------------------------------------------

def _ctx_current_verdicts() -> str:
    try:
        rows = _score_store().get_all_latest()
        if not rows:
            return ""
        lines = [
            f"  {r['ticker']}: {r['verdict']} (score={float(r['final_score']):.2f}, run {r['run_at'][:10]})"
            for r in rows
        ]
        return "CURRENT VERDICTS:\n" + "\n".join(lines)
    except Exception:
        return ""


def _ctx_recent_history(days: int = 14) -> str:
    try:
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = _score_store().get_by_date_range(since)
        if not rows:
            return f"HISTORY (last {days} days): No analyses run in this window."
        lines = [
            f"  {r['run_at'][:10]} | {r['ticker']} → {r['verdict']} (score={float(r['final_score']):.2f})"
            for r in rows[:30]
        ]
        return f"ANALYSIS HISTORY (last {days} days):\n" + "\n".join(lines)
    except Exception:
        return ""


def _ctx_ticker_detail(ticker: str) -> str:
    try:
        store = _score_store()
        rows = store.get_history(ticker.upper(), limit=6)
        if not rows:
            return ""
        lines = [
            f"  {r['run_at'][:10]}: {r['verdict']} score={float(r['final_score']):.2f}"
            for r in rows
        ]
        delta = store.get_score_delta(ticker.upper())
        delta_str = f" | Δscore={delta:+.3f} vs prior" if delta is not None else ""
        return f"{ticker.upper()} HISTORY{delta_str}:\n" + "\n".join(lines)
    except Exception:
        return ""


def _sector_for_ticker(sym: str) -> str:
    """Resolve a ticker's sector: managed_tickers.json first, then directory scan."""
    s = sym.upper().strip()
    try:
        for t in _load_mt():
            if t.get("sym", "").upper() == s and t.get("sector"):
                return t["sector"]
    except Exception:
        pass
    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if sector_dir.is_dir() and (sector_dir / s).is_dir():
                return sector_dir.name
    except Exception:
        pass
    # Defensive fallback: "automobile" is our most-tracked sector. Real,
    # tracked tickers should always resolve via managed_tickers.json or the
    # directory scan above; this only fires for unknown/untracked symbols.
    return "automobile"


def _ctx_rl_learning() -> str:
    try:
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        from core.config import settings as cfg
        parts = []
        for ticker in (cfg.SCHEDULER_TICKERS or []):
            try:
                ps = PredictionStore(ticker, sector=_sector_for_ticker(ticker))
                cycle_id = ps.current_cycle_id()

                fb_log = ps.load_feedback_log(cycle_id)
                if fb_log and fb_log.entries:
                    recent = fb_log.entries[-10:]
                    correct = sum(1 for e in recent if e.direction_correct)
                    avg_err = sum(abs(e.price_error_pct) for e in recent) / len(recent)
                    wrong_dates = [e.date for e in recent if not e.direction_correct][-3:]
                    wrong_str = f" | missed on: {', '.join(wrong_dates)}" if wrong_dates else ""
                    parts.append(
                        f"  {ticker}: {correct}/{len(recent)} correct, "
                        f"avg price error {avg_err:.1f}%{wrong_str}"
                    )

                wm = ps.load_weight_memory()
                if wm and wm.current_weights:
                    top = sorted(wm.current_weights.items(), key=lambda x: x[1], reverse=True)[:3]
                    top_str = " > ".join(f"{k}({v:.2f})" for k, v in top)
                    parts.append(f"    {ticker} top-weighted agents: {top_str}")
            except Exception:
                continue
        return ("RL LEARNING STATE:\n" + "\n".join(parts)) if parts else ""
    except Exception:
        return ""


def _session_state() -> dict:
    """Current NSE session dict (see nse_calendar.market_session). Never raises."""
    try:
        from core.intelligence.rl.nse_calendar import market_session
        return market_session()
    except Exception:
        from datetime import date as _d
        return {"state": "OPEN", "is_live": True, "date": _d.today(),
                "last_close_day": _d.today(), "opens_at": "09:15 IST", "closes_at": "15:30 IST"}


def _nse_market_context() -> str:
    """
    Returns a compact block describing the *current* NSE session in IST — not
    just whether today is a trading day, but whether the market is actually
    trading right now (pre-market / pre-open / open / closed / holiday).

    Injected into every chat prompt so the LLM can (a) avoid saying "the market
    is open" before 09:15 IST, and (b) know whether a quoted price is a live
    quote or a settled last-close. All reasoning is anchored to IST, since the
    market trades in IST and a UTC date can be a day behind in early morning.
    """
    try:
        from core.intelligence.rl.nse_calendar import market_session

        s = market_session()  # current IST moment
        d = s["date"]
        today_str = d.strftime("%Y-%m-%d (%A)")
        last = s["last_close_day"]
        last_str = last.strftime("%Y-%m-%d (%A)")
        state = s["state"]

        if state == "OPEN":
            return (
                f"TODAY: {today_str} IST — NSE OPEN (live, continuous trading until "
                f"{s['closes_at']}). Quoted live prices are current."
            )
        if state == "PRE_OPEN":
            return (
                f"TODAY: {today_str} IST — NSE PRE-OPEN auction (09:00–09:15 IST); "
                f"continuous trading starts {s['opens_at']}. The market has NOT opened "
                f"for live trading yet. Prices shown are the LAST CLOSE ({last_str})."
            )
        if state == "PRE_MARKET":
            return (
                f"TODAY: {today_str} IST — NSE not yet open (opens {s['opens_at']}). "
                f"The market has NOT opened for live trading yet. Prices shown are the "
                f"LAST CLOSE ({last_str})."
            )
        if state == "CLOSED":
            return (
                f"TODAY: {today_str} IST — NSE CLOSED for the day (trading ended "
                f"{s['closes_at']}). Prices shown are today's CLOSE ({last_str})."
            )
        # HOLIDAY (weekend / NSE holiday)
        return (
            f"TODAY: {today_str} IST — NSE CLOSED (weekend / holiday). "
            f"Last trading day: {last_str}. Prices shown are the LAST CLOSE ({last_str})."
        )
    except Exception:
        from core.intelligence.rl.nse_calendar import now_ist
        return f"TODAY: {now_ist().strftime('%Y-%m-%d (%A)')} IST"


def _result_age_label(published_date: str) -> str:
    """
    Convert a Tavily published_date ISO string to a factual age label.
    Returns only the date and how many days ago — no prescriptive relevance
    judgement.  The LLM decides relevance based on the question and content;
    a 4-day-old regulatory announcement can be just as relevant as today's
    price move depending on what was asked.

    Examples:
        "2026-05-12T08:00:00Z" → "2026-05-12 (today)"
        "2026-05-11T..."       → "2026-05-11 (1 day ago)"
        "2026-05-08T..."       → "2026-05-08 (4 days ago)"
        "2026-04-01T..."       → "2026-04-01 (41 days ago)"
        ""                     → "date unknown — treat with caution"
    """
    if not published_date:
        return "date unknown — treat with caution"
    try:
        today = datetime.now(timezone.utc).date()
        pub = date.fromisoformat(published_date[:10])
        days_ago = (today - pub).days
        if days_ago < 0:
            return f"{published_date[:10]} (future-dated — ignore timestamp)"
        if days_ago == 0:
            return f"{published_date[:10]} (today)"
        if days_ago == 1:
            return f"{published_date[:10]} (1 day ago)"
        return f"{published_date[:10]} ({days_ago} days ago)"
    except Exception:
        return published_date[:10] if published_date else "date unknown — treat with caution"


# Intent types that benefit from macro news injection.
# SINGLE_STOCK / PRICE_QUERY / STOCK_COMPARE only need live prices + verdicts.
_MACRO_CONTEXT_INTENTS = frozenset({"NEWS_QUERY", "SECTOR_OVERVIEW", "MULTI_SECTOR", "GENERAL"})


def _get_macro_context_for_intent(intent_type: str) -> str:
    """Return formatted HIGH-severity macro news block for broad intents; empty string otherwise."""
    if intent_type not in _MACRO_CONTEXT_INTENTS:
        return ""
    # Short-circuit: if today's feed file doesn't exist, no background job has run yet.
    # Skip the MacroNewsCache import and disk read entirely — saves ~2ms per request.
    from pathlib import Path as _Path
    from datetime import date as _date
    if not (_Path("data/macro_news") / f"{_date.today().isoformat()}_macro_feed.json").exists():
        return ""
    try:
        from services.background.macro_news_cache import MacroNewsCache
        from backend.shared.config import settings as _cfg
        max_items = getattr(_cfg, "MACRO_NEWS_CONTEXT_MAX_ITEMS", 3)
        return MacroNewsCache().get_formatted_context(max_items=max_items)
    except Exception:
        return ""


async def _chat_tool_get_macro_news() -> str:
    """
    Today's macro feed. Primary source is the background daily cache; if that has
    not been populated yet (dev, or before the scheduler's first run in prod) it
    self-heals with a live Serper fetch of top India market headlines so the tool
    is never a dead end.
    """
    try:
        from services.background.macro_news_cache import MacroNewsCache
        entries = MacroNewsCache().get_all_today()
    except Exception:
        entries = []

    if entries:
        lines = [f"INDIA MACRO NEWS TODAY ({len(entries)} items):"]
        for e in entries:
            sev   = e.get("severity", "LOW")
            pub   = e.get("published_date", "")
            tags  = ", ".join(e.get("impact_tags", []))
            summ  = e.get("summary", "")
            url   = e.get("url", "")
            lines.append(
                f"[{sev}] [{pub}] {e.get('title', '')}\n"
                f"  Summary: {summ}\n"
                f"  Tags: {tags}\n"
                f"  Source: {url}"
            )
        return "\n\n".join(lines)

    # Fallback: live fetch (background feed not warmed yet today).
    try:
        from services.data.fetchers.news import search_serper_news, _normalize_date
        raw = await asyncio.to_thread(
            search_serper_news, "India stock market Sensex Nifty FII RBI macro news today", 6, geo="in"
        )
        _NOISE = ("horoscope", "astrolog", "zodiac", "numerolog", "tarot", "rashifal")
        raw = [
            r for r in raw
            if not any(n in (r.get("title", "") + r.get("link", "")).lower() for n in _NOISE)
        ]
        if raw:
            lines = ["INDIA MACRO NEWS (live — background feed not yet populated today):"]
            for r in raw[:6]:
                iso = _normalize_date(r.get("date", ""))
                age = _result_age_label(iso) if iso else "recent"
                lines.append(f"[{age}] {r.get('title', '')} — {r.get('source', '')} | {r.get('link', '')}")
            return "\n".join(lines)
    except Exception as exc:
        logger.debug("[macro] live fallback failed: %s", exc)

    return ("No macro news available right now — background feed is empty and the live fetch "
            "returned nothing. Use search_market_news for a specific topic.")


def _build_chat_context(_message: str, intent_type: str = "GENERAL") -> str:
    """
    Always-available lightweight context: date/market status, optional macro trending
    news (broad intents only), and current ticker verdicts.
    History and RL data are fetched on-demand via get_analysis_history / get_rl_insights tools.
    """
    market_ctx = _nse_market_context()
    macro_ctx  = _get_macro_context_for_intent(intent_type)
    cv         = _ctx_current_verdicts()
    db_line    = cv or "No analysis data yet — run a ticker analysis from the Home screen first."
    parts = [market_ctx]
    if macro_ctx:
        parts.append(macro_ctx)
    parts.append(db_line)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Agentic chat — tools the LLM can call
# ---------------------------------------------------------------------------

_COMMODITY_YF = {
    "silver": "SI=F",
    "gold": "GC=F",
    "crude": "CL=F",
    "crude oil": "CL=F",
    "oil": "CL=F",
    "copper": "HG=F",
    "aluminium": "ALI=F",
    "aluminum": "ALI=F",
    "palladium": "PA=F",
    "platinum": "PL=F",
    "nifty": "^NSEI",
    "nifty50": "^NSEI",
    "nifty 50": "^NSEI",
    "nifty auto": "^CNXAUTO",
    "sensex": "^BSESN",
    "usd": "USDINR=X",
    "dollar": "USDINR=X",
    "usdinr": "USDINR=X",
    "dxy": "DX-Y.NYB",
    "us dollar index": "DX-Y.NYB",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
}

# Sector name → yfinance NSE sector index (all 27 sectors mapped where index exists)
_SECTOR_INDEX_YF: dict[str, str] = {
    # Tier-1 (enabled)
    "automobile":       "^CNXAUTO",
    "banking_bfsi":     "^NSEBANK",
    "it_sector":        "^CNXIT",
    "renewable_energy": "^CNXENERGY",
    # Tier-2 (disabled by default — index available for snapshot even if analysis is off)
    "pharma":           "^CNXPHARMA",
    "fmcg":             "^CNXFMCG",
    "metals":           "^CNXMETAL",
    "capgoods":         "^CNXINFRA",
    "infra":            "^CNXINFRA",
    "realestate":       "^CNXREALTY",
    "oilgas":           "^CNXENERGY",    # closest proxy
    "chemicals":        "^CNXPHARMA",   # closest proxy
    "defence":          "^CNXPSUBANK",  # PSU proxy
    "insurance":        "^NSEBANK",     # BFSI proxy
    "logistics":        "^CNXINFRA",    # infra proxy
    "media":            "^CNXMEDIA",
    "retail":           "^CNXCONSUMP",
    "agrochem":         "^CNXPHARMA",   # specialty chem proxy
    "telecom":          "^CNXPSE",      # PSE proxy
}

# Sector → tracked tickers for verdict aggregation (derived from registry TICKER_SECTOR)
def _build_sector_tickers_map() -> dict[str, list[str]]:
    from backend.sectors.registry import TICKER_SECTOR, SectorRegistry
    result: dict[str, list[str]] = {}
    for ticker, sector in TICKER_SECTOR.items():
        result.setdefault(sector, []).append(ticker)
    # Only expose tickers for enabled sectors in verdict summaries
    enabled = set(SectorRegistry.enabled_sectors())
    return {s: tickers for s, tickers in result.items() if s in enabled}

_SECTOR_TICKERS_MAP: dict[str, list[str]] = _build_sector_tickers_map()

_SECTOR_ALIASES: dict[str, str] = {
    "auto":          "automobile",   "automotive":    "automobile",
    "banking":       "banking_bfsi", "bank":          "banking_bfsi",
    "bfsi":          "banking_bfsi", "nbfc":          "banking_bfsi",
    "finance":       "banking_bfsi",
    "it":            "it_sector",    "tech":          "it_sector",
    "software":      "it_sector",
    "energy":        "renewable_energy", "renewable": "renewable_energy",
    "solar":         "renewable_energy", "power":     "renewable_energy",
    "wind":          "renewable_energy",
    "pharma":        "pharma",       "healthcare":    "pharma",
    "fmcg":          "fmcg",         "consumer":      "fmcg",
    "metals":        "metals",       "steel":         "metals",
    "mining":        "metals",
    "oil":           "oilgas",       "gas":           "oilgas",
    "oilgas":        "oilgas",       "petroleum":     "oilgas",
    "capgoods":      "capgoods",     "engineering":   "capgoods",
    "capital goods": "capgoods",
    "infra":         "infra",        "infrastructure":"infra",
    "construction":  "infra",        "cement":        "infra",
    "realestate":    "realestate",   "real estate":   "realestate",
    "reit":          "realestate",
    "insurance":     "insurance",
    "defence":       "defence",      "defense":       "defence",
    "aerospace":     "defence",
    "chemicals":     "chemicals",    "specialty":     "chemicals",
    "logistics":     "logistics",    "transport":     "logistics",
    "media":         "media",        "entertainment": "media",
    "retail":        "retail",       "ecommerce":     "retail",
    "agro":          "agrochem",     "agrochem":      "agrochem",
    "fertiliser":    "agrochem",     "fertilizer":    "agrochem",
    "hospitality":   "hospitality",  "hotel":         "hospitality",
    "telecom":       "telecom",      "telco":         "telecom",
}


async def _chat_tool_get_sector_snapshot(sector: str) -> str:
    """
    Live sector view: index level + per-stock movers (sorted by 1-day % change) +
    any DB verdicts. The per-stock movers are what let the model answer ranking
    questions like "which IT stocks to book profit" (top gainers) or "what's cheap
    after the fall" (top losers) — not just an index number.
    """
    sector_key = sector.strip().lower().replace(" ", "_")
    sector_key = _SECTOR_ALIASES.get(sector_key, sector_key)

    yf_sym = _SECTOR_INDEX_YF.get(sector_key)
    if not yf_sym:
        return f"Unknown sector '{sector}'. Known: {', '.join(_SECTOR_INDEX_YF)}."

    label = sector_key.replace("_", " ").title()
    sess = _session_state()
    freshness = "live" if sess["state"] == "OPEN" else f"last close {sess['last_close_day'].isoformat()}"

    # Index level
    price, change = await asyncio.to_thread(_fetch_yf_price, yf_sym)
    arrow = "▲" if change >= 0 else "▼"
    header = (
        f"{label} index ({yf_sym}): {price:,.0f}  {arrow}{abs(change):.2f}% ({freshness})"
        if price else f"{label} index: price unavailable"
    )

    # Per-stock movers — fetch live prices for the sector's tracked tickers concurrently.
    tickers_in_sector = _SECTOR_TICKERS_MAP.get(sector_key, [])[:16]

    async def _one(sym: str) -> tuple[str, float] | None:
        try:
            p, ch = await asyncio.to_thread(_fetch_yf_price, _nse_yf(sym))
            return (sym, ch) if p else None
        except Exception:
            return None

    moves = [m for m in await asyncio.gather(*[_one(s) for s in tickers_in_sector]) if m]
    moves.sort(key=lambda x: x[1], reverse=True)

    lines = [header]
    if moves:
        gainers = [f"▲ {s} +{c:.1f}%" for s, c in moves if c >= 0][:5]
        losers  = [f"▼ {s} {c:.1f}%" for s, c in moves if c < 0][:5]
        if gainers:
            lines.append("Top gainers (" + freshness + "): " + "   ".join(gainers))
        if losers:
            lines.append("Top losers (" + freshness + "): " + "   ".join(losers))

    # DB verdicts (if any analyses have been run for this sector)
    store = _score_store()
    verdicts = [
        row["verdict"]
        for sym in tickers_in_sector
        if (row := await asyncio.to_thread(store.get_latest, sym))
    ]
    if verdicts:
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v] = counts.get(v, 0) + 1
        summary = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        lines.append(f"StockAgent verdicts [{len(verdicts)}]: {summary}")

    return "\n".join(lines)


def _window_stats(yf_sym: str) -> dict | None:
    """
    1-month daily history → multi-window returns + position-in-range. Sync.
    pos: 0.0 = trading at its 1-month low, 1.0 = at its 1-month high. This is the
    cheap proxy for 'oversold/beaten-down' (pos→0) vs 'extended/overbought' (pos→1).
    """
    import yfinance as yf

    def _try(t: str) -> dict | None:
        try:
            h = yf.Ticker(t).history(period="1mo", auto_adjust=True)
            if h.empty or len(h) < 2:
                return None
            close = h["Close"]
            last = float(close.iloc[-1])
            d1 = (last / float(close.iloc[-2]) - 1) * 100
            w1 = (last / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else d1
            m1 = (last / float(close.iloc[0]) - 1) * 100
            lo, hi = float(close.min()), float(close.max())
            pos = (last - lo) / (hi - lo) if hi > lo else 0.5
            return {"last": round(last, 2), "d1": round(d1, 2), "w1": round(w1, 2),
                    "m1": round(m1, 2), "pos": round(pos, 2)}
        except Exception:
            return None

    r = _try(yf_sym)
    if r is None and yf_sym.endswith(".NS"):
        r = _try(yf_sym[:-3] + ".BO")
    return r


async def _chat_tool_screen_stocks(sector: str = "", mode: str = "value") -> str:
    """
    Multi-factor screen over a sector's stocks — surfaces NON-OBVIOUS ideas, not
    blue-chips. mode: value (buy-the-dip / near lows), momentum (leaders),
    profit (extended / near highs → trim). Each row carries real signal so the
    LLM ranks on data, not memory.
    """
    mode = (mode or "value").lower()
    key = sector.strip().lower().replace(" ", "_")
    key = _SECTOR_ALIASES.get(key, key)
    tickers = _SECTOR_TICKERS_MAP.get(key, [])[:16]
    if not tickers:
        return (f"No stock universe for sector '{sector}'. "
                f"Known sectors: {', '.join(list(_SECTOR_INDEX_YF)[:10])} …")

    stats = await asyncio.gather(*[asyncio.to_thread(_window_stats, _nse_yf(t)) for t in tickers])
    rows = [(t, s) for t, s in zip(tickers, stats) if s]
    if not rows:
        return f"Could not fetch screen data for {sector} right now — try again shortly."

    sess = _session_state()
    fresh = "live" if sess["state"] == "OPEN" else f"close {sess['last_close_day'].isoformat()}"

    if mode == "momentum":
        rows.sort(key=lambda r: r[1]["w1"], reverse=True)
        title = "MOMENTUM — leaders (1-week trend, continuation candidates)"
    elif mode in ("profit", "profit_booking", "book", "trim"):
        rows.sort(key=lambda r: (r[1]["pos"], r[1]["w1"]), reverse=True)
        title = "PROFIT-BOOKING — extended names near 1-month highs (candidates to trim)"
    else:  # value / oversold / buy-the-dip
        rows.sort(key=lambda r: (r[1]["pos"], r[1]["w1"]))
        title = "VALUE / OVERSOLD — beaten down near 1-month lows (buy-the-dip candidates)"

    lines = [f"{key.replace('_', ' ').title()} screen — {title}  [{fresh}]"]
    for t, s in rows[:5]:
        where = "at lows" if s["pos"] <= 0.25 else ("at highs" if s["pos"] >= 0.75 else "mid-range")
        lines.append(
            f"  {t}: ₹{s['last']}  1d {s['d1']:+.1f}%  1w {s['w1']:+.1f}%  1mo {s['m1']:+.1f}%  ({where})"
        )
    lines.append("(pos in 1-mo range: 'at lows' = oversold/value, 'at highs' = extended)")
    return "\n".join(lines)


async def _chat_tool_run_agent_analysis(ticker: str) -> str:
    """Return cached analysis from DB; trigger orchestrator with 45s timeout if no cache."""
    ticker = ticker.strip().upper()
    store = _score_store()
    row = await asyncio.to_thread(store.get_latest, ticker)
    if row:
        score = float(row["final_score"])
        verdict = row["verdict"]
        run_at = (row.get("run_at") or "")[:10]
        thesis = (row.get("investment_thesis") or "")[:200]
        return (
            f"{ticker}: {verdict} (score={score:.2f}, run {run_at})\n"
            f"Thesis: {thesis}"
        )
    try:
        from backend.sectors import detect_sector, get_orchestrator
        sector = detect_sector(ticker)
        OrchestratorClass = get_orchestrator(sector)
        orchestrator = OrchestratorClass()
        report = await asyncio.wait_for(
            orchestrator.analyse_async(ticker),
            timeout=45.0,
        )
        return (
            f"{ticker}: {report.verdict} (score={report.final_score:.2f}, fresh)\n"
            f"Thesis: {(report.investment_thesis or '')[:200]}"
        )
    except asyncio.TimeoutError:
        return f"Analysis for {ticker} timed out (45s). Click 'Analyze' on the Home screen to run a full pipeline."
    except Exception as exc:
        return f"Could not run analysis for {ticker}: {exc}"


_CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_live_price",
            "description": (
                "Fetch the current live price and 1-day % change for a stock or global commodity/index. "
                "Use this FIRST whenever the user asks about any price, how high/low something is today, "
                "or what a commodity is doing. "
                "For NSE stocks pass the ticker (MARUTI, TATAMOTORS, HDFCBANK). "
                "For global markets use a plain name (silver, gold, crude, nifty, usd, bitcoin) "
                "OR a direct yfinance symbol if you know it (SI=F, GC=F, CL=F, ^NSEI, XAGUSD=X). "
                "Unknown assets are resolved automatically via live symbol search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Plain name ('silver', 'brent crude'), NSE ticker ('MARUTI'), or yfinance symbol ('SI=F', 'BZ=F', '^NSEI')."
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_historical_prices",
            "description": (
                "Fetch the last N trading days of OHLCV data (close + day-over-day % "
                "change) for a yfinance symbol. Use when the user asks about recent "
                "price history, a losing/winning streak, or how a stock/index has "
                "moved over the past several days."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "yfinance symbol, e.g. MARUTI.NS, ^NSEI, SI=F.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of trailing trading days to fetch (default 5).",
                        "default": 5,
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_macro_news",
            "description": (
                "Today's India macro news feed (RBI, Fed, oil, FII/DII flows, GIFT "
                "Nifty and other market-wide headlines). Use for broad macro context "
                "questions that aren't about a specific stock or search query."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_market_news",
            "description": (
                "Search for the latest news and analyst commentary behind a market move. "
                "Use this when the user asks WHY something is moving, for recent events, "
                "or for context about any global or Indian market development. "
                "Be specific in the query — include the asset name and 'today' or the year."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query e.g. 'silver price surge today reasons 2026', 'MARUTI Q4 results 2026'."
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screen_stocks",
            "description": (
                "Screen a sector's stocks by multi-window performance to surface NON-OBVIOUS ideas. "
                "mode='value' → beaten-down names near their 1-month lows (buy-the-dip: buy now, sell higher later); "
                "mode='momentum' → leaders trending up; "
                "mode='profit' → extended names near 1-month highs (candidates to book/trim profit). "
                "USE THIS for 'which stock to invest/buy', 'good stocks to buy now', 'undervalued/oversold "
                "stocks', 'what to accumulate' — NEVER answer those from memory or with generic blue-chip names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "auto, banking, IT, energy, pharma, FMCG, …"},
                    "mode": {
                        "type": "string",
                        "enum": ["value", "momentum", "profit"],
                        "description": "value = buy-the-dip / oversold; momentum = leaders; profit = trim winners",
                    },
                },
                "required": ["sector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_analysis",
            "description": (
                "Get the latest StockAgent AI analysis for a tracked NSE stock: verdict, composite score, "
                "agent breakdown, key positives and risks. Use when the user asks about a specific stock's outlook."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker e.g. MARUTI, TATAMOTORS, BAJAJ-AUTO."
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analysis_history",
            "description": (
                "Get recent analysis history for tracked NSE stocks: verdicts, scores, and changes over time. "
                "Use when the user asks about past performance, what happened last week/month, "
                "or how a stock has been trending in our system."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many days back to look (default 14, max 30).",
                        "default": 14,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rl_insights",
            "description": (
                "Get reinforcement learning insights: which agents are most accurate, recent prediction misses, "
                "learned agent weights, and pattern lessons. Use when asked about agent trust, accuracy, "
                "which agent to believe, or what the system has learned."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_snapshot",
            "description": (
                "Fetch the live NSE sector index level PLUS per-stock movers — top gainers and "
                "losers with their live 1-day % change — and our verdicts. Use this whenever the "
                "user asks which stocks in a sector to buy or book profit on, what's leading/lagging, "
                "or what to do after a sector crash/rally (auto, banking, IT, energy, pharma, FMCG). "
                "Pass the sector name as a plain string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Sector name: automobile, banking_bfsi, it_sector, renewable_energy, pharma, fmcg",
                    }
                },
                "required": ["sector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_agent_analysis",
            "description": (
                "Get the latest StockAgent deep analysis for an NSE ticker: verdict, score, thesis, "
                "agent breakdown. Returns cached result if available, otherwise triggers a fresh analysis. "
                "Use when the user wants a detailed deep-dive on a specific stock."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker symbol e.g. MARUTI, TATAMOTORS.",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rl_prediction",
            "description": (
                "Our RL model's prediction for a tracked NSE ticker today: predicted "
                "verdict, confidence, predicted close, and conviction streak / "
                "reversion prior. Use for 'will it rise', forecast, or next-session "
                "questions about a specific tracked stock."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE ticker, e.g. MARUTI",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ticker_dossier",
            "description": (
                "Accumulated knowledge dossier for a tracked NSE ticker — thesis, "
                "learned price-response signatures, open management guidance, "
                "recurring catalysts, institutional flow trend. Use for any deep "
                "dive or 'what do we know about X' question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "NSE symbol, e.g. MARUTI",
                    }
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_brief",
            "description": (
                "The latest proactive morning brief (or EOD digest) for the user's "
                "virtual portfolio: value, P&L, per-holding verdicts, escalations, "
                "regime, discovery-shelf adds, upcoming earnings and IPO lock-in flags. "
                "Use whenever the user says 'brief', 'morning brief', 'portfolio update', "
                "'my portfolio', or asks what happened to their holdings today."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _looks_like_yf_symbol(s: str) -> bool:
    """True if the string is already a yfinance symbol (e.g. SI=F, ^NSEI, BTC-USD, XAGUSD=X)."""
    return "=" in s or s.startswith("^") or ("-" in s and len(s) <= 10)


def _looks_like_plain_ticker(s: str) -> bool:
    """
    True for plain ticker-looking input — uppercase alphanumerics (and the
    '&'/'-' NSE allows, e.g. M&M, BAJAJ-AUTO), no spaces. Used to decide
    whether a naive "{SYM}.NS" quotability check should run before trusting
    a fuzzy yfinance.Search result (validate-naive-first).
    """
    return bool(s) and " " not in s and all(c.isalnum() or c in "&-" for c in s)


# Common Indian company names → NSE ticker. Keeps the most-asked names instant and
# correct without a network round-trip (yfinance.Search ranks US tickers above .NS).
_NSE_NAME_ALIASES: dict[str, str] = {
    "reliance": "RELIANCE", "ril": "RELIANCE",
    "tata motors": "TATAMOTORS", "tatamotors": "TATAMOTORS",
    "tata steel": "TATASTEEL", "tcs": "TCS", "tata consultancy": "TCS",
    "infosys": "INFY", "infy": "INFY",
    "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
    "icici": "ICICIBANK", "icici bank": "ICICIBANK",
    "sbi": "SBIN", "state bank": "SBIN",
    "axis": "AXISBANK", "axis bank": "AXISBANK", "kotak": "KOTAKBANK",
    "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "mahindra": "M&M", "m&m": "M&M",
    "bajaj auto": "BAJAJ-AUTO", "bajaj finance": "BAJFINANCE", "bajaj finserv": "BAJAJFINSV",
    "hero": "HEROMOTOCO", "hero motocorp": "HEROMOTOCO", "eicher": "EICHERMOT",
    "wipro": "WIPRO", "hcl": "HCLTECH", "hcl tech": "HCLTECH", "tech mahindra": "TECHM",
    "adani green": "ADANIGREEN", "adani power": "ADANIPOWER", "tata power": "TATAPOWER",
    "ntpc": "NTPC", "powergrid": "POWERGRID", "power grid": "POWERGRID",
    "sun pharma": "SUNPHARMA", "dr reddy": "DRREDDY", "cipla": "CIPLA",
    "itc": "ITC", "hul": "HINDUNILVR", "hindustan unilever": "HINDUNILVR",
    "airtel": "BHARTIARTL", "bharti airtel": "BHARTIARTL", "lt": "LT", "l&t": "LT",
    "larsen": "LT", "ongc": "ONGC", "coal india": "COALINDIA",
}


# NSE ticker → correct yfinance symbol via the shared self-healing resolver
# (curated overrides in settings.YF_SYMBOL_OVERRIDES + the learned cache).
def _nse_yf(ticker: str) -> str:
    """Map an NSE ticker to its yfinance symbol (override → learned cache → naive)."""
    from backend.shared.data.fetchers.symbol_resolver import resolve_yf_symbol
    return resolve_yf_symbol(ticker)


def _known_nse_tickers() -> frozenset[str]:
    """Set of all NSE tickers known to the sector registry (cached)."""
    cached = getattr(_known_nse_tickers, "_cache", None)
    if cached is not None:
        return cached
    tickers: set[str] = set()
    try:
        from backend.sectors.registry import TICKER_SECTOR
        tickers = {t.upper() for t in TICKER_SECTOR}
    except Exception:
        pass
    result = frozenset(tickers)
    _known_nse_tickers._cache = result  # type: ignore[attr-defined]
    return result


async def _resolve_yf_symbol(symbol: str) -> str | None:
    """
    NSE-first symbol resolution for an Indian-market assistant.

    Order (first hit wins):
      1. Static commodity/global-index dict  — silver, gold, crude, nifty, sensex …
      2. Explicit yfinance symbol             — already has =, ^, or - (SI=F, ^NSEI)
      3. Known NSE ticker / company-name alias → "{TICKER}.NS"  (instant, no network)
      4. India-preferred yfinance.Search       — prefers .NS/.BO listings over US tickers
      5. Final fallback                        → "{SYM}.NS"

    Tiers 3-5 default to NSE because a bare name ("reliance", "infosys") almost always
    means the Indian listing here. Plain yfinance.Search ranks US tickers (e.g. "RS")
    above "RELIANCE.NS", which is the bug this ordering fixes.
    """
    sym_lower = symbol.strip().lower()
    sym_upper = symbol.strip().upper()

    # Tier 1: static commodity / global-index dict
    if sym_lower in _COMMODITY_YF:
        return _COMMODITY_YF[sym_lower]

    # Tier 2: already a valid yfinance symbol (=, ^, or short hyphenated)
    if _looks_like_yf_symbol(sym_upper):
        return sym_upper

    # Tier 3: known NSE ticker or common Indian company-name alias → .NS (no network)
    if sym_lower in _NSE_NAME_ALIASES:
        return _nse_yf(_NSE_NAME_ALIASES[sym_lower])
    if sym_upper in _known_nse_tickers():
        return _nse_yf(sym_upper)

    # Validate-naive-first: for plain ticker-looking input (uppercase
    # alnum/&/-, no spaces — e.g. "MARUTI", "ATHER") that reached here
    # unresolved, check whether the naive "{SYM}.NS" itself quotes BEFORE
    # trusting a fuzzy yfinance.Search result. A fuzzy search on a real
    # ticker symbol can match an unrelated company (e.g. "MARUTI" ->
    # "JAYBARMARU.NS", a different ~Rs 131 company vs Maruti Suzuki's
    # ~Rs 13,000) — especially while Yahoo is erroring. ONE cheap
    # quotability call; if naive quotes, it wins outright.
    if _looks_like_plain_ticker(sym_upper):
        from backend.shared.data.fetchers.symbol_resolver import _has_price
        naive = f"{sym_upper}.NS"
        if await asyncio.to_thread(_has_price, naive):
            return naive

    # Tier 4: yfinance.Search, but PREFER Indian-listed results (.NS / .BO).
    try:
        import yfinance as yf

        def _search():
            results = yf.Search(symbol, max_results=6, news_count=0)
            quotes = getattr(results, "quotes", []) or []
            tradable = [
                q for q in quotes
                if (q.get("quoteType") or "").upper()
                in ("FUTURE", "INDEX", "CRYPTOCURRENCY", "EQUITY", "CURRENCY")
            ]
            # 1) Indian listing among tradable quotes wins.
            for q in tradable:
                sym = q.get("symbol") or ""
                if sym.endswith(".NS") or sym.endswith(".BO"):
                    return sym
            # 2) Else first tradable quote (genuinely global names: apple, tesla).
            if tradable:
                return tradable[0].get("symbol")
            return quotes[0].get("symbol") if quotes else None

        found = await asyncio.to_thread(_search)
        if found:
            logger.info("[chat/price] yfinance.Search resolved '%s' → %s", symbol, found)
            return found
    except Exception as exc:
        logger.debug("[chat/price] yfinance.Search failed for '%s': %s", symbol, exc)

    # Tier 5: final fallback — assume NSE stock
    return sym_upper + ".NS"


async def _chat_tool_get_live_price(symbol: str) -> str:
    yf_sym = await _resolve_yf_symbol(symbol)
    if not yf_sym:
        return f"Could not resolve a market symbol for '{symbol}'."

    try:
        price, change_pct = await asyncio.to_thread(_fetch_yf_price, yf_sym)
        if price == 0.0:
            return f"No price data for '{symbol}' (tried {yf_sym}) — market may be closed or symbol unavailable."

        # Classify the instrument so we label units and freshness correctly.
        is_global = any(yf_sym.endswith(s) for s in ("=F", "-USD", "=X"))
        is_index  = yf_sym.startswith("^")
        follows_nse = (
            yf_sym.endswith(".NS") or yf_sym.endswith(".BO")
            or (is_index and (yf_sym.startswith("^NSE") or yf_sym.startswith("^CNX") or yf_sym == "^BSESN"))
        )
        unit  = "USD" if is_global else ("pts" if is_index else "INR")
        arrow = "▲" if change_pct >= 0 else "▼"

        # Freshness: only NSE-listed instruments follow the IST session. When the
        # market is not in its continuous OPEN session, yfinance returns the last
        # settled close — say so explicitly so it is never passed off as live.
        if follows_nse:
            s = _session_state()
            freshness = "live" if s["state"] == "OPEN" else f"last close {s['last_close_day'].isoformat()}"
        else:
            freshness = "latest"

        return f"{symbol.title()} ({yf_sym}): {price:.2f} {unit}  {arrow}{abs(change_pct):.2f}% ({freshness})"
    except Exception as exc:
        return f"Price fetch failed for '{symbol}': {exc}"


def _build_search_variants(query: str, today: date) -> list[str]:
    """
    Deterministic multi-query expansion (RAG-Fusion style): a few diverse phrasings
    of one query surface results any single phrasing would miss. No LLM call.
    """
    q = query.strip()
    ql = q.lower()
    variants = [q, f"{q} latest news {today.isoformat()}"]
    if not any(t in ql for t in ("india", "nifty", "sensex", "nse", "bse")):
        variants.append(f"India {q}")
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:3]


def _rrf_fuse(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion: merge several ranked result lists into one. A doc's
    score = Σ 1/(k + rank) across lists, so items that rank high in MULTIPLE
    queries float to the top — more robust than any single query's ranking.
    Dedupes by link/url.
    """
    def _key(r: dict) -> str:
        return r.get("link") or r.get("url") or r.get("title", "")

    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    for lst in result_lists:
        for rank, r in enumerate(lst):
            key = _key(r)
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            items.setdefault(key, r)
    return sorted(items.values(), key=lambda r: scores[_key(r)], reverse=True)


async def _chat_tool_search_news(query: str) -> str:
    """
    Search news with multi-query expansion + Reciprocal Rank Fusion for relevance,
    then explicit freshness metadata.

    Primary:  Serper /news — 2-3 deterministic query variants fused via RRF.
              Real headlines from ET, Mint, NDTV Profit etc., India-focused (gl=in).
    Fallback: Tavily with after:TODAY anchor when Serper is empty/exhausted.

    Both paths include a market-context header and per-result age labels.
    """
    from services.data.fetchers.news import search_serper_news, _normalize_date
    from services.clients.tavily_fetcher import search_tavily

    market_ctx = _nse_market_context()
    today      = datetime.now(timezone.utc).date()

    # ── Primary: Serper /news ─────────────────────────────────────────────────
    # Detect whether the query is about India-local events or global events.
    # India-local: use gl=in so Nifty/NSE queries surface ET, Mint, NDTV Profit.
    # Global entities (OpenAI, Fed, Musk, US/EU/China): drop the geo filter so
    # primary sources (Bloomberg, TechCrunch, Reuters) are not suppressed.
    _india_terms  = {"india", "nifty", "sensex", "bse", "nse", "dalal", "rbi", "sebi"}
    _global_terms = {"openai", "fed ", "federal reserve", "musk", "china", "us ", "eu ",
                     "dollar", "trump", "europe", "ukraine", "nasdaq", "s&p"}
    q_lower = query.lower()
    has_india  = any(t in q_lower for t in _india_terms)
    has_global = any(t in q_lower for t in _global_terms)
    geo = None if (has_global and not has_india) else "in"

    # Multi-query expansion → fire variants concurrently → fuse by RRF.
    variants = _build_search_variants(query, today)
    try:
        lists = await asyncio.gather(
            *[asyncio.to_thread(search_serper_news, v, 5, geo=geo) for v in variants],
            return_exceptions=True,
        )
        result_lists = [l for l in lists if isinstance(l, list) and l]
        raw = _rrf_fuse(result_lists)

        # Global entity but thin India-biased results → add an un-geo'd pass and re-fuse.
        if len(raw) < 3 and has_global:
            more = await asyncio.to_thread(search_serper_news, query, 5, geo=None)
            if isinstance(more, list) and more:
                raw = _rrf_fuse(result_lists + [more])
    except Exception:
        raw = []

    # Drop off-topic noise (market-prediction queries on Serper often surface
    # horoscope/astrology pieces that pollute the grounding context).
    _NOISE = ("horoscope", "astrolog", "zodiac", "numerolog", "tarot", "rashifal", "panchang")
    raw = [
        r for r in raw
        if not any(n in (r.get("title", "") + " " + r.get("link", "")).lower() for n in _NOISE)
    ]

    if raw:
        # Keep RRF relevance order, but push undated results to the end (stable sort
        # preserves the fused ranking within the dated group).
        def _has_date(r: dict) -> bool:
            d = r.get("date", "")
            return bool(d) and d.lower() not in ("", "date unknown")

        raw_sorted = sorted(raw, key=lambda r: not _has_date(r))[:8]

        lines = [f"=== NEWS RESULTS (Serper News + RRF) ===\n{market_ctx}\n"]
        for i, r in enumerate(raw_sorted, 1):
            iso_date  = _normalize_date(r.get("date", ""))
            age_label = _result_age_label(iso_date)
            snippet   = (r.get("snippet") or "")[:300]
            lines.append(
                f"[Result {i} — published: {age_label}]\n"
                f"Title: {r['title']}\n"
                f"Source: {r.get('source','')} | {r['link']}\n"
                f"Snippet: {snippet}\n"
            )
        return "\n".join(lines)

    # ── Fallback: Tavily with date anchor ─────────────────────────────────────
    try:
        anchored = f"{query} after:{today.isoformat()}"
        results  = await asyncio.to_thread(search_tavily, anchored, 3, "advanced")
        if not results:
            results = await asyncio.to_thread(search_tavily, query, 4, "advanced")
    except Exception:
        results = []

    if not results:
        return f"No recent news found for: {query}\n{market_ctx}"

    lines = [f"=== NEWS RESULTS (Tavily) ===\n{market_ctx}\n"]
    for i, r in enumerate(results, 1):
        age     = _result_age_label(r.get("published_date", ""))
        content = (r.get("content") or "")[:400]
        lines.append(
            f"[Result {i} — published: {age}]\n"
            f"Title: {r['title']}\n"
            f"Source: {r['url']}\n"
            f"Content: {content}\n"
        )
    return "\n".join(lines)


async def _chat_tool_historical_prices(symbol: str, days: int = 5) -> str:
    """Fetch last N trading days OHLCV for a yfinance symbol."""
    try:
        import math
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days + 7}d")  # buffer for weekends/holidays
        if hist.empty:
            return f"No historical data for {symbol}"

        # Compute close-to-close change BEFORE tail() so the buffer day
        # provides prev_close for the first visible row.
        hist["prev_close"] = hist["Close"].shift(1)
        hist = hist.tail(days)
        lines = [f"{symbol} — Last {len(hist)} trading days:"]
        closes: list[float] = []
        for dt, row in hist.iterrows():
            date_str = dt.strftime("%Y-%m-%d (%a)")
            if math.isnan(row["prev_close"]):
                change_str = "N/A"
            else:
                change_pct = ((row["Close"] - row["prev_close"]) / row["prev_close"]) * 100
                arrow = "▲" if change_pct >= 0 else "▼"
                change_str = f"{arrow}{abs(change_pct):.2f}%"
            lines.append(
                f"{date_str}  Close: {row['Close']:,.2f}  Change: {change_str}"
            )
            closes.append(float(row["Close"]))

        if len(closes) >= 2:
            net = ((closes[-1] - closes[0]) / closes[0]) * 100
            arrow = "▲" if net >= 0 else "▼"
            lines.append(f"Net {len(closes)}-day: {arrow}{abs(net):.2f}%")
            down_streak = 0
            for i in range(len(closes) - 1, 0, -1):
                if closes[i] < closes[i - 1]:
                    down_streak += 1
                else:
                    break
            if down_streak >= 2:
                lines.append(f"Trend: {down_streak} consecutive down days")

        return "\n".join(lines)
    except Exception:
        return f"No historical data for {symbol}"


async def _chat_tool_rl_prediction(ticker: str) -> str:
    """Read today's RL prediction envelope for a ticker. Returns '' if not found."""
    if ticker.upper() in _RL_INDEX_NAMES:
        return ""

    ticker_upper = ticker.upper()
    today = str(date.today())
    cycle_id = f"{ticker_upper}_{today[:7]}"  # e.g. TCS_2026-05

    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if not sector_dir.is_dir():
                continue
            candidate = sector_dir / ticker_upper / f"{cycle_id}_prediction_envelope.json"
            if not candidate.exists():
                continue

            envelope = json.loads(candidate.read_text(encoding="utf-8"))
            forecasts = envelope.get("daily_forecasts", [])
            today_row = next((d for d in forecasts if d.get("date") == today), None)
            if not today_row:
                return ""

            streak = envelope.get("conviction_streak", {})
            streak_days = streak.get("streak_days", 0)
            reversion = envelope.get("reversion_prior", 0.0)
            lines = [
                f"RL PREDICTION — {ticker_upper} ({today}):",
                (
                    f"Verdict: {today_row['predicted_verdict']}"
                    f"  |  Confidence: {today_row['confidence']:.2f}"
                    f"  |  Predicted close: ₹{today_row['predicted_close']:,.0f}"
                ),
                (
                    f"Conviction streak: {streak_days} consecutive"
                    f" {streak.get('current_verdict', '')} days"
                    f" — reversion prior: {reversion * 100:.0f}%"
                ),
            ]
            assumptions = today_row.get("key_assumptions", [])
            if assumptions:
                lines.append(f"Key assumptions: {assumptions}")
            if today_row.get("revised"):
                lines.append(
                    f"Revised: Yes (revision {today_row.get('revision_count', 1)})"
                )
            return "\n".join(lines)
    except Exception:
        return ""

    return ""


async def _chat_tool_ticker_dossier(ticker: str) -> str:
    """Accumulated daily-tracking knowledge for a ticker (RL dossier digest)."""
    t = (ticker or "").upper().strip()
    if not t or t in _RL_INDEX_NAMES:
        return ""
    try:
        for sector_dir in _PREDICTIONS_DIR.iterdir():
            if not sector_dir.is_dir():
                continue
            f = sector_dir / t / f"{t}_dossier.json"
            if f.exists():
                from backend.shared.schemas.dossier import TickerDossier
                d = TickerDossier(**json.loads(f.read_text(encoding="utf-8")))
                return d.to_digest(2000)
    except Exception:
        return ""
    return ""


def _tool_cache_key(name: str, args: dict) -> str:
    parts = []
    for k in sorted(args):
        v = args[k]
        parts.append(f"{k}={v.strip().lower() if isinstance(v, str) else v}")
    return f"{name}({','.join(parts)})"


async def _execute_chat_tool(name: str, args: dict, cache: dict | None = None) -> str:
    """
    Dispatch a chat tool, with an optional per-turn memo cache. The model
    sometimes re-requests the same sector snapshot / news search inside its loop;
    caching identical (tool, args) calls for the duration of ONE chat turn avoids
    duplicate Serper credits and yfinance hits at zero behavioural cost.
    """
    if cache is not None:
        ckey = _tool_cache_key(name, args)
        if ckey in cache:
            return cache[ckey]
        result = await _dispatch_chat_tool(name, args)
        cache[ckey] = result
        return result
    return await _dispatch_chat_tool(name, args)


def _chat_tool_portfolio_brief() -> str:
    """Latest morning brief; falls back to the latest EOD digest (Compass Phase C)."""
    try:
        from core.portfolio.store import PortfolioStore
        store = PortfolioStore()
        brief = store.load_latest_brief()
        if brief:
            from core.delivery.brief import render_brief_text
            return render_brief_text(brief)[:1800]
        digest = store.load_latest_digest()
        if digest:
            lines = [
                f"EOD digest {digest['date']} — value ₹{digest.get('portfolio_value', 0):,.0f} "
                f"({digest.get('total_pnl_pct', 0.0):+.1f}%)"
            ]
            for row in digest.get("holdings", [])[:10]:
                pnl = row.get("pnl_pct")
                pnl_s = f" ({pnl:+.1f}%)" if pnl is not None else ""
                lines.append(f"{row['symbol']}: {row['verdict']}{pnl_s} — {row.get('reason', '')}")
            return "\n".join(lines)[:1800]
        return ("No brief yet — the morning-brief job hasn't produced one. "
                "Add holdings via /portfolio, then POST /delivery/run-brief.")
    except Exception as exc:
        logger.warning("[chat] portfolio brief failed: %s", exc, exc_info=True)
        return "Brief unavailable right now — try again in a moment."


async def _dispatch_chat_tool(name: str, args: dict) -> str:
    if name == "get_live_price":
        return await _chat_tool_get_live_price(args.get("symbol", ""))
    if name == "get_macro_news":
        return await _chat_tool_get_macro_news()
    if name == "search_market_news":
        return await _chat_tool_search_news(args.get("query", ""))
    if name == "get_stock_analysis":
        ticker = args.get("ticker", "").strip().upper()
        result = _ctx_ticker_detail(ticker)
        return result or f"No analysis for {ticker} yet — run it from the Home screen first."
    if name == "get_analysis_history":
        days = int(args.get("days", 14))
        return _ctx_recent_history(days=min(days, 30)) or "No analysis history found."
    if name == "get_rl_insights":
        return _ctx_rl_learning() or "No RL data yet — needs at least one full analysis cycle."
    if name == "get_sector_snapshot":
        return await _chat_tool_get_sector_snapshot(args.get("sector", ""))
    if name == "screen_stocks":
        return await _chat_tool_screen_stocks(args.get("sector", ""), args.get("mode", "value"))
    if name == "run_agent_analysis":
        return await _chat_tool_run_agent_analysis(args.get("ticker", ""))
    if name == "get_historical_prices":
        return await _chat_tool_historical_prices(
            args.get("symbol", "^NSEI"), int(args.get("days", 5))
        )
    if name == "get_rl_prediction":
        return await _chat_tool_rl_prediction(args.get("ticker", ""))
    if name == "get_ticker_dossier":
        return await _chat_tool_ticker_dossier(args.get("ticker", ""))
    if name == "get_portfolio_brief":
        return _chat_tool_portfolio_brief()
    return f"Unknown tool: {name}"


_CHAT_SYSTEM_PROMPT = """\
You are StockAgent, a market intelligence assistant with real-time web search and live price tools.

## Your tools
- **get_live_price(symbol)** — live price for any NSE stock or global commodity/index.
  Pass a plain name (silver, gold, crude, nifty, usd, bitcoin) OR a yfinance symbol (SI=F, BZ=F, ^NSEI).
  Unknown assets are resolved automatically — just pass what the user said.
- **search_market_news(query)** — real-time web search: headlines, data, analysis
- **get_sector_snapshot(sector)** — sector index level + LIVE per-stock movers (top gainers/losers)
  + our verdicts. THIS is how you answer "which stocks in X", "what to book profit / buy in X".
- **get_stock_analysis(ticker)** — our AI verdict + 9-agent scores for tracked NSE stocks
- **get_rl_prediction(ticker)** — our model's next-session/30-day predicted direction + confidence
- **get_analysis_history(days)** — past verdicts and score trends from our database
- **get_rl_insights()** — agent accuracy, learned weights, and prediction lessons
- **get_ticker_dossier(ticker)** — what we've LEARNED about this stock from daily tracking
  (thesis, response signatures, guidance, flows).
- **get_historical_prices(symbol, days)** — last N trading days of close prices + % change.
- **get_macro_news()** — today's India macro headlines (RBI, Fed, oil, FII/DII flows).

## When to call tools — call first, answer after
| User asks | Tools to call |
|---|---|
| Current price | get_live_price |
| Why moving / what's driving | get_live_price + search_market_news (parallel) |
| Outlook / forecast / next N days | get_live_price + search_market_news("X outlook [year]") |
| **Tomorrow / will it rise / market prediction** | get_live_price(index) + search_market_news("Indian stock market outlook GIFT Nifty FII DII analyst view [today's date]") + get_rl_prediction (if a tracked ticker) |
| **Which stocks to buy / book profit / best in a sector** | get_sector_snapshot(sector) + search_market_news("[sector] stocks to buy/book profit today") |
| **Sector crashed / rallied — what now** | get_sector_snapshot(sector) + search_market_news("why [sector] fell/rose today [date]") |
| NSE stock deep dive | get_live_price + get_stock_analysis + get_rl_prediction + get_ticker_dossier + search_market_news |
| What happened last week / history | get_analysis_history |
| Agent accuracy / which to trust | get_rl_insights |
| Macro event (Fed, RBI, oil) | search_market_news |

ALWAYS call search_market_news for forward-looking questions. Use specific queries:
"silver price outlook next 30 days supply demand 2026" not just "silver".

## Tool budget — be economical (web search costs money)
- **search_market_news: call it AT MOST ONCE per answer.** One well-phrased query (add
  "India … [date]") beats several. Never fire it twice for the same answer.
- **Never call the same tool with the same arguments twice** — you already have that result above.
- **screen_stocks works ONLY for these sectors:** automobile, IT, banking, renewable energy.
  Do NOT call screen_stocks for pharma/FMCG/energy/metals (no universe → wasted call); use
  get_sector_snapshot for those.
- For a buy question with NO sector named: probe at most the 2 most-relevant screenable sectors
  with screen_stocks (it is free), pick the most beaten-down, then ONE search_market_news for the
  catalyst. Do not snapshot every sector.

## STEP BACK — decide the real intent before calling any tool
A good answer to an investing question depends on what the user is actually trying to do.
Silently classify the intent, then pick the tool + mode:
- "which stock to buy / good to invest / accumulate / undervalued / oversold / good for long term"
  → they want to BUY LOW. You MUST call screen_stocks(sector, mode="value") — get_sector_snapshot
  alone is NOT acceptable for a buy question, because today's gainers are the WRONG answer for
  buy-the-dip. screen_stocks(value) finds beaten-down names near their 1-month lows; THEN confirm a
  recovery catalyst with search_market_news. A stock being down is the *opportunity*, not a reason to
  avoid it. NEVER recommend today's top gainers or famous blue-chips from memory for a buy question.
- "book profit / take profit / trim / which to sell / overheated" → they HOLD winners and want exits.
  Call screen_stocks(sector, mode="profit") — extended names near 1-month highs.
- "what's leading / strongest / momentum / breakout" → screen_stocks(sector, mode="momentum").
- If no sector is given for a buy question, check 2-3 sectors with get_sector_snapshot, pick the most
  beaten-down one, then screen it (that is where the value is). Only ask the user if truly ambiguous.
Every pick MUST carry a number (its move + where it sits in its 1-month range) and a one-line reason
(the catalyst or the risk). One sentence with no number = a banned, generic answer.

## Forward-looking & ranking answers (do not punt these)
- "Tomorrow's market" / "will it go up": you CANNOT know the future, but you CAN give a grounded
  lean. Combine: today's index move + direction, the search results (analyst previews, GIFT Nifty
  cues, global setup), and any get_rl_prediction. State the lean ("cautiously positive / negative /
  rangebound") WITH the 2-3 concrete reasons behind it and the key risk. Never reply "I can't predict".
- "Which stocks to book profit / buy now": call get_sector_snapshot to see the actual movers, then
  NAME specific tickers with their live % move and a one-line reason. Profit-booking = stocks that
  are UP / extended; bargain-hunting = quality names that are DOWN. Ground every pick in the data
  you fetched — never invent a recommendation without a number behind it.

## Hard rules
- NEVER say "consult market research reports", "check external sources", or "I cannot predict".
  You HAVE web search — use it and give your own observation from the data you fetch.
- NEVER refuse to give an outlook. Always search first, then synthesise what the data shows.
- Base conclusions on: live price + fetched news/analysis. Not training memory.
- Analyst opinions may be cited as one data point but must not be the conclusion.
- **SEARCH EMPTY — CRITICAL**: If search_market_news returns "No recent news found" or fewer than
  2 useful results, you MUST explicitly say: "I searched for current information but the results
  were empty or insufficient for this specific query. I cannot provide a grounded answer about
  this specific event from live data." Do NOT fill in from training knowledge for news/events.
  Training knowledge has a cutoff and will produce stale or fabricated sources/dates.
- **NO FABRICATED SOURCES**: NEVER invent source names, publication dates, or article headlines.
  Every citation must come directly from a search_market_news result. If you did not call the
  tool or the tool returned nothing, there are no sources to cite.
- **SPECIFICITY — CRITICAL**: When search results contain specific numbers and events, use them
  verbatim. "Sensex fell 1,450 pts; FII sold ₹2,800 crore; IT sector dropped 2.3%" is a good
  answer. "Markets fell due to global risk aversion and macroeconomic concerns" is a bad answer —
  it is the same generic sentence that could describe any down day in the last 5 years.
  If a headline says "Sensex crashes 1,300 points", say exactly that. Do not paraphrase into
  "broad market weakness". The user can read; give them the actual data from the articles.
- **PRICE VALUES**: ONLY cite prices from get_live_price() results. NEVER quote a price figure
  from a news article — article prices are stale the moment they're published. If an article
  mentions "₹210 target", treat it as analyst opinion only, verify current price via get_live_price.
- **DATA FRESHNESS + TEMPORAL REASONING**: Each news result shows its publication date
  and age in days: `[published: YYYY-MM-DD (N days ago)]`. Use your judgment — relevance
  depends on WHAT WAS ASKED, not just the age:
  - A 4-day-old RBI rate decision is still fully relevant today.
  - A 4-day-old article explaining "why the market fell on Tuesday" may not explain today.
  - An earnings result from 3 weeks ago is still the latest quarterly data.
  - A policy announcement from last week is still in effect unless superseded.
  Always state the article's date when citing it: "As of [date], ..." not just "currently".
  The only special case: `date unknown` results — note the missing date and weight accordingly.
- **NSE MARKET STATUS**: The context block shows whether NSE was OPEN or CLOSED today
  and the last trading day. When NSE was CLOSED (weekend / holiday):
  - Do NOT say "today the market fell" — say "as of [last trading day], the market..."
  - A result from Friday is NOT stale if today is Saturday — it IS the latest trading data.

## Output format — built for a NARROW phone-width chat bubble (~40 chars wide)

The reply renders in a small chat panel, NOT a laptop screen. Wide layouts break.
RENDERING RULES — no exceptions:
- **NEVER use markdown tables** (`| col | col |`). They overflow and become unreadable on a phone.
- Each stock is a **2-line stacked block** (see below) — NOT one long line that wraps messily.
- Group picks under a short bold sub-header per sector/theme, e.g. `📉 IT — heavy dip ▼5.6%`.
- No paragraphs in a picks answer. Short stacked lines only.
- Use ▼/▲ for moves, `·` as the in-line separator, `₹` for price. Keep tickers UPPERCASE.
- A single newline IS a line break here — put each line on its own line, no manual spacing/padding
  (extra spaces collapse). Use the `└` connector to visually tie the reason to the ticker above it.

**Per-pick block — EXACTLY two lines (this is the unit of a buy / sell / screen answer):**
```
**TICKER** ₹price ▼1d%
└ 1mo ▼mo% · short reason (catalyst or risk)
```
e.g.
```
**TCS** ₹2,242 ▼8.4%
└ 1mo ▼6.5% · oversold; MS overweight India
```

**Buy / sell / screen answer shape:**
```
🎯 [Headline — e.g. Value picks · buy-the-dip]

📉 IT — heavy dip ▼5.6%
**TCS** ₹2,242 ▼8.4%
└ 1mo ▼6.5% · oversold bounce candidate
**LTTS** ₹3,299 ▼6.0%
└ 1mo ▼10% · worst IT performer, deep value

🚗 Auto — near lows
**ASHOKLEY** ₹146 ▼0.5%
└ 1mo ▼7.7% · CV cycle turning

📰 [1-2 short context lines, newest first, with source]
⚠️ Watch: [1-3 short signals]
```
Cap it: max ~5-7 picks total, grouped. Trim ruthlessly — every block carries a number + a reason.

**Price / news / outlook answer shape (under 120 words):**
```
**[Asset]** ₹PRICE ▲/▼CHG%   (omit if get_live_price failed)

📰 What's driving:
"[Exact headline]" — Source, date
└ one-line impact   (max 3, newest first)

⚠️ Watch: [only a genuinely NEW signal not said earlier in this chat]
*Sources: S1 · S2*
```

STRICT RULES — no exceptions:
- NEVER add "Critical Note", "Important Note", "Final Note", "Revision Note", "Note:", or any
  data-limitation disclaimers. State facts, not caveats about the data.
- NEVER say "real-time data required", "for precise causality", or "always verify with" — just
  state what the fetched data shows and its publication date.
- Skip undated results entirely; cite only results that have a publication date.
- "Watch:" only when the signal is genuinely new vs an earlier "Watch:" in this conversation.
- Every line adds new specific information. No filler, no restating the question.

## StockAgent's specialist agents (invoked via full analysis, not chat)
Sales & Demand · Fundamentals · Pattern Analysis · Raw Materials · Sentiment ·
Policy & Regulatory · Competitive Intel · Risk & Macro · Valuation & Catalyst
These run on NSE stocks via "Run Analysis". Chat uses live tools above instead.

## Tracked-ticker context (from our database)
{context}"""


@router.post("/chat", summary="AI assistant chat reply")
async def chat(body: dict) -> dict:
    """
    Agentic chat: LLM can call get_live_price, search_market_news, get_stock_analysis
    in a tool loop (max 4 rounds) before composing a grounded reply.
    """
    message: str = (body.get("message") or "").strip()
    # AUD-104: ONE memory model for both chat endpoints — the server-side
    # session store (same store + 12-message window as /ui/chat/stream).
    # Client-supplied "history" is deliberately ignored: it let the client
    # inject arbitrary prior turns, and the live UI never sent it anyway.
    session_id: str = body.get("session_id") or str(uuid.uuid4())
    if not message:
        return {"reply": "Ask me anything — live prices, why a market is moving, stock verdicts, or what our agents say.",
                "session_id": session_id}

    context = _build_chat_context(message)
    system_prompt = _CHAT_SYSTEM_PROMPT.format(context=context)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(_session_history_get(session_id))
    messages.append({"role": "user", "content": message})

    try:
        from services.clients.llm_client import get_async_llm_client
        client = get_async_llm_client()
        turn_deadline = time.monotonic() + _CHAT_TURN_BUDGET_S  # AUD-101

        for _round in range(_CHAT_MAX_TOOL_ROUNDS):
            if time.monotonic() >= turn_deadline:
                logger.warning("[chat] turn budget spent after %d tool rounds — forcing final answer", _round)
                break
            resp = await _chat_completion(
                client,
                messages=messages,
                temperature=0.4,
                max_tokens=600,
                tools=_CHAT_TOOLS,
                tool_choice="auto",
                deadline=turn_deadline,
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                reply = (msg.content or "").strip()
                _session_history_append(session_id, message, reply)
                return {"reply": reply, "session_id": session_id}

            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
            messages.append(assistant_entry)

            tool_results = await asyncio.gather(*[
                _execute_chat_tool(tc.function.name, json.loads(tc.function.arguments or "{}"))
                for tc in tool_calls
            ])
            for tc, result in zip(tool_calls, tool_results):
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # Final synthesis after max tool rounds / spent budget — always allowed
        # (no deadline), so a long turn still ends in a grounded answer (AUD-101).
        resp = await _chat_completion(
            client,
            messages=messages,
            temperature=0.4,
            max_tokens=600,
        )
        reply = (resp.choices[0].message.content or "").strip()
        _session_history_append(session_id, message, reply)
        return {"reply": reply, "session_id": session_id}

    except Exception as exc:
        logger.warning("[ui/chat] LLM call failed: %s", exc)
        reply = _mock_reply(message)
        _session_history_append(session_id, message, reply)
        return {"reply": reply, "session_id": session_id}


def _mock_reply(q: str) -> str:
    ql = q.lower()
    if "maruti" in ql:
        return "MARUTI's latest score reflects strong sales dispatch data and easing raw material costs. Check the Sales & Demand and Raw Materials agents for specifics."
    if "tata" in ql or "tatamotors" in ql:
        return "TATAMOTORS is being driven by EV order book strength. Watch JLR margin recovery and China supply chain risks in Risk & Macro."
    if "agent" in ql and "trust" in ql:
        return "For short-term moves, Pattern Analysis and Sentiment lead. For 3–6 month horizons, Fundamentals and Sales & Demand carry more weight."
    return "Ask me about a specific ticker like MARUTI or BAJAJ-AUTO, or about an agent like Sales & Demand."


# ---------------------------------------------------------------------------
# Agentic streaming chat — shared helpers
# ---------------------------------------------------------------------------

try:
    from backend.shared.config import settings as _chat_cfg
    _CHAT_MODEL = _chat_cfg.LLM_MODEL_FAST            # fast tool-loop model (qwen3.6-flash)
    _CHAT_FALLBACK_MODEL = _chat_cfg.LLM_MODEL_REASONING  # escalate on rate-limit/5xx
except Exception:
    _CHAT_MODEL = "qwen/qwen3.6-flash"
    _CHAT_FALLBACK_MODEL = "z-ai/glm-5.2"
_CHAT_MAX_TOOL_ROUNDS = 4              # max tool rounds before forcing a final answer
_CHAT_RETRIES_PER_MODEL = 2            # AUD-101: was 3 — caps the retry x model product at 4
_CHAT_TURN_BUDGET_S = 45.0             # AUD-101: soft wall-clock budget per user turn


def _is_transient_llm_error(exc: Exception) -> bool:
    """True for rate-limit / upstream-5xx errors that are worth retrying."""
    status = getattr(exc, "status_code", None)
    msg = str(exc).lower()
    if status == 429 or (isinstance(status, int) and 500 <= status < 600):
        return True
    return any(s in msg for s in ("429", "rate-limit", "rate limit", "502", "503", "temporarily"))


async def _chat_completion(client, *, models: tuple[str, ...] | list[str] | None = None,
                           caller: str = "ui_chat", deadline: float | None = None,
                           **kwargs):
    """
    chat.completions.create with resilience: retry the primary model on transient
    rate-limit/5xx errors (exponential backoff), then ESCALATE to the reasoning
    tier (deliberate: quality over cost while the fast tier is rate-limited).
    `models` overrides the model chain (used by the model-comparison harness).
    Raises the last exception only if every model+retry is exhausted.
    AUD-092: reasoning is disabled by default — chat output is user-visible text
    and <think> blocks are stripped downstream, so paying for them is waste.
    AUD-093: every attempt is recorded to telemetry.
    AUD-101: `deadline` (time.monotonic() stamp) is the per-turn wall-clock
    budget — chat is latency-bound, so once the budget is blown we fail fast
    with the last transient error (the caller shows an honest "retry shortly"
    message) instead of sleeping through more backoff.
    """
    from services.clients.llm_client import JSON_MODE_EXTRA_BODY, record_llm_call
    kwargs.setdefault("extra_body", JSON_MODE_EXTRA_BODY)
    last_exc: Exception | None = None
    for model in (models or (_CHAT_MODEL, _CHAT_FALLBACK_MODEL)):
        for attempt in range(_CHAT_RETRIES_PER_MODEL):
            t0 = time.monotonic()
            try:
                resp = await client.chat.completions.create(model=model, **kwargs)
            except Exception as exc:  # noqa: BLE001 — inspect then re-raise non-transient
                record_llm_call(caller, model, 0, 0, int((time.monotonic() - t0) * 1000), False)
                last_exc = exc
                if not _is_transient_llm_error(exc):
                    raise
                sleep_s = 0.8 * (2 ** attempt)  # 0.8s, 1.6s
                if deadline is not None and time.monotonic() + sleep_s >= deadline:
                    logger.warning("[chat] turn budget exhausted — giving up early")
                    raise last_exc
                await asyncio.sleep(sleep_s)
            else:
                usage = getattr(resp, "usage", None)
                record_llm_call(
                    caller, model,
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    int((time.monotonic() - t0) * 1000), True,
                )
                return resp
        logger.warning("[chat] model %s exhausted retries — falling back", model)
    raise last_exc  # type: ignore[misc]

# In-process per-session memory (mirrors the old MemorySaver semantics: in-RAM,
# cleared on restart). Keyed by session_id → list of {role, content} turns.
_SESSION_HISTORY: dict[str, list[dict]] = {}
_SESSION_MAX_TURNS = 12               # keep last 12 messages (≈6 exchanges) per session


def _session_history_get(session_id: str) -> list[dict]:
    return list(_SESSION_HISTORY.get(session_id, []))


def _session_history_append(session_id: str, user_text: str, assistant_text: str) -> None:
    hist = _SESSION_HISTORY.setdefault(session_id, [])
    hist.append({"role": "user", "content": user_text})
    hist.append({"role": "assistant", "content": assistant_text})
    if len(hist) > _SESSION_MAX_TURNS:
        del hist[: len(hist) - _SESSION_MAX_TURNS]


def _strip_think(text: str) -> str:
    """Remove Qwen3 <think>…</think> reasoning blocks from a completed message."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _chunk_for_stream(text: str):
    """Yield a completed answer as small word-grouped chunks for a streaming feel."""
    words = text.split(" ")
    group = 3
    for i in range(0, len(words), group):
        piece = " ".join(words[i : i + group])
        # Preserve the inter-group space so the reassembled text is exact.
        yield piece if i + group >= len(words) else piece + " "


# ---------------------------------------------------------------------------
# Deterministic intent pre-router (Tier-1 routing — does not rely on the LLM
# reliably choosing screen_stocks; cf. BFCL: qwen3-235b is a weak function-caller).
# When the message is clearly a buy/sell/momentum screen query for a sector we
# can screen, we run the screen ourselves and inject it, so the right candidate
# set ALWAYS reaches the model.
# ---------------------------------------------------------------------------

_INTENT_SELL = ("book profit", "profit booking", "profit-booking", "trim", "take profit",
                "take gains", "book gains", "overbought", "overheated", " sell ", " exit ")
_INTENT_MOM  = ("momentum", "leaders", "leading", "strongest", "breakout", "outperform",
                "top performer", "hot stock")
_INTENT_BUY  = ("invest", "buy", "accumulate", "undervalued", "oversold", "bargain",
                "cheap", "buy the dip", "worth buying", "good to buy", "should i buy")

_SECTOR_NL: dict[str, tuple[str, ...]] = {
    "automobile":       ("auto", "automobile", "car", "vehicle", "two-wheeler", "2-wheeler"),
    "it_sector":        ("it sector", " it ", "it stock", "tech", "software", "technology"),
    "banking_bfsi":     ("bank", "bfsi", "lender", "nbfc", "financial", "finance"),
    "renewable_energy": ("renewable", "solar", "wind", "green energy", "clean energy",
                         "power sector", "energy"),
}


def _detect_invest_intent(message: str) -> dict | None:
    """
    Classify a screen-type intent deterministically. Requires BOTH an action and
    a screenable sector. Returns {action, mode, sector} or None (→ pure LLM path).
    """
    m = f" {message.lower()} "
    if any(w in m for w in _INTENT_SELL):
        action, mode = "sell", "profit"
    elif any(w in m for w in _INTENT_MOM):
        action, mode = "momentum", "momentum"
    elif any(w in m for w in _INTENT_BUY):
        action, mode = "buy", "value"
    else:
        return None

    for key, kws in _SECTOR_NL.items():
        if key in _SECTOR_TICKERS_MAP and any(kw in m for kw in kws):
            return {"action": action, "mode": mode, "sector": key}
    return None


# ---------------------------------------------------------------------------
# Deterministic answer sanitizer. We tried an LLM Reflexion self-critique gate
# here; on qwen3-235b it was unreliable — it either hallucinated numbers (an
# ungrounded critic "filling in" data) or failed to catch a bad draft. That
# matches the literature: Reflexion is vulnerable to degeneration-of-thought.
# Since Task-A grounded pre-fetch already prevents fabrication at the source,
# we keep only a cheap, reliable rule-based strip for the disclaimer labels the
# model occasionally sneaks in despite the prompt. (Revisit a *grounded* critic
# once on a stronger function-calling model.)
# ---------------------------------------------------------------------------

_BANNED_NOTE_RE = re.compile(
    r"(?im)^\s*\**\s*(critical note|important note|final note|revision note|disclaimer)\b.*?(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def _is_table_sep(line: str) -> bool:
    """A GFM table separator row, e.g. `|---|---|` or `| :-- | --: |`."""
    s = line.strip()
    return "-" in s and bool(s) and set(s) <= set("|-: \t")


def _table_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _tables_to_bullets(text: str) -> str:
    """
    Convert any markdown table into a compact one-line-per-row bullet list.
    The chat bubble is phone-width; wide <table> HTML overflows it. The prompt
    already forbids tables, but models slip — this guarantees a narrow layout.
    Each data row → `• **col0** col1 · col2 … — lastcol` (first cell bold = the
    ticker/label, last cell = the reason). The header row is dropped (the cells
    are self-describing: price, move, catalyst).
    """
    if "|" not in text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        is_header = "|" in line and line.strip().startswith("|")
        if is_header and i + 1 < n and _is_table_sep(lines[i + 1]):
            i += 2  # skip header + separator
            while i < n and lines[i].strip().startswith("|"):
                cells = [c for c in _table_cells(lines[i])]
                if cells and any(cells):
                    first, rest = cells[0], cells[1:]
                    bullet = f"• **{first}**" if first else "•"
                    if rest:
                        last, mid = rest[-1], rest[:-1]
                        mid_txt = " · ".join(c for c in mid if c)
                        if mid_txt:
                            bullet += f" {mid_txt}"
                        if last:
                            bullet += f" — {last}"
                    out.append(bullet)
                i += 1
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


def _sanitize_answer(text: str) -> str:
    """Strip disclaimer blocks and flatten any wide tables for the narrow chat bubble."""
    cleaned = _BANNED_NOTE_RE.sub("", text).rstrip()
    cleaned = _tables_to_bullets(cleaned)
    return cleaned or text


# ---------------------------------------------------------------------------
# T3: POST /ui/chat/stream — SSE streaming agentic chat (tool loop)
# ---------------------------------------------------------------------------

@router.post("/chat/stream", summary="AI assistant chat — SSE streaming response")
async def chat_stream(body: dict):
    """
    Streaming agentic chat. The model runs a multi-round tool loop (live prices,
    sector movers, web search, RL predictions) and then streams a grounded answer.
    Carry-over is in-process per session_id. Events: intent | tool_result | token | done.
    """
    from fastapi.responses import StreamingResponse as _SR

    message: str = (body.get("message") or "").strip()
    session_id: str = body.get("session_id") or str(uuid.uuid4())

    if not message:
        async def _empty():
            yield 'data: {"event":"done"}\n\n'
        return _SR(_empty(), media_type="text/event-stream")

    async def generate():
        import json as _json
        from services.clients.llm_client import get_async_llm_client

        # Emit intent first so the client captures/persists session_id.
        yield f'data: {_json.dumps({"event": "intent", "session_id": session_id, "tier": "active", "query": message[:80]})}\n\n'

        # Strong system prompt (IST market context + grounding rules) + carried history.
        context = _build_chat_context(message)
        system_prompt = _CHAT_SYSTEM_PROMPT.format(context=context)
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(_session_history_get(session_id))
        messages.append({"role": "user", "content": message})

        # Tier-1 deterministic pre-route (plan-and-execute): if this is clearly a
        # buy/sell/momentum screen query, run BOTH the screen and a news fetch
        # ourselves and inject them. This makes the right candidates AND real
        # headlines always reach the model — so it neither mis-routes nor
        # fabricates catalysts when left to its own (unreliable) tool-calling.
        _tool_cache: dict[str, str] = {}   # per-turn memo → no duplicate Serper/yfinance
        intent = _detect_invest_intent(message)
        if intent:
            _sec_label = {
                "automobile": "auto", "it_sector": "IT",
                "banking_bfsi": "banking", "renewable_energy": "renewable energy",
            }.get(intent["sector"], intent["sector"])
            _action_phrase = {"buy": "stocks to buy oversold value",
                              "sell": "stocks profit booking overvalued",
                              "momentum": "stocks momentum leaders"}[intent["action"]]
            from datetime import date as _date
            news_q = f"India {_sec_label} {_action_phrase} {_date.today().isoformat()}"

            screen, news = await asyncio.gather(
                _chat_tool_screen_stocks(intent["sector"], intent["mode"]),
                _chat_tool_search_news(news_q),
                return_exceptions=True,
            )
            if isinstance(screen, str) and "screen —" in screen:
                _tool_cache[_tool_cache_key("screen_stocks",
                    {"sector": intent["sector"], "mode": intent["mode"]})] = screen
                yield f'data: {_json.dumps({"event": "tool_result", "tool": "screen_stocks", "summary": screen[:600]})}\n\n'
                messages.append({
                    "role": "system",
                    "content": (
                        f"PRE-FETCHED SCREEN (action={intent['action']}, sector={intent['sector']}, "
                        f"mode={intent['mode']}):\n{screen}\n\n"
                        "Base your stock picks ONLY on this screen. Each pick needs its number + a reason."
                    ),
                })
            if isinstance(news, str) and "NEWS RESULTS" in news:
                yield f'data: {_json.dumps({"event": "tool_result", "tool": "search_market_news", "summary": news[:600]})}\n\n'
                messages.append({
                    "role": "system",
                    "content": (
                        f"PRE-FETCHED NEWS:\n{news}\n\n"
                        "Cite ONLY headlines that appear above, with their real source and date. If a "
                        "pick has no matching headline here, say 'no specific catalyst in today's news' "
                        "— NEVER invent a headline, source, or date."
                    ),
                })

        final_text = ""
        try:
            client = get_async_llm_client()
            turn_deadline = time.monotonic() + _CHAT_TURN_BUDGET_S  # AUD-101

            for _round in range(_CHAT_MAX_TOOL_ROUNDS):
                if time.monotonic() >= turn_deadline:
                    logger.warning("[chat] turn budget spent after %d tool rounds — forcing final answer", _round)
                    break
                resp = await _chat_completion(
                    client,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=700,
                    tools=_CHAT_TOOLS,
                    tool_choice="auto",
                    deadline=turn_deadline,
                )
                msg = resp.choices[0].message
                tcs = getattr(msg, "tool_calls", None) or []

                if not tcs:
                    final_text = _strip_think(msg.content or "")
                    break

                # Record the assistant tool-call turn, then run all calls in parallel.
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tcs
                    ],
                })
                parsed_args = []
                for tc in tcs:
                    try:
                        parsed_args.append(_json.loads(tc.function.arguments or "{}"))
                    except Exception:
                        parsed_args.append({})
                results = await asyncio.gather(*[
                    _execute_chat_tool(tc.function.name, a, _tool_cache)
                    for tc, a in zip(tcs, parsed_args)
                ])
                for tc, result in zip(tcs, results):
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    summary = (result or "")[:600]
                    yield f'data: {_json.dumps({"event": "tool_result", "tool": tc.function.name, "summary": summary})}\n\n'

            if not final_text:
                # Rounds or budget exhausted with tool context pending → ONE final
                # no-tools synthesis, always allowed (no deadline): the user gets a
                # grounded answer over a mock even when the turn ran long (AUD-101).
                resp = await _chat_completion(
                    client, messages=messages, temperature=0.4, max_tokens=700,
                )
                final_text = _strip_think(resp.choices[0].message.content or "")

            if not final_text:
                final_text = "I couldn't compose a grounded answer from the live data this time — try rephrasing."
            else:
                final_text = _sanitize_answer(final_text)

            for piece in _chunk_for_stream(final_text):
                yield f'data: {_json.dumps({"event": "token", "text": piece})}\n\n'

        except Exception as exc:
            logger.warning("[ui/chat/stream] agentic loop error: %s", exc)
            # Be honest on rate-limit instead of a canned (and possibly wrong) mock answer.
            if _is_transient_llm_error(exc):
                final_text = ("The market model is briefly rate-limited upstream. "
                              "Please retry in a few seconds.")
            else:
                final_text = _mock_reply(message)
            yield f'data: {_json.dumps({"event": "token", "text": final_text})}\n\n'

        _session_history_append(session_id, message, final_text)
        yield 'data: {"event":"done"}\n\n'

    return _SR(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Managed tickers — GET/PUT/POST/DELETE /ui/tickers/managed
# ---------------------------------------------------------------------------

def _get_valid_sectors() -> list[str]:
    """Return the list of enabled sectors from SectorRegistry (dynamic)."""
    try:
        from backend.sectors.registry import SectorRegistry
        return SectorRegistry.enabled_sectors()
    except Exception:
        return ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]


def _load_mt():
    from services.api.log_buffer import load_managed_tickers
    return load_managed_tickers()


def _save_mt(tickers: list[dict]) -> None:
    from services.api.log_buffer import save_managed_tickers
    save_managed_tickers(tickers)


@router.get("/tickers/managed", summary="Get managed ticker list (drives RL scheduling)")
async def get_managed_tickers() -> dict:
    """
    Returns the full managed ticker list from data/managed_tickers.json.
    Bootstrapped from settings.SCHEDULER_TICKERS on first call.
    """
    return {"tickers": _load_mt()}


class _ManagedTickerBody(BaseModel):
    sym:     str = ""
    name:    str = ""
    sector:  str = "automobile"
    enabled: bool = True


@router.put("/tickers/managed", summary="Replace the entire managed ticker list")
async def replace_managed_tickers(body: list[_ManagedTickerBody],
                                  x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    valid_sectors = _get_valid_sectors()
    tickers = [t.model_dump() for t in body]
    for t in tickers:
        t["sym"] = (t.get("sym") or "").strip().upper()
        if not t["sym"]:
            raise HTTPException(status_code=422,
                                detail="Each ticker needs a non-empty 'sym'.")
        if t["sector"] not in valid_sectors:
            raise HTTPException(status_code=422, detail=f"Unknown sector '{t['sector']}'")
    _save_mt(tickers)
    logger.info("[ui/tickers/managed] Replaced list: %d tickers", len(tickers))
    return {"tickers": tickers}


async def _generate_envelope_for_new_ticker(sym: str, sector: str) -> None:
    """Background task: generate forecast envelope for a newly added ticker."""
    try:
        from core.intelligence.rl.workflows.generate_forecast import generate_forecast
        import asyncio as _asyncio
        logger.info(
            "[tickers/managed] ENVELOPE START: %s (sector=%s) — running full 9-agent pipeline (~2 min)",
            sym, sector,
        )
        env = await _asyncio.to_thread(generate_forecast, sym, sector=sector)
        if env:
            logger.info(
                "[tickers/managed] ENVELOPE DONE: %s  cycle=%s  horizon=%dd  base=%.2f  weights=v%d",
                sym, env.cycle_id, len(env.daily_forecasts), env.base_close, env.weight_version_used,
            )
        else:
            logger.warning("[tickers/managed] ENVELOPE DONE: %s returned None envelope", sym)
    except Exception as exc:
        logger.warning(
            "[tickers/managed] ENVELOPE FAILED: %s: %s — scheduler will retry on 1st of month",
            sym, exc, exc_info=True,
        )


def _cleanup_ticker_rl_data(sym: str, sector: str) -> None:
    """Remove prediction data for a deleted ticker. Non-fatal."""
    try:
        import shutil as _shutil
        from pathlib import Path as _Path
        data_dir = _Path("data/predictions") / sector / sym
        if data_dir.exists():
            _shutil.rmtree(data_dir)
            logger.info("[ui/tickers/managed] Cleaned up RL data at %s", data_dir)
        else:
            logger.debug("[ui/tickers/managed] No RL data directory for %s/%s", sector, sym)
    except Exception as exc:
        logger.warning("[ui/tickers/managed] RL data cleanup failed for %s: %s", sym, exc)


@router.post("/tickers/managed/{sym}", summary="Add a ticker to the managed list")
async def add_managed_ticker(sym: str, body: _ManagedTickerBody = _ManagedTickerBody(),
                             x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    import asyncio as _asyncio
    from services.api.log_buffer import _KNOWN_NAMES
    valid_sectors = _get_valid_sectors()
    tickers = _load_mt()
    sym_up = sym.strip().upper()

    # FIX 4: Tightened duplicate check — prevent same sym in any sector
    existing = next((t for t in tickers if t["sym"] == sym_up), None)
    if existing:
        if existing.get("sector") != body.sector:
            logger.warning(
                "[ui/tickers/managed] %s already in sector '%s'; not adding duplicate in '%s'",
                sym_up, existing.get("sector"), body.sector,
            )
        return {"tickers": tickers, "message": f"{sym_up} already managed (sector: {existing.get('sector', 'unknown')})"}

    # FIX 1: Auto-detect sector from SectorRegistry
    try:
        from backend.sectors.registry import SectorRegistry
        auto_sector = SectorRegistry.resolve(sym_up)
    except Exception:
        auto_sector = "automobile"

    user_sector = getattr(body, "sector", "") or ""
    if user_sector in valid_sectors and user_sector == auto_sector:
        # User and registry agree
        resolved_sector = user_sector
        sector_auto_detected = False
    elif user_sector in valid_sectors and auto_sector == "automobile" and user_sector != "automobile":
        # Registry defaulted to automobile (unknown ticker) but user specified something valid — trust user
        resolved_sector = user_sector
        sector_auto_detected = False
    else:
        # Registry has a clear answer — use it (silently corrects wrong user input)
        resolved_sector = auto_sector if auto_sector in valid_sectors else "automobile"
        sector_auto_detected = (resolved_sector != user_sector)
        if sector_auto_detected and user_sector:
            logger.info(
                "[ui/tickers/managed] Sector auto-corrected for %s: '%s' → '%s'",
                sym_up, user_sector, resolved_sector,
            )

    # FIX 2: Validate ticker exists on NSE (non-blocking, times out gracefully)
    try:
        import yfinance as _yf
        _t = _yf.Ticker(f"{sym_up}.NS")
        _fi = _t.fast_info
        _price = _fi.last_price if hasattr(_fi, "last_price") else None
        if not _price or _price <= 0:
            raise ValueError(f"No price data for {sym_up}.NS")
    except Exception as _ve:
        logger.warning("[ui/tickers/managed] Ticker validation warning for %s: %s", sym_up, _ve)
        # Non-fatal — if yfinance is down, we allow the add but warn
        # This prevents blocking on yfinance outage while still catching obvious garbage

    tickers.append({
        "sym":     sym_up,
        "name":    body.name or _KNOWN_NAMES.get(sym_up, sym_up),
        "sector":  resolved_sector,
        "enabled": body.enabled,
    })
    _save_mt(tickers)

    from pathlib import Path as _P
    _mt_abs = _P("data/managed_tickers.json").resolve()
    logger.info(
        "[tickers/managed] ADD: %s  sector=%s  auto_detected=%s | "
        "file=%s | total_tickers=%d: %s",
        sym_up, resolved_sector, sector_auto_detected,
        _mt_abs, len(tickers), [t["sym"] for t in tickers],
    )
    logger.info(
        "[tickers/managed] Scheduler will pick up %s on next job run "
        "(daily review / monthly forecast reads managed_tickers.json fresh each time)",
        sym_up,
    )

    # Trigger async envelope generation so new ticker doesn't wait until month-end
    _asyncio.create_task(_generate_envelope_for_new_ticker(sym_up, resolved_sector))
    logger.info(
        "[tickers/managed] Envelope generation queued for %s (%s) in background",
        sym_up, resolved_sector,
    )

    return {
        "added": sym_up,
        "sector": resolved_sector,
        "sector_auto_detected": sector_auto_detected,
        "note": "Envelope generation started in background",
        "tickers": tickers,
    }


@router.post("/tickers/managed/{sym}/generate-envelope", summary="Trigger immediate envelope generation for a ticker")
async def trigger_envelope_generation(sym: str, sector: str = "automobile",
                                      x_scheduler_key: str | None = Header(default=None)) -> dict:
    """
    Immediately generate a forecast envelope for this ticker.
    Use this when adding a new ticker mid-month and don't want to wait until month-end.
    """
    check_scheduler_key(x_scheduler_key, context="ui_data")
    import asyncio as _asyncio
    sym_up = sym.upper()
    _asyncio.create_task(_generate_envelope_for_new_ticker(sym_up, sector))
    return {"triggered": sym_up, "sector": sector, "note": "Generating in background — check /ui/tickers/managed for status"}


@router.delete("/tickers/managed/{sym}", summary="Remove a ticker from the managed list")
async def remove_managed_ticker(sym: str,
                                x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    sym_up = sym.strip().upper()
    tickers = _load_mt()
    # Find the ticker's sector BEFORE removing it
    removed_entry = next((t for t in tickers if t["sym"] == sym_up), None)
    tickers = [t for t in tickers if t["sym"] != sym_up]
    _save_mt(tickers)

    from pathlib import Path as _P
    _mt_abs = _P("data/managed_tickers.json").resolve()
    logger.info(
        "[tickers/managed] REMOVE: %s | file=%s | remaining=%d: %s",
        sym_up, _mt_abs, len(tickers), [t["sym"] for t in tickers],
    )

    # FIX 3: Clean up RL prediction data (non-fatal if it fails)
    if removed_entry:
        logger.info(
            "[tickers/managed] Cleaning up RL prediction data for %s (sector=%s)",
            sym_up, removed_entry.get("sector", "automobile"),
        )
        _cleanup_ticker_rl_data(sym_up, removed_entry.get("sector", "automobile"))

    return {"removed": sym_up, "tickers": tickers}


@router.patch("/tickers/managed/{sym}/toggle", summary="Enable or disable a managed ticker")
async def toggle_managed_ticker(sym: str,
                                x_scheduler_key: str | None = Header(default=None)) -> dict:
    check_scheduler_key(x_scheduler_key, context="ui_data")
    sym_up = sym.strip().upper()
    tickers = _load_mt()
    toggled = None
    for t in tickers:
        if t["sym"] == sym_up:
            t["enabled"] = not t.get("enabled", True)
            toggled = t
            break
    _save_mt(tickers)

    from pathlib import Path as _P
    _mt_abs = _P("data/managed_tickers.json").resolve()
    if toggled:
        logger.info(
            "[tickers/managed] TOGGLE: %s  enabled=%s | file=%s | active_count=%d",
            sym_up, toggled["enabled"], _mt_abs,
            sum(1 for t in tickers if t.get("enabled", True)),
        )
    else:
        logger.warning("[tickers/managed] TOGGLE: %s not found in managed list", sym_up)

    return {"tickers": tickers}


# ---------------------------------------------------------------------------
# Live log streaming — GET /ui/logs  and  GET /ui/logs/stream (SSE)
# ---------------------------------------------------------------------------

@router.get("/logs", summary="Return recent server log entries (polling fallback)")
async def get_logs(level: str = "INFO", limit: int = 200) -> dict:
    from services.api.log_buffer import snapshot
    entries = snapshot(level=level, limit=min(limit, 1000))
    return {"entries": entries, "count": len(entries)}


@router.get("/logs/stream", summary="Server-Sent Events stream of live log entries")
async def stream_logs(level: str = "INFO"):
    """
    Connect via EventSource('/ui/logs/stream').
    Sends buffered history first, then live entries as they arrive.
    Keepalive comments are sent every 30 s to prevent proxy timeouts.
    """
    import asyncio
    import queue as _tq
    from fastapi.responses import StreamingResponse
    from services.api import log_buffer

    min_ord = log_buffer._LEVEL_ORDER.get(level.upper(), 1)

    async def generate():
        q = log_buffer.subscribe()
        try:
            # 1. Flush history snapshot
            for entry in log_buffer.snapshot(level=level, limit=500):
                yield f"data: {json.dumps(entry)}\n\n"
            # 2. Stream live entries
            while True:
                try:
                    entry = await asyncio.to_thread(q.get, True, 30.0)
                    if log_buffer._LEVEL_ORDER.get(entry["level"], 0) >= min_ord:
                        yield f"data: {json.dumps(entry)}\n\n"
                except _tq.Empty:
                    yield ": keepalive\n\n"
                except Exception:
                    yield ": keepalive\n\n"
        finally:
            log_buffer.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
