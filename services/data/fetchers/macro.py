"""
tools/macro_fetcher.py
======================
Macro-economic data via yfinance (no API key needed).
Covers INR/USD, crude oil, steel, aluminium, and rubber prices.

Public API
----------
get_commodity_prices()      → dict
get_inr_usd_rate()          → float
get_macro_context()         → str   (formatted for prompt injection)
get_macro_result() / get_raw_materials_result() → FetchResult (SA-002)
get_overnight_markets(on)   → list[dict]  (the brief's "Before the open", PR-003)
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import date, datetime as _dt, timedelta

import yfinance as yf

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache for RBI repo rate (60-day TTL — MPC meets every ~45 days)
# ---------------------------------------------------------------------------
_RBI_CACHE: dict = {}  # {"rbi": {"repo_rate_pct": str, "stance": str, "fetched_at": str, ...}}
_RBI_CACHE_LOCK = threading.Lock()  # FIX 2: prevents duplicate Serper calls under concurrency

# ---------------------------------------------------------------------------
# In-memory cache for rubber price (4-hour TTL — market-level, same for all tickers)
# ---------------------------------------------------------------------------
_RUBBER_CACHE: dict = {}  # {"rubber": {"change_3m_pct": float, "source": str, "fetched_at": str}}

# ---------------------------------------------------------------------------
# In-memory daily cache for shared commodity tickers (avoids duplicate yfinance calls)
# ---------------------------------------------------------------------------
_COMMODITY_CACHE: dict = {}  # {ticker: {"data": {...}, "date": "YYYY-MM-DD"}}

# Map of macro indicator → yfinance ticker
_MACRO_TICKERS: dict[str, str] = {
    "crude_oil_usd":   settings.CRUDE_OIL_TICKER,   # WTI Crude Futures
    "inr_usd":         settings.INR_USD_TICKER,      # INR per 1 USD
    "steel_etf":       settings.STEEL_TICKER,        # SLX Steel ETF (USD proxy)
    "aluminium_stock": settings.ALUMINIUM_TICKER,    # Alcoa as aluminium proxy
}

# Raw material tickers for the Raw Materials agent
_RAW_MATERIAL_TICKERS: dict[str, str] = {
    "steel_etf":       settings.STEEL_TICKER,        # SLX — body/frame cost
    "aluminium_stock": settings.ALUMINIUM_TICKER,    # AA (Alcoa) — structural cost
    "platinum_etf":    settings.PLATINUM_TICKER,     # PPLT — catalytic converters
    "palladium_etf":   settings.PALLADIUM_TICKER,    # PALL — catalytic converters
    "crude_oil_wti":   settings.CRUDE_OIL_TICKER,   # CL=F — polymer cost proxy
    "crude_oil_brent": settings.BRENT_TICKER,        # BZ=F — global benchmark
}

_LOOKBACK_DAYS = 90  # 3 months for trend


def _fetch_latest(yf_ticker: str) -> dict[str, float]:
    """
    Fetch latest price and 3-month % change for a yfinance ticker.
    Returns {"current": x, "change_3m_pct": y}
    """
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS + 10)
    try:
        df = yf.download(
            yf_ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if df.empty or len(df) < 2:
            logger.warning("[macro] No price data returned for %s (empty or too short)", yf_ticker)
            return {"current": None, "change_3m_pct": None, "error": "no data returned"}

        close = df["Close"]
        if hasattr(close, "columns"):   # DataFrame (multi-ticker or multi-level columns)
            close = close.iloc[:, 0]
        close = close.dropna().astype(float)
        if len(close) < 2:
            logger.warning("[macro] Insufficient close prices for %s after dropna", yf_ticker)
            return {"current": None, "change_3m_pct": None, "error": "insufficient data after dropna"}
        current = float(close.iloc[-1])
        start_val = float(close.iloc[0])
        change_pct = (current - start_val) / start_val * 100 if start_val != 0 else 0.0
        return {
            "current": round(current, 4),
            "change_3m_pct": round(change_pct, 2),
        }
    except Exception as exc:
        logger.warning("[macro] Fetch failed for %s: %s", yf_ticker, exc)
        return {"current": None, "change_3m_pct": None, "error": str(exc)}


def _fetch_latest_cached(yf_ticker: str) -> dict[str, float]:
    """_fetch_latest with daily cache — avoids duplicate yfinance calls for shared tickers."""
    today = str(date.today())
    cached = _COMMODITY_CACHE.get(yf_ticker)
    if cached and cached.get("date") == today:
        return cached["data"]
    result = _fetch_latest(yf_ticker)
    _COMMODITY_CACHE[yf_ticker] = {"data": result, "date": today}
    return result


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_inr_usd_rate() -> dict[str, float]:
    """Returns current INR/USD rate and 3-month trend."""
    return _fetch_latest(settings.INR_USD_TICKER)


def get_crude_oil_price() -> dict[str, float]:
    """Returns current WTI crude oil price (USD/barrel) and 3-month trend."""
    return _fetch_latest(settings.CRUDE_OIL_TICKER)


def get_commodity_prices() -> dict[str, dict[str, float]]:
    """
    Returns latest price + 3-month change for all tracked macro commodities.

    Note on proxies:
      - Steel: uses SLX (VanEck Steel ETF, USD)
      - Aluminium: uses AA (Alcoa stock, USD) as a price-direction proxy
      - Rubber: TOCOM rubber not available on yfinance freely;
                uses MCX rubber futures via yfinance if available, else skipped
    """
    result: dict[str, dict[str, float]] = {}
    for name, ticker in _MACRO_TICKERS.items():
        result[name] = _fetch_latest_cached(ticker)

    # Rubber — yfinance tickers are delisted; use Serper news proxy instead
    rubber = _fetch_rubber_price_via_news()
    if rubber.get("change_3m_pct") is not None:
        result["rubber_futures"] = rubber

    return result


def get_raw_material_prices() -> dict[str, dict[str, float]]:
    """
    Returns latest price + 3-month change for raw materials relevant to auto OEMs.

    Covers:
      Steel (SLX ETF), Aluminium (Alcoa proxy), Platinum (PPLT ETF),
      Palladium (PALL ETF), WTI Crude (CL=F), Brent Crude (BZ=F)
    """
    result: dict[str, dict[str, float]] = {}
    for name, ticker in _RAW_MATERIAL_TICKERS.items():
        result[name] = _fetch_latest_cached(ticker)
    return result


def _fetch_rubber_price_via_news() -> dict[str, float]:
    """
    Fetch natural rubber price direction via Serper news search.
    Returns {"current": 0, "change_3m_pct": <direction>} — direction derived from news.
    Falls back to empty dict if no data.

    Result is cached for 4 hours (same as macro cache TTL) because rubber is
    a market-level indicator — the same for all tickers in a batch, so we only
    need one Serper call per 4-hour window regardless of batch size.
    """
    # FIX 1: Check 4-hour in-memory cache before firing a Serper call
    cached = _RUBBER_CACHE.get("rubber")
    if cached:
        try:
            age_hours = (_dt.now() - _dt.fromisoformat(cached["fetched_at"])).seconds / 3600
            if age_hours < 4:
                return cached
        except Exception:
            pass  # corrupt cache entry — re-fetch

    try:
        from services.data.fetchers.news import search_serper
        import re as _re
        results = search_serper(
            "natural rubber price India MCX today 2026",
            n=3,
            api_key=settings.SERPER_API_KEY,
        )
        for r in results:
            text = r.get("snippet", "") + " " + r.get("title", "")
            # Look for percentage change
            m = _re.search(r"(\d+\.?\d*)\s*%", text)
            direction = 1.0
            tl = text.lower()
            if any(w in tl for w in ["fall", "drop", "down", "decline", "lower"]):
                direction = -1.0
            elif any(w in tl for w in ["rise", "gain", "up", "rally", "higher"]):
                direction = 1.0
            if m:
                try:
                    pct = float(m.group(1).replace(",", "")) * direction
                except (ValueError, AttributeError) as exc:
                    logger.warning("[macro] Failed to parse rubber price from %r: %s",
                                   m.group(1) if m else None, exc)
                    continue
                result = {"current": 0, "change_3m_pct": round(pct, 2), "source": "serper_news",
                          "fetched_at": _dt.now().isoformat()}
                _RUBBER_CACHE["rubber"] = result
                return result
    except Exception as exc:
        logger.debug("[macro] Rubber news fetch failed: %s", exc)
    return {}


def get_raw_materials_context() -> str:
    """
    Returns a formatted string summarising raw material prices for prompt injection.
    Used by ContextBuilder._build_raw_materials().
    """
    return _format_raw_materials(get_raw_material_prices())


def _format_raw_materials(prices: dict) -> str:
    """The prompt text, byte-identical to the pre-SA-002 context string."""
    steel     = prices.get("steel_etf", {})
    aluminium = prices.get("aluminium_stock", {})
    platinum  = prices.get("platinum_etf", {})
    palladium = prices.get("palladium_etf", {})
    wti       = prices.get("crude_oil_wti", {})
    brent     = prices.get("crude_oil_brent", {})

    def fmt(d: dict, prefix: str = "$") -> str:
        cur = d.get("current", "N/A")
        chg = d.get("change_3m_pct", "N/A")
        if isinstance(chg, float):
            return f"{prefix}{cur} (3m: {chg:+.2f}%)"
        return f"{prefix}{cur} (3m: {chg})"

    return (
        f"=== Raw Material Prices ===\n"
        f"Steel (SLX ETF):         {fmt(steel)}\n"
        f"Aluminium (Alcoa proxy): {fmt(aluminium)}\n"
        f"Platinum (PPLT ETF):     {fmt(platinum)}\n"
        f"Palladium (PALL ETF):    {fmt(palladium)}\n"
        f"Crude Oil WTI:           {fmt(wti)}/bbl\n"
        f"Crude Oil Brent:         {fmt(brent)}/bbl"
    )


def get_rbi_repo_rate() -> dict[str, str]:
    """
    Live RBI repo rate from Serper, cached in-memory for 60 days.
    Fallback chain: Serper → settings.RBI_REPO_RATE_PCT → log warning.

    The entire function body runs under _RBI_CACHE_LOCK to prevent concurrent
    orchestrator threads from each hitting the cache miss simultaneously and
    firing parallel Serper calls for the same rate (FIX 2).
    """
    from datetime import date as _date
    import re as _re

    with _RBI_CACHE_LOCK:
        # Cache check (60-day TTL — MPC meets every ~45 days)
        cached = _RBI_CACHE.get("rbi")
        if cached:
            try:
                fetched = _date.fromisoformat(cached["fetched_at"])
                if (_date.today() - fetched).days < 60:
                    return cached
            except Exception:
                pass  # corrupt cache entry — re-fetch

        # Live fetch via Serper
        try:
            from services.data.fetchers.news import search_serper
            results = search_serper(
                "RBI Monetary Policy Committee repo rate India latest decision 2026",
                n=3,
                api_key=settings.SERPER_API_KEY,
            )
            for r in results:
                text = (r.get("snippet", "") + " " + r.get("title", "")).lower()
                # Match "repo rate [at/to/of/unchanged at] X.XX%"
                m = _re.search(r"repo rate[^\d]*(\d+\.?\d*)\s*%", text)
                if m:
                    rate = m.group(1)
                    # Detect stance
                    stance = "neutral"
                    if any(w in text for w in ["cut", "reduce", "lower", "dovish", "accommodative"]):
                        stance = "accommodative"
                    elif any(w in text for w in ["hike", "raise", "increase", "hawkish", "withdrawal"]):
                        stance = "withdrawal of accommodation"
                    result = {
                        "repo_rate_pct": rate,
                        "last_change": r.get("date", settings.RBI_REPO_RATE_DATE),
                        "stance": stance,
                        "note": f"Source: Serper live fetch ({_date.today()})",
                        "fetched_at": _date.today().isoformat(),
                    }
                    _RBI_CACHE["rbi"] = result
                    logger.info("[macro] RBI rate fetched live: %s%% (%s)", rate, stance)
                    return result
        except Exception as exc:
            logger.warning("[macro] RBI live fetch failed: %s — using settings fallback", exc)

        # Fallback to settings
        fallback = {
            "repo_rate_pct": settings.RBI_REPO_RATE_PCT,
            "last_change": settings.RBI_REPO_RATE_DATE,
            "stance": settings.RBI_REPO_RATE_STANCE,
            "note": f"Source: settings fallback (live fetch failed; update settings.RBI_REPO_RATE_PCT)",
            "fetched_at": _date.today().isoformat(),
            "fallback": True,   # SA-002: a configured value, not a fetched one
        }
        # Log staleness warning
        try:
            staleness = (_date.today() - _date.fromisoformat(settings.RBI_REPO_RATE_DATE)).days
            if staleness > 90:
                logger.warning("[macro] RBI settings fallback is %d days stale", staleness)
        except Exception:
            pass
        return fallback


# ---------------------------------------------------------------------------
# Convenience: full macro context string
# ---------------------------------------------------------------------------

def get_macro_context() -> str:
    """
    Returns a formatted string summarising macro indicators for prompt injection.

    Raises (TypeError/ValueError from the format specs) when a core indicator
    has no value — callers rely on that; `get_macro_result` reports it instead.
    """
    inr = get_inr_usd_rate()
    crude = get_crude_oil_price()
    commodities = get_commodity_prices()
    rbi = get_rbi_repo_rate()
    return _format_macro(inr, crude, commodities, rbi)


_MACRO_CORE = (("INR/USD", "inr"), ("crude WTI", "crude"),
               ("steel", "steel_etf"), ("aluminium", "aluminium_stock"))


def get_macro_result():
    """
    `get_macro_context` as a `FetchResult` (SA-002). A core indicator without
    a value is reported as `empty`, naming it, instead of surfacing as a
    format-spec TypeError; the bundle then renders the section `unavailable`,
    as it did when this raised. A missing rubber proxy or the RBI settings
    fallback is named in `reason` without changing the status: neither is a
    core indicator.
    """
    from services.data.context.fetch_result import (
        STATUS_EMPTY, STATUS_OK, FetchResult, join_reasons,
    )

    inr = get_inr_usd_rate()
    crude = get_crude_oil_price()
    commodities = get_commodity_prices()
    rbi = get_rbi_repo_rate()

    core = {"inr": inr, "crude": crude, **commodities}
    missing = [label for label, key in _MACRO_CORE
               if (core.get(key) or {}).get("current") is None
               or (core.get(key) or {}).get("change_3m_pct") is None]
    if missing:
        return FetchResult("", STATUS_EMPTY, "yfinance",
                           reason="no value for " + ", ".join(missing))
    return FetchResult(
        _format_macro(inr, crude, commodities, rbi), STATUS_OK, "yfinance",
        reason=join_reasons([
            "rubber proxy unavailable" if "rubber_futures" not in commodities else None,
            "RBI repo rate from settings fallback" if rbi.get("fallback") else None,
        ]),
    )


def get_raw_materials_result():
    """
    `get_raw_materials_context` as a `FetchResult` (SA-002): `empty` when no
    raw-material price came back (the text then shows `$None` on every line),
    `ok` otherwise with the missing ones named in `reason`.
    """
    from services.data.context.fetch_result import STATUS_EMPTY, STATUS_OK, FetchResult

    prices = get_raw_material_prices()
    text = _format_raw_materials(prices)
    missing = [name for name in _RAW_MATERIAL_TICKERS
               if (prices.get(name) or {}).get("current") is None]
    if len(missing) == len(_RAW_MATERIAL_TICKERS):
        return FetchResult(text, STATUS_EMPTY, "yfinance", reason="no raw-material price returned")
    return FetchResult(text, STATUS_OK, "yfinance",
                       reason=("no price for " + ", ".join(missing)) if missing else None)


def _format_macro(inr: dict, crude: dict, commodities: dict, rbi: dict) -> str:
    """The prompt text, byte-identical to the pre-SA-002 context string."""
    steel = commodities.get("steel_etf", {})
    aluminium = commodities.get("aluminium_stock", {})
    rubber = commodities.get("rubber_futures", {})

    rubber_str = (
        f"{rubber.get('change_3m_pct', 'N/A'):+.2f}% (news-based)"
        if rubber.get("change_3m_pct") is not None else "N/A (no data)"
    )

    return (
        f"=== Macro & Commodity Data ===\n"
        f"INR/USD: {inr['current']} (3m change: {inr['change_3m_pct']:+.2f}%)\n"
        f"Crude Oil (WTI): ${crude['current']}/bbl (3m: {crude['change_3m_pct']:+.2f}%)\n"
        f"Steel (SLX ETF): ${steel.get('current', 'N/A')} (3m: {steel.get('change_3m_pct', 'N/A'):+.2f}%)\n"
        f"Aluminium (Alcoa proxy): ${aluminium.get('current', 'N/A')} "
        f"(3m: {aluminium.get('change_3m_pct', 'N/A'):+.2f}%)\n"
        f"Rubber (MCX, news proxy): {rubber_str}\n"
        f"RBI Repo Rate: {rbi['repo_rate_pct']}% | Stance: {rbi['stance']}"
    )


# ---------------------------------------------------------------------------
# Overnight market figures for the morning brief (PR-003)
# ---------------------------------------------------------------------------

def _yahoo_daily_bars(ticker: str):
    """About a fortnight of Yahoo daily bars, indexed in the exchange's zone."""
    return yf.Ticker(ticker).history(period="10d", interval="1d", auto_adjust=False)


