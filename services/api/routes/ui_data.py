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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui", tags=["UI"])

# User-overridden agent weights persisted between server restarts
_CUSTOM_WEIGHTS_PATH = Path("data/agent_weights.json")
# User-overridden agent task flags persisted between server restarts
_CUSTOM_TASKS_PATH   = Path("data/agent_tasks.json")
# User-curated watchlist (overrides the hardcoded default)
_WATCHLIST_PATH      = Path("data/watchlist.json")


# ---------------------------------------------------------------------------
# Static agent metadata
# Kept here so the UI always has consistent labels, icons, and descriptions
# even before any analyses have run.
# ---------------------------------------------------------------------------

_AGENT_META: list[dict] = [
    {
        "key": "sales_demand",
        "name": "Sales & Demand",
        "icon": "📊",
        "beginner": "How many cars are actually selling each month.",
        "desc": "Tracks FADA/SIAM dispatches, EV Vahan registrations, dealer inventory, DGFT exports, used car price index.",
        "sources": ["Serper news", "FADA", "SIAM", "Vahan"],
    },
    {
        "key": "fundamentals",
        "name": "Fundamentals",
        "icon": "📈",
        "beginner": "Whether the company makes more money each quarter.",
        "desc": "Revenue & EBITDA delta, margin vs peers, order book, headcount, FII/DII flow.",
        "sources": ["yfinance", "Serper news", "NSE filings"],
    },
    {
        "key": "pattern_analysis",
        "name": "Pattern Analysis",
        "icon": "🔍",
        "beginner": "Reads the price chart for buying/selling pressure.",
        "desc": "10-yr OHLCV, RSI/MACD/Bollinger, support/resistance, Nifty Auto correlation.",
        "sources": ["yfinance OHLCV", "RSI/MACD/BB (C++)"],
    },
    {
        "key": "raw_materials",
        "name": "Raw Materials",
        "icon": "⚙️",
        "beginner": "How costly the metals & oil they buy are right now.",
        "desc": "Steel, aluminium, palladium, crude — input cost stack.",
        "sources": ["yfinance commodities", "Serper news"],
    },
    {
        "key": "sentiment",
        "name": "Sentiment",
        "icon": "💬",
        "beginner": "What the news, social media & forums are saying.",
        "desc": "News tone, mgmt commentary, Twitter/Reddit/YouTube spikes.",
        "sources": ["Serper news", "Twitter/Reddit", "YouTube"],
    },
    {
        "key": "policy_regulatory",
        "name": "Policy & Regulatory",
        "icon": "📋",
        "beginner": "Government rules helping or hurting the company.",
        "desc": "FAME/EV subsidies, BS6 emissions, PLI scheme, state incentives.",
        "sources": ["Tavily", "Serper", "gov circulars"],
    },
    {
        "key": "competitive_intel",
        "name": "Competitive Intel",
        "icon": "🎯",
        "beginner": "How rivals like Tata, Hyundai, Kia are doing.",
        "desc": "EV market share, model pipeline, JV/M&A, ADAS ratings.",
        "sources": ["Serper news", "peer baskets"],
    },
    {
        "key": "risk_macro",
        "name": "Risk & Macro",
        "icon": "⚠️",
        "beginner": "Big-picture risks: currency, oil, interest rates.",
        "desc": "INR/USD, crude, RBI repo, geopolitics, China supply chain.",
        "sources": ["yfinance INR/crude", "macro cache"],
    },
    {
        "key": "valuation_catalyst",
        "name": "Valuation & Catalyst",
        "icon": "💎",
        "beginner": "Whether the stock is cheap or expensive right now.",
        "desc": "P/E vs history & peers, fair value, recovery catalysts.",
        "sources": ["LLM knowledge", "peer P/E", "price targets"],
    },
]

