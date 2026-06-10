"""
services/data/fetchers/nse_market.py
=====================================
NSE market-level intelligence via nsepython (no API key needed).

Provides structured FII/DII flows, bulk/block deals, and upcoming
earnings events sourced directly from the NSE exchange.

Architecture
------------
Pre-fetch pattern: get_nse_market_data() fetches once and caches for the day.
ContextBuilder methods call format_nse_market_context() — no re-fetch per agent.

Cache: in-process dict keyed by date. Re-fetches on new calendar day or restart.

Signal value
------------
- FII/DII: structured daily net flows (Cr) — replaces fragile Serper news scraping
- Bulk deals: institutional accumulation/distribution per symbol (>0.5% listed shares)
- Upcoming earnings: board meeting dates per NSE symbol (earnings trigger signal)

Serper calls saved
------------------
- risk_macro: "{ticker} FII DII India net buying today" — eliminated
- institutional / bfsi_institutional: "{ticker} BSE bulk deal block trade" — eliminated
- fundamentals: "{company_name} next results date" across all agents — eliminated
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process daily cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict] = {}   # { "YYYY-MM-DD": market_data_dict }


def _today_key() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Internal fetch (calls nsepython)
# ---------------------------------------------------------------------------

def _fetch_nse_market_data() -> dict:
    """
    Live fetch from NSE via nsepython.
    Always returns a dict; never raises. Sets 'error' key on failure.
    """
    result: dict = {
        "fii_net_cr":            None,
        "dii_net_cr":            None,
        "combined_net_cr":       None,
        "fii_dii_signal":        "",
        "bulk_deal_net_buyers":  [],
        "bulk_deal_net_sellers": [],
        "bulk_deals_by_ticker":  {},   # { "TATAMOTORS": {"net_qty": int, "side": "BUY"|"SELL"|"MIXED"} }
        "upcoming_earnings":     [],   # [{"symbol": str, "date": str, "purpose": str}]
        "fetched_at":            _today_key(),
        "error":                 None,
    }

    try:
        from nsepython import get_bulkdeals, nse_fiidii, nse_events
        import pandas as pd
    except ImportError:
        result["error"] = "nsepython_not_installed"
        logger.warning("[nse_market] nsepython not installed — context will be empty")
        return result

    # --- FII / DII ---
    try:
        fii_df = nse_fiidii()
        if isinstance(fii_df, pd.DataFrame) and "netValue" in fii_df.columns:
            for _, row in fii_df.iterrows():
                cat = str(row.get("category", "")).upper()
                val = float(row.get("netValue", 0) or 0)
                if "FII" in cat or "FPI" in cat:
                    result["fii_net_cr"] = round(val, 2)
                elif "DII" in cat:
                    result["dii_net_cr"] = round(val, 2)

            fii = result["fii_net_cr"]
            dii = result["dii_net_cr"]
            if fii is not None and dii is not None:
                result["combined_net_cr"] = round(fii + dii, 2)
                if fii < 0 and dii > 0:
                    result["fii_dii_signal"] = "DII absorbing FII selling — moderate support"
                elif fii > 0 and dii > 0:
                    result["fii_dii_signal"] = "Both FII and DII buying — strong bullish conviction"
                elif fii < 0 and dii < 0:
                    result["fii_dii_signal"] = "Both FII and DII selling — risk-off, reduce exposure"
                else:
                    result["fii_dii_signal"] = "FII buying, DII selling — FII-led rally, watch DII re-entry"
    except Exception as exc:
        logger.debug("[nse_market] FII/DII fetch failed (non-fatal): %s", exc)

    # --- Bulk deals ---
    try:
        bd = get_bulkdeals()
        if isinstance(bd, pd.DataFrame) and not bd.empty:
            buys  = bd[bd["Buy/Sell"].str.upper() == "BUY"].groupby("Symbol")["Quantity Traded"].sum()
            sells = bd[bd["Buy/Sell"].str.upper() == "SELL"].groupby("Symbol")["Quantity Traded"].sum()
            net   = buys.subtract(sells, fill_value=0).sort_values(ascending=False)
            result["bulk_deal_net_buyers"]  = net[net > 0].index.tolist()[:5]
            result["bulk_deal_net_sellers"] = net[net < 0].index.tolist()[:5]

            # Per-ticker lookup
            for sym in set(bd["Symbol"].dropna().unique()):
                sym_rows = bd[bd["Symbol"] == sym]
                b_qty = int(sym_rows[sym_rows["Buy/Sell"].str.upper() == "BUY"]["Quantity Traded"].sum())
                s_qty = int(sym_rows[sym_rows["Buy/Sell"].str.upper() == "SELL"]["Quantity Traded"].sum())
                net_qty = b_qty - s_qty
                side = "BUY" if net_qty > 0 else ("SELL" if net_qty < 0 else "MIXED")
                result["bulk_deals_by_ticker"][str(sym)] = {"net_qty": net_qty, "side": side}
    except Exception as exc:
        logger.debug("[nse_market] Bulk deals fetch failed (non-fatal): %s", exc)

    # --- Upcoming earnings ---
    try:
        ev_df = nse_events()
        if isinstance(ev_df, pd.DataFrame) and not ev_df.empty:
            result["upcoming_earnings"] = [
                {
                    "symbol":  str(row.get("symbol", "")),
                    "date":    str(row.get("date", "")),
                    "purpose": str(row.get("purpose", ""))[:80],
                }
                for _, row in ev_df.head(15).iterrows()
                if row.get("symbol")
            ]
    except Exception as exc:
        logger.debug("[nse_market] Events fetch failed (non-fatal): %s", exc)

    logger.info(
        "[nse_market] Fetched: FII=%s Cr / DII=%s Cr | bulk_buyers=%s | "
        "upcoming_earnings=%d events",
        result["fii_net_cr"], result["dii_net_cr"],
        result["bulk_deal_net_buyers"],
        len(result["upcoming_earnings"]),
    )
    return result


# ---------------------------------------------------------------------------
# Public API — cached daily
# ---------------------------------------------------------------------------

def get_nse_market_data(force_refresh: bool = False) -> dict:
    """
    Return today's NSE market intelligence, fetching once per day.

    The result is an in-process cache — zero overhead for subsequent calls
    within the same process (typical: ContextBuilder calls this per agent,
    but NSE is only hit once per analysis session).
    """
    key = _today_key()
    if not force_refresh and key in _CACHE:
        return _CACHE[key]

    data = _fetch_nse_market_data()
    _CACHE[key] = data
    return data


# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

FocusMode = Literal["fii_dii", "bulk_deals", "all"]


def format_nse_market_context(
    data: dict,
    focus: FocusMode = "all",
    ticker: str | None = None,
) -> str:
    """
    Convert NSE market data dict to a formatted context string for prompt injection.

    Parameters
    ----------
    data   : dict from get_nse_market_data()
    focus  : "fii_dii"    — only FII/DII section (for risk_macro, re_risk, it_risk_macro)
             "bulk_deals" — only bulk deal section (for sentiment, institutional)
             "all"        — both sections + upcoming earnings
    ticker : when focus includes bulk_deals, show this ticker's specific activity

    Returns "" when data is empty or errored (agents fall back to Serper).
    """
    if not data or data.get("error") in ("nsepython_not_installed",):
        return ""

    lines: list[str] = []
    today = data.get("fetched_at", date.today().isoformat())

    # FII/DII section
    if focus in ("fii_dii", "all"):
        fii = data.get("fii_net_cr")
        dii = data.get("dii_net_cr")
        signal = data.get("fii_dii_signal", "")
        if fii is not None or dii is not None:
            lines.append(f"[NSE MARKET FLOWS — {today}]")
            if fii is not None:
                lines.append(f"  FII net: {fii:+,.2f} Cr")
            if dii is not None:
                lines.append(f"  DII net: {dii:+,.2f} Cr")
            combined = data.get("combined_net_cr")
            if combined is not None:
                lines.append(f"  Combined: {combined:+,.2f} Cr")
            if signal:
                lines.append(f"  Signal: {signal}")

    # Bulk deals section
    if focus in ("bulk_deals", "all"):
        buyers  = data.get("bulk_deal_net_buyers", [])
        sellers = data.get("bulk_deal_net_sellers", [])
        by_tkr  = data.get("bulk_deals_by_ticker", {})

        if buyers or sellers:
            lines.append(f"[NSE BULK DEALS — {today}]")
            if buyers:
                lines.append(f"  Net institutional buyers: {', '.join(buyers)}")
            if sellers:
                lines.append(f"  Net institutional sellers: {', '.join(sellers)}")

        # Ticker-specific activity
        if ticker and by_tkr:
            tkr_info = by_tkr.get(ticker.upper())
            if tkr_info:
                qty = tkr_info["net_qty"]
                side = tkr_info["side"]
                lines.append(
                    f"  {ticker}: bulk deal activity — net {side.lower()} "
                    f"{abs(qty):,} shares"
                )
            else:
                lines.append(f"  {ticker}: no bulk deal activity today")

    # Upcoming earnings (all mode only)
    if focus == "all":
        earnings = data.get("upcoming_earnings", [])
        if earnings:
            lines.append(f"[UPCOMING NSE EVENTS (next 10)]")
            for ev in earnings[:10]:
                sym     = ev.get("symbol", "")
                dt      = ev.get("date", "")
                purpose = ev.get("purpose", "")[:60]
                lines.append(f"  [{dt}] {sym}: {purpose}")

    return "\n".join(lines) if lines else ""


def get_upcoming_earnings_for_ticker(ticker: str, data: dict | None = None) -> str | None:
    """
    Return the next earnings date string for the given ticker, or None if not found.
    Uses pre-fetched market data (or fetches if not provided).
    """
    if data is None:
        data = get_nse_market_data()
    events = data.get("upcoming_earnings", [])
    for ev in events:
        if ev.get("symbol", "").upper() == ticker.upper():
            return ev.get("date")
    return None
