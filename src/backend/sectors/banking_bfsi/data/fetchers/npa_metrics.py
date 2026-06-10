"""
data/fetchers/npa_metrics.py — Banking BFSI
=============================================
Fetches GNPA%, Net NPA%, PCR, CRAR/CET1 from quarterly BSE/NSE filings.

Sources (free tier):
  - yfinance quarterly_income_stmt → provision data (~200 tokens)
  - Serper → results press release with NPA highlights (~275 tokens)
  - Tavily → BSE/NSE filing page for CRAR data (~1,000 tokens)

Status: stub — implement in Phase 7.
        The ContextBuilder uses yfinance fundamentals + Serper news as fallback.
"""
from __future__ import annotations


def get_npa_metrics(ticker: str) -> dict:
    """
    Fetch asset quality metrics for a banking stock.

    Returns dict with keys:
    - gnpa_pct (float)           — Gross NPA as % of gross advances
    - net_npa_pct (float)        — Net NPA as % of net advances
    - pcr_pct (float)            — Provision Coverage Ratio %
    - slippage_ratio_pct (float) — New NPA additions as % of standard advances
    - restructured_book_pct (float) — Restructured/ECLGS as % of advances
    - quarter (str)              — e.g. "Q3 FY2025"

    Implementation plan (Phase 7):
    1. Use yfinance ticker.quarterly_income_stmt to get provision data.
    2. Compute GNPA% from provision + gross advances (from quarterly balance sheet).
    3. Use Serper to fetch results press release for PCR and slippage details.
    4. Use Tavily on BSE filing page for CRAR confirmation.
    """
    raise NotImplementedError(
        "npa_metrics.get_npa_metrics not implemented — Phase 7. "
        "ContextBuilder uses yfinance fundamentals + Serper news fallback."
    )


def get_capital_adequacy(ticker: str) -> dict:
    """
    Fetch CRAR and CET1 ratio from quarterly disclosures.

    Returns dict with keys:
    - crar_pct (float)   — Total Capital Adequacy Ratio %
    - cet1_pct (float)   — Common Equity Tier-1 ratio %
    - tier2_pct (float)  — Tier-2 capital ratio %
    - rbi_minimum_crar (float) — 11.5% for most banks
    - buffer_over_minimum (float) — crar_pct - rbi_minimum_crar
    - quarter (str)

    Implementation plan (Phase 7):
    1. Serper → RBI Pillar-3 disclosure filing snippet.
    2. Tavily → BSE regulatory filing page for Pillar-3 document.
    3. Parse CRAR, CET1 from Basel III table in the disclosure.
    """
    raise NotImplementedError(
        "npa_metrics.get_capital_adequacy not implemented — Phase 7. "
        "ContextBuilder uses Serper RBI filing snippet fallback."
    )


def get_nim_casa(ticker: str) -> dict:
    """
    Derive NIM and CASA ratio from yfinance quarterly income statement.

    Returns dict with keys:
    - nim_pct (float)         — Net Interest Margin % (NII / avg interest-earning assets)
    - casa_ratio_pct (float)  — CASA as % of total deposits
    - nii_qoq_growth (float)  — NII growth quarter-on-quarter %
    - cost_of_funds_pct (float)

    Implementation plan (Phase 7):
    1. yfinance ticker.quarterly_income_stmt → NII, interest expense.
    2. yfinance ticker.quarterly_balance_sheet → total deposits, CASA (if available).
    3. Compute NIM = NII / avg earning assets.
    4. Fall back to Serper results snippet for CASA if yfinance doesn't have it.
    """
    raise NotImplementedError(
        "npa_metrics.get_nim_casa not implemented — Phase 7. "
        "ContextBuilder uses yfinance quarterly_income_stmt fallback."
    )
