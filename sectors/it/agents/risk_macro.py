from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITRiskMacroAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "risk_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a risk analyst covering Indian IT companies. "
            "Assess visa, AI disruption, and concentration risks. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. visa_risk            — H1B/L1 approval rates, denial trends, visa reform legislation
2. ai_disruption        — % of revenue at risk from GenAI/automation, AI deal wins
3. client_concentration — Top-5 client revenue %, churn risk, vertical concentration
4. fx_hedge             — INR/USD hedge coverage, derivative positions, revenue mix
5. talent_risk          — Supply of skilled talent, campus hiring, moonlighting trends

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "visa_risk": <float>,
    "ai_disruption": <float>,
    "client_concentration": <float>,
    "fx_hedge": <float>,
    "talent_risk": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<date>"
}}
"""
        return system, user

    def _parse_output(self, data: dict[str, Any], ticker: str) -> AgentOutput:
        return AgentOutput(
            agent=self.agent_name, ticker=ticker,
            overall_score=self._clamp(float(data.get("overall_score", 0.5))),
            key_positives=data.get("key_positives", []),
            key_risks=data.get("key_risks", []),
            summary=data.get("summary", ""),
            data_freshness=data.get("data_freshness", ""),
        )
