# Shim — agents split into individual files in sectors/renewable/agents/
from sectors.renewable.agents.fundamentals import REFundamentalsAgent  # noqa: F401
from sectors.renewable.agents.business import REBusinessAgent  # noqa: F401
from sectors.renewable.agents.valuation import REValuationAgent  # noqa: F401
from sectors.renewable.agents.sentiment_policy import RESentimentPolicyAgent  # noqa: F401
from sectors.renewable.agents.technical import RETechnicalAgent  # noqa: F401
from sectors.renewable.agents.risk import RERiskAgent  # noqa: F401
from sectors.renewable.registry import AGENTS, WEIGHTS  # noqa: F401
