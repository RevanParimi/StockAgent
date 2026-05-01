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
GET  /ui/tickers             — all tickers with latest score + live price
GET  /ui/market/summary      — market pulse, drivers, sector changes, sparkline
POST /ui/chat                — conversational AI assistant reply
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ui", tags=["UI"])


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
    {"sym": "MARUTI",     "name": "Maruti Suzuki India Ltd",  "yf": "MARUTI.NS"},
    {"sym": "TATAMOTORS", "name": "Tata Motors Ltd",          "yf": "TATAMOTORS.NS"},
    {"sym": "M&M",        "name": "Mahindra & Mahindra Ltd",  "yf": "M&M.NS"},
    {"sym": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd",           "yf": "BAJAJ-AUTO.NS"},
    {"sym": "HEROMOTOCO", "name": "Hero MotoCorp Ltd",        "yf": "HEROMOTOCO.NS"},
    {"sym": "EICHERMOT",  "name": "Eicher Motors Ltd",        "yf": "EICHERMOT.NS"},
    {"sym": "TVSMOTORS",  "name": "TVS Motor Company Ltd",    "yf": "TVSMOTORS.NS"},
    {"sym": "ASHOKLEY",   "name": "Ashok Leyland Ltd",        "yf": "ASHOKLEY.NS"},
]

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
    {"key": "ev",      "icon": "⚡", "label": "EV-first",     "count": 5, "color": "#7c3aed"},
    {"key": "mass",    "icon": "🚗", "label": "Mass-market",  "count": 8, "color": "#0891b2"},
    {"key": "premium", "icon": "💎", "label": "Premium",      "count": 4, "color": "#d97706"},
    {"key": "cv",      "icon": "🚛", "label": "Commercial",   "count": 3, "color": "#16a34a"},
    {"key": "2w",      "icon": "🏍️", "label": "Two-wheelers", "count": 4, "color": "#dc2626"},
    {"key": "parts",   "icon": "⚙️", "label": "Auto-parts",   "count": 6, "color": "#475569"},
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
    """Return (current_price, change_pct). Sync — call via asyncio.to_thread."""
    try:
        import yfinance as yf
        t = yf.Ticker(yf_ticker)
        hist = t.history(period="5d", auto_adjust=True)
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


def _build_agents_response() -> dict:
    from core.config import settings
    weights = settings.AGENT_WEIGHTS
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

    ticker_rows = await asyncio.gather(*(fetch_one(t) for t in _ALL_TICKERS))
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

        # Watchlist — window.WATCHLIST
        "WATCHLIST": _WATCHLIST_DEFAULT,

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
    Accepts {message: str, context?: str} and returns {reply: str}.
    Uses the same LLM client as the analysis agents.
    Keeps a simple context: recent ticker verdicts injected into the system prompt.
    """
    message: str = (body.get("message") or "").strip()
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

    try:
        from services.clients.llm_client import get_async_llm_client
        client = await get_async_llm_client()
        resp = await client.chat.completions.create(
            model="qwen/qwen3-235b-a22b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": message},
            ],
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
