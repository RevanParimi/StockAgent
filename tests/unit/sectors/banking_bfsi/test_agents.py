"""
Unit tests for Banking BFSI sub-agents.
Tests _parse_output() for each of the 6 BFSI agents.
LLM is mocked — no real API calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.sectors.banking_bfsi.agents.fundamentals    import BFSIFundamentalsAgent
from backend.sectors.banking_bfsi.agents.risk            import BFSIRiskAgent
from backend.sectors.banking_bfsi.agents.macro_policy    import BFSIMacroPolicyAgent
from backend.sectors.banking_bfsi.agents.universe_setup  import BFSIUniverseAgent


def _base_json(agent_name: str, score: float = 0.68) -> str:
    return json.dumps({
        "overall_score": score,
        "sub_scores":    {k: score for k in ["a", "b", "c", "d", "e"]},
        "key_positives": ["Strong NIM"],
        "key_risks":     ["Rising NPA"],
        "summary":       f"{agent_name} analysis complete.",
        "data_freshness": "Q4 FY26",
    })


AGENT_CASES = [
    ("fundamentals",    BFSIFundamentalsAgent,   "fundamentals"),
    ("risk",            BFSIRiskAgent,           "risk"),
    ("macro_policy",    BFSIMacroPolicyAgent,    "macro_policy"),
    ("universe_setup",  BFSIUniverseAgent,       "universe_setup"),
]


@pytest.mark.parametrize("key,cls,expected_name", AGENT_CASES)
def test_agent_name(key, cls, expected_name):
    agent = cls.__new__(cls)
    assert agent.agent_name == expected_name


@pytest.mark.parametrize("key,cls,expected_name", AGENT_CASES)
def test_sector(key, cls, expected_name):
    agent = cls.__new__(cls)
    assert agent.sector == "bfsi"


@pytest.mark.parametrize("key,cls,expected_name", AGENT_CASES)
def test_parse_valid_json(key, cls, expected_name):
    agent = cls.__new__(cls)
    data = json.loads(_base_json(key, score=0.72))
    result = agent._parse_output(data, "HDFCBANK")
    assert result.agent == expected_name
    assert result.ticker == "HDFCBANK"
    assert abs(result.overall_score - 0.72) < 1e-6
    assert result.key_positives == ["Strong NIM"]
    assert result.key_risks == ["Rising NPA"]


@pytest.mark.parametrize("key,cls,expected_name", AGENT_CASES)
def test_score_clamped_above(key, cls, expected_name):
    agent = cls.__new__(cls)
    data = json.loads(_base_json(key, score=1.5))
    result = agent._parse_output(data, "HDFCBANK")
    assert result.overall_score == 1.0


@pytest.mark.parametrize("key,cls,expected_name", AGENT_CASES)
def test_score_clamped_below(key, cls, expected_name):
    agent = cls.__new__(cls)
    data = json.loads(_base_json(key, score=-0.3))
    result = agent._parse_output(data, "HDFCBANK")
    assert result.overall_score == 0.0
