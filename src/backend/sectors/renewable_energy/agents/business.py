"""
agents/business.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.business.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import business as P


class REBusinessAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "business"

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
                "subsector_mix": self._clamp(float(sub.get("subsector_mix", 0.5))),
                "ppa_quality": self._clamp(float(sub.get("ppa_quality", 0.5))),
                "pipeline_cred": self._clamp(float(sub.get("pipeline_cred", 0.5))),
                "customer_divers": self._clamp(float(sub.get("customer_divers", 0.5))),
                "geography_spread": self._clamp(float(sub.get("geography_spread", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
