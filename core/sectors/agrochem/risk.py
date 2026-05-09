"""
sectors/agrochem/risk.py
==========================
Risk sub-agent for the Agrochemicals & Fertilizers sector.

Data dimensions covered:
  1. Monsoon Failure Risk
  2. China Dumping & Price Erosion
  3. Patent Cliff on In-licensed AIs
  4. Regulatory Bans (CIB)
  5. Inventory Build-up Risk
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.agrochem import risk as P


class AgroChemRiskAgent(BaseAgent):
    """Analyses risk dimensions for Agrochemicals & Fertilizers companies."""

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
