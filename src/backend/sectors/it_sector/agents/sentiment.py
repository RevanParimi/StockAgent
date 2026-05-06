"""
agents/sentiment.py — IT Sector
Covers AI narrative, layoff signals, management tone, sector narrative, news volume.
Imports prompts from backend.sectors.it_sector.prompts.sentiment.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import sentiment as P


class ITSentimentAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "sentiment"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user

    def _parse_output(self, data: dict, ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores={
                "ai_narrative": self._clamp(float(sub.get("ai_narrative", 0.5))),
                "layoff_signals": self._clamp(float(sub.get("layoff_signals", 0.5))),
                "management_tone": self._clamp(float(sub.get("management_tone", 0.5))),
                "sector_narrative": self._clamp(float(sub.get("sector_narrative", 0.5))),
                "news_volume": self._clamp(float(sub.get("news_volume", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
