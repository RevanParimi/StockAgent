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
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import yfinance as yf

from core.config import settings

logger = logging.getLogger(__name__)

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
            return {"current": 0.0, "change_3m_pct": 0.0}

        close = df["Close"]
        if hasattr(close, "columns"):   # DataFrame (multi-ticker or multi-level columns)
            close = close.iloc[:, 0]
        close = close.dropna().astype(float)
        if len(close) < 2:
            return {"current": 0.0, "change_3m_pct": 0.0}
        current = float(close.iloc[-1])
        start_val = float(close.iloc[0])
        change_pct = (current - start_val) / start_val * 100 if start_val != 0 else 0.0
        return {
            "current": round(current, 4),
            "change_3m_pct": round(change_pct, 2),
        }
    except Exception as exc:
        logger.warning("[macro] Fetch failed for %s: %s", yf_ticker, exc)
        return {"current": 0.0, "change_3m_pct": 0.0}


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
        result[name] = _fetch_latest(ticker)

    # Rubber futures (TOCOM proxy) — skip gracefully if unavailable
    rubber = _fetch_latest(settings.RUBBER_TICKER)
    if rubber["current"] > 0:
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
        result[name] = _fetch_latest(ticker)
    return result


def get_raw_materials_context() -> str:
    """
    Returns a formatted string summarising raw material prices for prompt injection.
    Used by ContextBuilder._build_raw_materials().
    """
    prices = get_raw_material_prices()

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


_RBI_RATE_LAST_KNOWN     = "6.50"
_RBI_RATE_LAST_KNOWN_DATE = "2024-02-08"


def get_rbi_repo_rate() -> dict[str, str]:
    """
    RBI repo rate sourced from env var RBI_REPO_RATE_PCT (preferred) or
    last-known hardcoded value with a staleness warning.

    To update: set RBI_REPO_RATE_PCT=6.25 and RBI_RATE_DATE=2025-02-07 in .env
    Long-term: automate via Serper search or RBI press release scrape.
    See STATIC_AUDIT.md #1.
    """
    import os
    from datetime import date

    rate = os.getenv("RBI_REPO_RATE_PCT", "").strip()
    rate_date = os.getenv("RBI_RATE_DATE", "").strip()

    if not rate:
        rate = _RBI_RATE_LAST_KNOWN
        rate_date = _RBI_RATE_LAST_KNOWN_DATE
        try:
            last_dt = date.fromisoformat(rate_date)
            staleness = (date.today() - last_dt).days
            if staleness > 90:
                logger.warning(
                    "[macro] RBI repo rate is %s days stale (%s = %s%%). "
                    "Set RBI_REPO_RATE_PCT env var to override.",
                    staleness, rate_date, rate,
                )
        except Exception:
            pass

    return {
        "repo_rate_pct": rate,
        "last_change":   rate_date or _RBI_RATE_LAST_KNOWN_DATE,
        "stance":        os.getenv("RBI_RATE_STANCE", "neutral"),
        "note": "Source: RBI_REPO_RATE_PCT env var (set to override hardcoded fallback)",
    }


# ---------------------------------------------------------------------------
# Convenience: full macro context string
# ---------------------------------------------------------------------------

def get_macro_context() -> str:
    """
    Returns a formatted string summarising macro indicators for prompt injection.
    """
    inr = get_inr_usd_rate()
    crude = get_crude_oil_price()
    commodities = get_commodity_prices()
    rbi = get_rbi_repo_rate()

    steel = commodities.get("steel_etf", {})
    aluminium = commodities.get("aluminium_stock", {})
    rubber = commodities.get("rubber_futures", {})

    return (
        f"=== Macro & Commodity Data ===\n"
        f"INR/USD: {inr['current']} (3m change: {inr['change_3m_pct']:+.2f}%)\n"
        f"Crude Oil (WTI): ${crude['current']}/bbl (3m: {crude['change_3m_pct']:+.2f}%)\n"
        f"Steel (SLX ETF): ${steel.get('current', 'N/A')} (3m: {steel.get('change_3m_pct', 'N/A'):+.2f}%)\n"
        f"Aluminium (Alcoa proxy): ${aluminium.get('current', 'N/A')} "
        f"(3m: {aluminium.get('change_3m_pct', 'N/A'):+.2f}%)\n"
        f"Rubber Futures: {rubber.get('current', 'N/A')} "
        f"(3m: {rubber.get('change_3m_pct', 'N/A')})\n"
        f"RBI Repo Rate: {rbi['repo_rate_pct']}% | Stance: {rbi['stance']}"
    )
