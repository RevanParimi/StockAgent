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
# User-customised category ticker lists (overrides hardcoded _CATEGORIES tickers)
_CATEGORY_TICKERS_PATH = Path("data/category_tickers.json")


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
        # Agent array — matches window.AGENTS shape expected by prototype
        "AGENTS": _build_agents_response()["agents"],

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
async def update_category_tickers(key: str, body: _CategoryTickersBody) -> dict:
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


def _ctx_rl_learning() -> str:
    try:
        from core.intelligence.rl.stores.prediction_store import PredictionStore
        from core.config import settings as cfg
        parts = []
        for ticker in (cfg.SCHEDULER_TICKERS or []):
            try:
                ps = PredictionStore(ticker, sector="automobile")
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
                if wm and wm.learned_weights:
                    top = sorted(wm.learned_weights.items(), key=lambda x: x[1], reverse=True)[:3]
                    top_str = " > ".join(f"{k}({v:.2f})" for k, v in top)
                    parts.append(f"    {ticker} top-weighted agents: {top_str}")
            except Exception:
                continue
        return ("RL LEARNING STATE:\n" + "\n".join(parts)) if parts else ""
    except Exception:
        return ""


def _build_chat_context(_message: str) -> str:
    """Always-available lightweight context: current verdicts only.
    History and RL data are fetched on-demand via get_analysis_history / get_rl_insights tools."""
    cv = _ctx_current_verdicts()
    return cv or "No analysis data yet — run a ticker analysis from the Home screen first."


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
]


def _looks_like_yf_symbol(s: str) -> bool:
    """True if the string is already a yfinance symbol (e.g. SI=F, ^NSEI, BTC-USD, XAGUSD=X)."""
    return "=" in s or s.startswith("^") or ("-" in s and len(s) <= 10)


async def _resolve_yf_symbol(symbol: str) -> str | None:
    """
    Three-tier symbol resolution:
    1. Static dict   — instant, covers ~20 known commodities/indices
    2. Direct symbol — if input already looks like a yfinance ticker
    3. yfinance.Search — real-time discovery for anything unrecognised
    Returns the resolved yfinance symbol, or None if all tiers fail.
    """
    sym_lower = symbol.strip().lower()
    sym_upper = symbol.strip().upper()

    # Tier 1: static dict
    if sym_lower in _COMMODITY_YF:
        return _COMMODITY_YF[sym_lower]

    # Tier 2: already a valid yfinance symbol
    if _looks_like_yf_symbol(sym_upper):
        return sym_upper

    # Tier 3: yfinance.Search for anything unrecognised (real-time)
    try:
        import yfinance as yf
        def _search():
            results = yf.Search(symbol, max_results=3, news_count=0)
            quotes = getattr(results, "quotes", []) or []
            # Prefer equity/futures/index quotes over ETFs
            for q in quotes:
                qtype = (q.get("quoteType") or "").upper()
                if qtype in ("FUTURE", "INDEX", "CRYPTOCURRENCY", "EQUITY", "CURRENCY"):
                    return q.get("symbol")
            return quotes[0].get("symbol") if quotes else None
        found = await asyncio.to_thread(_search)
        if found:
            logger.info("[chat/price] yfinance.Search resolved '%s' → %s", symbol, found)
            return found
    except Exception as exc:
        logger.debug("[chat/price] yfinance.Search failed for '%s': %s", symbol, exc)

    # Final fallback: treat as NSE stock
    return sym_upper + ".NS"


async def _chat_tool_get_live_price(symbol: str) -> str:
    yf_sym = await _resolve_yf_symbol(symbol)
    if not yf_sym:
        return f"Could not resolve a market symbol for '{symbol}'."

    try:
        price, change_pct = await asyncio.to_thread(_fetch_yf_price, yf_sym)
        if price == 0.0:
            return f"No price data for '{symbol}' (tried {yf_sym}) — market may be closed or symbol unavailable."
        is_usd = any(yf_sym.endswith(s) for s in ("=F", "-USD", "=X")) or yf_sym.startswith("^")
        currency = "USD" if is_usd else "INR"
        arrow = "▲" if change_pct >= 0 else "▼"
        return f"{symbol.title()} ({yf_sym}): {price:.2f} {currency}  {arrow}{abs(change_pct):.2f}% today"
    except Exception as exc:
        return f"Price fetch failed for '{symbol}': {exc}"


async def _chat_tool_search_news(query: str) -> str:
    try:
        from services.clients.tavily_fetcher import search_tavily
        results = await asyncio.to_thread(search_tavily, query, 3, "basic")
        if not results:
            return "No recent news found for that query."
        lines = []
        for r in results:
            date_str = r.get("published_date", "")
            date_tag = f" [{date_str[:10]}]" if date_str else ""  # e.g. [2026-05-07]
            lines.append(f"• {r['title']}{date_tag}: {r['content'][:300]}\n  Source: {r['url']}")
        return "\n".join(lines)
    except Exception as exc:
        return f"News search failed: {exc}"


async def _execute_chat_tool(name: str, args: dict) -> str:
    if name == "get_live_price":
        return await _chat_tool_get_live_price(args.get("symbol", ""))
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
    return f"Unknown tool: {name}"


