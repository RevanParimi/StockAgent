"""
sectors/insurance/fundamentals.py
===================================
Fundamentals sub-agent for the Insurance sector.

Data dimensions covered:
  1. Embedded Value (EV) Growth
  2. Operating RoEV
  3. Solvency Ratio
  4. Investment Yield
  5. Cost Ratio
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.insurance import fundamentals as P


class InsFundamentalsAgent(BaseAgent):
    """Analyses fundamentals dimensions for Insurance companies."""

    @property
    def agent_name(self) -> str:
        return "fundamentals"

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
