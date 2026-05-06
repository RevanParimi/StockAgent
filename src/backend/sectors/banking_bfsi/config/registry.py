"""Agent registry for banking_bfsi."""
from __future__ import annotations
from backend.sectors.banking_bfsi.agents.fundamentals import BFSIFundamentalsAgent
from backend.sectors.banking_bfsi.agents.risk import BFSIRiskAgent
from backend.sectors.banking_bfsi.agents.macro_policy import BFSIMacroPolicyAgent
from backend.sectors.banking_bfsi.agents.institutional import BFSIInstitutionalAgent
from backend.sectors.banking_bfsi.agents.pattern_analysis import BFSIPatternAgent
from backend.sectors.banking_bfsi.agents.universe_setup import BFSIUniverseAgent
from backend.sectors.banking_bfsi.config.settings import AGENT_WEIGHTS

AGENTS: dict = {
    "fundamentals": BFSIFundamentalsAgent(),
    "risk": BFSIRiskAgent(),
    "macro_policy": BFSIMacroPolicyAgent(),
    "institutional": BFSIInstitutionalAgent(),
    "pattern_analysis": BFSIPatternAgent(),
    "universe_setup": BFSIUniverseAgent(),
}
WEIGHTS: dict[str, float] = AGENT_WEIGHTS
