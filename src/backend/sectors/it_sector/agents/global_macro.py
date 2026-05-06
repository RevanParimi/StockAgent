"""
agents/global_macro.py — IT Sector
Covers US IT spend, Fed rate impact, USD/INR, geopolitical, M&A multiples.
Imports prompts from backend.sectors.it_sector.prompts.global_macro.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import global_macro as P


class ITGlobalMacroAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "global_macro"

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
                "us_tech_spend": self._clamp(float(sub.get("us_tech_spend", 0.5))),
                "fed_rate_impact": self._clamp(float(sub.get("fed_rate_impact", 0.5))),
                "usd_inr": self._clamp(float(sub.get("usd_inr", 0.5))),
                "geopolitical": self._clamp(float(sub.get("geopolitical", 0.5))),
                "ma_activity": self._clamp(float(sub.get("ma_activity", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
