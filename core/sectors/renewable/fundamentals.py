"""
sectors/renewable/fundamentals.py
=====================================
Fundamentals sub-agent for the Renewable Energy sector.

Data dimensions covered:
  1. DSCR — Debt Service Coverage Ratio (target ≥1.3x)
  2. CUF — Capacity Utilisation Factor vs technology benchmark
  3. EBITDA/MW — normalised profitability per megawatt
  4. LCOE — Levelised Cost of Energy vs auction competition
  5. Net Debt/EBITDA — leverage (5-8x typical; >10x = stress)
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import fundamentals as P


class REFundamentalsAgent(BaseAgent):
    """Analyses project-finance metrics and balance-sheet health for RE IPPs."""

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
