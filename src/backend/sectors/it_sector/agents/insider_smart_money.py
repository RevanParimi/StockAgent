"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITInsiderAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "insider_smart_money"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Analyst tracking insider and institutional smart-money flows for Indian IT. Return ONLY valid JSON."""
        user = """Insider and smart-money analysis for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. promoter_activity — Open-market buys/sells, ESOP exercise
2. director_trades — Non-executive director trades pre/post results
3. smart_money_flow — Tier-1 MF allocation changes
4. short_interest — F&O put-call ratio, short-selling trend
5. block_deals — Recent block/bulk deal activity and counterparties

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
