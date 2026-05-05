from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITSentimentAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "sentiment"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a sentiment analyst tracking news and social signals for "
            "Indian IT companies. Return ONLY valid JSON."
        )
        user = f"""
Sentiment analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. ai_narrative      — GenAI deal announcements, AI transformation storyline strength
2. layoff_signals    — Workforce reduction news, bench utilisation concerns
3. management_tone   — CFO/CEO interview sentiment, guidance language analysis
4. media_coverage    — Volume and tone of recent news coverage
5. social_buzz       — LinkedIn/Twitter/Reddit IT community sentiment

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "ai_narrative": <float>,
    "layoff_signals": <float>,
    "management_tone": <float>,
    "media_coverage": <float>,
    "social_buzz": <float>
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
