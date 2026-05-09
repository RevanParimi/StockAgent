"""
sectors/realestate/macro.py
=============================
Macro sub-agent for the Real Estate & REITs sector.

Data dimensions covered:
  1. RBI Repo Rate & Home Loan Rates
  2. Housing Affordability Index
  3. PMAY & Government Schemes
  4. Commercial Real Estate Demand
  5. NRI Demand
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.realestate import macro as P


class RealEstMacroAgent(BaseAgent):
    """Analyses macro dimensions for Real Estate & REITs companies."""

    @property
    def agent_name(self) -> str:
        return "macro"

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
