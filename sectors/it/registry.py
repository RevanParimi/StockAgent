from sectors.it.agents.fundamentals import ITFundamentalsAgent
from sectors.it.agents.global_macro import ITGlobalMacroAgent
from sectors.it.agents.risk_macro import ITRiskMacroAgent
from sectors.it.agents.peer_benchmark import ITPeerBenchmarkAgent
from sectors.it.agents.pattern_analysis import ITPatternAgent
from sectors.it.agents.sentiment import ITSentimentAgent
from sectors.it.agents.transcript_nlp import ITTranscriptNLPAgent
from sectors.it.agents.insider_smart_money import ITInsiderAgent

AGENTS: dict = {
    "fundamentals":        ITFundamentalsAgent(),
    "global_macro":        ITGlobalMacroAgent(),
    "risk_macro":          ITRiskMacroAgent(),
    "peer_benchmark":      ITPeerBenchmarkAgent(),
    "pattern_analysis":    ITPatternAgent(),
    "sentiment":           ITSentimentAgent(),
    "transcript_nlp":      ITTranscriptNLPAgent(),
    "insider_smart_money": ITInsiderAgent(),
}

WEIGHTS: dict[str, float] = {
    "fundamentals":        0.25,
    "global_macro":        0.20,
    "risk_macro":          0.15,
    "peer_benchmark":      0.15,
    "pattern_analysis":    0.10,
    "sentiment":           0.08,
    "transcript_nlp":      0.04,
    "insider_smart_money": 0.03,
}
