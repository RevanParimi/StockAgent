"""
agents/universe_setup.py — Banking BFSI
=========================================
Establishes index membership (Nifty Bank/PSU Bank/Private Bank/Bankex),
peer group classification, market cap tier, corporate action calendar,
and AMFI MF rebalancing flow.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.banking_bfsi.prompts import universe_setup as P


class BFSIUniverseAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "universe_setup"

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
                "index_weight":      self._clamp(float(sub.get("index_weight", 0.5))),
                "peer_positioning":  self._clamp(float(sub.get("peer_positioning", 0.5))),
                "market_cap_tier":   self._clamp(float(sub.get("market_cap_tier", 0.5))),
                "corporate_actions": self._clamp(float(sub.get("corporate_actions", 0.5))),
                "rebalancing_risk":  self._clamp(float(sub.get("rebalancing_risk", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
