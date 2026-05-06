"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class BFSIPatternAgent(BaseAgent):
    @property
    def sector(self) -> str: return "bfsi"
    @property
    def agent_name(self) -> str: return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Technical analyst specialising in Indian banking stocks. Return ONLY valid JSON."""
        user = """Technical and pattern analysis for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle — 10-year cycle, rate-cut rally seasonality
2. momentum — RSI (14d), MACD, Bollinger Bands
3. breakout_zones — Key support/resistance
4. relative_strength — Performance vs Nifty Bank, PSU Bank
5. volume_pattern — OBV trend, accumulation/distribution

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
