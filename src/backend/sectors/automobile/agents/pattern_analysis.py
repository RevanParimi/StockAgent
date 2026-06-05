"""
agents/pattern_analysis.py
==========================
Pattern Analysis sub-agent.

Data dimensions covered:
  1. 10-yr price history cycle detection
  2. Seasonal sales window patterns
  3. RSI / MACD / Bollinger Bands periodic refresh
  4. Breakout / support zone mapping
  5. Peer correlation (Nifty Auto vs stock)
"""

from __future__ import annotations

from typing import Any

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import (
    AgentOutput,
    PatternAnalysisOutput,
    PatternAnalysisSubScores,
    StockQuery,
)
from backend.sectors.automobile.prompts import pattern_analysis as P


class PatternAnalysisAgent(BaseAgent):
    """Analyses technical price patterns and momentum indicators."""

    @property
    def agent_name(self) -> str:
        return "pattern_analysis"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        from backend.sectors.automobile.config.settings import get_business_model_context
        biz_ctx = get_business_model_context(query.ticker)
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
            business_model_context=biz_ctx,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return PatternAnalysisOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=PatternAnalysisSubScores(
                price_cycle_position=self._clamp(float(sub.get("price_cycle_position", 0.5))),
                seasonal_pattern=self._clamp(float(sub.get("seasonal_pattern", 0.5))),
                rsi_macd_bb=self._clamp(float(sub.get("rsi_macd_bb", 0.5))),
                breakout_support_zone=self._clamp(float(sub.get("breakout_support_zone", 0.5))),
                peer_correlation=self._clamp(float(sub.get("peer_correlation", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
            ticker_vs_peers=data.get("ticker_vs_peers", ""),
            bull_case_if=data.get("bull_case_if", ""),
            bear_case_if=data.get("bear_case_if", ""),
            what_changed=data.get("what_changed", ""),
            data_confidence=float(data.get("data_confidence", 0.5)),
        )
