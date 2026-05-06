"""
agents/fundamentals.py — Banking BFSI
======================================
Analyses asset quality (GNPA/NPA/PCR), NIM/CASA, CRAR/CET1,
profitability (RoA/RoE/credit cost), and loan book composition.
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.banking_bfsi.prompts import fundamentals as P


class BFSIFundamentalsAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

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
                "asset_quality":    self._clamp(float(sub.get("asset_quality", 0.5))),
                "net_interest":     self._clamp(float(sub.get("net_interest", 0.5))),
                "capital_adequacy": self._clamp(float(sub.get("capital_adequacy", 0.5))),
                "profitability":    self._clamp(float(sub.get("profitability", 0.5))),
                "loan_mix":         self._clamp(float(sub.get("loan_mix", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
