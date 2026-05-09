"""
sectors/renewable/valuation.py
=================================
Valuation sub-agent for the Renewable Energy sector.

Data dimensions covered:
  1. EV/MW vs peer range (primary metric — ₹3-6 Cr/MW solar, ₹5-8 Cr/MW wind)
  2. EV/EBITDA vs 15-25x healthy range and 5-year historical range
  3. Tariff vs current MNRE auction L1 rates
  4. Pipeline DCF with probability-weighted haircuts
  5. Implied equity IRR vs WACC (target spread ≥200-300bps)
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import valuation as P


class REValuationAgent(BaseAgent):
    """Estimates intrinsic value using RE-specific multiples and DCF methodology."""

    @property
    def agent_name(self) -> str:
        return "valuation"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        fair_value = data.get("fair_value_estimate")
        current_discount = data.get("current_discount_pct")

        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
