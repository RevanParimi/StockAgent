"""
agents/transcript_nlp.py — IT Sector
Covers guidance delta, vertical mix, geography colour, AI deal count, analyst Q&A pushback.
Imports prompts from backend.sectors.it_sector.prompts.transcript_nlp.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import transcript_nlp as P


class ITTranscriptNLPAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "transcript_nlp"

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
                "guidance_delta": self._clamp(float(sub.get("guidance_delta", 0.5))),
                "vertical_mix": self._clamp(float(sub.get("vertical_mix", 0.5))),
                "geography_colour": self._clamp(float(sub.get("geography_colour", 0.5))),
                "ai_deal_count": self._clamp(float(sub.get("ai_deal_count", 0.5))),
                "analyst_pushback": self._clamp(float(sub.get("analyst_pushback", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
