"""
agents/valuation.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.valuation.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import valuation as P


class REValuationAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "valuation"

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
                "ev_per_mw": self._clamp(float(sub.get("ev_per_mw", 0.5))),
                "ev_ebitda": self._clamp(float(sub.get("ev_ebitda", 0.5))),
                "tariff_vs_auction": self._clamp(float(sub.get("tariff_vs_auction", 0.5))),
                "pipeline_dcf": self._clamp(float(sub.get("pipeline_dcf", 0.5))),
                "implied_irr": self._clamp(float(sub.get("implied_irr", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
