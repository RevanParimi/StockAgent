"""
agents/risk_macro.py
====================
Risk & Macro sub-agent.

Data dimensions covered:
  1. INR/USD & crude oil revenue exposure
  2. Steel / Aluminium / Rubber prices
  3. RBI repo rate & EMI impact
  4. Emission norms & policy risk
  5. Global geopolitical risk (oil shock, FII outflow, INR depreciation, supply disruption)
"""

from __future__ import annotations

from typing import Any

from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, RiskMacroOutput, RiskMacroSubScores, StockQuery
from core.config.prompts.automobile import risk_macro as P


class RiskMacroAgent(BaseAgent):
    """Analyses macro-economic and geopolitical risk factors."""

    @property
    def agent_name(self) -> str:
        return "risk_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return RiskMacroOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=RiskMacroSubScores(
                inr_usd_crude_exposure=self._clamp(
                    float(sub.get("inr_usd_crude_exposure", 0.5))
                ),
                commodity_prices=self._clamp(float(sub.get("commodity_prices", 0.5))),
                rbi_repo_emi_impact=self._clamp(float(sub.get("rbi_repo_emi_impact", 0.5))),
                emission_policy_risk=self._clamp(float(sub.get("emission_policy_risk", 0.5))),
                global_geopolitical_risk=self._clamp(
                    float(sub.get("global_geopolitical_risk", 0.5))
                ),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
