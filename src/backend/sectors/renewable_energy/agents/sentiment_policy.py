"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class RESentimentPolicyAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "sentiment_policy"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Policy analyst and sentiment tracker for Indian renewable energy. Return ONLY valid JSON."""
        user = """Sentiment and policy analysis for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. mnre_auction_health — Recent auction GW awarded, tariff trajectory
2. budget_allocation — Union Budget RE capex, green hydrogen funding
3. policy_tailwinds — RPO targets, must-run status, ISTS waiver
4. green_hydrogen — Company exposure to green H2 opportunity
5. news_sentiment — Recent news tone: project wins, delays, support

Return ONLY valid JSON."""
        return system, user.format(
            ticker=query.ticker,
            company_name=query.company_name,
            analysis_date=query.analysis_date,
            context=context,
        )

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
