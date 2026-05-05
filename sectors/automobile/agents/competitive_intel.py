"""
agents/competitive_intel.py
=============================
Competitive Intelligence sub-agent.

Data dimensions covered:
  1. EV market share — Tata/BYD/Ather/Ola/MG vs target OEM
  2. New model launch pipeline and pricing strategy
  3. JV and acquisition announcements
  4. ADAS milestones and BNAP/NCAP safety ratings
  5. Overall competitive position and market share trend
"""

from __future__ import annotations

from typing import Any

from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, CompetitiveIntelOutput, CompetitiveIntelSubScores, StockQuery
from core.config.prompts.automobile import competitive_intel as P


class CompetitiveIntelAgent(BaseAgent):
    """Analyses competitive positioning, EV landscape, and strategic moves."""

    @property
    def agent_name(self) -> str:
        return "competitive_intel"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return CompetitiveIntelOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=CompetitiveIntelSubScores(
                ev_market_share=self._clamp(float(sub.get("ev_market_share", 0.5))),
                new_model_pipeline=self._clamp(float(sub.get("new_model_pipeline", 0.5))),
                jv_acquisitions=self._clamp(float(sub.get("jv_acquisitions", 0.5))),
                adas_safety_ratings=self._clamp(float(sub.get("adas_safety_ratings", 0.5))),
                competitive_position=self._clamp(float(sub.get("competitive_position", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
