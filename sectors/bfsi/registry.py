from sectors.bfsi.agents.fundamentals import BFSIFundamentalsAgent
from sectors.bfsi.agents.risk import BFSIRiskAgent
from sectors.bfsi.agents.macro_policy import BFSIMacroPolicyAgent
from sectors.bfsi.agents.institutional import BFSIInstitutionalAgent
from sectors.bfsi.agents.pattern_analysis import BFSIPatternAgent
from sectors.bfsi.agents.universe_setup import BFSIUniverseAgent

AGENTS: dict = {
    "fundamentals":     BFSIFundamentalsAgent(),
    "risk":             BFSIRiskAgent(),
    "macro_policy":     BFSIMacroPolicyAgent(),
    "institutional":    BFSIInstitutionalAgent(),
    "pattern_analysis": BFSIPatternAgent(),
    "universe_setup":   BFSIUniverseAgent(),
}

WEIGHTS: dict[str, float] = {
    "fundamentals":     0.25,
    "risk":             0.20,
    "macro_policy":     0.20,
    "institutional":    0.15,
    "pattern_analysis": 0.15,
    "universe_setup":   0.05,
}
