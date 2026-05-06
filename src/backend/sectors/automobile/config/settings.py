"""
src/backend/sectors/automobile/config/settings.py
==================================================
Automobile-sector-specific configuration.

These constants are automobile-only — they override or extend the shared
settings in backend.shared.config.settings.base when working in this sector.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Agent weights — must sum to 1.0
# ---------------------------------------------------------------------------
AGENT_WEIGHTS: dict[str, float] = {
    "sales_demand":       0.15,
    "raw_materials":      0.09,
    "fundamentals":       0.18,
    "pattern_analysis":   0.11,
    "sentiment":          0.04,
    "policy_regulatory":  0.09,
    "competitive_intel":  0.09,
    "risk_macro":         0.13,
    "valuation_catalyst": 0.12,
}

# ---------------------------------------------------------------------------
# Tracked tickers (NSE symbols without .NS suffix)
# ---------------------------------------------------------------------------
TICKERS: list[str] = [
    t.strip() for t in
    os.getenv("AUTO_TICKERS", "MARUTI,TATAMOTORS,M&M,HEROMOTOCO,BAJAJ-AUTO,EICHERMOT,TVSMOTORS,ASHOKLEY").split(",")
    if t.strip()
]

# Peer OEM tickers for valuation comparison (NSE symbols)
PEER_TICKERS: list[str] = [
    "MARUTI", "TATAMOTORS", "M&M", "HEROMOTOCO",
    "BAJAJ-AUTO", "EICHERMOT", "TVSMOTORS",
]

# ---------------------------------------------------------------------------
# Sector-specific data source URLs
# ---------------------------------------------------------------------------
FADA_DATA_URL: str  = "https://www.fada.in/news/monthly-reports"
SIAM_DATA_URL: str  = "https://www.siam.in/statistics.aspx"
VAHAN_DATA_URL: str = "https://vahan.parivahan.gov.in/vahan4dashboard/"
DGFT_DATA_URL: str  = "https://www.dgft.gov.in"

# Raw material commodity tickers (yfinance)
STEEL_TICKER:     str = "SLX"     # Van Eck Steel ETF
ALUMINIUM_TICKER: str = "AA"      # Alcoa (proxy for aluminium prices)
PALLADIUM_TICKER: str = "PALL"    # Aberdeen Palladium ETF
BRENT_TICKER:     str = "BZ=F"    # Brent Crude Futures

# ---------------------------------------------------------------------------
# Score thresholds (automobile-specific)
# ---------------------------------------------------------------------------
SCORE_THRESHOLDS: dict[str, tuple[float, float]] = {
    "strong_buy":  (0.75, 1.00),
    "buy":         (0.55, 0.75),
    "neutral":     (0.40, 0.55),
    "sell":        (0.20, 0.40),
    "strong_sell": (0.00, 0.20),
}
