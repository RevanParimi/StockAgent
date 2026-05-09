"""
sectors/logistics/management.py
=================================
Management sub-agent for the Logistics & Supply Chain sector.

Data dimensions covered:
  1. Promoter Track Record
  2. Capital Allocation
  3. RPT
  4. Tech Strategy
  5. ESG
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.logistics import management as P


class LogistManagementAgent(BaseAgent):
    """Analyses management dimensions for Logistics & Supply Chain companies."""

    @property
    def agent_name(self) -> str:
        return "management"

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
