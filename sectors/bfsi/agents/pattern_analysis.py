from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIPatternAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a technical analyst specialising in Indian banking stocks. "
            "Identify price cycles, seasonality, and momentum signals. "
            "Return ONLY valid JSON."
        )
        user = f"""
Technical and pattern analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. price_cycle        — 10-year cycle position, rate-cut rally seasonality
2. momentum           — RSI (14d), MACD, Bollinger Band position
3. breakout_zones     — Key support/resistance, breakout or breakdown levels
4. relative_strength  — Performance vs Nifty Bank, Nifty PSU Bank indices
5. volume_pattern     — OBV trend, institutional accumulation/distribution

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "price_cycle": <float>,
    "momentum": <float>,
    "breakout_zones": <float>,
    "relative_strength": <float>,
    "volume_pattern": <float>
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
