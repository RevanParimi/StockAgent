"""Agent registry for renewable_energy."""
from __future__ import annotations
from backend.sectors.renewable_energy.agents.fundamentals import REFundamentalsAgent
from backend.sectors.renewable_energy.agents.business import REBusinessAgent
from backend.sectors.renewable_energy.agents.valuation import REValuationAgent
from backend.sectors.renewable_energy.agents.sentiment_policy import RESentimentPolicyAgent
from backend.sectors.renewable_energy.agents.technical import RETechnicalAgent
from backend.sectors.renewable_energy.agents.risk import RERiskAgent
from backend.sectors.renewable_energy.config.settings import AGENT_WEIGHTS

AGENTS: dict = {
    "fundamentals": REFundamentalsAgent(),
    "business": REBusinessAgent(),
    "valuation": REValuationAgent(),
    "sentiment_policy": RESentimentPolicyAgent(),
    "technical": RETechnicalAgent(),
    "risk": RERiskAgent(),
}
WEIGHTS: dict[str, float] = AGENT_WEIGHTS
