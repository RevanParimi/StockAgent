"""
agents/sentiment_policy.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.sentiment_policy.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import sentiment_policy as P


class RESentimentPolicyAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "sentiment_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores={
                "mnre_auction_health": self._clamp(float(sub.get("mnre_auction_health", 0.5))),
                "budget_allocation": self._clamp(float(sub.get("budget_allocation", 0.5))),
                "policy_tailwinds": self._clamp(float(sub.get("policy_tailwinds", 0.5))),
                "rbi_rate_impact": self._clamp(float(sub.get("rbi_rate_impact", 0.5))),
                "module_price": self._clamp(float(sub.get("module_price", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
