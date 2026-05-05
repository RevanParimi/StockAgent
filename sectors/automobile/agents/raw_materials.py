"""
agents/raw_materials.py
========================
Raw Materials Cost sub-agent.

Data dimensions covered:
  1. Steel HRC & Aluminium — body/frame BOM cost
  2. Platinum & Palladium — catalytic converter cost (ICE OEMs)
  3. Crude oil / Brent — polymer costs + fuel price signal
  4. Power tariff — EV TCO impact
  5. Commodities trend — 3-month basket direction
"""

from __future__ import annotations

from typing import Any

from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, RawMaterialsOutput, RawMaterialsSubScores, StockQuery
from core.config.prompts.automobile import raw_materials as P


class RawMaterialsAgent(BaseAgent):
    """Analyses raw material and input cost pressure on OEM margins."""

    @property
    def agent_name(self) -> str:
        return "raw_materials"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return RawMaterialsOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=RawMaterialsSubScores(
                steel_aluminium=self._clamp(float(sub.get("steel_aluminium", 0.5))),
                platinum_palladium=self._clamp(float(sub.get("platinum_palladium", 0.5))),
                crude_oil_polymer=self._clamp(float(sub.get("crude_oil_polymer", 0.5))),
                power_tariff=self._clamp(float(sub.get("power_tariff", 0.5))),
                commodities_trend=self._clamp(float(sub.get("commodities_trend", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
