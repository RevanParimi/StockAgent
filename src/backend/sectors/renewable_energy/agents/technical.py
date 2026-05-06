"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class RETechnicalAgent(BaseAgent):
    @property
    def sector(self) -> str: return "re"
    @property
    def agent_name(self) -> str: return "technical"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Technical analyst providing timing signals for Indian renewable energy stocks. Return ONLY valid JSON."""
        user = """Technical timing for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. moving_averages — 50-DMA vs 200-DMA (golden/death cross)
2. rsi_signal — Weekly RSI: oversold < 35 bullish, overbought > 70 bearish
3. macd_weekly — Weekly MACD crossover and histogram trend
4. volume_catalyst — Volume surge on policy/MNRE news
5. accumulation_zone — Price vs 52-week range, Fibonacci levels

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
