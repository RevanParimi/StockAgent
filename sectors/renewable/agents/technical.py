from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class RETechnicalAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "technical"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst providing entry/exit timing signals for "
            "Indian renewable energy stocks. Return ONLY valid JSON."
        )
        user = f"""
Technical timing signal for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. moving_averages   — 50-DMA vs 200-DMA (golden cross / death cross)
2. rsi_signal        — Weekly RSI: oversold <35 = bullish, overbought >70 = bearish
3. macd_weekly       — Weekly MACD crossover direction and histogram trend
4. volume_catalyst   — Volume surge on policy/MNRE news, accumulation zones
5. accumulation_zone — Current price vs 52-week range, Fibonacci retracement levels

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "moving_averages": <float>,
    "rsi_signal": <float>,
    "macd_weekly": <float>,
    "volume_catalyst": <float>,
    "accumulation_zone": <float>
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
