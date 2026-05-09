"""
sectors/realestate/fundamentals.py
====================================
Fundamentals sub-agent for the Real Estate & REITs sector.

Data dimensions covered:
  1. Revenue Recognition (Completion Method)
  2. EBITDA Margin
  3. Net Debt & Leverage
  4. Operating Cash Flow
  5. Land Bank Value
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.realestate import fundamentals as P


class RealEstFundamentalsAgent(BaseAgent):
    """Analyses fundamentals dimensions for Real Estate & REITs companies."""

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
