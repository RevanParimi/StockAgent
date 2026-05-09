"""
sectors/insurance/macro.py
============================
Macro sub-agent for the Insurance sector.

Data dimensions covered:
  1. IRDAI Regulatory Changes
  2. Interest Rate Cycle (Investment Yield)
  3. Insurance Penetration Expansion
  4. Health Inflation
  5. Reinsurance Costs
"""

from __future__ import annotations
from typing import Any
from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.insurance import macro as P


class InsMacroAgent(BaseAgent):
    """Analyses macro dimensions for Insurance companies."""

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
