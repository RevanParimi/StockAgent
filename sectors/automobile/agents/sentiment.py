"""
agents/sentiment.py
===================
Sentiment sub-agent.

Data dimensions covered:
  1. News NLP (Reuters / ET / Bloomberg)
  2. Management tone (earnings call NLP)
  3. Twitter / Reddit consumer sentiment
  4. YouTube review view spikes
  5. Dealer / consumer feedback signals
"""

from __future__ import annotations

from typing import Any

from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, SentimentOutput, SentimentSubScores, StockQuery
from core.config.prompts.automobile import sentiment as P


class SentimentAgent(BaseAgent):
    """Analyses multi-source sentiment signals."""

    @property
    def agent_name(self) -> str:
        return "sentiment"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return SentimentOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=SentimentSubScores(
                news_nlp=self._clamp(float(sub.get("news_nlp", 0.5))),
                management_tone=self._clamp(float(sub.get("management_tone", 0.5))),
                twitter_reddit_sentiment=self._clamp(
                    float(sub.get("twitter_reddit_sentiment", 0.5))
                ),
                youtube_view_spikes=self._clamp(float(sub.get("youtube_view_spikes", 0.5))),
                dealer_consumer_feedback=self._clamp(
                    float(sub.get("dealer_consumer_feedback", 0.5))
                ),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
