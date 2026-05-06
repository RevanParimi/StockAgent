"""
agents/macro_policy.py — Banking BFSI
======================================
Analyses RBI MPC decisions, system credit/deposit growth, LAF liquidity,
SEBI/RBI regulatory circulars, and fiscal policy (borrowing / PSU recap / IBC).
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.banking_bfsi.prompts import macro_policy as P


class BFSIMacroPolicyAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "macro_policy"

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
                "rbi_rate_cycle":       self._clamp(float(sub.get("rbi_rate_cycle", 0.5))),
                "system_credit":        self._clamp(float(sub.get("system_credit", 0.5))),
                "liquidity_conditions": self._clamp(float(sub.get("liquidity_conditions", 0.5))),
                "regulatory_actions":   self._clamp(float(sub.get("regulatory_actions", 0.5))),
                "fiscal_policy":        self._clamp(float(sub.get("fiscal_policy", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
