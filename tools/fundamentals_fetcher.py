"""
tools/fundamentals_fetcher.py
==============================
Financial statement data via yfinance (no API key needed).
Covers quarterly P&L, margins, shareholding, and order book proxies.

Public API
----------
get_financials(ticker)      → dict   (revenue, EBITDA, margins, QoQ/YoY)
get_shareholding(ticker)    → dict   (promoter %, FII %, DII %)
get_fundamentals_context(ticker) → str  (formatted for prompt injection)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from config import settings

logger = logging.getLogger(__name__)


def _nse_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.endswith(settings.YFINANCE_SUFFIX):
        return t
    if t in {"M&M", "MM"}:
        return f"M&M{settings.YFINANCE_SUFFIX}"
    return f"{t}{settings.YFINANCE_SUFFIX}"


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Revenue & EBITDA
# ---------------------------------------------------------------------------

def get_financials(ticker: str) -> dict:
    """
    Fetch quarterly income statement data.

    Returns
    -------
    dict with:
      quarterly_revenue   : list of (quarter, revenue_cr)
      quarterly_ebitda    : list of (quarter, ebitda_cr)  [approximated as operating income]
      revenue_qoq_pct     : QoQ revenue growth %
      revenue_yoy_pct     : YoY revenue growth %
      ebitda_margin_pct   : latest EBITDA margin %
      peer_ebitda_margins : dict of peer → margin (requires separate calls)
    """
    yf_ticker = _nse_ticker(ticker)
    try:
        stock = yf.Ticker(yf_ticker)
        q_income = stock.quarterly_income_stmt

        if q_income is None or q_income.empty:
            logger.warning("[fundamentals] No quarterly income data for %s", yf_ticker)
            return {"error": f"No financial data available for {ticker}"}

        # yfinance columns are dates (newest first) — take last N quarters
        n = settings.FINANCIALS_LOOKBACK_QUARTERS
        quarters = q_income.columns[:n]

        def get_row(df: pd.DataFrame, *keys: str) -> pd.Series:
            for k in keys:
                if k in df.index:
                    return df.loc[k]
            return pd.Series([0.0] * len(df.columns), index=df.columns)

        revenue_row = get_row(q_income, "Total Revenue", "Revenue")
        op_income_row = get_row(q_income, "Operating Income", "EBIT", "Gross Profit")

        revenues = [_safe_float(revenue_row[q]) / 1e7 for q in quarters]   # to Crores
        ebitdas = [_safe_float(op_income_row[q]) / 1e7 for q in quarters]
        quarter_labels = [str(q)[:10] for q in quarters]

        # QoQ and YoY growth
        rev_qoq = (
            (revenues[0] - revenues[1]) / abs(revenues[1]) * 100
            if len(revenues) >= 2 and revenues[1] != 0 else 0.0
        )
        rev_yoy = (
            (revenues[0] - revenues[-1]) / abs(revenues[-1]) * 100
            if len(revenues) >= 4 and revenues[-1] != 0 else 0.0
        )
        ebitda_margin = (
            ebitdas[0] / revenues[0] * 100
            if revenues[0] != 0 else 0.0
        )

        return {
            "quarterly_revenue_cr": list(zip(quarter_labels, [round(r, 2) for r in revenues])),
            "quarterly_ebitda_cr":  list(zip(quarter_labels, [round(e, 2) for e in ebitdas])),
            "revenue_qoq_pct":  round(rev_qoq, 2),
            "revenue_yoy_pct":  round(rev_yoy, 2),
            "ebitda_margin_pct": round(ebitda_margin, 2),
        }

    except Exception as exc:
        logger.error("[fundamentals] get_financials failed for %s: %s", yf_ticker, exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Margins vs peers
# ---------------------------------------------------------------------------

def get_peer_margins(peers: list[str] | None = None) -> dict[str, float]:
    """
    Fetch latest EBITDA margin for a list of peer OEM tickers.
    Returns {ticker: ebitda_margin_pct}
    """
    if peers is None:
        peers = settings.PEER_TICKERS[:5]  # limit to avoid rate limits

    result: dict[str, float] = {}
    for p in peers:
        fin = get_financials(p)
        if "error" not in fin:
            result[p] = fin.get("ebitda_margin_pct", 0.0)
    return result


# ---------------------------------------------------------------------------
# Shareholding (FII / DII / Promoter proxy via institutional holders)
# ---------------------------------------------------------------------------

def get_shareholding(ticker: str) -> dict:
    """
    Returns institutional (FII+DII proxy) and major holder breakdown.
    yfinance does not separate FII from DII — returns combined institutional %.
    """
    yf_ticker = _nse_ticker(ticker)
    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info or {}

        institutional_pct = _safe_float(info.get("heldPercentInstitutions", 0)) * 100
        insider_pct = _safe_float(info.get("heldPercentInsiders", 0)) * 100

        major_holders = stock.major_holders
        promoter_pct = 0.0
        if major_holders is not None and not major_holders.empty:
            # Row 0: % shares held by insiders; Row 2: % held by institutions
            try:
                promoter_pct = float(str(major_holders.iloc[0, 0]).strip("%"))
            except Exception:
                pass

        return {
            "promoter_insider_pct": round(insider_pct, 2),
            "institutional_pct":    round(institutional_pct, 2),
            "note": "yfinance combines FII+DII into institutional_pct. "
                    "For split, use NSE bulk deal data.",
        }
    except Exception as exc:
        logger.warning("[fundamentals] get_shareholding failed for %s: %s", yf_ticker, exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Company info (headcount proxy + basic metadata)
# ---------------------------------------------------------------------------

def get_company_info(ticker: str) -> dict:
    """Fetch basic company info from yfinance."""
    yf_ticker = _nse_ticker(ticker)
    try:
        info = yf.Ticker(yf_ticker).info or {}
        return {
            "company_name":    info.get("longName", ticker),
            "sector":          info.get("sector", ""),
            "industry":        info.get("industry", ""),
            "full_time_employees": info.get("fullTimeEmployees", "N/A"),
            "market_cap_cr":   round(_safe_float(info.get("marketCap", 0)) / 1e7, 2),
            "pe_ratio":        round(_safe_float(info.get("trailingPE", 0)), 2),
            "pb_ratio":        round(_safe_float(info.get("priceToBook", 0)), 2),
            "dividend_yield":  round(_safe_float(info.get("dividendYield", 0)) * 100, 2),
            "description":     (info.get("longBusinessSummary", "") or "")[:400],
        }
    except Exception as exc:
        logger.warning("[fundamentals] get_company_info failed for %s: %s", yf_ticker, exc)
        return {}


# ---------------------------------------------------------------------------
# Convenience: full fundamentals context string
# ---------------------------------------------------------------------------

def get_fundamentals_context(ticker: str) -> str:
    fin = get_financials(ticker)
    sh = get_shareholding(ticker)
    info = get_company_info(ticker)

    if "error" in fin:
        fin_block = f"Financial data unavailable: {fin['error']}"
    else:
        rev_table = " | ".join(
            f"{q}: ₹{r}Cr" for q, r in fin.get("quarterly_revenue_cr", [])
        )
        ebitda_table = " | ".join(
            f"{q}: ₹{e}Cr" for q, e in fin.get("quarterly_ebitda_cr", [])
        )
        fin_block = (
            f"Revenue (quarterly): {rev_table}\n"
            f"EBITDA  (quarterly): {ebitda_table}\n"
            f"Revenue QoQ: {fin.get('revenue_qoq_pct', 0):+.1f}% | "
            f"Revenue YoY: {fin.get('revenue_yoy_pct', 0):+.1f}% | "
            f"EBITDA Margin: {fin.get('ebitda_margin_pct', 0):.1f}%"
        )

    sh_block = (
        f"Promoter/Insider: {sh.get('promoter_insider_pct', 'N/A')}% | "
        f"Institutional (FII+DII): {sh.get('institutional_pct', 'N/A')}%"
        if "error" not in sh
        else f"Shareholding unavailable: {sh.get('error')}"
    )

    info_block = (
        f"Employees: {info.get('full_time_employees', 'N/A')} | "
        f"Market Cap: ₹{info.get('market_cap_cr', 'N/A')}Cr | "
        f"P/E: {info.get('pe_ratio', 'N/A')} | P/B: {info.get('pb_ratio', 'N/A')}"
    ) if info else ""

    return (
        f"=== Fundamentals: {ticker} ===\n"
        f"{fin_block}\n"
        f"{sh_block}\n"
        f"{info_block}"
    )
