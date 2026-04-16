"""
agents/policy_regulatory.py
=============================
Policy & Regulatory sub-agent.

Data dimensions covered:
  1. FAME / EV subsidy disbursements — MoHI notifications (via Tavily)
  2. Emission norms — BS7 / CAFE standards (via Tavily, full doc)
  3. Union Budget — auto component import duties (via Serper)
  4. PLI scheme utilization by OEMs (via Serper)
  5. State EV incentives — registration waivers, road tax (via Serper)
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import AgentOutput, PolicyRegulatoryOutput, PolicyRegulatorySubScores, StockQuery
from prompts import policy_regulatory as P


class PolicyRegulatoryAgent(BaseAgent):
    """Analyses government policy tailwinds and regulatory risks for an OEM."""

    @property
    def agent_name(self) -> str:
        return "policy_regulatory"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        user_prompt = P.ANALYSIS_PROMPT.format(
            ticker=query.ticker,
            company_name=query.company_name or query.ticker,
            context=context,
        )
        return P.SYSTEM_PROMPT, user_prompt

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        sub = data.get("sub_scores", {})
        return PolicyRegulatoryOutput(
            ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            sub_scores=PolicyRegulatorySubScores(
                fame_ev_subsidy=self._clamp(float(sub.get("fame_ev_subsidy", 0.5))),
                emission_norms=self._clamp(float(sub.get("emission_norms", 0.5))),
                union_budget_duties=self._clamp(float(sub.get("union_budget_duties", 0.5))),
                pli_scheme=self._clamp(float(sub.get("pli_scheme", 0.5))),
                state_ev_incentives=self._clamp(float(sub.get("state_ev_incentives", 0.5))),
            ),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
