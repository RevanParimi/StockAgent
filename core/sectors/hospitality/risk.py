"""
sectors/hospitality/risk.py
=============================
Risk sub-agent for the Hospitality & Travel sector.

Data dimensions covered:
  1. Pandemic / Travel Disruption Risk
  2. Oversupply in Key Markets
  3. High Fixed Cost Structure
  4. Rising Energy & Labour Costs
  5. Seasonality
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.hospitality import risk as P


class HospRiskAgent(BaseAgent):
    """Analyses risk dimensions for Hospitality & Travel companies."""

    @property
    def agent_name(self) -> str:
        return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
