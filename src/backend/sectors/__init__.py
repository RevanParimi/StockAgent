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
    t = ticker.strip().upper()
    # Exact NSE ticker match (fast path)
    if t in _BANKING: return "banking_bfsi"
    if t in _IT:      return "it_sector"
    if t in _RE:      return "renewable_energy"
    # Company name / partial input match (slow path — only reached for unknowns)
    tl = t.lower()
    if any(name in tl for name in _RE_NAMES):      return "renewable_energy"
    if any(name in tl for name in _BANKING_NAMES): return "banking_bfsi"
    if any(name in tl for name in _IT_NAMES):      return "it_sector"
    return "automobile"


def get_orchestrator(sector: str):
    """Lazy-import and return the orchestrator class for a sector key."""
    if sector == "banking_bfsi":
        from backend.sectors.banking_bfsi.pipeline.orchestrator import BankingAgentOrchestrator
        return BankingAgentOrchestrator
    if sector == "it_sector":
        from backend.sectors.it_sector.pipeline.orchestrator import ITAgentOrchestrator
        return ITAgentOrchestrator
    if sector == "renewable_energy":
        from backend.sectors.renewable_energy.pipeline.orchestrator import RenewableAgentOrchestrator
        return RenewableAgentOrchestrator
    from backend.sectors.automobile.pipeline.orchestrator import AutomobileAgentOrchestrator
    return AutomobileAgentOrchestrator
