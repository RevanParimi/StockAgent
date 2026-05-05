from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class REValuationAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "re"

    @property
    def agent_name(self) -> str:
        return "valuation"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a valuation analyst for Indian renewable energy stocks. "
            "Use sector-specific multiples and DCF methodology. "
            "Return ONLY valid JSON."
        )
        user = f"""
Valuation analysis for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. ev_per_mw         — EV/MW vs peer range (Solar: ₹4-6Cr/MW, Wind: ₹5-8Cr/MW)
2. ev_ebitda         — EV/EBITDA vs healthy range 15-25x for quality RE assets
3. tariff_vs_auction — Existing PPA tariffs vs current MNRE auction L1 rates
4. pipeline_dcf      — Pipeline value with −25% haircut on unbuilt MW
5. implied_irr       — Implied equity IRR vs WACC (target spread ≥200-300bps)

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "ev_per_mw": <float>,
    "ev_ebitda": <float>,
    "tariff_vs_auction": <float>,
    "pipeline_dcf": <float>,
    "implied_irr": <float>
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
