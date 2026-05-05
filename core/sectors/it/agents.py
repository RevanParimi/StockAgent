# Shim — agents split into individual files in sectors/it/agents/
from sectors.it.agents.fundamentals import ITFundamentalsAgent  # noqa: F401
from sectors.it.agents.global_macro import ITGlobalMacroAgent  # noqa: F401
from sectors.it.agents.risk_macro import ITRiskMacroAgent  # noqa: F401
from sectors.it.agents.peer_benchmark import ITPeerBenchmarkAgent  # noqa: F401
from sectors.it.agents.pattern_analysis import ITPatternAgent  # noqa: F401
from sectors.it.agents.sentiment import ITSentimentAgent  # noqa: F401
from sectors.it.agents.transcript_nlp import ITTranscriptNLPAgent  # noqa: F401
from sectors.it.agents.insider_smart_money import ITInsiderAgent  # noqa: F401
from sectors.it.registry import AGENTS, WEIGHTS  # noqa: F401
