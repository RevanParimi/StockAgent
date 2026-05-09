"""
sectors/renewable/earnings.py
================================
Earnings Quality sub-agent for the Renewable Energy sector.

New agent added from the 8-pillar HTML framework (weight: 0.05).
Core test: Published MUs generated × tariff (₹/kWh) should reconcile
with reported revenue. Divergences signal billing disputes or accounting
manipulation.

Data dimensions covered:
  1. Project-level DSCR vs consolidated stated DSCR
  2. Interest capitalisation ratio (construction vs commissioned)
  3. Generation data vs revenue reconciliation
  4. Off-balance-sheet obligations and contingent liabilities
  5. Operating cash flow vs PAT consistency (cash conversion ratio)
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import earnings as P


class REEarningsAgent(BaseAgent):
    """Assesses earnings quality and accounting integrity for RE IPPs."""

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
