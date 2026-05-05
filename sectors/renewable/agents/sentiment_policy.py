from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class RESentimentPolicyAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "sentiment_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a policy analyst and sentiment tracker for Indian renewable energy. "
            "Track MNRE auctions, Budget allocations, and sector news flow. "
            "Return ONLY valid JSON."
        )
        user = f"""
Sentiment and policy analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. mnre_auction_health — Recent auction GW awarded, tariff trajectory, bid pipeline
2. budget_allocation   — Union Budget RE capex, green hydrogen mission funding
3. policy_tailwinds    — RPO targets, must-run status, ISTS waiver continuation
4. green_hydrogen      — Company exposure to green H2 opportunity/investment
5. news_sentiment      — Recent news tone: project wins, delays, govt support

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "mnre_auction_health": <float>,
    "budget_allocation": <float>,
    "policy_tailwinds": <float>,
    "green_hydrogen": <float>,
    "news_sentiment": <float>
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
