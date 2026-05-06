"""Auto-generated agent file. Edit prompt strings to customise LLM behaviour."""
from __future__ import annotations
from typing import Any
from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery


class ITSentimentAgent(BaseAgent):
    @property
    def sector(self) -> str: return "it"
    @property
    def agent_name(self) -> str: return "sentiment"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = """Sentiment analyst tracking news and social signals for Indian IT. Return ONLY valid JSON."""
        user = """Sentiment analysis for {ticker} ({company_name}) as of {analysis_date}.

Context:
{context}

Evaluate:
1. ai_narrative — GenAI deal announcements, AI transformation storyline
2. layoff_signals — Workforce reduction news, bench utilisation
3. management_tone — CFO/CEO interview sentiment, guidance language
4. media_coverage — Volume and tone of news coverage
5. social_buzz — LinkedIn/Twitter/Reddit IT community sentiment

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
