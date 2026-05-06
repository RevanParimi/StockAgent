"""Unit tests for Renewable Energy sub-agents (6 agents)."""
from __future__ import annotations

import json
import pytest

from backend.sectors.renewable_energy.agents.fundamentals     import REFundamentalsAgent
from backend.sectors.renewable_energy.agents.business         import REBusinessAgent
from backend.sectors.renewable_energy.agents.valuation        import REValuationAgent
from backend.sectors.renewable_energy.agents.sentiment_policy import RESentimentPolicyAgent
from backend.sectors.renewable_energy.agents.technical        import RETechnicalAgent
from backend.sectors.renewable_energy.agents.risk             import RERiskAgent


def _base_json(score: float = 0.65) -> str:
    return json.dumps({
        "overall_score": score,
        "sub_scores":    {k: score for k in ["a", "b", "c", "d", "e"]},
        "key_positives": ["Strong CUF"],
        "key_risks":     ["DISCOM payment delay"],
        "summary":       "Renewable analysis complete.",
        "data_freshness": "Q4 FY26",
    })


AGENT_CASES = [
    (REFundamentalsAgent,   "fundamentals",     "re"),
    (REBusinessAgent,       "business",         "re"),
    (REValuationAgent,      "valuation",        "re"),
    (RESentimentPolicyAgent,"sentiment_policy", "re"),
    (RETechnicalAgent,      "technical",        "re"),
    (RERiskAgent,           "risk",             "re"),
]


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_agent_name(cls, expected_agent, expected_sector):
    assert cls.__new__(cls).agent_name == expected_agent


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_sector(cls, expected_agent, expected_sector):
    assert cls.__new__(cls).sector == expected_sector


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_parse_output(cls, expected_agent, expected_sector):
    agent = cls.__new__(cls)
    data = json.loads(_base_json(0.75))
    result = agent._parse_output(data, "ADANIGREEN")
    assert result.ticker == "ADANIGREEN"
    assert result.agent == expected_agent
    assert abs(result.overall_score - 0.75) < 1e-6


@pytest.mark.parametrize("cls,expected_agent,expected_sector", AGENT_CASES)
def test_score_clamp(cls, expected_agent, expected_sector):
    agent = cls.__new__(cls)
    assert agent._parse_output(json.loads(_base_json(1.5)),  "ADANIGREEN").overall_score == 1.0
    assert agent._parse_output(json.loads(_base_json(-0.5)), "ADANIGREEN").overall_score == 0.0