_ALL_TICKERS: list[dict] = [
    {"sym": "MARUTI",      "name": "Maruti Suzuki India Ltd",        "yf": "MARUTI.NS"},
    {"sym": "TATAMOTORS",  "name": "Tata Motors Ltd",                "yf": "TATAMOTORS.NS"},
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

    Uses period="1mo" instead of "5d" — NSE tickers on yfinance frequently
    return empty results on short periods due to exchange delays or weekend gaps.
    1mo is reliable and still gives us the last two trading days we need.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(yf_ticker)
        hist = t.history(period="1mo", auto_adjust=True)
        if hist.empty or len(hist) < 1:
            return 0.0, 0.0
        current = float(hist["Close"].iloc[-1])
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            change = (current - prev) / prev * 100 if prev else 0.0
        else:
            change = 0.0
        return round(current, 2), round(change, 2)
    except Exception as exc:
        logger.debug("[ui_data] yfinance price fetch failed for %s: %s", yf_ticker, exc)
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


def _pulse_from_scores(scores: list[float]) -> str:
    if not scores:
        return "Neutral"
    avg = sum(scores) / len(scores)
    if avg >= 0.70:
        return "Mostly green"
    if avg >= 0.55:
        return "Building strength"
    if avg >= 0.45:
        return "Mixed signals"
    return "Caution ahead"


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


def _load_custom_weights() -> dict[str, float]:
    """Return user-saved weight overrides from data/agent_weights.json (empty dict if none)."""
    try:
        if _CUSTOM_WEIGHTS_PATH.exists():
            raw = json.loads(_CUSTOM_WEIGHTS_PATH.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in raw.items()}
    except Exception as exc:
        logger.debug("[ui_data] Could not load custom weights: %s", exc)
    return {}


def _build_agents_response() -> dict:
    from core.config import settings
    base_weights = dict(settings.AGENT_WEIGHTS)
    custom = _load_custom_weights()
    weights = {**base_weights, **custom}  # custom overrides base
    agents = []
    for meta in _AGENT_META:
        key = meta["key"]
        w = weights.get(key, 0.10)
        agents.append({
            **meta,
            "weight": round(w, 4),
            "enabled": w > 0,
        })
    return {"agents": agents}


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

@router.get("/agents", summary="All 9 agent definitions + current weights")
async def get_agents() -> dict:
    return _build_agents_response()


class _WeightsBody(BaseModel):
    weights: dict[str, float]


@router.put("/agents/weights", summary="Persist user-adjusted agent weights to data/agent_weights.json")
async def update_agent_weights(body: _WeightsBody) -> dict:
    """
    Accepts {weights: {agent_key: float}} and persists only the changed keys as
    overrides on top of the base settings.AGENT_WEIGHTS.

    Rules:
      - Each weight must be 0.00–0.30
      - All 9 final weights (base merged with overrides) must sum to 0.95–1.05
      - Only valid agent keys are accepted; unknown keys are silently dropped
    """
    from core.config import settings
    valid_keys = set(settings.AGENT_WEIGHTS.keys())
    incoming = {k: float(v) for k, v in body.weights.items() if k in valid_keys}
    if not incoming:
        raise HTTPException(status_code=422, detail="No valid agent keys in request body")

    for k, v in incoming.items():
        if not (0.0 <= v <= 0.30):
            raise HTTPException(
                status_code=422,
                detail=f"Weight for '{k}' must be between 0.00 and 0.30, got {v:.4f}",
            )

    existing_custom = _load_custom_weights()
    merged_custom = {**existing_custom, **incoming}

    # Check sum over the full set (base + all custom overrides)
    final = {**dict(settings.AGENT_WEIGHTS), **merged_custom}
    total = sum(final.values())
    if not (0.95 <= total <= 1.05):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Weights must sum to ~1.0 (got {total:.4f}). "
                "Adjust other agents so the total stays within 0.95–1.05."
            ),
        )

    _CUSTOM_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_WEIGHTS_PATH.write_text(json.dumps(merged_custom, indent=2), encoding="utf-8")
    logger.info("[ui/agents/weights] Saved custom weights: %s", merged_custom)
    return _build_agents_response()


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

    scores = [float(r["final_score"]) for r in db_latest if r.get("final_score") is not None]
    pulse  = _pulse_from_scores(scores)

    one_liner_today = (
        db_latest[0].get("investment_thesis", "")[:160] if db_latest else
        "Auto sector data will appear here after your first analysis runs."
    )
    one_liner_month = (
        "EV momentum + PLI benefits flowing through margins. Watch crude & INR."
        if not db_latest else
        "Multiple analyses available — check agent verdicts for the full picture."
    )

    market_data = await _gather_market_data(db_latest)

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
    ticker_rows, db_latest = await _gather_ticker_data()
    market_data = await _gather_market_data(db_latest)

    scores    = [float(r["final_score"]) for r in db_latest if r.get("final_score")]
    pulse     = _pulse_from_scores(scores)
    auto_chg  = next(
        (s["pct"] for s in market_data["sector_changes"] if s["name"] == "Auto"), 0.0
    )

    trending = sorted(
        [t for t in ticker_rows if t["hasData"]],
        key=lambda t: abs(t["change"]),
        reverse=True,
    )[:4]
    suggestions = [t for t in ticker_rows if t["sym"] not in _WATCHLIST_DEFAULT and t["hasData"]][:3]

    return {
        # Agent array — matches window.AGENTS shape expected by prototype
        "AGENTS": _build_agents_response()["agents"],

        # Tickers — window.TICKERS
        "TICKERS": ticker_rows,

        # Watchlist — window.WATCHLIST (user-persisted or default)
        "WATCHLIST": _load_watchlist(),

        # Agent task overrides — window.AGENT_TASK_FLAGS
        "AGENT_TASK_FLAGS": _load_agent_task_flags(),

        # Market today — window.MARKET_TODAY
        "MARKET_TODAY": {
            "pulse":       pulse,
            "oneLiner":    (db_latest[0].get("investment_thesis", "")[:160] if db_latest
                            else "Run your first analysis to see live market intelligence here."),
            "autoChange":  auto_chg,
            "drivers":     _build_drivers_from_db(db_latest),
            "sectorChange": market_data["sector_changes"],
        },

        # Market month — window.MARKET_MONTH
        "MARKET_MONTH": {
            "pulse":      pulse,
            "oneLiner":   "EV momentum + PLI benefits flowing through margins. Watch crude & INR.",
            "drivers":    _build_drivers_from_db(db_latest),
            "agentVotes": _build_month_agent_scores(db_latest),
        },

        # Nifty Auto sparkline — window.NIFTY_AUTO_HISTORY
        "NIFTY_AUTO_HISTORY": market_data["nifty_history"] or _fallback_sparkline(),

        # Trending — window.TRENDING
        "TRENDING": [
            {"sym": t["sym"], "delta": f"{t['change']:+.2f}%",
             "volume": "—", "why": f"Score {t['score']:.2f} · {t['verdict']}"}
            for t in trending
        ],

        # Suggestions — window.SUGGESTIONS
        "SUGGESTIONS": [
            {"sym": t["sym"], "reason": t["name"],
             "score": t["score"], "why": "Based on recent agent scores"}
            for t in suggestions
        ],

        # Categories + chat seeds (static, no API needed)
        "CATEGORIES":  _CATEGORIES,
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
async def update_agent_tasks(body: _TaskFlagsBody) -> dict:
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
async def update_watchlist(body: _WatchlistBody) -> dict:
    valid_syms = {t["sym"] for t in _ALL_TICKERS}
    sanitized = [s.strip().upper() for s in body.watchlist if s.strip().upper() in valid_syms]
    sanitized = list(dict.fromkeys(sanitized))   # deduplicate preserving order

    _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_PATH.write_text(json.dumps(sanitized), encoding="utf-8")
    logger.info("[ui/watchlist] Saved watchlist: %s", sanitized)
    return {"watchlist": sanitized}


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
                ps = PredictionStore(ticker=sym, sector="automobile")
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


@router.post("/chat", summary="AI assistant chat reply")
async def chat(body: dict) -> dict:
    """
    Accepts {message: str, history?: [{role, content}]} and returns {reply: str}.
    History is the last N turns from the frontend — passed directly to the LLM
    so the assistant can refer back to prior context in the same session.
    """
    message: str = (body.get("message") or "").strip()
    history: list = body.get("history") or []
    if not message:
        return {"reply": "Please ask me something about Indian auto stocks."}

    try:
        store     = _score_store()
        db_latest = store.get_all_latest()
        context_lines = [
            f"{r['ticker']}: {r['verdict']} (score={float(r['final_score']):.2f})"
            for r in db_latest
        ]
        ticker_context = "\n".join(context_lines) if context_lines else "No analyses run yet."
    except Exception:
        ticker_context = "No analyses available."

    system_prompt = (
        "You are StockAgent, an AI assistant specialising in Indian automobile stocks listed on NSE. "
        "You have 9 specialist agents: Sales & Demand, Fundamentals, Pattern Analysis, Raw Materials, "
        "Sentiment, Policy & Regulatory, Competitive Intel, Risk & Macro, and Valuation & Catalyst. "
        "Answer concisely (2-4 sentences max). Focus on Indian auto sector context (MARUTI, TATAMOTORS, M&M, etc.).\n\n"
        f"Current verdicts from your agents:\n{ticker_context}"
    )

    # Build messages: system + conversation history + new user message
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history[-6:]:  # cap at last 6 turns to control token usage
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        from services.clients.llm_client import get_async_llm_client
        client = await get_async_llm_client()
        resp = await client.chat.completions.create(
            model="qwen/qwen3-235b-a22b",
            messages=messages,
            temperature=0.4,
            max_tokens=256,
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("[ui/chat] LLM call failed: %s", exc)
        reply = _mock_reply(message)

    return {"reply": reply}


def _mock_reply(q: str) -> str:
    ql = q.lower()
    if "maruti" in ql:
        return "MARUTI's latest score reflects strong sales dispatch data and easing raw material costs. Check the Sales & Demand and Raw Materials agents for specifics."
    if "tata" in ql or "tatamotors" in ql:
        return "TATAMOTORS is being driven by EV order book strength. Watch JLR margin recovery and China supply chain risks in Risk & Macro."
    if "agent" in ql and "trust" in ql:
        return "For short-term moves, Pattern Analysis and Sentiment lead. For 3–6 month horizons, Fundamentals and Sales & Demand carry more weight."
    return "Ask me about a specific ticker like MARUTI or BAJAJ-AUTO, or about an agent like Sales & Demand."
