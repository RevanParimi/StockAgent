"""
agents/fundamentals.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.fundamentals.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import fundamentals as P


class REFundamentalsAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

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
                "capacity_utilisation": self._clamp(float(sub.get("capacity_utilisation", 0.5))),
                "ebitda_quality": self._clamp(float(sub.get("ebitda_quality", 0.5))),
                "debt_serviceability": self._clamp(float(sub.get("debt_serviceability", 0.5))),
                "receivables": self._clamp(float(sub.get("receivables", 0.5))),
                "leverage": self._clamp(float(sub.get("leverage", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
