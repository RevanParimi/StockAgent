"""
sectors/media/earnings.py
===========================
Earnings sub-agent for the Media & Entertainment sector.

Data dimensions covered:
  1. Ad Revenue vs Guidance
  2. Subscription Growth
  3. Content Cost vs Budget
  4. Operating Leverage
  5. One-time Impairments
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.media import earnings as P


class MediaEarningsAgent(BaseAgent):
    """Analyses earnings dimensions for Media & Entertainment companies."""

    @property
    def agent_name(self) -> str:
        return "earnings"

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
