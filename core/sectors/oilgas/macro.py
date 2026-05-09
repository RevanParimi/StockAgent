"""
sectors/oilgas/macro.py
=========================
Macro sub-agent for the Oil & Gas sector.

Data dimensions covered:
  1. Brent Crude Price Outlook
  2. OPEC+ Production Policy
  3. USD/INR Impact
  4. India Fuel Subsidy Policy
  5. APM Gas Price
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.oilgas import macro as P


class OilGasMacroAgent(BaseAgent):
    """Analyses macro dimensions for Oil & Gas companies."""

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
