"""Unit tests for IT Sector sub-agents (8 agents)."""
from __future__ import annotations

import json
import pytest

from backend.sectors.it_sector.agents.fundamentals      import ITFundamentalsAgent
from backend.sectors.it_sector.agents.global_macro      import ITGlobalMacroAgent
from backend.sectors.it_sector.agents.risk_macro        import ITRiskMacroAgent
from backend.sectors.it_sector.agents.peer_benchmark    import ITPeerBenchmarkAgent
from backend.sectors.it_sector.agents.pattern_analysis  import ITPatternAgent
from backend.sectors.it_sector.agents.sentiment         import ITSentimentAgent
from backend.sectors.it_sector.agents.transcript_nlp    import ITTranscriptNLPAgent
from backend.sectors.it_sector.agents.insider_smart_money import ITInsiderAgent


def _base_json(score: float = 0.65) -> str:
    return json.dumps({
        "overall_score": score,
        "sub_scores":    {k: score for k in ["a", "b", "c", "d", "e"]},
        "key_positives": ["Strong deal wins"],
        "key_risks":     ["H1B visa uncertainty"],
        "summary":       "IT analysis complete.",
        "data_freshness": "Q4 FY26",
    })


AGENT_CASES = [
    (ITFundamentalsAgent,   "fundamentals",        "it"),
    (ITGlobalMacroAgent,    "global_macro",        "it"),
    (ITRiskMacroAgent,      "risk_macro",          "it"),
    (ITPeerBenchmarkAgent,  "peer_benchmark",      "it"),
    (ITPatternAgent,        "pattern_analysis",    "it"),
    (ITSentimentAgent,      "sentiment",           "it"),
    (ITTranscriptNLPAgent,  "transcript_nlp",      "it"),
    (ITInsiderAgent,        "insider_smart_money", "it"),
]


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_agent_name(cls, expected_agent, expected_sector):
    assert cls.__new__(cls).agent_name == expected_agent


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_sector(cls, expected_agent, expected_sector):
    assert cls.__new__(cls).sector == expected_sector


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_parse_returns_agent_output(cls, expected_agent, expected_sector):
    agent = cls.__new__(cls)
    data = json.loads(_base_json(0.70))
    result = agent._parse_output(data, "TCS")
    assert result.ticker == "TCS"
    assert result.agent == expected_agent
    assert abs(result.overall_score - 0.70) < 1e-6


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_score_clamp(cls, expected_agent, expected_sector):
    agent = cls.__new__(cls)
    assert agent._parse_output(json.loads(_base_json(2.0)), "TCS").overall_score == 1.0
    assert agent._parse_output(json.loads(_base_json(-1.0)), "TCS").overall_score == 0.0
