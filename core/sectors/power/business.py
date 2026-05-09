"""
sectors/power/business.py
===========================
Business sub-agent for the Power & Utilities sector.

Data dimensions covered:
  1. Generation Mix (Thermal/Hydro/RE)
  2. PPA Coverage & Tenure
  3. T&D Business
  4. DISCOM Payment Health
  5. Merchant vs Regulated Revenue
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.power import business as P


class PowerBusinessAgent(BaseAgent):
    """Analyses business dimensions for Power & Utilities companies."""

    @property
    def agent_name(self) -> str:
        return "business"

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
