from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class BFSIFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "bfsi"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a senior banking analyst specialising in Indian BFSI stocks. "
            "Analyse credit quality, capital adequacy, and profitability metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Analyse the fundamentals of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate these dimensions (score each 0.0–1.0):
1. asset_quality     — Gross NPA %, Net NPA %, Provision Coverage Ratio (PCR)
2. net_interest      — NIM trend (8-quarter), CASA ratio quality
3. capital_adequacy  — CRAR/CET1 vs RBI minimum, tier-1 buffer
4. profitability     — RoA, RoE, credit cost trend, cost-to-income
5. loan_mix          — Retail vs corporate split, secured vs unsecured, MSME %

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "asset_quality": <float>,
    "net_interest": <float>,
    "capital_adequacy": <float>,
    "profitability": <float>,
    "loan_mix": <float>
  }},
  "key_positives": ["<point>", ...],
  "key_risks": ["<risk>", ...],
  "summary": "<2-3 sentence summary>",
  "data_freshness": "<quarter/date of data used>"
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
