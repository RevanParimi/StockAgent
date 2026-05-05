from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITGlobalMacroAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "global_macro"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a global macro analyst tracking demand drivers for Indian IT. "
            "Focus on US tech spending, Fed policy, and geopolitical risk. "
            "Return ONLY valid JSON."
        )
        user = f"""
Global macro environment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. us_tech_spend     — US IT capex trends, enterprise software budgets, cloud spend
2. fed_rate_impact   — Fed funds rate trajectory, impact on US client capex decisions
3. usd_inr           — USD/INR trend, hedge ratio, revenue translation impact
4. geopolitical      — US-China tech war impact, CHIPS Act, offshoring sentiment
5. ma_activity       — Global IT M&A wave, deal multiples, consolidation risk

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "us_tech_spend": <float>,
    "fed_rate_impact": <float>,
    "usd_inr": <float>,
    "geopolitical": <float>,
    "ma_activity": <float>
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
