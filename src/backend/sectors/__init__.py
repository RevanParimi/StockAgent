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
    "INOXGREEN","WAAREEENER",
})


def detect_sector(ticker: str) -> str:
    t = ticker.strip().upper()
    if t in _BANKING: return "banking_bfsi"
    if t in _IT:      return "it_sector"
    if t in _RE:      return "renewable_energy"
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