def _closes_by_date(df) -> list[tuple[date, float]]:
    """(exchange-local date, close) per bar, oldest first: finite positive
    closes on weekdays only, the last row kept when Yahoo repeats a date.
    Yahoo carries weekend quotes for some currencies (INR=X), but none of the
    brief's instruments has a weekend session, so a Saturday or Sunday bar is
    neither a level nor a previous session."""
    close = df["Close"]
    if hasattr(close, "columns"):   # multi-level columns
        close = close.iloc[:, 0]
    by_day: dict[date, float] = {}
    for ts, value in close.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v) and v > 0:
            day = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            if day.weekday() < 5:
                by_day[day] = v
    return sorted(by_day.items())


def _overnight_row(inst: dict, on: date, history, max_age_days: int) -> dict:
    row = {"label": inst["label"], "ticker": inst["ticker"],
           "unit": inst.get("unit", "index"), "session": inst.get("session", "24h")}
    try:
        bars = _closes_by_date(history(inst["ticker"]))
    except Exception as exc:
        logger.warning("[macro] overnight figure %s failed: %s", inst["ticker"], exc)
        return {**row, "status": "unavailable", "reason": "fetch failed"}
    # Issue-time rule: nothing dated after the brief; a US session dated the
    # brief's own day has not closed by 08:50 IST.
    last_ok = on - timedelta(days=1) if row["session"] == "us_close" else on
    bars = [b for b in bars if b[0] <= last_ok]
    if len(bars) < 2:
        return {**row, "status": "unavailable", "reason": "too few sessions"}
    (prev_day, prev), (day, value) = bars[-2], bars[-1]
    if row["session"] == "asia_live" and day != on:
        return {**row, "status": "closed", "as_of": day.isoformat()}
    if (on - day).days > max_age_days:
        return {**row, "status": "unavailable", "reason": f"latest session {day.isoformat()}"}
    out = {**row, "status": "ok", "value": round(value, 4), "as_of": day.isoformat(),
           "prev_as_of": prev_day.isoformat()}
    if row["unit"] == "yield":
        if not (0 < value < 20 and 0 < prev < 20):
            return {**row, "status": "unavailable", "reason": "implausible yield"}
        out["change_bp"] = round((value - prev) * 100, 1)
    else:
        out["change_pct"] = round((value / prev - 1) * 100, 2)
    return out


def get_overnight_markets(on: date, instruments: list[dict] | None = None,
                          history=None, max_age_days: int | None = None) -> list[dict]:
    """
    The brief's "Before the open" figures: one row per instrument with the
    latest close (or live level) up to `on`, its change on the previous
    session and the exchange-local date it is as of.

    status "ok" carries value, change_pct (change_bp for a yield) and as_of;
    "unavailable" (fetch failed, too few sessions, older than max_age_days,
    an implausible yield) carries no figure at all — never a zero; "closed"
    marks an asia_live market with no session on `on`. `history(ticker)` is
    injectable for tests; the default reads Yahoo.
    """
    instruments = settings.DELIVERY_BRIEF_MARKETS if instruments is None else instruments
    history = history or _yahoo_daily_bars
    max_age = settings.DELIVERY_BRIEF_MARKET_MAX_AGE_DAYS if max_age_days is None else max_age_days
    return [_overnight_row(inst, on, history, max_age) for inst in instruments]
