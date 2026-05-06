"""
agents/risk_macro.py — IT Sector
Covers H1B/L1 visa risk, AI disruption, client concentration, FX hedge, talent supply.
Imports prompts from backend.sectors.it_sector.prompts.risk_macro.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import risk_macro as P


class ITRiskMacroAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "risk_macro"

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
                "visa_risk": self._clamp(float(sub.get("visa_risk", 0.5))),
                "ai_disruption": self._clamp(float(sub.get("ai_disruption", 0.5))),
                "client_concentration": self._clamp(float(sub.get("client_concentration", 0.5))),
                "fx_hedge": self._clamp(float(sub.get("fx_hedge", 0.5))),
                "talent_risk": self._clamp(float(sub.get("talent_risk", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
