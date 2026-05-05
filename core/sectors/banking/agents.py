# Shim — agents split into individual files in sectors/bfsi/agents/
from sectors.bfsi.agents.fundamentals import BFSIFundamentalsAgent  # noqa: F401
from sectors.bfsi.agents.risk import BFSIRiskAgent  # noqa: F401
from sectors.bfsi.agents.macro_policy import BFSIMacroPolicyAgent  # noqa: F401
from sectors.bfsi.agents.institutional import BFSIInstitutionalAgent  # noqa: F401
from sectors.bfsi.agents.pattern_analysis import BFSIPatternAgent  # noqa: F401
from sectors.bfsi.agents.universe_setup import BFSIUniverseAgent  # noqa: F401
from sectors.bfsi.registry import AGENTS, WEIGHTS  # noqa: F401
