"""
agents/pattern_analysis.py — Banking BFSI
==========================================
Analyses 10-year price cycles, rate-cut seasonality, RSI/MACD/BB momentum,
breakout zones, and relative strength vs Nifty Bank.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.banking_bfsi.prompts import pattern_analysis as P


class BFSIPatternAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "bfsi"

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
                "price_cycle":       self._clamp(float(sub.get("price_cycle", 0.5))),
                "momentum":          self._clamp(float(sub.get("momentum", 0.5))),
                "breakout_zones":    self._clamp(float(sub.get("breakout_zones", 0.5))),
                "relative_strength": self._clamp(float(sub.get("relative_strength", 0.5))),
                "volume_pattern":    self._clamp(float(sub.get("volume_pattern", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
