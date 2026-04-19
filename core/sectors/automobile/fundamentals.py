"""
agents/fundamentals.py
======================
Fundamentals sub-agent.

Data dimensions covered:
  1. Revenue & EBITDA QoQ / YoY delta
  2. Margin vs sector peers
  3. Deal wins & order book pipeline
  4. Attrition & headcount at OEMs
  5. Promoter holding & FII/DII flow
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import AgentOutput, FundamentalsOutput, FundamentalsSubScores, StockQuery
from prompts import fundamentals as P


class FundamentalsAgent(BaseAgent):
    """Analyses financial fundamentals and balance-sheet quality."""

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
        sub = data.get("sub_scores", {})
        return FundamentalsOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=FundamentalsSubScores(
                revenue_ebitda_delta=self._clamp(float(sub.get("revenue_ebitda_delta", 0.5))),
                margin_vs_peers=self._clamp(float(sub.get("margin_vs_peers", 0.5))),
                order_book_pipeline=self._clamp(float(sub.get("order_book_pipeline", 0.5))),
                attrition_headcount=self._clamp(float(sub.get("attrition_headcount", 0.5))),
                promoter_fii_dii_flow=self._clamp(float(sub.get("promoter_fii_dii_flow", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
