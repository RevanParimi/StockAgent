"""
agents/insider_smart_money.py — IT Sector
Covers promoter/SAST activity, director trades, AMFI MF flow, FII futures, block deals.
Imports prompts from backend.sectors.it_sector.prompts.insider_smart_money.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import insider_smart_money as P


class ITInsiderAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "insider_smart_money"

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
                "promoter_activity": self._clamp(float(sub.get("promoter_activity", 0.5))),
                "director_trades": self._clamp(float(sub.get("director_trades", 0.5))),
                "amfi_mf_flow": self._clamp(float(sub.get("amfi_mf_flow", 0.5))),
                "fii_futures": self._clamp(float(sub.get("fii_futures", 0.5))),
                "block_deals": self._clamp(float(sub.get("block_deals", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
