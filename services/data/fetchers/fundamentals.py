"""
tools/fundamentals_fetcher.py
==============================
Financial statement data via yfinance (no API key needed).
Covers quarterly P&L, margins, shareholding, and order book proxies.

Public API
----------
get_financials(ticker)      → dict   (revenue, EBITDA or a bank's net interest income,
                                      margins, QoQ/YoY)
get_shareholding(ticker)    → dict   (promoter %, FII %, DII %)
get_fundamentals_context(ticker) → str  (formatted for prompt injection)
get_fundamentals_result(ticker)  → FetchResult (the same text + status/as-of, SA-002)
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd
import yfinance as yf

from core.config import settings

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


def _is_reported(val: Any) -> bool:
    """True when a statement cell holds a finite number.

    SA-002 review M2: yfinance lists an announced quarter before its figures
    are populated, as NaN. `_safe_float` passes NaN through (the prompt shows
    `nan`) and turns None into 0.0; neither is a reported figure.
    """
    try:
        return math.isfinite(float(val))
    except (TypeError, ValueError):
        return False


# FIX-003: a bank's statement reports interest income and net interest income
# and has no operating line at all. That is its format, not a gap. The shape
# decides it, never the ticker or its sector: PAYTM reports EBIT beside its net
# interest income and stays a standard statement.
_OPERATING_ROWS = ("Operating Income", "EBIT", "Gross Profit")
_BANK_ROWS = ("Interest Income", "Net Interest Income")


def _is_bank_format(index: pd.Index) -> bool:
    """Both bank rows present, and none of the rows operating income is read from."""
    return (all(k in index for k in _BANK_ROWS)
            and not any(k in index for k in _OPERATING_ROWS))


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

    A bank-format statement (FIX-003) has `statement_format` "bank", its
    `quarterly_net_interest_income_cr` in place of an operating line, and
    `quarterly_ebitda_cr` and `ebitda_margin_pct` None rather than zeros.
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

        missing_rows: list[str] = []

        def get_row(df: pd.DataFrame, label: str, *keys: str) -> pd.Series:
            for k in keys:
                if k in df.index:
                    return df.loc[k]
            # SA-002: the zeros below are a substitute, not a reported figure.
            missing_rows.append(label)
            return pd.Series([0.0] * len(df.columns), index=df.columns)

        revenue_row = get_row(q_income, "revenue", "Total Revenue", "Revenue")
        # FIX-003: a bank's earnings line is its net interest income. It has
        # no operating income, so none is substituted.
        bank = _is_bank_format(q_income.index)
        core_label, core_keys = (("net_interest_income", ("Net Interest Income",)) if bank
                                 else ("operating_income", _OPERATING_ROWS))
        core_row = get_row(q_income, core_label, *core_keys)

        revenues = [_safe_float(revenue_row[q]) / 1e7 for q in quarters]   # to Crores
        core = [_safe_float(core_row[q]) / 1e7 for q in quarters]
        quarter_labels = [str(q)[:10] for q in quarters]

        # SA-002 review M2: a present row can still lack a figure for a
        # quarter. Name those cells, and date the statement by the newest
        # quarter in which every present row reported one.
        missing_values: dict[str, list[str]] = {}
        for label, row in (("revenue", revenue_row), (core_label, core_row)):
            if label in missing_rows:
                continue
            blank = [ql for q, ql in zip(quarters, quarter_labels) if not _is_reported(row[q])]
            if blank:
                missing_values[label] = blank
        reported = [ql for ql in quarter_labels
                    if not any(ql in qs for qs in missing_values.values())]

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
            core[0] / revenues[0] * 100
            if revenues[0] != 0 else 0.0
        )
        core_cr = list(zip(quarter_labels, [round(e, 2) for e in core]))

        result = {
            "quarterly_revenue_cr": list(zip(quarter_labels, [round(r, 2) for r in revenues])),
            # FIX-003: a bank has no EBITDA line and no margin to show: None, not 0.0.
            "quarterly_ebitda_cr":  None if bank else core_cr,
            "revenue_qoq_pct":  round(rev_qoq, 2),
            "revenue_yoy_pct":  round(rev_yoy, 2),
            "ebitda_margin_pct": None if bank else round(ebitda_margin, 2),
            # SA-002 provenance, additive: the newest fully reported quarter
            # end, which statement rows were absent and replaced by zeros, and
            # which present rows had no figure (row -> quarter ends).
            "as_of": reported[0] if reported else None,
            "missing_rows": missing_rows,
            "missing_values": missing_values,
            "statement_format": "bank" if bank else "standard",   # FIX-003, additive
        }
        if bank:
            result["quarterly_net_interest_income_cr"] = core_cr
        return result

    except Exception as exc:
        logger.error("[fundamentals] get_financials failed for %s: %s", yf_ticker, exc)
        return {"error": str(exc), "error_type": type(exc).__name__}


# ---------------------------------------------------------------------------
# Margins vs peers
# ---------------------------------------------------------------------------

def get_peer_margins(peers: list[str] | None = None) -> dict[str, float]:
    """
    Fetch latest EBITDA margin for a list of peer OEM tickers.
    Returns {ticker: ebitda_margin_pct}. A bank-format statement has no
    margin (FIX-003) and is left out.
    """
    if peers is None:
        peers = settings.PEER_TICKERS[:5]  # limit to avoid rate limits

    result: dict[str, float] = {}
    for p in peers:
        fin = get_financials(p)
        if "error" not in fin and fin.get("ebitda_margin_pct") is not None:
            result[p] = fin["ebitda_margin_pct"]
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
            # SA-002, additive: fields yfinance omitted, shown above as 0.0.
            "missing_fields": [k for k in ("heldPercentInsiders", "heldPercentInstitutions")
                               if info.get(k) is None],
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
            # SA-002, additive: fields yfinance omitted, shown as 0.0 / N/A.
            "missing_fields": [k for k in ("marketCap", "trailingPE", "priceToBook")
                               if info.get(k) is None],
        }
    except Exception as exc:
        logger.warning("[fundamentals] get_company_info failed for %s: %s", yf_ticker, exc)
        return {}


# ---------------------------------------------------------------------------
# Convenience: full fundamentals context string
# ---------------------------------------------------------------------------

def get_fundamentals_context(ticker: str) -> str:
    return get_fundamentals_result(ticker).text


def get_fundamentals_result(ticker: str):
    """
    `get_fundamentals_context` with its outcome (SA-002). The status follows
    the core datum, the quarterly statement, read from `get_financials`'
    structured result — never from the rendered sentence:

    - no statement (`error`): `empty`, or `failed:<Type>` when it raised;
    - a revenue or operating-income row absent, so zeros were substituted:
      `fallback`. A bank-format statement (FIX-003) has no operating line by
      format; its net interest income stands in that rule's place, and
      `reason` names the format;
    - the newest listed quarter without a figure in a present row (NaN, as
      yfinance lists an announced but unpopulated quarter): `fallback`, with
      `as_of` the newest fully reported quarter (review M2);
    - newest quarter older than the fundamentals freshness bound: `stale`;
    - otherwise `ok`. Missing shareholding or company info, and an older
      quarter without a figure, are named in `reason` without changing the
      status.
    """
    from services.data.context.fetch_result import (
        STATUS_EMPTY, STATUS_FAILED_PREFIX, STATUS_FALLBACK, STATUS_OK, STATUS_STALE,
        FetchResult, fundamentals_max_age_days, is_stale, join_reasons,
    )

    fin = get_financials(ticker)
    sh = get_shareholding(ticker)
    info = get_company_info(ticker)
    text = _format_fundamentals(ticker, fin, sh, info)

    partial = [
        "shareholding unavailable" if "error" in sh else None,
        ("shareholding fields absent, 0.0 shown: " + ", ".join(sh["missing_fields"])
         if sh.get("missing_fields") else None),
        "company info unavailable" if not info else None,
        ("company info fields absent, 0.0 shown: " + ", ".join(info["missing_fields"])
         if info.get("missing_fields") else None),
    ]
    if "error" in fin:
        status = (f"{STATUS_FAILED_PREFIX}{fin['error_type']}" if fin.get("error_type")
                  else STATUS_EMPTY)
        return FetchResult(text, status, "yfinance",
                           reason=join_reasons([f"financials: {fin['error']}", *partial]))

    as_of = fin.get("as_of")
    listed = [q for q, _ in fin.get("quarterly_revenue_cr", [])]    # newest first
    newest = listed[0] if listed else None
    blank = fin.get("missing_values") or {}
    newest_blank = [row for row, qs in blank.items() if newest in qs]
    older_blank = [f"{row} {q}" for row, qs in blank.items() for q in qs if q != newest]
    statement = [
        ("bank-format statement (interest income and net interest income, no operating-income"
         " row): operating margin not reported" if fin.get("statement_format") == "bank" else None),
        ("statement rows absent, zeros substituted: " + ", ".join(fin["missing_rows"])
         if fin.get("missing_rows") else None),
        (f"newest quarter {newest} has no figure for: " + ", ".join(newest_blank)
         + (f"; newest fully reported quarter {as_of}" if as_of else "; no quarter fully reported")
         if newest_blank else None),
        ("older quarters without a figure: " + ", ".join(older_blank) if older_blank else None),
    ]
    if fin.get("missing_rows") or newest_blank:
        return FetchResult(text, STATUS_FALLBACK, "yfinance", as_of=as_of,
                           reason=join_reasons([*statement, *partial]))
    max_age = fundamentals_max_age_days()
    if is_stale(as_of, max_age):
        return FetchResult(text, STATUS_STALE, "yfinance", as_of=as_of,
                           reason=join_reasons([
                               f"newest quarter {as_of} is older than {max_age} days",
                               *statement, *partial]))
    return FetchResult(text, STATUS_OK, "yfinance", as_of=as_of,
                       reason=join_reasons([*statement, *partial]))


def _format_fundamentals(ticker: str, fin: dict, sh: dict, info: dict) -> str:
    """The prompt text, byte-identical to the pre-SA-002 context string for a
    standard statement. A bank-format statement (FIX-003) shows its net
    interest income and says operating margin is not reported, never 0.0."""
    if "error" in fin:
        fin_block = f"Financial data unavailable: {fin['error']}"
    else:
        rev_table = " | ".join(
            f"{q}: ₹{r}Cr" for q, r in fin.get("quarterly_revenue_cr", [])
        )
        if fin.get("statement_format") == "bank":
            nii_table = " | ".join(
                f"{q}: ₹{v}Cr" for q, v in fin.get("quarterly_net_interest_income_cr", [])
            )
            core_line = f"Net interest income (quarterly): {nii_table}"
            margin = ("Operating margin: not reported "
                      "(bank-format statement, no operating-income line)")
        else:
            ebitda_table = " | ".join(
                f"{q}: ₹{e}Cr" for q, e in fin.get("quarterly_ebitda_cr", [])
            )
            core_line = f"EBITDA  (quarterly): {ebitda_table}"
            margin = f"EBITDA Margin: {fin.get('ebitda_margin_pct', 0):.1f}%"
        fin_block = (
            f"Revenue (quarterly): {rev_table}\n"
            f"{core_line}\n"
            f"Revenue QoQ: {fin.get('revenue_qoq_pct', 0):+.1f}% | "
            f"Revenue YoY: {fin.get('revenue_yoy_pct', 0):+.1f}% | "
            f"{margin}"
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
