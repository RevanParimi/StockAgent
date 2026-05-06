"""
agents/risk.py — Banking BFSI
================================
Analyses NPA slippage trends, ALM mismatch, regulatory enforcement orders,
cyber/fraud incidents (CERT-In / RBI fraud reports), and concentration risk.
Note: real-time interbank rates, SWIFT flows, FX swap desk — dropped (paid/restricted).
"""
from __future__ import annotations

from backend.shared.pipeline.base_agent import BaseAgent
from backend.shared.schemas.pipeline import AgentOutput, StockQuery
from backend.sectors.banking_bfsi.prompts import risk as P


class BFSIRiskAgent(BaseAgent):

    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "risk"

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
                "asset_quality_trend": self._clamp(float(sub.get("asset_quality_trend", 0.5))),
                "concentration_risk":  self._clamp(float(sub.get("concentration_risk", 0.5))),
                "deposit_stability":   self._clamp(float(sub.get("deposit_stability", 0.5))),
                "regulatory_risk":     self._clamp(float(sub.get("regulatory_risk", 0.5))),
                "cyber_fraud_risk":    self._clamp(float(sub.get("cyber_fraud_risk", 0.5))),
            },
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
