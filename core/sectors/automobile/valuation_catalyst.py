"""
agents/valuation_catalyst.py
=============================
Valuation & Catalyst sub-agent.

Data dimensions covered:
  1. P/E discount vs 5-year historical average
  2. P/E discount vs peer median (Maruti/TataMotors/M&M/Hero/Bajaj)
  3. Discount reason clarity (macro shock vs fundamental decline)
  4. Recovery catalyst strength and nearness
  5. Price target confidence (analyst consensus convergence)
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import (
    AgentOutput,
    ValuationCatalystOutput,
    ValuationCatalystSubScores,
    StockQuery,
)
from config.prompts.automobile import valuation_catalyst as P


class ValuationCatalystAgent(BaseAgent):
    """Estimates intrinsic value, discount reason, and recovery catalysts."""

    @property
    def agent_name(self) -> str:
        return "valuation_catalyst"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})

        fair_value = data.get("fair_value_estimate")
        price_target = data.get("price_target")
        current_discount = data.get("current_discount_pct")
        recovery_quarters = data.get("recovery_timeline_quarters")

        return ValuationCatalystOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=ValuationCatalystSubScores(
                pe_discount_vs_history=self._clamp(float(sub.get("pe_discount_vs_history", 0.5))),
                pe_discount_vs_peers=self._clamp(float(sub.get("pe_discount_vs_peers", 0.5))),
                discount_reason_clarity=self._clamp(float(sub.get("discount_reason_clarity", 0.5))),
                catalyst_strength=self._clamp(float(sub.get("catalyst_strength", 0.5))),
                price_target_confidence=self._clamp(float(sub.get("price_target_confidence", 0.5))),
            ),
            fair_value_estimate=float(fair_value) if fair_value is not None else None,
            current_discount_pct=float(current_discount) if current_discount is not None else None,
            discount_reason=data.get("discount_reason"),
            recovery_catalysts=data.get("recovery_catalysts", []),
            price_target=float(price_target) if price_target is not None else None,
            recovery_timeline_quarters=int(recovery_quarters) if recovery_quarters is not None else None,
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
