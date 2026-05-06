"""
agents/peer_benchmark.py — IT Sector
Covers revenue rank, margin rank, deal TCV rank, attrition rank, valuation z-score vs peers.
Imports prompts from backend.sectors.it_sector.prompts.peer_benchmark.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import peer_benchmark as P


class ITPeerBenchmarkAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "peer_benchmark"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores={
                "revenue_growth_rank": self._clamp(float(sub.get("revenue_growth_rank", 0.5))),
                "margin_rank": self._clamp(float(sub.get("margin_rank", 0.5))),
                "deal_momentum_rank": self._clamp(float(sub.get("deal_momentum_rank", 0.5))),
                "attrition_rank": self._clamp(float(sub.get("attrition_rank", 0.5))),
                "valuation_gap": self._clamp(float(sub.get("valuation_gap", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
