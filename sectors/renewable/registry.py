from sectors.renewable.agents.fundamentals import REFundamentalsAgent
from sectors.renewable.agents.business import REBusinessAgent
from sectors.renewable.agents.valuation import REValuationAgent
from sectors.renewable.agents.sentiment_policy import RESentimentPolicyAgent
from sectors.renewable.agents.technical import RETechnicalAgent
from sectors.renewable.agents.risk import RERiskAgent

AGENTS: dict = {
    "fundamentals":     REFundamentalsAgent(),
    "business":         REBusinessAgent(),
    "valuation":        REValuationAgent(),
    "sentiment_policy": RESentimentPolicyAgent(),
    "technical":        RETechnicalAgent(),
    "risk":             RERiskAgent(),
}

# risk runs as a monitoring agent — weight=0 means its score doesn't alter the
# verdict, but its key_risks surface in FinalReport.top_risks
WEIGHTS: dict[str, float] = {
    "fundamentals":     0.30,
    "business":         0.25,
    "valuation":        0.20,
    "sentiment_policy": 0.15,
    "technical":        0.10,
    "risk":             0.00,
}
