from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITPatternAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst covering Indian IT stocks. "
            "Identify price patterns, momentum signals, and seasonality. "
            "Return ONLY valid JSON."
        )
        user = f"""
Technical analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle       — 10yr cycle position, quarter-end rebalancing seasonality
2. momentum          — RSI (14d), MACD line/signal crossover, BB width
3. breakout_levels   — Key support/resistance levels, recent breakouts/breakdowns
4. nifty_it_beta     — Rolling 12M beta vs Nifty IT, alpha generation
5. volume_quality    — Volume trend, accumulation/distribution, put-call ratio

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_levels": <float>,
    "nifty_it_beta": <float>,
    "volume_quality": <float>
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
