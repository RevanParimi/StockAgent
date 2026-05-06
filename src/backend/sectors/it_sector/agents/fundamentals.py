"""
agents/fundamentals.py — IT Sector
Covers revenue CC growth, EBIT margins, TCV/deal wins, attrition, valuation vs peers.
Imports prompts from backend.sectors.it_sector.prompts.fundamentals.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import fundamentals as P


class ITFundamentalsAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

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
                "revenue_growth": self._clamp(float(sub.get("revenue_growth", 0.5))),
                "ebit_margins": self._clamp(float(sub.get("ebit_margins", 0.5))),
                "deal_wins": self._clamp(float(sub.get("deal_wins", 0.5))),
                "attrition": self._clamp(float(sub.get("attrition", 0.5))),
                "valuation": self._clamp(float(sub.get("valuation", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