_CHAT_SYSTEM_PROMPT = """\
You are StockAgent, a market intelligence assistant with real-time web search and live price tools.

## Your tools
- **get_live_price(symbol)** — live price for any NSE stock or global commodity/index.
  Pass a plain name (silver, gold, crude, nifty, usd, bitcoin) OR a yfinance symbol (SI=F, BZ=F, ^NSEI).
  Unknown assets are resolved automatically — just pass what the user said.
- **search_market_news(query)** — real-time web search: headlines, data, analysis
- **get_stock_analysis(ticker)** — our AI verdict + 9-agent scores for tracked NSE stocks
- **get_analysis_history(days)** — past verdicts and score trends from our database
- **get_rl_insights()** — agent accuracy, learned weights, and prediction lessons

## When to call tools — call first, answer after
| User asks | Tools to call |
|---|---|
| Current price | get_live_price |
| Why moving / what's driving | get_live_price + search_market_news (parallel) |
| Outlook / forecast / next N days | get_live_price + search_market_news("X outlook [year]") |
| NSE stock deep dive | get_live_price + get_stock_analysis + search_market_news |
| What happened last week / history | get_analysis_history |
| Agent accuracy / which to trust | get_rl_insights |
| Macro event (Fed, RBI, oil) | search_market_news |

ALWAYS call search_market_news for forward-looking questions. Use specific queries:
"silver price outlook next 30 days supply demand 2026" not just "silver".

## Hard rules
- NEVER say "consult market research reports", "check external sources", or "I cannot predict".
  You HAVE web search — use it and give your own observation from the data you fetch.
- NEVER refuse to give an outlook. Always search first, then synthesise what the data shows.
- Base conclusions on: live price + fetched news/analysis. Not training memory.
- Analyst opinions may be cited as one data point but must not be the conclusion.
- If search returns nothing useful, say what the live price action itself implies directionally.
- **PRICE VALUES**: ONLY cite prices from get_live_price() results. NEVER quote a price figure
  from a news article — article prices are stale the moment they're published. If an article
  mentions "₹210 target", treat it as analyst opinion only, verify current price via get_live_price.
- **DATA FRESHNESS**: Each search result includes a [YYYY-MM-DD] publication date. Always note
  if an article is older than 3 days. Prefer articles dated within the last 48 hours.

## Output format — always structured markdown
**Asset: $PRICE ▲/▼CHANGE% today**

One-line context sentence.

**What the data shows:**
- **Driver 1** — specific detail from fetched data
- **Driver 2** — specific detail
- **Near-term signal** — what current price action + news implies for the next period

*Source: live price · [headline or search result]*

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
    history: list = body.get("history") or []
    if not message:
        return {"reply": "Ask me anything — live prices, why a market is moving, stock verdicts, or what our agents say."}

    context = _build_chat_context(message)
    system_prompt = _CHAT_SYSTEM_PROMPT.format(context=context)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history[-8:]:
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        from services.clients.llm_client import get_async_llm_client
        client = get_async_llm_client()

        for _ in range(4):
            resp = await client.chat.completions.create(
                model="qwen/qwen3-235b-a22b",
                messages=messages,
                temperature=0.4,
                max_tokens=600,
                tools=_CHAT_TOOLS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                return {"reply": (msg.content or "").strip()}

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

        # Final synthesis after max tool rounds
        resp = await client.chat.completions.create(
            model="qwen/qwen3-235b-a22b",
            messages=messages,
            temperature=0.4,
            max_tokens=600,
        )
        return {"reply": (resp.choices[0].message.content or "").strip()}

    except Exception as exc:
        logger.warning("[ui/chat] LLM call failed: %s", exc)
        return {"reply": _mock_reply(message)}


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
# Managed tickers — GET/PUT/POST/DELETE /ui/tickers/managed
# ---------------------------------------------------------------------------

_VALID_SECTORS = ["automobile", "banking_bfsi", "it_sector", "renewable_energy"]


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
    sym:     str
    name:    str = ""
    sector:  str = "automobile"
    enabled: bool = True


@router.put("/tickers/managed", summary="Replace the entire managed ticker list")
async def replace_managed_tickers(body: list[_ManagedTickerBody]) -> dict:
    tickers = [t.model_dump() for t in body]
    for t in tickers:
        if t["sector"] not in _VALID_SECTORS:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail=f"Unknown sector '{t['sector']}'")
    _save_mt(tickers)
    logger.info("[ui/tickers/managed] Replaced list: %d tickers", len(tickers))
    return {"tickers": tickers}


@router.post("/tickers/managed/{sym}", summary="Add a ticker to the managed list")
async def add_managed_ticker(sym: str, body: _ManagedTickerBody) -> dict:
    from services.api.log_buffer import _KNOWN_NAMES
    tickers = _load_mt()
    sym_up = sym.strip().upper()
    if any(t["sym"] == sym_up for t in tickers):
        return {"tickers": tickers, "message": f"{sym_up} already in managed list"}
    tickers.append({
        "sym":     sym_up,
        "name":    body.name or _KNOWN_NAMES.get(sym_up, sym_up),
        "sector":  body.sector if body.sector in _VALID_SECTORS else "automobile",
        "enabled": body.enabled,
    })
    _save_mt(tickers)
    logger.info("[ui/tickers/managed] Added %s (%s)", sym_up, body.sector)
    return {"tickers": tickers}


@router.delete("/tickers/managed/{sym}", summary="Remove a ticker from the managed list")
async def remove_managed_ticker(sym: str) -> dict:
    sym_up = sym.strip().upper()
    tickers = [t for t in _load_mt() if t["sym"] != sym_up]
    _save_mt(tickers)
    logger.info("[ui/tickers/managed] Removed %s", sym_up)
    return {"tickers": tickers}


@router.patch("/tickers/managed/{sym}/toggle", summary="Enable or disable a managed ticker")
async def toggle_managed_ticker(sym: str) -> dict:
    sym_up = sym.strip().upper()
    tickers = _load_mt()
    for t in tickers:
        if t["sym"] == sym_up:
            t["enabled"] = not t.get("enabled", True)
            break
    _save_mt(tickers)
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
