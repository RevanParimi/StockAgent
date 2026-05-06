"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class REFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Project-finance analyst specialising in Indian renewable energy. Return ONLY valid JSON."""
        user = """Fundamental analysis of {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. capacity_utilisation — CUF % vs technology benchmark
2. ebitda_quality — EBITDA/MW trend, O&M cost control
3. debt_serviceability — DSCR (target >= 1.2x), refinancing risk
4. receivables — Receivables aging, DISCOM payment delays
5. leverage — Project D/E, holdco leverage

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
