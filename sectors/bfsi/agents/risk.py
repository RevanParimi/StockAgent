from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIRiskAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "risk"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a credit risk specialist covering Indian banks and NBFCs. "
            "Identify structural risks that could impair capital or liquidity. "
            "Return ONLY valid JSON."
        )
        user = f"""
Risk assessment for {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate:
1. asset_quality_trend — SMA/SMA-2 slippage, restructured book, watchlist
2. concentration_risk  — Top-5 borrower exposure, sectoral concentration
3. deposit_stability   — Wholesale deposit %, CASA trend, deposit run-off risk
4. regulatory_risk     — RBI/SEBI penalties pending, prompt corrective action risk
5. macro_sensitivity   — Rate sensitivity (NIM compression), FX exposure

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "asset_quality_trend": <float>,
    "concentration_risk": <float>,
    "deposit_stability": <float>,
    "regulatory_risk": <float>,
    "macro_sensitivity": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter/date>"
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
