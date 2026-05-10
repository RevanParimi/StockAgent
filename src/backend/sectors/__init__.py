"""
src/backend/sectors/__init__.py
================================
Sector registry: maps ticker symbols to their orchestrator class.
Automobile is the default fallback.
"""
from __future__ import annotations

_BANKING: frozenset[str] = frozenset({
    "HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK",
    "INDUSINDBK","BANKBARODA","PNB","CANARABANK","FEDERALBNK",
    "IDFCFIRSTB","BANDHANBNK","RBLBANK","YESBANK",
    "HDFCAMC","BAJAJFINSV","BAJFINANCE","MUTHOOTFIN","CHOLAFIN",
})
_IT: frozenset[str] = frozenset({
    "TCS","INFY","WIPRO","HCLTECH","TECHM","LTIM",
    "COFORGE","MPHASIS","PERSISTENT","LTTS","KPITTECH",
    "TATAELXSI","NIIT","MASTEK","HEXAWARE",
})
_RE: frozenset[str] = frozenset({
    "ADANIGREEN","TATAPOWER","TORNTPOWER","CESC","SJVN",
    "NHPC","NTPC","POWERGRID","ADANIPOWER","JSWENERGY",
    "INOXGREEN","INOXWIND","WAAREEENER","SUZLON",
    "PREMIERENE","RPOWER",
})

# Company name fragments for each sector — used when the caller passes a
# full name ("Suzlon Energy") instead of an NSE ticker code ("SUZLON").
_RE_NAMES: tuple[str, ...] = (
    "adani green","tata power","torrent power","sjvn","nhpc","ntpc",
    "powergrid","jsw energy","inox wind","inox green","waaree",
    "suzlon","premier energies","reliance power","cesc","adani power",
)
_BANKING_NAMES: tuple[str, ...] = (
    "hdfc bank","icici bank","state bank","kotak","axis bank",
    "indusind","bank of baroda","punjab national","canara","federal bank",
    "idfc first","bandhan","rbl bank","yes bank","bajaj finance",
    "bajaj finserv","muthoot","chola",
)
_IT_NAMES: tuple[str, ...] = (
    "tata consultancy","infosys","wipro","hcl tech","tech mahindra",
    "ltimindtree","coforge","mphasis","persistent","l&t technology",
    "kpit","tata elxsi","mastek","hexaware",
)


def detect_sector(ticker: str) -> str:
    """
    Resolve ticker → sector key.
    Phase 0+1: routes through SectorRegistry (extended ticker map + toggle awareness).
    Kept backward-compatible — always returns a usable sector string.
    """
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.resolve(ticker)


def get_orchestrator(sector: str):
    """
    Return the orchestrator class for a sector key.
    Phase 0: disabled sectors degrade to AutomobileAgentOrchestrator with a log warning.
    """
    from backend.sectors.registry import SectorRegistry
    return SectorRegistry.get_handler(sector)
