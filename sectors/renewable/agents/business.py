from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class REBusinessAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "business"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are an energy sector analyst evaluating the business quality of "
            "Indian renewable energy companies. Return ONLY valid JSON."
        )
        user = f"""
Business quality assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. subsector_mix     — Solar/Wind/Hydro/Hybrid %, technology diversification score
2. ppa_quality       — PPA tariff level, tenor remaining, counterparty (central/state/C&I)
3. pipeline_cred     — Under-construction % of total target, commissioning track record
4. customer_divers   — DISCOM diversification (state mix), C&I customer %
5. geography_spread  — MW by state, wind resource quality, irradiance levels

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "subsector_mix": <float>,
    "ppa_quality": <float>,
    "pipeline_cred": <float>,
    "customer_divers": <float>,
    "geography_spread": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter>"
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
