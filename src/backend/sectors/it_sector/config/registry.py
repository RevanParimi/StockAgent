"""Agent registry for it_sector."""
from __future__ import annotations
from backend.sectors.it_sector.agents.fundamentals import ITFundamentalsAgent
from backend.sectors.it_sector.agents.global_macro import ITGlobalMacroAgent
from backend.sectors.it_sector.agents.risk_macro import ITRiskMacroAgent
from backend.sectors.it_sector.agents.peer_benchmark import ITPeerBenchmarkAgent
from backend.sectors.it_sector.agents.pattern_analysis import ITPatternAgent
from backend.sectors.it_sector.agents.sentiment import ITSentimentAgent
from backend.sectors.it_sector.agents.transcript_nlp import ITTranscriptNLPAgent
from backend.sectors.it_sector.agents.insider_smart_money import ITInsiderAgent
from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS

AGENTS: dict = {
    "fundamentals": ITFundamentalsAgent(),
    "global_macro": ITGlobalMacroAgent(),
    "risk_macro": ITRiskMacroAgent(),
    "peer_benchmark": ITPeerBenchmarkAgent(),
    "pattern_analysis": ITPatternAgent(),
    "sentiment": ITSentimentAgent(),
    "transcript_nlp": ITTranscriptNLPAgent(),
    "insider_smart_money": ITInsiderAgent(),
}
WEIGHTS: dict[str, float] = AGENT_WEIGHTS
