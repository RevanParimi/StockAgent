"""
sectors/renewable/macro.py
=============================
Macro & Policy sub-agent for the Renewable Energy sector.

Replaces the previous 'sentiment_policy' agent with a more structured
macro framework aligned with the 8-pillar HTML analysis guide.

Data dimensions covered:
  1. MNRE auction health — GW awarded, L1 tariff trend, bid pipeline
  2. RBI rate cycle — repo rate direction and IRR impact
  3. Solar module price trend — capex and margin implications
  4. DISCOM financial health — payment risk proxy
  5. Policy tailwinds — RPO, must-run, ISTS waiver, green hydrogen mission
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import macro as P


class REMacroAgent(BaseAgent):
    """Tracks macro drivers and policy environment for Indian renewable energy."""

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
