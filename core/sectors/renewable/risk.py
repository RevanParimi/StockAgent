"""
sectors/renewable/risk.py
===========================
Risk sub-agent for the Renewable Energy sector.

Scoring convention: 1.0 = LOW risk (safe), 0.0 = HIGH risk (dangerous).
This agent runs with full weight (0.10) and its scores contribute to the
final verdict. High risk sub-scores (<0.3) also surface as top_risks in
the FinalReport.

Data dimensions covered:
  1. DISCOM payment risk — #1 operational risk for Indian RE IPPs
  2. Curtailment & grid integration risk
  3. Tariff renegotiation & regulatory risk
  4. Land acquisition & execution risk
  5. Resource variability & commodity input risk
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import risk as P


class RERiskAgent(BaseAgent):
    """Identifies structural risks that can impair RE project cash flows."""

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
