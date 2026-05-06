"""
agents/technical.py -- Renewable Energy
Imports prompts from backend.sectors.renewable_energy.prompts.technical.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.renewable_energy.prompts import technical as P


class RETechnicalAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "technical"

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
                "moving_averages": self._clamp(float(sub.get("moving_averages", 0.5))),
                "rsi_signal": self._clamp(float(sub.get("rsi_signal", 0.5))),
                "macd_weekly": self._clamp(float(sub.get("macd_weekly", 0.5))),
                "volume_catalyst": self._clamp(float(sub.get("volume_catalyst", 0.5))),
                "accumulation_zone": self._clamp(float(sub.get("accumulation_zone", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
