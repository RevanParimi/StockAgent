"""
agents/pattern_analysis.py — IT Sector
Covers 10yr price cycle, RSI/MACD/BB, breakout levels, Nifty IT beta, volume quality.
Imports prompts from backend.sectors.it_sector.prompts.pattern_analysis.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.it_sector.prompts import pattern_analysis as P


class ITPatternAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

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
                "price_cycle": self._clamp(float(sub.get("price_cycle", 0.5))),
                "momentum": self._clamp(float(sub.get("momentum", 0.5))),
                "breakout_levels": self._clamp(float(sub.get("breakout_levels", 0.5))),
                "nifty_it_beta": self._clamp(float(sub.get("nifty_it_beta", 0.5))),
                "volume_quality": self._clamp(float(sub.get("volume_quality", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
