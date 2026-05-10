"""
src/backend/sectors/it_sector/config/registry.py
=================================================
IT sector agent registry — Phase 2 refactor.

7 of 8 agents replaced with UniversalAgent.
1 sector-specific agent kept:
  - ITTranscriptNLPAgent : custom earnings-call transcript parsing + NLP scoring
"""
from __future__ import annotations

from backend.shared.agents.universal                             import UniversalAgent
from backend.sectors.it_sector.agents.transcript_nlp            import ITTranscriptNLPAgent
from backend.sectors.it_sector.prompts import (
    fundamentals         as _fund,
    global_macro         as _gmac,
    risk_macro           as _risk,
    peer_benchmark       as _peer,
    pattern_analysis     as _pat,
    sentiment            as _sent,
    insider_smart_money  as _ins,
)
from backend.sectors.it_sector.config.settings import AGENT_WEIGHTS

_S = "it_sector"

AGENTS: dict = {
    "fundamentals":       UniversalAgent("fundamentals",       _fund, sector=_S),
    "global_macro":       UniversalAgent("global_macro",       _gmac, sector=_S),
    "risk_macro":         UniversalAgent("risk_macro",         _risk, sector=_S),
    "peer_benchmark":     UniversalAgent("peer_benchmark",     _peer, sector=_S),
    "pattern_analysis":   UniversalAgent("pattern_analysis",   _pat,  sector=_S),
    "sentiment":          UniversalAgent("sentiment",          _sent, sector=_S),
    "transcript_nlp":     ITTranscriptNLPAgent(),
    "insider_smart_money":UniversalAgent("insider_smart_money",_ins,  sector=_S),
}

WEIGHTS: dict[str, float] = AGENT_WEIGHTS
