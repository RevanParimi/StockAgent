"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Senior IT equity analyst covering Indian technology companies. Return ONLY valid JSON."""
        user = """Fundamental analysis of {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. revenue_growth — QoQ/YoY revenue, constant-currency
2. ebit_margins — EBIT margin trend 8 quarters
3. deal_wins — TCV large deals, win rates
4. attrition — 12M attrition %, fresher intake
5. valuation — P/E, EV/Revenue, PEG vs peers

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
