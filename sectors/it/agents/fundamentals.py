from __future__ import annotations
from typing import Any
from pipeline.base_agent import BaseAgent
from core.schemas.pipeline import AgentOutput, StockQuery


class ITFundamentalsAgent(BaseAgent):
    @property
    def sector(self) -> str:
        return "it"

    @property
    def agent_name(self) -> str:
        return "fundamentals"

    def _build_prompt(self, query: StockQuery, context: str) -> tuple[str, str]:
        system = (
            "You are a senior IT equity analyst covering Indian technology companies. "
            "Assess financial performance, deal pipeline, and talent metrics. "
            "Return ONLY valid JSON."
        )
        user = f"""
Fundamental analysis of {query.ticker} ({query.company_name}) as of {query.analysis_date}.

Context:
{context}

Evaluate (score 0.0–1.0 each):
1. revenue_growth   — QoQ and YoY revenue growth, constant-currency growth
2. ebit_margins     — EBIT margin trend over 8 quarters, guidance vs actual
3. deal_wins        — TCV of large deals, deal pipeline health, win rates
4. attrition        — Trailing 12M attrition %, trend, fresher intake ratio
5. valuation        — P/E, EV/Revenue, PEG vs 5yr historical and peers

Return:
{{
  "overall_score": <0.0–1.0>,
  "sub_scores": {{
    "revenue_growth": <float>,
    "ebit_margins": <float>,
    "deal_wins": <float>,
    "attrition": <float>,
    "valuation": <float>
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
