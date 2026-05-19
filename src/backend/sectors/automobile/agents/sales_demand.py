"""
agents/sales_demand.py
======================
Sales & Demand sub-agent.

Data dimensions covered:
  1. FADA/SIAM monthly dispatch
  2. EV segment Vahan registration data
  3. Dealer inventory days
  4. Export/Import DGFT data
  5. Used car price index (Cars24, CarDekho)
"""

from __future__ import annotations

from typing import Any

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, SalesDemandOutput, SalesDemandSubScores, StockQuery
from backend.sectors.automobile.prompts import sales_demand as P


class SalesDemandAgent(BaseAgent):
    """Analyses retail sales velocity and demand-side indicators."""

    @property
    def agent_name(self) -> str:
        return "sales_demand"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        from backend.sectors.automobile.config.settings import get_business_model_context
        biz_ctx = get_business_model_context(query.ticker)
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
            business_model_context=biz_ctx,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return SalesDemandOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=SalesDemandSubScores(
                fada_siam_dispatch=self._clamp(float(sub.get("fada_siam_dispatch", 0.5))),
                ev_segment_vahan=self._clamp(float(sub.get("ev_segment_vahan", 0.5))),
                dealer_inventory=self._clamp(float(sub.get("dealer_inventory", 0.5))),
                export_import=self._clamp(float(sub.get("export_import", 0.5))),
                used_car_price_index=self._clamp(float(sub.get("used_car_price_index", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
            ticker_vs_peers=data.get("ticker_vs_peers", ""),
            bull_case_if=data.get("bull_case_if", ""),
            bear_case_if=data.get("bear_case_if", ""),
            what_changed=data.get("what_changed", ""),
            data_confidence=float(data.get("data_confidence", 0.5)),
        )
