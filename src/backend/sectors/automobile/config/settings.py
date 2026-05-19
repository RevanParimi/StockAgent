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

# ---------------------------------------------------------------------------
# Ticker-specific business model context
# Injected into every agent prompt to prevent treating MARUTI (PV-rural) the
# same as TATAMOTORS (CV-EV-mixed) — gives the LLM structural anchoring per OEM.
# ---------------------------------------------------------------------------
BUSINESS_MODEL_SNAPSHOTS: dict[str, dict[str, str]] = {
    "MARUTI": {
        "portfolio": "80% PV (hatchback/sedan), 15% UV, 5% LCV; dominant in entry-level Tier 2/3 cities",
        "ev_status": "Late to EV: e-Vitara launching FY26; EV <2% of current revenue",
        "revenue_mix": "Domestic 85%, exports 15%; rural/semi-urban drives 40% of domestic volume",
        "margin_anchor": "Best-in-class EBITDA margins (~19%) via cost discipline and vendor ecosystem",
        "key_watch": "Rural demand recovery, EV launch execution, commodity input costs",
    },
    "TATAMOTORS": {
        "portfolio": "40% PV, 30% CV (trucks/buses), 20% EV (Nexon/Tigor/Tiago EV), 10% JLR contribution",
        "ev_status": "EV leader: 3 active models, ~12% of PV sales; EV growing 50% YoY",
        "revenue_mix": "Domestic 60%, exports 40% (JLR drives exports); urban-heavy",
        "margin_anchor": "Improving but below peers (~14-15% EBITDA); EV capex heavy until FY27",
        "key_watch": "JLR order book, EV margin trajectory, CV cycle recovery",
    },
    "M&M": {
        "portfolio": "60% UV/SUV, 25% tractors, 15% CV/LCV; SUV segment dominant post Scorpio-N/XUV700",
        "ev_status": "EV roadmap: XEV 9e, BE 6e launching FY25-26; targeting 20% EV mix by FY28",
        "revenue_mix": "Domestic 80%, exports 20%; urban + agri-linked tractor business",
        "margin_anchor": "SUV premiumization driving margins to ~18% (rising fast); tractor margin stable",
        "key_watch": "SUV order backlog, tractor demand (monsoon-linked), EV launch ramp",
    },
    "MAHINDRA": {
        "portfolio": "60% UV/SUV, 25% tractors, 15% CV/LCV; SUV segment dominant post Scorpio-N/XUV700",
        "ev_status": "EV roadmap: XEV 9e, BE 6e launching FY25-26; targeting 20% EV mix by FY28",
        "revenue_mix": "Domestic 80%, exports 20%; urban + agri-linked tractor business",
        "margin_anchor": "SUV premiumization driving margins to ~18% (rising fast); tractor margin stable",
        "key_watch": "SUV order backlog, tractor demand (monsoon-linked), EV launch ramp",
    },
    "BAJAJ-AUTO": {
        "portfolio": "70% motorcycles, 15% 3-wheelers, 15% exports; Pulsar/Dominar/KTM premium positioning",
        "ev_status": "Chetak EV scaling; targeting 1M EV units by FY28; CNG 3-wheelers growing",
        "revenue_mix": "Domestic 55%, exports 45%; Africa/LATAM key export corridors",
        "margin_anchor": "Best 2W margins (~20% EBITDA) via premium mix and export pricing power",
        "key_watch": "Export market stability, CNG 3W penetration, EV Chetak ramp",
    },
    "HEROMOTOCO": {
        "portfolio": "100% 2-wheelers; mass-market (Splendor, HF Deluxe dominate entry), limited premium",
        "ev_status": "Vida EV (premium scooter) launched; EV <1% of sales; behind Bajaj on EV",
        "revenue_mix": "Domestic 95%, exports 5%; rural-first, entry-level dominant",
        "margin_anchor": "Margin pressure (~14% EBITDA) vs Bajaj; rising urban competition from Bajaj premium",
        "key_watch": "Rural recovery, entry-level volume, EV competitive response",
    },
    "EICHERMOT": {
        "portfolio": "Royal Enfield (premium motorcycles 125cc-650cc), VECV (commercial vehicles JV)",
        "ev_status": "No EV roadmap declared for RE; focusing on IC engine premium niche",
        "revenue_mix": "RE: domestic 70%, exports 30%; VECV: domestic 90%; premium brand positioning",
        "margin_anchor": "RE segment EBITDA ~30% (highest in 2W); premium pricing power",
        "key_watch": "RE premium expansion (Flying Flea EV potential), export market mix, VECV cycle",
    },
    "ASHOKLEY": {
        "portfolio": "100% CV -- trucks, buses, LCV; public transport (STU) and logistics focus",
        "ev_status": "EV trucks pilot; government bus electrification opportunity (CESL tenders)",
        "revenue_mix": "Domestic 85%, exports 15%; cyclical -- tied to infrastructure spending",
        "margin_anchor": "EBITDA ~10-12%, cyclical; fixed cost leverage key in upswing",
        "key_watch": "Infrastructure capex cycle, CESL EV bus tenders, LCV market share vs TATA",
    },
    "TVSMOTORS": {
        "portfolio": "60% scooters (Jupiter, Ntorq), 30% motorcycles (Apache, Raider), 10% mopeds",
        "ev_status": "iQube EV scaling rapidly; ~8% of total volumes; strong dealer push",
        "revenue_mix": "Domestic 75%, exports 25%; strong South India presence; urban/semi-urban",
        "margin_anchor": "EBITDA ~12-13%; improving via EV mix and premiumization; below Bajaj",
        "key_watch": "iQube EV ramp, export recovery (Sri Lanka/Bangladesh), new model pipeline",
    },
}

# Default snapshot for tickers not explicitly mapped
BUSINESS_MODEL_SNAPSHOT_DEFAULT: dict[str, str] = {
    "portfolio": "Automobile sector company -- refer to latest filings",
    "ev_status": "EV transition underway -- check latest guidance",
    "revenue_mix": "Domestic + export mix -- refer to management commentary",
    "margin_anchor": "Sector-average margins -- verify vs peers",
    "key_watch": "Volume growth, margins, EV transition, commodity costs",
}


def get_business_model_context(ticker: str) -> str:
    """Return formatted business model context string for injection into agent prompts."""
    snapshot = BUSINESS_MODEL_SNAPSHOTS.get(ticker.upper(), BUSINESS_MODEL_SNAPSHOT_DEFAULT)
    return (
        f"TICKER BUSINESS MODEL ({ticker}):\n"
        f"  Portfolio: {snapshot['portfolio']}\n"
        f"  EV Status: {snapshot['ev_status']}\n"
        f"  Revenue Mix: {snapshot['revenue_mix']}\n"
        f"  Margin Profile: {snapshot['margin_anchor']}\n"
        f"  Key Watch: {snapshot['key_watch']}\n"
    )
