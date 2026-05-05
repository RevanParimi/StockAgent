from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITInsiderAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "insider_smart_money"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an analyst tracking insider and institutional smart-money flows "
            "for Indian IT stocks. Return ONLY valid JSON."
        )
        user = f"""
Insider and smart-money analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. promoter_activity   — Promoter open-market buys/sells, ESOP exercise patterns
2. director_trades     — Non-executive director trades pre/post results
3. smart_money_flow    — Tier-1 mutual fund allocation changes (SBI/HDFC/Mirae)
4. short_interest      — F&O put-call ratio, short-selling trend
5. block_deals         — Recent block/bulk deal activity and counterparties

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "promoter_activity": <float>,
    "director_trades": <float>,
    "smart_money_flow": <float>,
    "short_interest": <float>,
    "block_deals": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
}}
"""
        return system, user

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
