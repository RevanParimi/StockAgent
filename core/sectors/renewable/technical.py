"""
sectors/renewable/technical.py
=================================
Technical & Entry Timing sub-agent for the Renewable Energy sector.

RE-specific note: these stocks behave like long-duration bonds — they re-rate
when RBI signals rate cuts and sell off when rates rise. Rate-cut cycle breakouts
combined with MNRE policy catalysts are the primary technical entry signals.

Data dimensions covered:
  1. Moving averages (50-DMA vs 200-DMA, Golden/Death Cross)
  2. RSI (14-day) — oversold setups at key supports
  3. MACD (weekly) — crossover direction and histogram trend
  4. Volume & catalyst confirmation
  5. Support zone strength and 52-week range position
"""

from __future__ import annotations

from typing import Any

from core.pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery
from core.config.prompts.renewable import technical as P


class RETechnicalAgent(BaseAgent):
    """Provides entry/exit timing signals for renewable energy stocks."""

    @property
    def agent_name(self) -> str:
        return "technical"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name,
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
