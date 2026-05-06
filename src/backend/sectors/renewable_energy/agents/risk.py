"""
agents/risk.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.risk.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import risk as P


class RERiskAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "risk"

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
                "discom_credit": self._clamp(float(sub.get("discom_credit", 0.5))),
                "curtailment_risk": self._clamp(float(sub.get("curtailment_risk", 0.5))),
                "ppa_protection": self._clamp(float(sub.get("ppa_protection", 0.5))),
                "execution_risk": self._clamp(float(sub.get("execution_risk", 0.5))),
                "promoter_pledge": self._clamp(float(sub.get("promoter_pledge", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
