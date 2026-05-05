from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class RERiskAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a risk specialist for Indian renewable energy projects. "
            "Identify structural risks that could impair cash flows. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (1.0 = low risk, 0.0 = high risk — inverse scoring):
1. discom_credit     — DISCOM payment delays, state UDAY/RDSS compliance
2. regulatory_change — Retroactive tariff re-negotiation, curtailment orders
3. weather_resource  — Monsoon variability impact on hydro/solar generation
4. grid_integration  — Transmission bottlenecks, curtailment %, grid evacuation
5. commodity_input   — Steel/copper price impact on capex, module price volatility

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "discom_credit": <float>,
    "regulatory_change": <float>,
    "weather_resource": <float>,
    "grid_integration": <float>,
    "commodity_input": <float>
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
